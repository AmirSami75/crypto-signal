"""First-touch barrier resolution — the one definition of "which barrier came first".

A triple-barrier trade has three ways to end: the take-profit is reached, the stop-loss is reached, or
neither happens inside the holding horizon. Everything downstream (the labels the model learns, the
trades the backtest reports, the reason code the bot advisor returns) depends on resolving that
question the same way every time, so it is resolved here and nowhere else.

Two rules, and they are the whole point of this module:

**Adverse barrier wins a tie.** Candles are OHLC summaries, not paths. When one candle's high reaches
the take-profit *and* its low reaches the stop-loss, the order in which they were touched is not
recoverable from the data, so this module assumes the loss. Resolving such candles optimistically is
the single easiest way to make a backtest report profit that the market never offered, and because the
same rule is applied while labelling, the model is not taught an edge that only exists in the tie.

**Barriers come from information available at the decision candle.** This module never looks at a
future ATR, and it starts scanning at the candle *after* the one the decision was made on. Callers
compute barrier prices from the decision candle's own close and ATR; passing in a barrier derived from
later data would leak, and nothing here can detect that for you.

Right-edge honesty: a row whose forward window runs off the end of the data cannot be called a
timeout, because a barrier might sit one candle past the last one we have. Those rows come back
``resolved=False`` and belong nowhere near a training set.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from .direction import Direction

ADVERSE_WINS_TIE_BREAK = (
    "triple-barrier first-touch, adverse barrier wins an ambiguous candle"
)


class Outcome(IntEnum):
    """How a barrier trade ended. Also the class labels the classifier is trained on."""

    STOP_LOSS_FIRST = -1
    TIMEOUT = 0
    TAKE_PROFIT_FIRST = 1


# Fixed class order for `predict_proba` columns. Written out rather than derived from `Outcome` so the
# order can never drift with an enum edit: a reordering here silently reassigns every probability.
OUTCOME_CLASSES: tuple[int, int, int] = (-1, 0, 1)


@dataclass(frozen=True, slots=True)
class BarrierPair:
    """Barrier distances in ATR multiples — the form the model consumes.

    Percent distances are not comparable across markets: 2% is a long reach on BTC and a quiet
    afternoon on a coin that moves 12% a day. ATR multiples are, which is why the model is trained and
    queried in these units and the percentages stay at the edges of the system.
    """

    take_profit_atr: float
    stop_loss_atr: float

    def __post_init__(self) -> None:
        if not np.isfinite(self.take_profit_atr) or self.take_profit_atr <= 0:
            raise ValueError(f"take_profit_atr must be finite and > 0, got {self.take_profit_atr!r}")
        if not np.isfinite(self.stop_loss_atr) or self.stop_loss_atr <= 0:
            raise ValueError(f"stop_loss_atr must be finite and > 0, got {self.stop_loss_atr!r}")

    @property
    def risk_reward_ratio(self) -> float:
        return self.take_profit_atr / self.stop_loss_atr

    def mirrored(self) -> BarrierPair:
        """The same price levels read from the other side of the trade.

        A long risking 1 ATR to make 2 and a short risking 2 ATR to make 1 are watching the same two
        prices; only which one is the win differs.
        """
        return BarrierPair(take_profit_atr=self.stop_loss_atr, stop_loss_atr=self.take_profit_atr)

    def as_features(self) -> dict[str, float]:
        return {
            "take_profit_atr": float(self.take_profit_atr),
            "stop_loss_atr": float(self.stop_loss_atr),
        }


@dataclass(frozen=True, slots=True)
class TouchResult:
    """One resolved trade."""

    outcome: Outcome
    resolved: bool
    bars_held: int
    exit_price: float

    #: The resolving candle reached both barriers, so `outcome` reflects the tie-break rather than an
    #: observed sequence. Counted and reported, never silently folded in.
    ambiguous: bool


def _barrier_tests(
    direction: Direction,
    highs: np.ndarray,
    lows: np.ndarray,
    take_profit_price: np.ndarray | float,
    stop_loss_price: np.ndarray | float,
) -> tuple[np.ndarray, np.ndarray]:
    """Which candles reached the take-profit, and which reached the stop-loss.

    A long's take-profit sits above the entry and is reached by a high; its stop sits below and is
    reached by a low. A short is the mirror image. Both barriers are treated as touched on ``>=`` /
    ``<=`` — a resting order at exactly the barrier price fills.
    """
    if direction is Direction.LONG:
        return highs >= take_profit_price, lows <= stop_loss_price
    if direction is Direction.SHORT:
        return lows <= take_profit_price, highs >= stop_loss_price
    raise ValueError("A barrier trade needs a direction; FLAT has no barriers to touch")


def _resolve(first_take_profit: np.ndarray, first_stop_loss: np.ndarray, horizon: int) -> np.ndarray:
    """Turn two first-hit offsets into outcomes, adverse barrier winning any tie.

    `horizon` stands for "never touched inside the window", which is why the stop-loss branch still has
    to check it: ``first_stop_loss <= first_take_profit`` is also true when neither barrier was reached.
    """
    stop_loss_not_later = first_stop_loss <= first_take_profit
    return np.where(
        stop_loss_not_later,
        np.where(first_stop_loss < horizon, Outcome.STOP_LOSS_FIRST, Outcome.TIMEOUT),
        Outcome.TAKE_PROFIT_FIRST,
    ).astype(np.int8)


def resolve_first_touch(
    high: np.ndarray,
    low: np.ndarray,
    take_profit_price: np.ndarray,
    stop_loss_price: np.ndarray,
    direction: Direction,
    max_horizon: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Resolve every row at once. This is the labeller's path.

    Row *i* is a decision taken on candle *i*, so the scan covers candles ``i+1 .. i+max_horizon``:
    a decision cannot be filled or stopped by the candle it was made on.

    Returns ``(outcome, resolved, bars_held, ambiguous)``, each of length ``len(high)``. Rows whose
    forward window would run past the end of the data are ``resolved=False`` with ``outcome`` left at
    TIMEOUT and ``bars_held`` at 0 — see the module docstring on right-edge honesty.

    No exit price: a label only needs to know which barrier won. Fills are the backtester's business,
    because only it models gaps and slippage — see `first_touch`.
    """
    if max_horizon < 1:
        raise ValueError(f"max_horizon must be at least 1 candle, got {max_horizon!r}")

    high = np.ascontiguousarray(high, dtype=np.float64)
    low = np.ascontiguousarray(low, dtype=np.float64)
    take_profit_price = np.asarray(take_profit_price, dtype=np.float64)
    stop_loss_price = np.asarray(stop_loss_price, dtype=np.float64)

    total = high.shape[0]
    if not (low.shape[0] == take_profit_price.shape[0] == stop_loss_price.shape[0] == total):
        raise ValueError("high, low and both barrier arrays must be the same length")

    outcome = np.full(total, Outcome.TIMEOUT, dtype=np.int8)
    resolved = np.zeros(total, dtype=bool)
    bars_held = np.zeros(total, dtype=np.int32)
    ambiguous = np.zeros(total, dtype=bool)

    # `sliding_window_view` row j is `high[j : j + horizon]`; dropping row 0 shifts it to the window
    # that starts one candle after the decision. It is a view, so this costs no memory.
    if total <= max_horizon:
        return outcome, resolved, bars_held, ambiguous

    windows_high = sliding_window_view(high, max_horizon)[1:]
    windows_low = sliding_window_view(low, max_horizon)[1:]
    usable = windows_high.shape[0]

    reached_take_profit, reached_stop_loss = _barrier_tests(
        direction,
        windows_high,
        windows_low,
        take_profit_price[:usable, None],
        stop_loss_price[:usable, None],
    )

    # argmax on a boolean row gives the first True; where there is none it gives 0, so the `any` guard
    # rewrites those to `max_horizon`, the sentinel for "never".
    first_take_profit = np.where(
        reached_take_profit.any(axis=1), reached_take_profit.argmax(axis=1), max_horizon
    )
    first_stop_loss = np.where(
        reached_stop_loss.any(axis=1), reached_stop_loss.argmax(axis=1), max_horizon
    )

    outcome[:usable] = _resolve(first_take_profit, first_stop_loss, max_horizon)
    resolved[:usable] = True

    touched = np.minimum(first_take_profit, first_stop_loss)
    # +1 because offset 0 within the window is the candle after the decision, i.e. one bar held.
    bars_held[:usable] = np.where(touched < max_horizon, touched + 1, max_horizon)
    ambiguous[:usable] = (first_take_profit == first_stop_loss) & (first_take_profit < max_horizon)

    return outcome, resolved, bars_held, ambiguous


def first_touch(
    high: np.ndarray,
    low: np.ndarray,
    open_: np.ndarray,
    entry_index: int,
    take_profit_price: float,
    stop_loss_price: float,
    direction: Direction,
    max_horizon: int,
) -> TouchResult:
    """Resolve a single position, with the fill price. This is the backtester's path.

    ``entry_index`` is the candle the position is *held from* — the bar the orchestrator fills on, not
    the bar the decision was computed on. Scanning therefore includes ``entry_index`` itself: a bracket
    working at the venue can be filled by the very candle you entered on.

    Fills are pessimistic in the way real ones are. A take-profit is a resting limit order, so it fills
    at its own price and no better. A stop-loss is a market order once triggered, so a candle that
    *opened* through the stop fills at that open — the gap is charged to the trade, which is where it
    lands in reality.
    """
    if max_horizon < 1:
        raise ValueError(f"max_horizon must be at least 1 candle, got {max_horizon!r}")
    if entry_index < 0:
        raise ValueError(f"entry_index must be non-negative, got {entry_index!r}")

    total = len(high)
    stop = min(entry_index + max_horizon, total)
    if entry_index >= total:
        return TouchResult(Outcome.TIMEOUT, resolved=False, bars_held=0, exit_price=float("nan"),
                           ambiguous=False)

    window = slice(entry_index, stop)
    reached_take_profit, reached_stop_loss = _barrier_tests(
        direction,
        np.asarray(high[window], dtype=np.float64),
        np.asarray(low[window], dtype=np.float64),
        take_profit_price,
        stop_loss_price,
    )

    length = stop - entry_index
    first_take_profit = int(reached_take_profit.argmax()) if reached_take_profit.any() else length
    first_stop_loss = int(reached_stop_loss.argmax()) if reached_stop_loss.any() else length
    outcome = Outcome(int(_resolve(np.array([first_take_profit]), np.array([first_stop_loss]), length)[0]))

    # A window cut short by the end of the data proves nothing about the timeout it looks like.
    resolved = outcome is not Outcome.TIMEOUT or length == max_horizon
    ambiguous = first_take_profit == first_stop_loss < length

    if outcome is Outcome.TAKE_PROFIT_FIRST:
        exit_index = entry_index + first_take_profit
        exit_price = take_profit_price
    elif outcome is Outcome.STOP_LOSS_FIRST:
        exit_index = entry_index + first_stop_loss
        gapped_open = float(open_[exit_index])
        through_the_stop = (
            gapped_open < stop_loss_price if direction is Direction.LONG else gapped_open > stop_loss_price
        )
        exit_price = gapped_open if through_the_stop else stop_loss_price
    else:
        exit_index = stop - 1
        exit_price = float("nan")

    return TouchResult(
        outcome=outcome,
        resolved=resolved,
        bars_held=exit_index - entry_index + 1,
        exit_price=float(exit_price),
        ambiguous=bool(ambiguous),
    )


def resolve_first_touch_scalar(
    high: np.ndarray,
    low: np.ndarray,
    take_profit_price: np.ndarray,
    stop_loss_price: np.ndarray,
    direction: Direction,
    max_horizon: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """A plain loop with the same contract as `resolve_first_touch`.

    Kept because the vectorised version is index arithmetic over a strided view, which is fast and easy
    to get subtly wrong. The tests assert the two agree candle for candle; if they ever diverge, this
    one is the specification.
    """
    total = len(high)
    outcome = np.full(total, Outcome.TIMEOUT, dtype=np.int8)
    resolved = np.zeros(total, dtype=bool)
    bars_held = np.zeros(total, dtype=np.int32)
    ambiguous = np.zeros(total, dtype=bool)

    for index in range(total):
        last = index + max_horizon
        if last >= total:
            break

        resolved[index] = True
        bars_held[index] = max_horizon
        for offset in range(1, max_horizon + 1):
            candle = index + offset
            hit_take_profit, hit_stop_loss = _barrier_tests(
                direction,
                np.float64(high[candle]),
                np.float64(low[candle]),
                take_profit_price[index],
                stop_loss_price[index],
            )
            if not (hit_take_profit or hit_stop_loss):
                continue
            bars_held[index] = offset
            ambiguous[index] = bool(hit_take_profit and hit_stop_loss)
            outcome[index] = (
                Outcome.STOP_LOSS_FIRST if hit_stop_loss else Outcome.TAKE_PROFIT_FIRST
            )
            break

    return outcome, resolved, bars_held, ambiguous
