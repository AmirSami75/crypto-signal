"""RSI pullback: LONG when an uptrend dips to RSI<40 and the close resumes upward."""

from __future__ import annotations

import pandas as pd

from . import Signal, register
from .indicators import ema, rsi

TREND_EMA = 50
RSI_WINDOW = 14
DIP_LEVEL = 40.0


@register("rsi_pullback")
def evaluate(frame: pd.DataFrame) -> Signal | None:
    """Three conditions: uptrend, a recent RSI dip below 40, and a rising close on the final bar."""
    close = frame["close"]
    trend = ema(close, TREND_EMA)
    level = rsi(close, RSI_WINDOW)
    if len(close) < 3 or trend.iloc[-1] != trend.iloc[-1]:
        return None
    above_trend = bool((close.iloc[-TREND_EMA:] > trend.iloc[-TREND_EMA:]).all())
    dipped = bool((level.iloc[-3:-1] < DIP_LEVEL).any())
    resumed = close.iloc[-1] > close.iloc[-2]
    if above_trend and dipped and resumed:
        return Signal("LONG", len(close) - 1, f"uptrend pullback: rsi dipped<{DIP_LEVEL:g}, close resumed")
    return None
