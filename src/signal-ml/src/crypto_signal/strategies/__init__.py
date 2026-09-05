"""Strategy Zoo: named indicator strategies with one contract.

A strategy sees a feature-rich OHLCV frame (plus `atr`) and returns a Signal or None.
No I/O, no state — the same function backtests and serves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

__all__ = ["Signal", "Strategy", "STRATEGIES", "register"]


@dataclass(frozen=True, slots=True)
class Signal:
    """One strategy decision on one candle: a side, where it fired, and why."""

    direction: str  # "LONG" | "SHORT"
    entry_index: int
    reason: str


Strategy = Callable[[pd.DataFrame], "Signal | None"]

#: The registry every `@register` writes into. Keys are stable strategy keys — the league ranks
#: them, the scanner asks for them by name, and bots store them in `StrategyKey`.
STRATEGIES: dict[str, Strategy] = {}


def register(name: str):
    """Register a strategy under `name` and return the function unchanged."""

    def deco(fn: Strategy) -> Strategy:
        if name in STRATEGIES:
            raise ValueError(f"Strategy already registered: {name!r}")
        STRATEGIES[name] = fn
        return fn

    return deco


# Importing the package populates the registry: each module's `@register` runs at import time.
# One entry per strategy file, so a missing import is a missing strategy, visibly.
from . import (  # noqa: E402,F401  (imports are the registration mechanism)
    bollinger,
    donchian,
    ema_cross,
    keltner_breakout,
    macd,
    rsi,
    rsi_pullback,
    supertrend,
    triple_ema,
)
