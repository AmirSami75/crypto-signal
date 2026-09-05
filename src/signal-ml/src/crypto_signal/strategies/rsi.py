"""RSI mean reversion: LONG when oversold, SHORT when overbought."""

from __future__ import annotations

import pandas as pd

from . import Signal, register
from .indicators import rsi

OVERSOLD = 30.0
OVERBOUGHT = 70.0


@register("rsi")
def evaluate(frame: pd.DataFrame) -> Signal | None:
    """Fire on the transition into the oversold/overbought zone, not on every bar inside it."""
    level = rsi(frame["close"])
    if len(level) < 2:
        return None
    current, previous = level.iloc[-1], level.iloc[-2]
    if pd.isna(previous) or pd.isna(current):
        return None
    if previous >= OVERSOLD > current:
        return Signal("LONG", len(level) - 1, f"rsi crossed below {OVERSOLD:g} ({current:.1f})")
    if previous <= OVERBOUGHT < current:
        return Signal("SHORT", len(level) - 1, f"rsi crossed above {OVERBOUGHT:g} ({current:.1f})")
    return None
