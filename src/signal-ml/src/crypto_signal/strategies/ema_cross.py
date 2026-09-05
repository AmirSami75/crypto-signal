"""EMA crossover: LONG when the fast EMA crosses above the slow, SHORT on the reverse."""

from __future__ import annotations

import pandas as pd

from . import Signal, register
from .indicators import ema

FAST = 12
SLOW = 26


@register("ema_cross")
def evaluate(frame: pd.DataFrame) -> Signal | None:
    """Fire only on the crossing bar — a steady trend above the slow EMA emits nothing."""
    fast = ema(frame["close"], FAST)
    slow = ema(frame["close"], SLOW)
    if len(fast) < 2:
        return None
    was_below, is_above = fast.iloc[-2] <= slow.iloc[-2], fast.iloc[-1] > slow.iloc[-1]
    if was_below and is_above:
        return Signal("LONG", len(fast) - 1, f"ema{FAST} crossed above ema{SLOW}")
    was_above, is_below = fast.iloc[-2] >= slow.iloc[-2], fast.iloc[-1] < slow.iloc[-1]
    if was_above and is_below:
        return Signal("SHORT", len(fast) - 1, f"ema{FAST} crossed below ema{SLOW}")
    return None
