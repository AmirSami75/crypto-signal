"""Keltner channel breakout: LONG above EMA+2*ATR, SHORT below EMA-2*ATR."""

from __future__ import annotations

import pandas as pd

from . import Signal, register
from .indicators import atr, ema, true_range

EMA_WINDOW = 20
MULTIPLE = 2.0


@register("keltner_breakout")
def evaluate(frame: pd.DataFrame) -> Signal | None:
    """Fire on the first close outside a channel built on smoothed ATR; inside stays silent."""
    channel = _channel(frame)
    if channel is None:
        return None
    upper, lower = channel
    close = frame["close"]
    was_inside = lower.iloc[-2] <= close.iloc[-2] <= upper.iloc[-2]
    if was_inside and close.iloc[-1] > upper.iloc[-1]:
        return Signal("LONG", len(close) - 1, f"close {close.iloc[-1]:g} broke keltner upper {upper.iloc[-1]:g}")
    if was_inside and close.iloc[-1] < lower.iloc[-1]:
        return Signal("SHORT", len(close) - 1, f"close {close.iloc[-1]:g} broke keltner lower {lower.iloc[-1]:g}")
    return None


def _channel(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series] | None:
    """EMA(20) ± 2 * ATR(14). None while either window is still filling."""
    midpoint = ema(frame["close"], EMA_WINDOW)
    smoothed = true_range(frame).ewm(alpha=1 / 14, adjust=False).mean()
    if len(frame) < 2 or smoothed.iloc[-2:].isna().any():
        return None
    offset = MULTIPLE * smoothed
    return midpoint + offset, midpoint - offset


_ = atr  # re-exported for callers that import the yardstick from here
