"""Shared indicator helpers for the Strategy Zoo.

Thin wrappers over `crypto_signal.features.indicators` (the platform's single yardstick set) plus the
few series the zoo needs that the feature builder does not ship. Every helper is a plain series
transform with leading NaNs — no lookahead, index-preserving — so a strategy is safe to compute over
a full history and split in time.

Only here so each strategy module stays under its 60-line budget.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..features.indicators import average_true_range, relative_strength_index

__all__ = [
    "atr",
    "ema",
    "macd",
    "rsi",
    "sma",
    "stdev",
    "true_range",
]


def ema(series: pd.Series, window: int) -> pd.Series:
    """Exponential moving average (adjust=False, Wilder-style recursion)."""
    return series.ewm(span=window, adjust=False).mean()


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def stdev(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).std()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    return relative_strength_index(close, window)


def atr(frame: pd.DataFrame, window: int = 14) -> pd.Series:
    return average_true_range(frame, window)


def true_range(frame: pd.DataFrame) -> pd.Series:
    """Untamed true range: the piece ATR smooths, needed for ATR-on-top-of-EMA bands (Keltner)."""
    previous_close = frame["close"].shift(1)
    ranges = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)  # type: ignore[return-value]


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, pd.Series]:
    """MACD line, signal line, histogram — the classic 12/26/9."""
    line = ema(close, fast) - ema(close, slow)
    signal_line = line.ewm(span=signal, adjust=False).mean()
    return {"macd": line, "signal": signal_line, "histogram": line - signal_line}
