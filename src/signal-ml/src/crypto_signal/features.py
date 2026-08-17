from __future__ import annotations

import time
import numpy as np
import pandas as pd

from .log_setup import get_logger


FEATURE_COLUMNS: list[str] = []
logger = get_logger(__name__)


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    change = close.diff()
    gain = change.clip(lower=0).ewm(alpha=1 / window, adjust=False).mean()
    loss = (-change.clip(upper=0)).ewm(alpha=1 / window, adjust=False).mean()
    relative_strength = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + relative_strength))


def _atr(frame: pd.DataFrame, window: int = 14) -> pd.Series:
    previous_close = frame["close"].shift(1)
    ranges = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    )
    true_range = ranges.max(axis=1)
    return true_range.ewm(alpha=1 / window, adjust=False).mean()


def make_features(frame: pd.DataFrame) -> pd.DataFrame:
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
    output["rsi_14"] = _rsi(close, 14) / 100.0
    output["atr_14_normalized"] = _atr(frame, 14) / close

    mean_20 = close.rolling(20).mean()
    std_20 = close.rolling(20).std()
    output["bollinger_z_20"] = (close - mean_20) / std_20.replace(0, np.nan)

    rolling_low = low.rolling(14).min()
    rolling_high = high.rolling(14).max()
    output["stochastic_14"] = (close - rolling_low) / (
        rolling_high - rolling_low
    ).replace(0, np.nan)

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

    output = output.replace([np.inf, -np.inf], np.nan)
    global FEATURE_COLUMNS
    FEATURE_COLUMNS = list(output.columns)
    logger.info(
        "Feature engineering finished | rows=%s | features=%s | elapsed=%.3fs",
        f"{len(output):,}",
        f"{len(FEATURE_COLUMNS):,}",
        time.perf_counter() - started,
    )
    return output


def make_target(
    close: pd.Series,
    prediction_horizon: int,
    threshold: float,
) -> pd.DataFrame:
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


def make_supervised(
    frame: pd.DataFrame,
    prediction_horizon: int,
    threshold: float,
) -> tuple[pd.DataFrame, list[str]]:
    started = time.perf_counter()
    logger.info("Supervised dataset construction started")
    features = make_features(frame)
    targets = make_target(frame["close"].astype(float), prediction_horizon, threshold)
    feature_columns = list(features.columns)
    context_columns = frame[["timestamp", "open", "high", "low", "close", "volume"]]
    dataset = pd.concat([context_columns, features, targets], axis=1)
    readiness = [
        "log_return_1",
        "volatility_168",
        "sma_ratio_168",
        "volume_ratio_168",
        "target",
    ]
    dataset = dataset.dropna(subset=readiness).reset_index(drop=True)
    dataset["target"] = dataset["target"].astype(int)
    counts = dataset["target"].value_counts().sort_index().to_dict()
    logger.info(
        "Supervised dataset ready | rows=%s | features=%s | classes=%s | elapsed=%.3fs",
        f"{len(dataset):,}",
        f"{len(feature_columns):,}",
        counts,
        time.perf_counter() - started,
    )
    return dataset, feature_columns
