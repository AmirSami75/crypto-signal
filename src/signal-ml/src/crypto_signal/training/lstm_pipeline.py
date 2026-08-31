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
