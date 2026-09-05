"""Supertrend: trailing ATR-band trend follower; LONG on the flip above, SHORT on the flip below."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import Signal, register
from .indicators import atr

MULTIPLE = 3.0

# The league walks every prefix of a frame, calling `evaluate` once per candle. Recomputing the
# whole trailing-band walk per call is O(n^2) overall — hours on a 58k-candle history. Wilder's ATR
# is causal (bar i's value depends only on bars <= i), so when a prefix grows by one bar, every
# earlier bar's bands and trend are unchanged and only the new bar needs walking. One cached state
# keyed by length + last bar's values keeps that O(n) over the whole walk.
_STATE: dict[tuple, tuple[np.ndarray, np.ndarray, np.ndarray, float]] = {}


@register("supertrend")
def evaluate(frame: pd.DataFrame) -> Signal | None:
    """Fire on the flip bar of the trailing supertrend, after the band has established."""
    trend, upper, lower = _trend(frame)
    if trend is None or len(trend) < 2:
        return None
    close = float(frame["close"].iloc[-1])
    previous, current = int(trend[-2]), int(trend[-1])
    if previous == -1 and current == 1:
        return Signal("LONG", len(trend) - 1, f"supertrend flipped up at close {close:g}")
    if previous == 1 and current == -1:
        return Signal("SHORT", len(trend) - 1, f"supertrend flipped down at close {close:g}")
    return None


def _trend(frame: pd.DataFrame) -> tuple[np.ndarray | None, np.ndarray, np.ndarray]:
    """Full trend/band arrays for this frame, extended one bar when the cached prefix grew by one."""
    key = (
        len(frame),
        float(frame["close"].iloc[0]),
        float(frame["close"].iloc[-1]),
        float(frame["high"].iloc[-1]),
        float(frame["low"].iloc[-1]),
    )
    cached = _STATE.get(key)
    if cached is not None:
        return cached
    if len(_STATE) == 1:
        (prev_key, (prev_trend, prev_upper, prev_lower, prev_atr)) = next(iter(_STATE.items()))
        prev_len = prev_key[0]
        if key[0] == prev_len + 1 and prev_len >= 1:
            trend, upper, lower, last_atr = _extend_one(
                frame, prev_trend, prev_upper, prev_lower, prev_atr
            )
            _STATE.clear()
            _STATE[key] = (trend, upper, lower, last_atr)
            return trend, upper, lower
    trend, upper, lower, last_atr = _compute(frame)
    _STATE.clear()
    if trend is not None:
        _STATE[key] = (trend, upper, lower, last_atr)
    return trend, upper, lower


def _extend_one(
    frame: pd.DataFrame,
    prev_trend: np.ndarray,
    prev_upper: np.ndarray,
    prev_lower: np.ndarray,
    prev_atr: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Recompute only the final bar; earlier bars are frozen because ATR is causal.

    The previous bar's ATR (and so its basic bands) cannot change when the prefix grows, so the
    ratchet walk for bars 0..n-2 stands. Bar n-1 is walked from the stored state. Only the last
    ATR value is needed, so the causal recursion is advanced from the cached previous ATR directly
    instead of re-smoothing the whole prefix.
    """
    previous_close = float(frame["close"].iloc[-2])
    high_i = float(frame["high"].iloc[-1])
    low_i = float(frame["low"].iloc[-1])
    close_i = float(frame["close"].iloc[-1])
    true_range_i = max(
        high_i - low_i,
        abs(high_i - previous_close),
        abs(low_i - previous_close),
    )
    level_i = prev_atr + (true_range_i - prev_atr) / 14.0  # Wilder ewm, alpha=1/14
    basic_upper = (high_i + low_i) / 2 + MULTIPLE * level_i
    basic_lower = (high_i + low_i) / 2 - MULTIPLE * level_i
    if prev_trend[-1] == 0:
        trend_value, upper_value, lower_value = 1, basic_upper, basic_lower
    elif prev_trend[-1] == 1:
        upper_value = min(basic_upper, prev_upper[-1])
        lower_value = max(basic_lower, prev_lower[-1])
        trend_value = -1 if close_i < lower_value else 1
        if trend_value != prev_trend[-1]:
            upper_value, lower_value = basic_upper, basic_lower  # flip: restart the ratchet
    else:
        upper_value = min(basic_upper, prev_upper[-1])
        lower_value = max(basic_lower, prev_lower[-1])
        trend_value = 1 if close_i > upper_value else -1
        if trend_value != prev_trend[-1]:
            upper_value, lower_value = basic_upper, basic_lower  # flip: restart the ratchet
    return (
        np.append(prev_trend, trend_value),
        np.append(prev_upper, upper_value),
        np.append(prev_lower, lower_value),
        level_i,
    )


def _compute(frame: pd.DataFrame) -> tuple[np.ndarray | None, np.ndarray, np.ndarray]:
    """Cold-start walk of the trailing bands. None while the ATR window is still filling.

    The final bands ratchet against the trend — a downtrend's upper band only falls, an uptrend's
    lower band only rises — which is what makes a reversal cross a band frozen near the old extreme
    instead of chasing the price it is trying to catch.
    """
    level = atr(frame).to_numpy()
    high = frame["high"].to_numpy()
    low = frame["low"].to_numpy()
    close = frame["close"].to_numpy()
    basic_upper = (high + low) / 2 + MULTIPLE * level
    basic_lower = (high + low) / 2 - MULTIPLE * level
    n = len(frame)
    final_upper = np.full(n, np.nan)
    final_lower = np.full(n, np.nan)
    trend = np.zeros(n, dtype=int)
    started = False
    for i in range(n):
        if np.isnan(level[i]):
            continue
        if not started:
            final_upper[i], final_lower[i], trend[i] = basic_upper[i], basic_lower[i], 1
            started = True
            continue
        final_upper[i] = min(basic_upper[i], final_upper[i - 1])
        final_lower[i] = max(basic_lower[i], final_lower[i - 1])
        if trend[i - 1] == 1:
            trend[i] = -1 if close[i] < final_lower[i] else 1
        else:
            trend[i] = 1 if close[i] > final_upper[i] else -1
        if trend[i] != trend[i - 1]:
            # A flip restarts the ratchet from this bar's basic band: carrying the old trend's
            # frozen extreme across a flip re-triggers the flip on the very next bar (whipsaw).
            final_upper[i], final_lower[i] = basic_upper[i], basic_lower[i]
    if not started:
        return None, final_upper, final_lower, 0.0
    return trend, final_upper, final_lower, float(level[~np.isnan(level)][-1])
