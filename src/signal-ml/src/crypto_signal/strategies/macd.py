"""MACD momentum: LONG on a bullish signal-line cross, SHORT on a bearish one."""

from __future__ import annotations

import pandas as pd

from . import Signal, register
from .indicators import macd


@register("macd")
def evaluate(frame: pd.DataFrame) -> Signal | None:
    """Fire on the histogram's sign flip — the bar the lines cross, not the whole stretch after."""
    histogram = macd(frame["close"])["histogram"]
    if len(histogram) < 2 or histogram.iloc[-2:].isna().any():
        return None
    previous, current = histogram.iloc[-2], histogram.iloc[-1]
    if previous <= 0 < current:
        return Signal("LONG", len(histogram) - 1, f"macd histogram turned positive ({previous:.3g}->{current:.3g})")
    if previous >= 0 > current:
        return Signal("SHORT", len(histogram) - 1, f"macd histogram turned negative ({previous:.3g}->{current:.3g})")
    return None
