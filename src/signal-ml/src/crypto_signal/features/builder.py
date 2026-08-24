"""Feature construction.

Every column here is **scale-free** — a log return, a ratio, a z-score, a normalised oscillator — and
that is a load-bearing property, not a stylistic one. Because no feature carries an absolute price, one
estimator trained on pooled markets transfers to a market it has never seen, which is what lets the
engine answer "signal for the requested currency" for a symbol that has no dedicated model. Adding a
raw price column here would quietly break that and the failure would look like a model that works on
BTC and is wrong everywhere else.

Causality: value *t* uses candle *t* and earlier. `test_features` pins this down by mutating the future
and asserting the past does not move.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..log_setup import get_logger
from .indicators import (
    average_true_range,
    bollinger_z_score,
    relative_strength_index,
    stochastic_position,
)

logger = get_logger(__name__)

#: Columns whose window is the longest in the set. A row where any of these is still NaN is a warm-up
#: row: the estimator would be reading a half-filled window as if it were a signal. Trimming on these
#: rather than on "any NaN anywhere" keeps the rule explicit and stable when a column is added.
WARMUP_COLUMNS: tuple[str, ...] = (
    "log_return_1",
    "volatility_168",
    "sma_ratio_168",
    "volume_ratio_168",
)

#: The candles needed before the longest window has filled. Serving refuses a shorter request rather
#: than answering from a warm-up row.
LONGEST_WINDOW = 168


@dataclass(frozen=True, slots=True)
class FeatureFrame:
    """Features, their column order, and the raw ATR they were computed alongside.

    The column tuple travels *with* the frame because the model needs the exact order it was trained on,
    and it is a tuple because a shared list is something a caller can append to. This replaces a
    module-level `FEATURE_COLUMNS` that `make_features` reassigned through a `global` statement — a
    write that raced every other caller under the eight-worker gRPC server and left whichever request
    finished last in charge of what the columns were.

    `atr` is in price units and comes from the same pass as the features, so the ATR the model was
    trained against and the ATR a barrier is measured in cannot drift apart.
    """

    frame: pd.DataFrame
    columns: tuple[str, ...]
    atr: pd.Series

    def __len__(self) -> int:
        return len(self.frame)

    def select(self, rows: pd.Index | np.ndarray | slice) -> pd.DataFrame:
        """The feature matrix for a subset of rows, in training order."""
        return self.frame.loc[rows, list(self.columns)]


def build_features(frame: pd.DataFrame, atr_window: int = 14) -> FeatureFrame:
    """Build causal features; every row uses only that candle and earlier candles."""
    started = time.perf_counter()
    logger.info("Feature engineering started | input_rows=%s", f"{len(frame):,}")

    close = frame["close"].astype(float)
    open_ = frame["open"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    volume = frame["volume"].astype(float)
    log_close = np.log(close)
    log_volume = np.log1p(volume)
    output = pd.DataFrame(index=frame.index)

    for lag in (1, 3, 6, 12, 24, 72):
        output[f"log_return_{lag}"] = log_close.diff(lag)
        output[f"momentum_{lag}"] = close.pct_change(lag, fill_method=None)

    one_bar_return = log_close.diff()
    for window in (6, 24, 72, 168):
        output[f"volatility_{window}"] = one_bar_return.rolling(window).std()
        sma = close.rolling(window).mean()
        output[f"sma_ratio_{window}"] = close / sma - 1

    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    output["ema_ratio_12"] = close / ema_12 - 1
    output["ema_ratio_26"] = close / ema_26 - 1
    output["macd_normalized"] = (ema_12 - ema_26) / close
    output["rsi_14"] = relative_strength_index(close, 14) / 100.0

    atr = average_true_range(frame, atr_window)
    output[f"atr_{atr_window}_normalized"] = atr / close

    output["bollinger_z_20"] = bollinger_z_score(close, 20)
    output["stochastic_14"] = stochastic_position(close, high, low, 14)

    output["volume_log_change_1"] = log_volume.diff()
    output["volume_ratio_24"] = volume / volume.rolling(24).mean() - 1
    output["volume_ratio_168"] = volume / volume.rolling(168).mean() - 1

    safe_open = open_.replace(0, np.nan)
    safe_close = close.replace(0, np.nan)
    output["candle_body"] = (close - open_) / safe_open
    output["high_low_range"] = (high - low) / safe_close
    output["upper_shadow"] = (high - pd.concat([open_, close], axis=1).max(axis=1)) / safe_close
    output["lower_shadow"] = (pd.concat([open_, close], axis=1).min(axis=1) - low) / safe_close

    timestamp = pd.to_datetime(frame["timestamp"], utc=True)
    hour_angle = 2 * np.pi * timestamp.dt.hour / 24
    weekday_angle = 2 * np.pi * timestamp.dt.dayofweek / 7
    output["hour_sin"] = np.sin(hour_angle)
    output["hour_cos"] = np.cos(hour_angle)
    output["weekday_sin"] = np.sin(weekday_angle)
    output["weekday_cos"] = np.cos(weekday_angle)

    # An infinity is a division that found a zero denominator. Left in place it becomes either a crash
    # or, worse, a finite-looking split point; as a NaN it is trimmed with the warm-up rows.
    output = output.replace([np.inf, -np.inf], np.nan)

    columns = tuple(output.columns)
    logger.info(
        "Feature engineering finished | rows=%s | features=%s | elapsed=%.3fs",
        f"{len(output):,}",
        f"{len(columns):,}",
        time.perf_counter() - started,
    )
    return FeatureFrame(frame=output, columns=columns, atr=atr.rename("atr"))
