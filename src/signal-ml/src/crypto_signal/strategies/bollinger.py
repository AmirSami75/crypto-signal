"""Bollinger mean reversion: LONG below the lower band, SHORT above the upper."""

from __future__ import annotations

import pandas as pd

from . import Signal, register
from .indicators import sma, stdev

WINDOW = 20
BANDS = 2.0


@register("bollinger")
def evaluate(frame: pd.DataFrame) -> Signal | None:
    """Fire when the close pierces a band it was inside on the previous bar."""
    close = frame["close"]
    mean = sma(close, WINDOW)
    spread = stdev(close, WINDOW) * BANDS
    upper, lower = mean + spread, mean - spread
    if len(close) < 2 or any(s.iloc[-2:].isna().any() for s in (upper, lower)):
        return None
    was_inside = lower.iloc[-2] <= close.iloc[-2] <= upper.iloc[-2]
    if was_inside and close.iloc[-1] < lower.iloc[-1]:
        return Signal("LONG", len(close) - 1, f"close {close.iloc[-1]:g} broke lower band {lower.iloc[-1]:g}")
    if was_inside and close.iloc[-1] > upper.iloc[-1]:
        return Signal("SHORT", len(close) - 1, f"close {close.iloc[-1]:g} broke upper band {upper.iloc[-1]:g}")
    return None
