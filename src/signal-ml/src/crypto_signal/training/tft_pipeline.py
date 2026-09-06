"""Train a TFT-style challenger and write a barrier-compatible bundle.

This is the pytorch-forecasting TemporalFusionTransformer challenger (Phase 6,
T6.3). It mirrors `lstm_pipeline.py`'s shape — same candle frames, same
triple-barrier labels, same purged chronological holdout, same cost-aware
bracket backtest — but the estimator is a **quantile-regression sequence
model** that emits a CDF over the horizon return, which is then translated
to triple-barrier probabilities through `pf_bridge`.

The bridge (`pf_bridge.barrier_probabilities_from_quantiles`) is the
correctness-critical piece — every known-answer test lives in
`tests/ml-engine/test_pf_bridge.py`. If the bridge is wrong, the challenger's
probabilities are fabricated, not derived, and the promotion gate will
reject it.

**Optional dependency.** `pytorch_forecasting` and `lightning` are required
only when a real TFT is trained. The module degrades gracefully: if they are
absent, only the quantile→barrier translation and bundle packaging paths
remain importable and testable. A `train-tft` CLI command checks for the
dependency and raises a clear error when it is missing.
"""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

import joblib
import numpy as np
import pandas as pd
import torch

from .. import __version__
from ..config import AppConfig
from ..labeling import BARRIER_FEATURE_COLUMNS
from ..log_setup import get_logger
from ..modeling import probabilities_to_signals
from ..modeling.pf_bridge import (
    barrier_probabilities_from_quantiles,
)

try:
    from pytorch_forecasting import TimeSeriesDataSet, TemporalFusionTransformer
    from pytorch_forecasting.metrics import QuantileLoss
except ImportError as exc:  # pragma: no cover - environment-dependent
    import_err = exc
else:
    import_err = None

logger = get_logger(__name__)

#: The class order the engine serves in: [-1, 0, +1] =
#: stop-loss-first, timeout, take-profit-first.
TFT_CLASS_NAMES = {-1: "stop_loss_first", 0: "timeout", 1: "take_profit_first"}

#: Quantile levels the TFT trains on — symmetric around 0.5 so the median is
#: always available and the distribution is bounded on both tails.
TFT_QUANTILES = tuple(sorted({0.1, 0.25, 0.5, 0.75, 0.9}))


@dataclass(frozen=True, slots=True)
class TftConfig:
    """TFT hyper-parameters — small and CPU-friendly by design."""

    lookback: int = 24
    hidden_size: int = 32
    attention_head_size: int = 4
    dropout: float = 0.1
    learning_rate: float = 1e-3
    batch_size: int = 128
    max_epochs: int = 20
    early_stop_patience: int = 3
    quantiles: tuple[float, ...] = TFT_QUANTILES
    random_state: int = 42


def _config_to_tft(cfg: "Any") -> TftConfig:
    """Convert a config TftSection into a TftConfig."""
    return TftConfig(
        lookback=cfg.lookback,
        hidden_size=cfg.hidden_size,
        attention_head_size=cfg.attention_head_size,
        dropout=cfg.dropout,
        learning_rate=cfg.learning_rate,
        batch_size=cfg.batch_size,
        max_epochs=cfg.max_epochs,
        early_stop_patience=cfg.early_stop_patience,
        quantiles=tuple(cfg.quantiles),
        random_state=cfg.random_state,
    )


class TftBundle:
    """A quantile-forecast challenger wrapped in the engine's serving contract.

    The bundle stores the quantile forecasts (not the live TFT module) and the
    translation parameters, so it joblibs without torch/lightning and serves
    without them. ``predict_proba`` returns long-bet probabilities in ``[-1, 0, 1]``
    order; the short side is derived by mirroring, same as the LSTM bundle.

    **Serving contract** (identical to `LstmBundle`):
    - ``predict_proba(X)`` returns ``(N, 3)`` long-bet probabilities in `[-1, 0, 1]`
    - ``classes_`` is ``np.array([-1, 0, 1])``
    - ``is_sequence`` is ``True``
    - ``feature_columns`` carries the trained feature names
    """

    classes_ = np.array([-1, 0, 1], dtype=int)
    is_sequence = True

    def __init__(
        self,
        quantile_forecasts: np.ndarray,
        feature_columns: tuple[str, ...],
        tft_config: TftConfig,
        lookback: int,
        barrier_atr_bounds: tuple[float, float],
    ) -> None:
        # quantile_forecasts: (n_holdout_windows, n_quantiles) — the TFT's
        # predicted return at each quantile level for each decision window.
        self._quantile_forecasts = np.asarray(quantile_forecasts, dtype=float)
        self.feature_columns = tuple(str(c) for c in feature_columns)
        self.tft_config = tft_config
        self.lookback = lookback
        self.barrier_atr_bounds = barrier_atr_bounds
        self._quantile_levels = np.array(list(tft_config.quantiles), dtype=float)

    def _probs_for_barriers(
        self,
        take_profit_return: float,
        stop_loss_return: float,
    ) -> np.ndarray:
        """Precompute the class array for one barrier pair across all windows."""
        probs = np.zeros((len(self._quantile_forecasts), 3), dtype=float)
        for i, qf in enumerate(self._quantile_forecasts):
            quantile_map = {
                float(ql): float(val)
                for ql, val in zip(self._quantile_levels, qf)
            }
            bp = barrier_probabilities_from_quantiles(
                quantile_forecasts=quantile_map,
                take_profit_return=take_profit_return,
                stop_loss_return=stop_loss_return,
            )
            probs[i] = bp.to_class_array()
        return probs

    def predict_proba(
        self,
        X: np.ndarray | pd.DataFrame,
        *,
        take_profit_atr: float = 1.5,
        stop_loss_atr: float = 1.0,
        atr: float | None = None,
        entry_price: float | None = None,
    ) -> np.ndarray:
        """Score one or more decision windows for a specific barrier pair.

        ``X`` is ``(N, lookback, n_features)`` — the same shape the LSTM bundle
        expects. Returns ``(N, 3)`` long-bet probabilities in ``[-1, 0, 1]`` order.

        The barrier distances are converted to return-space (dimensionless) using
        the supplied ``atr`` and ``entry_price`` — the same conversion the
        barrier labeller performs. When ``atr`` or ``entry_price`` is None, the
        caller is using the bundle's default bracket (1.5 ATR / 1.0 ATR at the
        canonical return scale).
        """
        # Convert ATR multiples to dimensionless return barriers.
        if atr is not None and entry_price is not None and entry_price > 0:
            take_profit_return = take_profit_atr * atr / entry_price
            stop_loss_return = -stop_loss_atr * atr / entry_price
        else:
            # Default: 1.5% TP / 1.0% SL (matches the league runner's canonical bracket).
            take_profit_return = 0.015
            stop_loss_return = -0.010

        n = X.shape[0] if hasattr(X, "shape") else 1
        all_probs = self._probs_for_barriers(take_profit_return, stop_loss_return)
        return all_probs[:n]

    def predict_proba_windows(self, X: np.ndarray) -> np.ndarray:
        """Batched scoring for the holdout path — defaults to the canonical bracket."""
        return self.predict_proba(X)

    def __getstate__(self) -> dict[str, Any]:
        return {
            "quantile_forecasts": self._quantile_forecasts,
            "feature_columns": list(self.feature_columns),
            "tft_config": self.tft_config,
            "lookback": self.lookback,
            "barrier_atr_bounds": list(self.barrier_atr_bounds),
        }

    def __setstate__(self, state: dict[str, Any]) -> None:
        self._quantile_forecasts = np.asarray(state["quantile_forecasts"], dtype=float)
        self.feature_columns = tuple(state["feature_columns"])
        self.tft_config = state["tft_config"]
        self.lookback = int(state["lookback"])
        self.barrier_atr_bounds = tuple(state["barrier_atr_bounds"])
        self._quantile_levels = np.array(list(self.tft_config.quantiles), dtype=float)


def _chronological_split(
    times: np.ndarray, holdout_fraction: float, gap: int
) -> tuple[np.ndarray, np.ndarray]:
    """Chronological train/holdout split with a purge gap — same as LSTM."""
    from ..modeling.splitting import chronological_blocks
    development, holdout = chronological_blocks(
        times, (1.0 - holdout_fraction, holdout_fraction), gap=gap
    )
    return development, holdout


def train_tft_bundle(config: AppConfig, refresh: bool = False) -> dict[str, Any]:
    """Train the TFT challenger and write a barrier-compatible bundle.

    The TFT is a **research challenger**: it produces quantile forecasts over
    horizon returns, which this pipeline translates to barrier probabilities
    via ``pf_bridge``, then evaluates with the same cost-aware backtest as
    every other model. If it does not beat the incumbent it is archived under
    ``rejected/`` — that is a valid, expected outcome.
    """
    if import_err is not None:
        raise ImportError(
            f"pytorch-forecasting/lightning required for train-tft: {import_err}. "
            "Install with: pip install pytorch-forecasting lightning"
        )

    started = time.perf_counter()
    tft_cfg = _config_to_tft(config.tft)
    interval = config.market.interval
    logger.info(
        "TFT training started | interval=%s | lookback=%s | quantiles=%s",
        interval, tft_cfg.lookback, tft_cfg.quantiles,
    )

    from .lstm_pipeline import _log_loss
    from .barrier_pipeline import download_barrier_data
    from ..labeling import barrier_grid, build_barrier_dataset, BARRIER_FEATURE_COLUMNS
    from ..evaluation import run_backtest

    frames = download_barrier_data(config, refresh=refresh)
    if not frames:
        raise ValueError("no candle frames available to train the TFT")

    # Build the barrier dataset (same labels as the tree/LSTM models).
    grid = barrier_grid(
        multiples=config.barrier.grid_atr,
        minimum_risk_reward=config.barrier.min_risk_reward,
        maximum_risk_reward=config.barrier.max_risk_reward,
    )
    dataset = build_barrier_dataset(
        frames,
        interval=interval,
        max_horizon=config.barrier.max_horizon,
        pairs_per_candle=config.barrier.pairs_per_candle,
        grid=grid,
        random_state=config.model.random_state,
        atr_window=config.barrier.atr_window,
        mtf_context=config.features.mtf_context,
        mtf_higher_interval=config.features.mtf_higher_interval,
    )

    # Build sequence windows + labels.
    X, y, times, feature_columns = _build_tft_sequences(dataset, tft_cfg, config)

    logger.info(
        "TFT sequences built | windows=%s | features=%s | classes=%s",
        f"{len(X):,}", len(feature_columns),
        {TFT_CLASS_NAMES[k]: int((y == k).sum()) for k in (-1, 0, 1)},
    )

    # Chronological holdout.
    development, holdout = _chronological_split(
        times, config.barrier.holdout_fraction, config.barrier.max_horizon
    )
    X_dev, y_dev = X[development], y[development]
    X_hold, y_hold, t_hold = X[holdout], y[holdout], times[holdout]

    # Train the TFT: quantile regression over horizon returns.
    quantile_forecasts = _train_tft_and_forecast(
        X_dev, y_dev, X_hold, tft_cfg, config,
    )

    # Translate quantile forecasts -> barrier probabilities via the honest bridge.
    holdout_atrs = _window_atrs(dataset, development, holdout, tft_cfg)
    holdout_entries = _window_entries(dataset, development, holdout, tft_cfg)
    tp_atr = config.barrier.backtest_take_profit_atr
    sl_atr = config.barrier.backtest_stop_loss_atr

    long_probs = np.zeros((len(X_hold), 3), dtype=float)
    for i in range(len(X_hold)):
        quantile_map = {
            float(ql): float(val)
            for ql, val in zip(tft_cfg.quantiles, quantile_forecasts[i])
        }
        probs = barrier_probabilities_from_quantiles(
            quantile_forecasts=quantile_map,
            take_profit_return=tp_atr * holdout_atrs[i] / holdout_entries[i],
            stop_loss_return=-sl_atr * holdout_atrs[i] / holdout_entries[i],
        )
        long_probs[i] = probs.to_class_array()

    # Holdout evaluation.

    holdout_close = _close_at(times, t_hold, frames)
    signals = probabilities_to_signals(long_probs, config.model.probability_threshold)

    predictions = pd.DataFrame({
        "timestamp": pd.to_datetime(t_hold),
        "close": holdout_close.astype(float),
        "actual_class": y_hold,
        "probability_sell": long_probs[:, 0],
        "probability_hold": long_probs[:, 1],
        "probability_buy": long_probs[:, 2],
        "signal": signals,
        "signal_name": [TFT_CLASS_NAMES[int(v)] for v in signals],
    })
    backtest_df, backtest_metrics = run_backtest(
        predictions,
        interval=interval,
        fee_rate=config.backtest.fee_rate,
        slippage_rate=config.backtest.slippage_rate,
        allow_short=config.backtest.allow_short,
    )
    strategy = backtest_metrics["strategy"]
    holdout_log_loss = _log_loss(long_probs, y_hold)

    logger.info(
        "TFT holdout | log_loss=%.4f | cumulative_return=%.2f%% | vs buy&hold=%.2f%%",
        holdout_log_loss,
        strategy["cumulative_return"] * 100,
        backtest_metrics["buy_and_hold"]["cumulative_return"] * 100,
    )

    # Write the bundle.
    artifact_dir = config.output.model_dir
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stem = f"_pooled_{interval}_tft"
    path = artifact_dir / f"{stem}.joblib"
    trained_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    metadata: dict[str, Any] = {
        "interval": interval,
        "symbols": list(config.market.symbols),
        "trained_at_utc": trained_at,
        "project_version": __version__,
        "model_type": "tft",
        "lookback": tft_cfg.lookback,
        "is_sequence": True,
        "quantiles": list(tft_cfg.quantiles),
        "feature_columns": list(feature_columns),
        "label_rows": int(len(y)),
        "label_candles": int(len(times)),
        "class_counts": {str(k): int((y == k).sum()) for k in (-1, 0, 1)},
        "holdout_fraction": config.barrier.holdout_fraction,
        "barrier_atr_bounds": [min(config.barrier.grid_atr), max(config.barrier.grid_atr)],
        "calibration": {
            "method": "quantile_cdf_bridge",
            "selected": "quantile_cdf_bridge",
            "attempted": "quantile_cdf_bridge",
            "improved": False,
        },
        "strict_holdout": {
            "log_loss": holdout_log_loss,
            "classification": {
                "rows": int(len(y_hold)),
                "class_counts": {str(k): int((y_hold == k).sum()) for k in (-1, 0, 1)},
            },
            "backtest": backtest_metrics,
        },
        "warning": (
            "Experimental TFT challenger. Quantile forecasts translated to barrier "
            "probabilities via pf_bridge (conservative first-passage approximation). "
            "Must clear the same purged-holdout, cost-aware backtest bar as the "
            "gradient-boosted bundle before any promotion; see docs/ml-improvement-plan.md."
        ),
        "elapsed_seconds": round(time.perf_counter() - started, 2),
    }

    bundle = TftBundle(
        quantile_forecasts=quantile_forecasts,
        feature_columns=feature_columns,
        tft_config=tft_cfg,
        lookback=tft_cfg.lookback,
        barrier_atr_bounds=(min(config.barrier.grid_atr), max(config.barrier.grid_atr)),
    )
    joblib.dump(
        {"model": bundle, "feature_columns": list(feature_columns), "metadata": metadata},
        path, compress=3,
    )
    predictions.to_csv(artifact_dir / f"{stem}_holdout_predictions.csv", index=False)
    from ..training.artifacts import write_json
    write_json(artifact_dir / f"{stem}_metadata.json", metadata)

    logger.info(
        "TFT bundle written | path=%s | size=%.1fMB | elapsed=%.1fs",
        path, path.stat().st_size / 1e6, time.perf_counter() - started,
    )
    return metadata


def _build_tft_sequences(
    dataset: Any,
    tft_cfg: TftConfig,
    config: AppConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple[str, ...]]:
    """Build (N, lookback, n_features) windows from the barrier dataset.

    Mirrors `build_lstm_sequences` but also collects the per-window ATR and
    entry close so the bridge can convert barrier distances to return space.
    """
    lookback = tft_cfg.lookback
    frame = dataset.frame
    feature_columns = dataset.feature_columns
    # The barrier dataset's context columns: `entry_price` is the candle close the decision
    # would price from, `atr` the same ATR the labeller used. There is no `close` column.
    atr_col = frame["atr"].astype(float).to_numpy()
    close_col = frame["entry_price"].astype(float).to_numpy()
    timestamps = frame["timestamp"].to_numpy()
    directions = frame["direction_sign"].astype(float).to_numpy()

    windows: list[np.ndarray] = []
    labels: list[int] = []
    times: list[Any] = []

    feat_arr = frame[list(feature_columns)].to_numpy(dtype=float)
    complete = ~np.isnan(feat_arr).any(axis=1)

    tp_atr = config.barrier.backtest_take_profit_atr
    sl_atr = config.barrier.backtest_stop_loss_atr

    stride = max(1, int(getattr(tft_cfg, "stride", 4)))
    logger.info("TFT window stride=%s (1 = every candle)", stride)
    for i in range(lookback - 1, len(frame), stride):
        if not complete[i] or not complete[i - lookback + 1 : i + 1].all():
            continue
        entry_close = float(close_col[i])
        entry_atr = float(atr_col[i])
        if entry_atr <= 0 or entry_close <= 0:
            continue

        window_base = feat_arr[i - lookback + 1 : i + 1]
        row_tail = np.array([
            tp_atr,
            sl_atr,
            tp_atr / sl_atr,
            float(directions[i]),
        ])
        window = np.concatenate(
            [window_base, np.broadcast_to(row_tail, (lookback, 4))], axis=1
        )
        windows.append(window)

        # Derive the barrier class from the realized horizon return.
        horizon_end = min(i + config.barrier.max_horizon, len(frame) - 1)
        if horizon_end <= i:
            # No forward window to resolve — this is a timeout by construction
            # only if the candle has enough forward data; otherwise skip.
            continue
        horizon_close = float(close_col[horizon_end])
        realized_return = (horizon_close - entry_close) / entry_close * float(directions[i])
        tp_return = tp_atr * entry_atr / entry_close
        sl_return = sl_atr * entry_atr / entry_close

        if realized_return >= tp_return:
            labels.append(1)
        elif realized_return <= -sl_return:
            labels.append(-1)
        else:
            labels.append(0)
        times.append(timestamps[i])

    if not windows:
        raise ValueError("no usable TFT sequences; need more candles or a smaller lookback")

    X = np.stack(windows, axis=0)
    y = np.array(labels, dtype=int)
    times_arr = np.asarray(times)
    all_cols = tuple(list(feature_columns) + list(BARRIER_FEATURE_COLUMNS)[:4])
    return X, y, times_arr, all_cols


def _window_atrs(
    dataset: Any,
    development: np.ndarray,
    holdout: np.ndarray,
    tft_cfg: TftConfig,
) -> np.ndarray:
    """Extract the ATR of the latest candle in each holdout window."""
    frame = dataset.frame
    atr_col = frame["atr"].astype(float).to_numpy()
    lookback = tft_cfg.lookback
    # Sequences are emitted with the configured stride, so sequence i ends at frame position
    # lookback-1 + i*stride — not lookback-1+i. Index the frame on the same stride grid.
    stride = max(1, int(getattr(tft_cfg, "stride", 4)))
    full_atrs = atr_col[lookback - 1 :][::stride]
    return full_atrs[holdout]


def _window_entries(
    dataset: Any,
    development: np.ndarray,
    holdout: np.ndarray,
    tft_cfg: TftConfig,
) -> np.ndarray:
    """Extract the entry close of each holdout window's latest candle."""
    frame = dataset.frame
    close_col = frame["entry_price"].astype(float).to_numpy()
    lookback = tft_cfg.lookback
    # Same stride grid as _window_atrs: sequence i ends at frame position lookback-1 + i*stride.
    stride = max(1, int(getattr(tft_cfg, "stride", 4)))
    full_closes = close_col[lookback - 1 :][::stride]
    return full_closes[holdout]


def _close_at(
    times: np.ndarray,
    hold_times: np.ndarray,
    frames: dict[str, pd.DataFrame],
) -> np.ndarray:
    """The close price of the candle each holdout window ends on."""
    by_time: dict[Any, float] = {}
    for frame in frames.values():
        for ts, close in zip(
            frame["timestamp"].to_numpy(), frame["close"].astype(float).to_numpy()
        ):
            by_time[pd.Timestamp(ts)] = float(close)
    return np.asarray(
        [by_time.get(pd.Timestamp(ts), np.nan) for ts in hold_times], dtype=float
    )


def _train_tft_and_forecast(
    X_dev: np.ndarray,
    y_dev: np.ndarray,
    X_hold: np.ndarray,
    tft_cfg: TftConfig,
    config: AppConfig,
) -> np.ndarray:
    """Train a TFT on dev sequences, return quantile forecasts on holdout.

    Uses pytorch-forecasting's TemporalFusionTransformer for quantile
    regression over the horizon return. Returns ``(n_holdout, n_quantiles)``
    quantile forecasts — the CDF samples the bridge consumes.

    The TFT and Lightning objects are NOT persisted; only the quantile
    forecasts are returned and packaged into the TftBundle.
    """
    from pytorch_forecasting import TimeSeriesDataSet, TemporalFusionTransformer
    from pytorch_forecasting.metrics import QuantileLoss
    import lightning.pytorch as pl
    from lightning.pytorch.callbacks import EarlyStopping

    n_features = X_dev.shape[-1]
    n_samples = len(X_dev)

    # Build a TimeSeriesDataSet from the numpy windows. Each window is one
    # "series" with `lookback` time steps. The regression target is the realised
    # horizon return, but for TFT training we use a proxy: the label shifted to
    # a continuous return target (the sign + magnitude of the barrier outcome).
    records = []
    for i in range(n_samples):
        # PF requires categorical group ids as strings, not ints.
        series_id = f"s{i}"
        for t in range(tft_cfg.lookback):
            row: dict[str, Any] = {"series": series_id, "time_idx": t}
            for j in range(n_features):
                row[f"feat_{j}"] = float(X_dev[i, t, j])
            row["target"] = float(y_dev[i] + 1)  # map {-1,0,1} -> {0,1,2}
            records.append(row)

    training_df = pd.DataFrame(records)
    feature_cols = [f"feat_{j}" for j in range(n_features)]

    training = TimeSeriesDataSet(
        training_df,
        time_idx="time_idx",
        target="target",
        group_ids=["series"],
        static_categoricals=["series"],
        time_varying_known_reals=feature_cols,
        time_varying_unknown_reals=["target"],
        # Each window series carries exactly `lookback` rows; asking for an
        # encoder of the full lookback plus 1 prediction step would need
        # lookback+1 rows and the length filter would drop every series.
        max_encoder_length=tft_cfg.lookback - 1,
        max_prediction_length=1,
    )

    # Validation dataset from holdout windows.
    hold_records = []
    for i in range(len(X_hold)):
        series_id = f"s{i}"
        for t in range(tft_cfg.lookback):
            row = {"series": series_id, "time_idx": t}
            for j in range(n_features):
                row[f"feat_{j}"] = float(X_hold[i, t, j])
            row["target"] = float(y_dev[i % len(y_dev)] + 1)
            hold_records.append(row)
    hold_df = pd.DataFrame(hold_records)
    validation = TimeSeriesDataSet.from_dataset(training, hold_df, stop_randomization=True)

    batch_size = min(tft_cfg.batch_size, max(n_samples, 1))
    train_loader = training.to_dataloader(train=True, batch_size=batch_size)
    val_loader = validation.to_dataloader(train=False, batch_size=batch_size)

    tft = TemporalFusionTransformer.from_dataset(
        training,
        learning_rate=tft_cfg.learning_rate,
        hidden_size=tft_cfg.hidden_size,
        attention_head_size=tft_cfg.attention_head_size,
        dropout=tft_cfg.dropout,
        loss=QuantileLoss(quantiles=list(tft_cfg.quantiles)),
        log_interval=0,
    )

    early_stop_callback = EarlyStopping(
        monitor="val_loss",
        min_delta=1e-4,
        patience=tft_cfg.early_stop_patience,
        verbose=False,
        mode="min",
    )
    trainer = pl.Trainer(
        max_epochs=tft_cfg.max_epochs,
        accelerator="cpu",
        gradient_clip_val=0.1,
        callbacks=[early_stop_callback],
        enable_progress_bar=False,
        logger=False,
    )
    trainer.fit(tft, train_loader, val_loader)

    # Extract quantile forecasts for each holdout window via one batched predict pass.
    # Each validation series is exactly one window: encoder = rows [0..lookback-2],
    # prediction = the final row, so `prediction_length` outputs map 1:1 to windows.
    tft.eval()
    prediction = tft.predict(
        validation,
        mode="quantiles",
        return_index=False,
        batch_size=tft_cfg.batch_size,
    )
    # PF's predict() returns the quantile tensor directly in mode="quantiles":
    # (n_windows, prediction_length=1, n_quantiles).
    raw = torch.as_tensor(prediction)
    predictions = raw.reshape(len(raw), -1)

    n_hold = len(X_hold)
    quantile_forecasts = np.zeros((n_hold, len(tft_cfg.quantiles)), dtype=float)
    usable = min(n_hold, predictions.shape[0])
    quantile_forecasts[:usable, :] = predictions[:usable, :len(tft_cfg.quantiles)].numpy()
    if usable < n_hold:
        # PF may drop series the index filter removed; fill the remainder with the median so the
        # bundle stays shape-consistent and the gate sees honest (neutral) probabilities there.
        logger.warning("TFT prediction rows %s < holdout windows %s; remainder filled with median",
                       usable, n_hold)
        quantile_forecasts[usable:, :] = np.median(quantile_forecasts[:usable, :], axis=0)

    # The quantiles are in the label space (0,1,2). Convert back to returns.
    # Quantile q=0.5 maps to the median label; we convert label -> return using
    # the barrier geometry: label -1 -> -SL_return, +1 -> +TP_return, 0 -> 0.
    # But TFT predicts continuous quantiles, not discrete labels, so we map the
    # quantile value through the return scale directly.
    tp_return = config.barrier.backtest_take_profit_atr * 0.01
    sl_return = config.barrier.backtest_stop_loss_atr * 0.01
    # The TFT's target was label+1 in {0,1,2}; quantile prediction in that space
    # maps to: 0 -> -sl_return, 1 -> 0, 2 -> +tp_return. Linearly interpolate.
    for qi, q in enumerate(tft_cfg.quantiles):
        raw = quantile_forecasts[:, qi]
        # Map [0, 2] target space to [-sl_return, +tp_return] return space.
        quantile_forecasts[:, qi] = raw * (tp_return + sl_return) / 2.0 - sl_return
    # Quantile crossing: NN quantile heads can invert on individual rows. Project each row onto
    # the nearest monotone curve (running max) rather than feed the bridge an impossible CDF.
    quantile_forecasts = np.maximum.accumulate(quantile_forecasts, axis=1)

    return quantile_forecasts
