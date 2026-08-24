"""The original label: did the close move more than a threshold over a fixed horizon?

Superseded by `triple_barrier`, and kept because the legacy report and the close-to-close backtest are
still built on it — retiring both in the same change would leave nothing to compare the new model
against. It is not used to train the barrier-conditional model.

Its limitation is the reason the barrier labeller exists: a fixed +/-0.35% band over six candles is one
specific bet, so a caller asking for 2% profit with a 1% stop is thresholding a probability that was
never about their trade. Nothing about the horizon return says which barrier a position would have hit
first, and "first" is the entire question a bracket order asks.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd

from ..features import WARMUP_COLUMNS, build_features
from ..log_setup import get_logger

logger = get_logger(__name__)


def label_horizon_return(
    close: pd.Series,
    prediction_horizon: int,
    threshold: float,
) -> pd.DataFrame:
    """+1 above the band, -1 below it, 0 inside it, NaN where the future is unknown."""
    logger.info(
        "Creating target labels | horizon=%s candles | neutral_band=+/-%.3f%%",
        prediction_horizon,
        threshold * 100,
    )
    future_return = close.shift(-prediction_horizon) / close - 1
    target = pd.Series(np.nan, index=close.index, dtype="float64")
    valid = future_return.notna()
    target.loc[valid & (future_return > threshold)] = 1
    target.loc[valid & (future_return < -threshold)] = -1
    target.loc[valid & (future_return.abs() <= threshold)] = 0
    result = pd.DataFrame({"target": target, "future_return": future_return})
    counts = result["target"].value_counts(dropna=False).to_dict()
    logger.debug("Raw target counts (including unknown future rows) | %s", counts)
    return result


def build_horizon_dataset(
    frame: pd.DataFrame,
    prediction_horizon: int,
    threshold: float,
) -> tuple[pd.DataFrame, list[str]]:
    """Features, labels and the candle context in one frame, warm-up rows dropped."""
    started = time.perf_counter()
    logger.info("Supervised dataset construction started")

    features = build_features(frame)
    targets = label_horizon_return(frame["close"].astype(float), prediction_horizon, threshold)
    context_columns = frame[["timestamp", "open", "high", "low", "close", "volume"]]
    dataset = pd.concat([context_columns, features.frame, targets], axis=1)

    dataset = dataset.dropna(subset=[*WARMUP_COLUMNS, "target"]).reset_index(drop=True)
    dataset["target"] = dataset["target"].astype(int)

    counts = dataset["target"].value_counts().sort_index().to_dict()
    logger.info(
        "Supervised dataset ready | rows=%s | features=%s | classes=%s | elapsed=%.3fs",
        f"{len(dataset):,}",
        f"{len(features.columns):,}",
        counts,
        time.perf_counter() - started,
    )
    return dataset, list(features.columns)
