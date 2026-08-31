"""Train a pooled LSTM signal bundle for one interval and write it to the serving registry.

This is the experimental complement to `barrier_pipeline.train_barrier_model`: same candle frames, same
honest purged-holdout and cost-aware backtest, but a recurrent net that reads a window of `lookback`
candles instead of a single row. It is deliberately additive — it writes `_pooled_<INTERVAL>.joblib`
with `metadata["is_sequence"] = True`, and the registry loads it only when present, never replacing the
gradient-boosted bundle's role unless an operator opts in. See the module docstring in `modeling/lstm.py`
and `docs/ml-improvement-plan.md` for why the LSTM is experimental and must clear the same bar.
"""

from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .. import __version__
from ..config import AppConfig, LstmSection
from ..data import validate_ohlcv
from ..evaluation import run_backtest
from ..labeling.triple_barrier import barrier_grid
from ..log_setup import get_logger
from ..modeling import probabilities_to_signals
from ..modeling.lstm import LstmConfig, build_lstm_sequences, train_lstm
from .artifacts import write_json
from .barrier_pipeline import download_barrier_data

logger = get_logger(__name__)

#: The canonical bracket the LSTM labels against — the same one the holdout backtest trades, so the
#: label and the measurement agree about what bet is being scored.
LSTM_CLASS_NAMES = {-1: "stop_loss_first", 0: "timeout", 1: "take_profit_first"}


def _lstm_config(config: AppConfig) -> LstmConfig:
    """Read the parsed `[lstm]` section off `AppConfig`.

    `load_config` always populates `config.lstm` with an `LstmSection` (defaults when the TOML block is
    absent), so no dict-walking is needed here and an unparsed dict can never silently disagree with
    what the config loader validated.
    """
    section = getattr(config, "lstm", None) or LstmSection()
    return LstmConfig(
        lookback=int(section.lookback),
        hidden_size=int(section.hidden_size),
        num_layers=int(section.num_layers),
        dropout=float(section.dropout),
        learning_rate=float(section.learning_rate),
        batch_size=int(section.batch_size),
        epochs=int(section.epochs),
        weight_decay=float(section.weight_decay),
    )


def _chronological_split(times: np.ndarray, holdout_fraction: float, gap: int) -> tuple[np.ndarray, np.ndarray]:
    from ..modeling.splitting import chronological_blocks

    development, holdout = chronological_blocks(
        times, (1.0 - holdout_fraction, holdout_fraction), gap=gap
    )
    return development, holdout


def train_lstm_bundle(config: AppConfig, refresh: bool = False) -> dict[str, Any]:
    """Label, split, train, measure and persist the pooled LSTM bundle for `config.market.interval`."""
    from ..modeling.splitting import chronological_blocks

    started = time.perf_counter()
    lstm_cfg = _lstm_config(config)
    interval = config.market.interval
    logger.info(
        "LSTM training started | interval=%s | lookback=%s | symbols=%s",
        interval,
        lstm_cfg.lookback,
        ", ".join(config.market.symbols),
    )

    frames = download_barrier_data(config, refresh=refresh)
    if not frames:
        raise ValueError("no candle frames available to train the LSTM")

    X, y, feature_columns, times = build_lstm_sequences(
        frames,
        interval=interval,
        config=lstm_cfg,
        atr_window=config.barrier.atr_window,
        max_horizon=config.barrier.max_horizon,
        take_profit_atr=config.barrier.backtest_take_profit_atr,
        stop_loss_atr=config.barrier.backtest_stop_loss_atr,
    )
    logger.info(
        "LSTM sequences built | windows=%s | features=%s | classes=%s",
        f"{len(X):,}",
        len(feature_columns),
        {LSTM_CLASS_NAMES[k]: int((y == k).sum()) for k in (-1, 0, 1)},
    )

    development, holdout = _chronological_split(
        times, config.barrier.holdout_fraction, config.barrier.max_horizon
    )
    X_dev, y_dev = X[development], y[development]
    X_hold, y_hold, t_hold = X[holdout], y[holdout], times[holdout]

    bundle = train_lstm(X_dev, y_dev, feature_columns, lstm_cfg, progress=True)

    # Honest holdout: score the long-bet probabilities, mirror to short, and backtest net of costs.
    long_probs = _predict_windows(bundle, X_hold)
    signals = probabilities_to_signals(long_probs, config.model.probability_threshold)
    holdout_close = _close_at(times, t_hold, frames)
    predictions = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(t_hold),
            "close": holdout_close.astype(float),
            "actual_class": y_hold,
            "probability_sell": long_probs[:, 0],
            "probability_hold": long_probs[:, 1],
            "probability_buy": long_probs[:, 2],
            "signal": signals,
            "signal_name": [LSTM_CLASS_NAMES[int(v)] for v in signals],
        }
    )
    backtest_df, backtest_metrics = run_backtest(
        predictions,
        interval=interval,
        fee_rate=config.backtest.fee_rate,
        slippage_rate=config.backtest.slippage_rate,
        allow_short=config.backtest.allow_short,
    )
    strategy = backtest_metrics["strategy"]
    logger.info(
        "LSTM holdout backtest | cumulative_return=%.2f%% | vs buy&hold=%.2f%%",
        strategy["cumulative_return"] * 100,
        backtest_metrics["buy_and_hold"]["cumulative_return"] * 100,
    )

    artifact_dir = config.output.model_dir
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stem = f"_pooled_{interval}"
    path = artifact_dir / f"{stem}.joblib"
    trained_at = datetime.now(tz=timezone.utc).isoformat()
    metadata: dict[str, Any] = {
        "interval": interval,
        "symbols": list(config.market.symbols),
        "trained_at_utc": trained_at,
        "project_version": __version__,
        "atr_window": config.barrier.atr_window,
        "max_horizon": config.barrier.max_horizon,
        "lookback": lstm_cfg.lookback,
        "is_sequence": True,
        "algorithm": "lstm",
        "lstm": {
            "hidden_size": lstm_cfg.hidden_size,
            "num_layers": lstm_cfg.num_layers,
            "dropout": lstm_cfg.dropout,
        },
        "label_rows": int(len(X)),
        "label_candles": int(len(times)),
        "class_counts": {str(k): int((y == k).sum()) for k in (-1, 0, 1)},
        "holdout_fraction": config.barrier.holdout_fraction,
        "barrier_atr_bounds": [min(config.barrier.grid_atr), max(config.barrier.grid_atr)],
        "feature_columns": list(feature_columns),
        "calibration": {"method": "none", "selected": "none", "attempted": "none", "improved": False},
        "strict_holdout": {
            "classification": {
                "rows": int(len(y_hold)),
                "class_counts": {str(k): int((y_hold == k).sum()) for k in (-1, 0, 1)},
            },
            "backtest": backtest_metrics,
        },
        "warning": (
            "Experimental recurrent model. It must clear the same purged-holdout, cost-aware backtest bar "
            "as the gradient-boosted bundle before any promotion; see docs/ml-improvement-plan.md."
        ),
    }
    joblib.dump(
        {"model": bundle, "feature_columns": list(feature_columns), "metadata": metadata},
        path,
        compress=3,
    )
    predictions.to_csv(artifact_dir / f"{stem}_holdout_predictions.csv", index=False)
    write_json(artifact_dir / f"{stem}_metadata.json", metadata)
    logger.info(
        "LSTM bundle written | path=%s | size=%.1fMB | elapsed=%.1fs",
        path,
        path.stat().st_size / 1e6,
        time.perf_counter() - started,
    )
    return metadata


def _predict_windows(bundle: Any, X: np.ndarray) -> np.ndarray:
    """Score every window with the bundle under the serving contract (long-bet probabilities, `(N, 3)`)."""
    torch = __import__("torch", fromlist=["__version__"])
    from ..modeling.lstm import LstmBundle

    device = torch.device("cpu")
    bundle._module.to(device)
    bundle._module.eval()
    out = np.zeros((len(X), 3), dtype=float)
    step = 1024
    for start in range(0, len(X), step):
        batch = torch.as_tensor(X[start : start + step], dtype=torch.float32)
        with torch.no_grad():
            logits = bundle._module.forward(batch)
            out[start : start + step] = torch.softmax(logits, dim=-1).cpu().numpy()
    return out


def _close_at(times: np.ndarray, hold_times: np.ndarray, frames: dict[str, pd.DataFrame]) -> np.ndarray:
    """The close price of the candle each holdout window ends on, looked up per symbol."""
    closes: list[float] = []
    # `download_barrier_data` returns frames keyed by symbol; map by timestamp alone, which is unique per
    # candle across symbols because they share an exchange clock at the same interval.
    by_time: dict[Any, float] = {}
    for frame in frames.values():
        for ts, close in zip(frame["timestamp"].to_numpy(), frame["close"].astype(float).to_numpy()):
            by_time[pd.Timestamp(ts)] = float(close)
    for ts in hold_times:
        closes.append(by_time[pd.Timestamp(ts)])
    return np.asarray(closes, dtype=float)


# ─────────────────────────────── v2: attention ensemble ───────────────────────────────


def train_lstm_v2_bundle(config: AppConfig, refresh: bool = False) -> dict[str, Any]:
    """Train the attention-ensemble LSTM v2 and write `_pooled_<INTERVAL>_v2.joblib`.

    Same candle frames, same triple-barrier labels, same purged chronological holdout and the same
    cost-aware backtest as the v1 pipeline — only the estimator differs. The artifact name carries
    `_v2` so the registry serves whichever file is present, and a v2 challenger can never silently
    replace a v1 bundle at the same key.
    """
    from ..modeling.lstm_v2 import LstmV2Config, train_lstm_v2

    started = time.perf_counter()
    v2_cfg = _lstm_v2_config(config)
    interval = config.market.interval
    logger.info(
        "LSTM v2 training started | interval=%s | lookback=%s | members=%d | symbols=%s",
        interval,
        v2_cfg.lookback,
        v2_cfg.ensemble_seeds,
        ", ".join(config.market.symbols),
    )

    frames = download_barrier_data(config, refresh=refresh)
    if not frames:
        raise ValueError("no candle frames available to train the LSTM v2")

    X, y, feature_columns, times = build_lstm_sequences(
        frames,
        interval=interval,
        # Sequence building only reads `lookback` off the config; v2 shares the labeller's
        # barrier semantics with v1, so the v1-shaped config carries them.
        config=LstmConfig(lookback=v2_cfg.lookback),
        atr_window=config.barrier.atr_window,
        max_horizon=config.barrier.max_horizon,
        take_profit_atr=config.barrier.backtest_take_profit_atr,
        stop_loss_atr=config.barrier.backtest_stop_loss_atr,
    )
    logger.info(
        "LSTM v2 sequences built | windows=%s | features=%s | classes=%s",
        f"{len(X):,}",
        len(feature_columns),
        {LSTM_CLASS_NAMES[k]: int((y == k).sum()) for k in (-1, 0, 1)},
    )

    development, holdout = _chronological_split(
        times, config.barrier.holdout_fraction, config.barrier.max_horizon
    )
    X_dev, y_dev = X[development], y[development]
    X_hold, y_hold, t_hold = X[holdout], y[holdout], times[holdout]

    bundle, diagnostics = train_lstm_v2(
        X_dev, y_dev, feature_columns, v2_cfg, class_weight=True, progress=True
    )

    # Honest holdout, through the batched serving path so training and serving agree exactly.
    long_probs = bundle.predict_proba_windows(X_hold)
    signals = probabilities_to_signals(long_probs, config.model.probability_threshold)
    holdout_close = _close_at(times, t_hold, frames)
    predictions = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(t_hold),
            "close": holdout_close.astype(float),
            "actual_class": y_hold,
            "probability_sell": long_probs[:, 0],
            "probability_hold": long_probs[:, 1],
            "probability_buy": long_probs[:, 2],
            "signal": signals,
            "signal_name": [LSTM_CLASS_NAMES[int(v)] for v in signals],
        }
    )
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
        "LSTM v2 holdout | log_loss=%.4f | cumulative_return=%.2f%% | vs buy&hold=%.2f%%",
        holdout_log_loss,
        strategy["cumulative_return"] * 100,
        backtest_metrics["buy_and_hold"]["cumulative_return"] * 100,
    )

    artifact_dir = config.output.model_dir
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stem = f"_pooled_{interval}_v2"
    path = artifact_dir / f"{stem}.joblib"
    trained_at = datetime.now(tz=timezone.utc).isoformat()
    metadata: dict[str, Any] = {
        "interval": interval,
        "symbols": list(config.market.symbols),
        "trained_at_utc": trained_at,
        "project_version": __version__,
        "atr_window": config.barrier.atr_window,
        "max_horizon": config.barrier.max_horizon,
        "lookback": v2_cfg.lookback,
        "is_sequence": True,
        "algorithm": "lstm_v2_attention_ensemble",
        "lstm_v2": {
            "hidden_size": v2_cfg.hidden_size,
            "num_layers": v2_cfg.num_layers,
            "dropout": v2_cfg.dropout,
            "ensemble_seeds": v2_cfg.ensemble_seeds,
            "patience": v2_cfg.patience,
            "epochs_run_per_member": diagnostics["epochs_run_per_member"],
        },
        "label_rows": int(len(X)),
        "label_candles": int(len(times)),
        "class_counts": {str(k): int((y == k).sum()) for k in (-1, 0, 1)},
        "holdout_fraction": config.barrier.holdout_fraction,
        "barrier_atr_bounds": [min(config.barrier.grid_atr), max(config.barrier.grid_atr)],
        "feature_columns": list(feature_columns),
        "calibration": {
            "method": "temperature",
            "selected": "temperature",
            "temperature": diagnostics["temperature_mean"],
            "attempted": "temperature",
            "improved": bool(diagnostics["temperature_mean"] != 1.0),
        },
        "diagnostics": diagnostics,
        "strict_holdout": {
            "log_loss": holdout_log_loss,
            "classification": {
                "rows": int(len(y_hold)),
                "class_counts": {str(k): int((y_hold == k).sum()) for k in (-1, 0, 1)},
            },
            "backtest": backtest_metrics,
        },
        "warning": (
            "Experimental recurrent model (v2 attention ensemble). It must clear the same "
            "purged-holdout, cost-aware backtest bar as the gradient-boosted bundle before any "
            "promotion; see docs/ml-improvement-plan.md."
        ),
    }
    joblib.dump(
        {"model": bundle, "feature_columns": list(feature_columns), "metadata": metadata},
        path,
        compress=3,
    )
    predictions.to_csv(artifact_dir / f"{stem}_holdout_predictions.csv", index=False)
    write_json(artifact_dir / f"{stem}_metadata.json", metadata)
    logger.info(
        "LSTM v2 bundle written | path=%s | size=%.1fMB | elapsed=%.1fs",
        path,
        path.stat().st_size / 1e6,
        time.perf_counter() - started,
    )
    return metadata


def _lstm_v2_config(config: AppConfig) -> Any:
    """Read the parsed `[lstm_v2]` section off `AppConfig` (defaults when the block is absent)."""
    from ..modeling.lstm_v2 import LstmV2Config

    section = getattr(config, "lstm_v2", None)
    if section is None:
        return LstmV2Config()
    return LstmV2Config(
        lookback=int(section.lookback),
        hidden_size=int(section.hidden_size),
        num_layers=int(section.num_layers),
        dropout=float(section.dropout),
        learning_rate=float(section.learning_rate),
        batch_size=int(section.batch_size),
        epochs=int(section.epochs),
        weight_decay=float(section.weight_decay),
        patience=int(section.patience),
        validation_fraction=float(section.validation_fraction),
        ensemble_seeds=int(section.ensemble_seeds),
        seed_base=int(section.seed_base),
    )


def _log_loss(probs: np.ndarray, y: np.ndarray) -> float:
    """Multiclass log-loss over `[-1, 0, 1]`, the holdout metric the promotion gate compares."""
    one_hot = np.zeros((len(y), 3))
    one_hot[np.arange(len(y)), y + 1] = 1.0
    return float(-(one_hot * np.log(np.clip(probs, 1e-12, 1.0))).mean())
