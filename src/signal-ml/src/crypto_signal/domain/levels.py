"""Turning a requested bet into prices and into the units the model was trained on.

The caller asks in percentages, because that is how a trader thinks about a target: "2% up, 1% down".
The model was trained in ATR multiples, because that is the only form in which a barrier means the same
thing on two different markets. This module is the translation, and it goes in both directions — the
labeller converts a grid of ATR multiples into prices to walk the candles against, and the servicer
converts a requested percentage into the multiples that go into the feature row.

Both conversions use the ATR of the decision candle, never a later one.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .barriers import BarrierPair
from .direction import Direction

_PERCENT = 100.0


def atr_multiple(entry_price: float, percent: float, atr: float) -> float:
    """How many ATRs away a barrier `percent` from the entry sits."""
    if atr <= 0 or not np.isfinite(atr):
        raise ValueError(f"atr must be finite and > 0 to express a barrier in ATR units, got {atr!r}")
    return float(entry_price * (percent / _PERCENT) / atr)


def percent_from_atr(entry_price: float, multiple: float, atr: float) -> float:
    """The inverse: what percentage of the entry price an ATR multiple works out to."""
    if entry_price <= 0 or not np.isfinite(entry_price):
        raise ValueError(f"entry_price must be finite and > 0, got {entry_price!r}")
    return float(multiple * atr / entry_price * _PERCENT)


def barrier_prices(
    direction: Direction,
    entry_price: float | np.ndarray,
    take_profit_percent: float | np.ndarray,
    stop_loss_percent: float | np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Absolute take-profit and stop-loss prices for a bet, vectorised over rows.

    A long profits above the entry and stops below it; a short is the mirror. Returns
    ``(take_profit_price, stop_loss_price)`` — always in that order, whatever the direction, so callers
    never have to remember which of "upper" and "lower" is the win.
    """
    entry = np.asarray(entry_price, dtype=np.float64)
    take_profit = np.asarray(take_profit_percent, dtype=np.float64) / _PERCENT
    stop_loss = np.asarray(stop_loss_percent, dtype=np.float64) / _PERCENT

    if direction is Direction.LONG:
        return entry * (1.0 + take_profit), entry * (1.0 - stop_loss)
    if direction is Direction.SHORT:
        return entry * (1.0 - take_profit), entry * (1.0 + stop_loss)
    raise ValueError("FLAT has no barriers; ask for the direction you are considering")


def barrier_prices_from_atr(
    direction: Direction,
    entry_price: float | np.ndarray,
    take_profit_atr: float | np.ndarray,
    stop_loss_atr: float | np.ndarray,
    atr: float | np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Absolute barrier prices straight from ATR multiples — the labeller's path.

    Equivalent to converting the multiples to percentages and calling `barrier_prices`, but without the
    round trip: a distance of *k* ATRs is *k x atr* in price units, full stop. Skipping the detour keeps
    the prices the labeller walks candles against free of a division and a multiplication back, which
    matters only because a barrier sitting a float-epsilon above a candle's high is the difference
    between a win and a timeout.

    Returns ``(take_profit_price, stop_loss_price)``, in that order for either direction.
    """
    entry = np.asarray(entry_price, dtype=np.float64)
    take_profit_distance = np.asarray(take_profit_atr, dtype=np.float64) * np.asarray(atr, dtype=np.float64)
    stop_loss_distance = np.asarray(stop_loss_atr, dtype=np.float64) * np.asarray(atr, dtype=np.float64)

    if direction is Direction.LONG:
        return entry + take_profit_distance, entry - stop_loss_distance
    if direction is Direction.SHORT:
        return entry - take_profit_distance, entry + stop_loss_distance
    raise ValueError("FLAT has no barriers; ask for the direction you are considering")


@dataclass(frozen=True, slots=True)
class TradeLevels:
    """The prices a bet resolves to, plus the units the model saw it in.

    `entry_price` is the last closed candle's close. The orchestrator fills at the next candle's open;
    the difference between the two is slippage and belongs to the orchestrator's cost model, not here.
    """

    direction: Direction
    entry_price: float
    take_profit_price: float
    stop_loss_price: float
    atr: float
    barriers: BarrierPair

    @property
    def take_profit_atr(self) -> float:
        return self.barriers.take_profit_atr

    @property
    def stop_loss_atr(self) -> float:
        return self.barriers.stop_loss_atr

    @property
    def risk_reward_ratio(self) -> float:
        """Reward over risk, from the requested distances alone — no probability in it.

        Taken from the ATR multiples rather than the percentages, which is the same ratio, because the
        multiples are what the model was asked about.
        """
        return self.barriers.risk_reward_ratio


def levels_for(
    direction: Direction,
    entry_price: float,
    take_profit_percent: float,
    stop_loss_percent: float,
    atr: float,
) -> TradeLevels:
    """Resolve a requested percentage bet into prices and ATR multiples.

    Rejects a short whose take-profit would be at or below zero. A 100% profit target on a short is a
    price of zero, which no market reaches, and beyond that the barrier is negative — arithmetic that
    produces a level no candle can ever touch, so every such trade would time out and the model would
    learn a bet nobody can place.
    """
    if entry_price <= 0 or not np.isfinite(entry_price):
        raise ValueError(f"entry_price must be finite and > 0, got {entry_price!r}")
    if take_profit_percent <= 0 or not np.isfinite(take_profit_percent):
        raise ValueError(f"take_profit_percent must be finite and > 0, got {take_profit_percent!r}")
    if stop_loss_percent <= 0 or not np.isfinite(stop_loss_percent):
        raise ValueError(f"stop_loss_percent must be finite and > 0, got {stop_loss_percent!r}")
    if stop_loss_percent >= _PERCENT and direction is Direction.LONG:
        raise ValueError("A long cannot stop out at or below a price of zero; stop_loss_percent < 100")
    if take_profit_percent >= _PERCENT and direction is Direction.SHORT:
        raise ValueError("A short cannot take profit at or below a price of zero; take_profit_percent < 100")

    take_profit_price, stop_loss_price = barrier_prices(
        direction, entry_price, take_profit_percent, stop_loss_percent
    )

    return TradeLevels(
        direction=direction,
        entry_price=float(entry_price),
        take_profit_price=float(take_profit_price),
        stop_loss_price=float(stop_loss_price),
        atr=float(atr),
        barriers=BarrierPair(
            take_profit_atr=atr_multiple(entry_price, take_profit_percent, atr),
            stop_loss_atr=atr_multiple(entry_price, stop_loss_percent, atr),
        ),
    )
