"""What a bracket bet is worth, in ATR units, given the probability of each way it can end.

A bracket trade has exactly three endings, and a number that claims to be its expected value has to
account for all three. Two of them are easy — take-profit first pays `take_profit_atr`, stop-loss
first costs `stop_loss_atr`. The third is the one that gets dropped, and dropping it is not a small
approximation: it is the difference between a signal that looks profitable and one that is.

**Why the timeout branch cannot be renormalised away.** The tempting shortcut is to condition on
resolution — divide `P(win)` by `P(win) + P(loss)` and forget the rest. Measured on BTCUSDT 1h that
shortcut reports **+0.0814 ATR per trade for longs and +0.0670 for shorts at the same time**, on the
same price series, which no market permits. The mechanism is selection: a path that fails to touch
either barrier inside the horizon is disproportionately one drifting slowly toward the *far* barrier,
so discarding it flatters whichever barrier is nearer. Keeping the branch with its own probability
mass — even at a value of zero — shrinks the estimate toward zero by exactly the mass that has not
resolved, and the same measurement comes back +0.0383 long against −0.0440 short: mirrored around the
market's real drift, which is what an unbiased estimator looks like.

**Why the default value of a timeout is zero.** A timed-out trade exits at the horizon close, so its
true worth is that close minus the entry — pure accumulated drift. On the training history that
averages +0.0431 ATR, and crediting it to every signal would hand a permanent bonus to the long side
of a market that happened to rise over the sample. Drift is the one thing in this system that does
not generalise: it is a property of 2020-2026 Bitcoin, not of the features. So the engine values a
timeout at zero — "you leave roughly where you entered" — and the measured figure travels in the
report as a diagnostic rather than in the expected value as an assumption. `timeout_value_atr` is
still a parameter, because a backtest walking real candles *observes* the horizon close instead of
guessing at it, and should use what it sees.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .barriers import BarrierPair

#: Probabilities are model output, so they arrive with float error. This is the slack allowed on the
#: "they sum to one" check — wide enough for accumulated rounding, far too narrow to hide a renormalised
#: two-class distribution masquerading as three.
PROBABILITY_TOLERANCE = 1e-6


@dataclass(frozen=True, slots=True)
class OutcomeProbabilities:
    """How a bet ends, from the point of view of the bet.

    Direction-relative throughout, matching the labeller: `win` is "the take-profit was touched first",
    whether the take-profit sits above the entry (a long) or below it (a short). That is what lets one
    model answer for both sides.
    """

    win: float
    loss: float
    timeout: float

    def __post_init__(self) -> None:
        for name, value in (("win", self.win), ("loss", self.loss), ("timeout", self.timeout)):
            if not np.isfinite(value) or value < 0.0 or value > 1.0:
                raise ValueError(f"{name} must be a probability in [0, 1], got {value!r}")
        total = self.win + self.loss + self.timeout
        if abs(total - 1.0) > PROBABILITY_TOLERANCE:
            raise ValueError(
                f"win + loss + timeout must be 1, got {total!r}. A distribution over two outcomes "
                "means the timeout branch was renormalised away, which biases every expected value "
                "toward the nearer barrier."
            )

    @property
    def resolved(self) -> float:
        """The mass that touches a barrier inside the horizon."""
        return self.win + self.loss

    @classmethod
    def from_class_probabilities(cls, probabilities: np.ndarray | tuple[float, float, float]) -> OutcomeProbabilities:
        """Read a row of `[P(-1), P(0), P(+1)]` — the class order the estimator is trained on."""
        row = np.asarray(probabilities, dtype=np.float64).ravel()
        if row.shape != (3,):
            raise ValueError(f"expected three class probabilities in order (-1, 0, +1), got {row.shape}")
        return cls(win=float(row[2]), loss=float(row[0]), timeout=float(row[1]))


def expected_value(
    probabilities: OutcomeProbabilities,
    barriers: BarrierPair,
    timeout_value_atr: float = 0.0,
) -> float:
    """Expected profit of one bet in ATR units, before costs.

    ATR units rather than currency because that is the only form comparable across symbols: 1.5 ATR
    means the same size of move on Bitcoin and on a coin that swings ten times as hard. The caller
    converts to a percentage or to money once it knows the entry price.

    Costs are deliberately absent. Fees and slippage belong to whoever is placing the order and knows
    its venue, and folding a guess at them into the model's output would make the number impossible to
    audit against the venue's own fee schedule.
    """
    if not np.isfinite(timeout_value_atr):
        raise ValueError(f"timeout_value_atr must be finite, got {timeout_value_atr!r}")
    return float(
        probabilities.win * barriers.take_profit_atr
        - probabilities.loss * barriers.stop_loss_atr
        + probabilities.timeout * timeout_value_atr
    )


def break_even_win_rate(barriers: BarrierPair, timeout_share: float = 0.0, timeout_value_atr: float = 0.0) -> float:
    """The win rate among resolved trades at which the bet stops losing money.

    Reads as a sanity check on any confidence the engine reports: a 3:1 reward-to-risk bet needs to be
    right only a quarter of the time, so a model claiming 60% on one is claiming something remarkable
    and should be disbelieved before it is traded.
    """
    if not 0.0 <= timeout_share <= 1.0:
        raise ValueError(f"timeout_share must be in [0, 1], got {timeout_share!r}")
    resolved = 1.0 - timeout_share
    if resolved <= 0.0:
        raise ValueError("Every path times out, so no win rate makes this bet break even")
    span = barriers.take_profit_atr + barriers.stop_loss_atr
    carried = timeout_share * timeout_value_atr
    return float((barriers.stop_loss_atr * resolved - carried) / (span * resolved))
