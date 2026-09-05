"""Supertrend: trailing ATR-band trend follower; LONG on the flip above, SHORT on the flip below."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import Signal, register
from .indicators import atr

MULTIPLE = 3.0


@register("supertrend")
def evaluate(frame: pd.DataFrame) -> Signal | None:
    """Fire on the flip bar of the trailing supertrend, after the band has established."""
    trend, bands = _supertrend(frame)
    if trend is None or len(trend) < 2:
        return None
    close = float(frame["close"].iloc[-1])
    previous, current = int(trend.iloc[-2]), int(trend.iloc[-1])
    if previous == -1 and current == 1:
        return Signal("LONG", len(trend) - 1, f"supertrend flipped up at close {close:g}")
    if previous == 1 and current == -1:
        return Signal("SHORT", len(trend) - 1, f"supertrend flipped down at close {close:g}")
    return None


def _supertrend(frame: pd.DataFrame) -> tuple[pd.Series | None, pd.DataFrame | None]:
    """Trailing supertrend bands. None while the ATR window is still filling.

    The final bands ratchet against the trend — a downtrend's upper band only falls, an uptrend's
    lower band only rises — which is what makes a reversal cross a band frozen near the old extreme
    instead of chasing the price it is trying to catch.
    """
    level = atr(frame)
    basic_upper = (frame["high"] + frame["low"]) / 2 + MULTIPLE * level
    basic_lower = (frame["high"] + frame["low"]) / 2 - MULTIPLE * level
    close = frame["close"]
    n = len(frame)
    final_upper = np.full(n, np.nan)
    final_lower = np.full(n, np.nan)
    trend = np.zeros(n, dtype=int)
    started = False
    for i in range(n):
        if np.isnan(level.iloc[i]):
            continue
        if not started:
            final_upper[i], final_lower[i], trend[i] = basic_upper.iloc[i], basic_lower.iloc[i], 1
            started = True
            continue
        final_upper[i] = min(basic_upper.iloc[i], final_upper[i - 1])
        final_lower[i] = max(basic_lower.iloc[i], final_lower[i - 1])
        if trend[i - 1] == 1:
            trend[i] = -1 if close.iloc[i] < final_lower[i] else 1
        else:
            trend[i] = 1 if close.iloc[i] > final_upper[i] else -1
    if not started:
        return None, None
    bands = pd.DataFrame({"upper": final_upper, "lower": final_lower}, index=frame.index)
    return pd.Series(trend, index=frame.index), bands
