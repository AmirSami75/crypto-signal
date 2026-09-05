"""Triple EMA (TEMA) trend: LONG when price flips above TEMA, SHORT when it flips below."""

from __future__ import annotations

import pandas as pd

from . import Signal, register
from .indicators import ema

WINDOW = 20


def tema(series: pd.Series, window: int) -> pd.Series:
    """Triple exponentially smoothed average: 3*EMA1 - 3*EMA2 + EMA3 (EMAk = EMA of EMA(k-1))."""
    first = ema(series, window)
    second = ema(first, window)
    third = ema(second, window)
    return 3 * first - 3 * second + third


@register("triple_ema")
def evaluate(frame: pd.DataFrame) -> Signal | None:
    """Fire on the flip bar — price crossing its TEMA — not while it stays on one side."""
    level = tema(frame["close"], WINDOW)
    close = frame["close"]
    if len(close) < 2 or level.iloc[-2:].isna().any():
        return None
    was_below, is_above = close.iloc[-2] <= level.iloc[-2], close.iloc[-1] > level.iloc[-1]
    if was_below and is_above:
        return Signal("LONG", len(close) - 1, f"close crossed above tema{WINDOW} {level.iloc[-1]:g}")
    was_above, is_below = close.iloc[-2] >= level.iloc[-2], close.iloc[-1] < level.iloc[-1]
    if was_above and is_below:
        return Signal("SHORT", len(close) - 1, f"close crossed below tema{WINDOW} {level.iloc[-1]:g}")
    return None
