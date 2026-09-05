"""Donchian channel breakout: LONG on a new 20-bar high, SHORT on a new 20-bar low."""

from __future__ import annotations

import pandas as pd

from . import Signal, register

WINDOW = 20


@register("donchian")
def evaluate(frame: pd.DataFrame) -> Signal | None:
    """The band excludes the current bar, so a breakout is the close beyond every prior high/low."""
    high = frame["high"].shift(1).rolling(WINDOW).max()
    low = frame["low"].shift(1).rolling(WINDOW).min()
    close = frame["close"]
    if len(close) < 2 or high.iloc[-2:].isna().any() or low.iloc[-2:].isna().any():
        return None
    if close.iloc[-2] <= high.iloc[-2] < close.iloc[-1]:
        return Signal("LONG", len(close) - 1, f"close {close.iloc[-1]:g} broke 20-bar high {high.iloc[-2]:g}")
    if close.iloc[-2] >= low.iloc[-2] > close.iloc[-1]:
        return Signal("SHORT", len(close) - 1, f"close {close.iloc[-1]:g} broke 20-bar low {low.iloc[-2]:g}")
    return None
