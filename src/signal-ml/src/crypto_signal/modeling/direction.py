"""Choosing long, short, or neither, from one model and two forward passes.

The training set contains both sides of every candle: each barrier variant is emitted once as a long
and once as a short, with `direction_sign` as an ordinary feature and the label stated from the bet's
own point of view — `+1` means "the take-profit came first", whichever side of the entry it sat on. So
asking the model about a short is not a different model or a different label set; it is the same
feature row with the sign flipped.

That is the whole mechanism, and it is worth being clear about why the two obvious shortcuts are wrong.

**Reading one label set backwards.** Tempting: score the long, then call `1 - P(win)` the short's
probability. Every *unambiguous* outcome does mirror, but a tie does not. A candle whose high reaches
the take-profit and whose low reaches the stop-loss in the same bar is unknowable intrabar, so both
sides score it a loss — the adverse-wins rule, applied consistently. Mirroring would score it a short
*win*. On BTCUSDT 1h that is 7.7% of resolved rows at 0.5 ATR barriers, and the manufactured profit
lands entirely on the short side.

**Sign-flipping the features to train one canonical direction.** Also tempting, also wrong: RSI,
stochastic position, volatility and volume ratios have no meaningful mirror image, and crypto
drawdowns are genuinely faster than the rallies that precede them, so the two directions are not the
same problem viewed upside down.

Selection is then by expected value rather than by probability, because probability alone cannot
compare a 70%-likely 1:1 bet against a 40%-likely 3:1 bet. Both floors have to clear: an operator's
minimum confidence is a statement about how often they are willing to be wrong, and expected value is
a statement about what being right is worth.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd

from ..domain import BarrierPair, Direction
from ..domain.expectancy import OutcomeProbabilities, break_even_win_rate, expected_value
from ..labeling.triple_barrier import BARRIER_FEATURE_COLUMNS
from .estimator import aligned_probabilities

#: Both sides of one candle cannot win when the take-profit is at least as far as the stop-loss: to reach
#: `+tp` without touching `-sl` the price must pass `+sl` on the way, which is the short's stop. So the
#: two win probabilities are mutually exclusive and cannot sum past 1. When `tp < sl` they *can* both
#: happen — price clips a near take-profit in each direction before either far stop — so the check is
#: only applied where it is actually valid.
COHERENCE_TOLERANCE = 0.02


@dataclass(frozen=True, slots=True)
class DirectionCandidate:
    """One side of the bet, priced."""

    direction: Direction
    barriers: BarrierPair
    probabilities: OutcomeProbabilities
    expected_value_atr: float

    @property
    def confidence(self) -> float:
        """Calibrated probability that this bet reaches its take-profit before its stop-loss."""
        return self.probabilities.win

    @property
    def break_even(self) -> float:
        return break_even_win_rate(self.barriers, timeout_share=self.probabilities.timeout)

    @property
    def edge(self) -> float:
        """How far the win probability clears what the barrier geometry requires.

        Negative means the reward-to-risk on offer does not pay for how often this bet loses, whatever
        the raw confidence looks like.
        """
        return float(self.probabilities.win - self.break_even * self.probabilities.resolved)


@dataclass(frozen=True, slots=True)
class DirectionChoice:
    """The verdict, plus everything needed to explain it.

    `chosen` is None exactly when `direction` is FLAT. `candidates` always holds both sides, whether or
    not shorting was permitted, because a FLAT answer is only auditable if you can see what was
    declined.
    """

    direction: Direction
    chosen: DirectionCandidate | None
    candidates: tuple[DirectionCandidate, ...]
    rationale: tuple[str, ...]
    warning: str | None = None

    @property
    def confidence(self) -> float:
        return self.chosen.confidence if self.chosen is not None else 0.0

    @property
    def expected_value_atr(self) -> float:
        return self.chosen.expected_value_atr if self.chosen is not None else 0.0

    def candidate_for(self, direction: Direction) -> DirectionCandidate | None:
        for candidate in self.candidates:
            if candidate.direction is direction:
                return candidate
        return None


def barrier_variants(
    features: pd.DataFrame,
    barriers: BarrierPair,
    directions: Sequence[Direction] = (Direction.LONG, Direction.SHORT),
) -> pd.DataFrame:
    """One feature row in, one row per direction out — the input to the mirrored forward pass.

    The barrier columns are appended in `BARRIER_FEATURE_COLUMNS` order, the same order the labeller
    used, because a tree model addresses its inputs by position once it is fitted: hand it the same four
    numbers in a different order and it will answer confidently and wrongly.
    """
    if len(features) != 1:
        raise ValueError(f"expected exactly one feature row to price, got {len(features)}")
    for direction in directions:
        if not direction.is_open:
            raise ValueError("FLAT is the answer, never a candidate; price the directions you can take")

    rows = pd.concat([features] * len(directions), axis=0, ignore_index=True)
    rows["take_profit_atr"] = barriers.take_profit_atr
    rows["stop_loss_atr"] = barriers.stop_loss_atr
    rows["risk_reward_ratio"] = barriers.risk_reward_ratio
    rows["direction_sign"] = [float(direction.sign) for direction in directions]
    return rows


def _sequence_window(features: pd.DataFrame, barriers: BarrierPair, sign: int) -> pd.DataFrame:
    """The candle window a recurrent model scores for one direction.

    `features` is a window of scale-free candle rows (no bet columns); this appends the barrier distances
    and the requested `direction_sign` across every row, mirroring what `barrier_variants` does for a
    single row so the LSTM is conditioned on the same bet the tree is.
    """
    window = features.copy()
    window["take_profit_atr"] = float(barriers.take_profit_atr)
    window["stop_loss_atr"] = float(barriers.stop_loss_atr)
    window["risk_reward_ratio"] = float(barriers.risk_reward_ratio)
    window["direction_sign"] = float(sign)
    return window


def choose_direction(
    model,
    features: pd.DataFrame,
    barriers: BarrierPair,
    allow_short: bool = True,
    minimum_confidence: float = 0.0,
    minimum_expected_value_atr: float = 0.0,
    timeout_value_atr: float = 0.0,
    feature_columns: Sequence[str] | None = None,
) -> DirectionChoice:
    """Price both sides of a bet and answer with the better one, or with FLAT.

    A single `predict_proba` call covers both directions: the two rows differ only in `direction_sign`,
    so batching them also guarantees they are scored by the same model state — which matters when a
    registry can swap an artifact between calls.
    """
    if not 0.0 <= minimum_confidence <= 1.0:
        raise ValueError(f"minimum_confidence must be in [0, 1], got {minimum_confidence!r}")

    directions = (Direction.LONG, Direction.SHORT)

    if getattr(model, "is_sequence", False):
        # A recurrent model reads a window of candles; score the long and short bets by flipping the
        # `direction_sign` column across the whole window, exactly as the tree sees them.
        long_probs = np.asarray(model.predict_proba(_sequence_window(features, barriers, +1)), dtype=float)
        short_probs = np.asarray(model.predict_proba(_sequence_window(features, barriers, -1)), dtype=float)
        if long_probs.ndim == 1:
            long_probs = long_probs.reshape(1, -1)
            short_probs = short_probs.reshape(1, -1)
        probabilities = np.vstack([long_probs, short_probs])
    else:
        rows = barrier_variants(features, barriers, directions)
        if feature_columns is not None:
            missing = [column for column in feature_columns if column not in rows.columns]
            if missing:
                raise ValueError(f"feature row is missing {len(missing)} column(s) the model expects: {missing[:5]}")
            rows = rows[list(feature_columns)]

        probabilities = aligned_probabilities(model, rows)
    candidates = tuple(
        DirectionCandidate(
            direction=direction,
            barriers=barriers,
            probabilities=(outcome := OutcomeProbabilities.from_class_probabilities(probabilities[index])),
            expected_value_atr=expected_value(outcome, barriers, timeout_value_atr=timeout_value_atr),
        )
        for index, direction in enumerate(directions)
    )

    rationale: list[str] = [
        f"{candidate.direction.name.lower()}: confidence {candidate.confidence:.3f}, "
        f"expected value {candidate.expected_value_atr:+.3f} ATR, "
        f"break-even {candidate.break_even:.3f}, timeout mass {candidate.probabilities.timeout:.3f}"
        for candidate in candidates
    ]
    warning = _coherence_warning(candidates, barriers)
    if warning:
        rationale.append(warning)

    permitted = [
        candidate
        for candidate in candidates
        if allow_short or candidate.direction is not Direction.SHORT
    ]
    if not allow_short:
        rationale.append("short side priced but not permitted: allow_short is false")

    qualified = [
        candidate
        for candidate in permitted
        if candidate.confidence >= minimum_confidence
        and candidate.expected_value_atr >= minimum_expected_value_atr
    ]
    if not qualified:
        best = max(permitted, key=lambda candidate: candidate.expected_value_atr, default=None)
        if best is None:
            reason = "no direction was permitted"
        elif best.confidence < minimum_confidence:
            reason = (
                f"flat: best confidence {best.confidence:.3f} is below the {minimum_confidence:.3f} "
                "floor"
            )
        else:
            reason = (
                f"flat: best expected value {best.expected_value_atr:+.3f} ATR is below the "
                f"{minimum_expected_value_atr:+.3f} floor"
            )
        rationale.append(reason)
        return DirectionChoice(
            direction=Direction.FLAT,
            chosen=None,
            candidates=candidates,
            rationale=tuple(rationale),
            warning=warning,
        )

    # Expected value decides, and a tie goes to the higher confidence — a coin-flip between two equally
    # priced bets should land on the one the model is surer about, not on whichever came first in a list.
    chosen = max(qualified, key=lambda candidate: (candidate.expected_value_atr, candidate.confidence))
    rationale.append(
        f"chose {chosen.direction.name.lower()} on expected value {chosen.expected_value_atr:+.3f} ATR"
    )
    return DirectionChoice(
        direction=chosen.direction,
        chosen=chosen,
        candidates=candidates,
        rationale=tuple(rationale),
        warning=warning,
    )


def _coherence_warning(
    candidates: Sequence[DirectionCandidate],
    barriers: BarrierPair,
) -> str | None:
    """Flag a model that claims both sides of the same candle can win.

    Only checkable when the take-profit is at least as far out as the stop-loss, where the two wins are
    genuinely mutually exclusive. A violation is not a bug in this module — it is the model telling you
    its probabilities are not internally consistent, which is worth surfacing on the response rather
    than hiding behind a plausible-looking confidence.
    """
    if barriers.take_profit_atr < barriers.stop_loss_atr:
        return None
    total = sum(candidate.probabilities.win for candidate in candidates)
    if total <= 1.0 + COHERENCE_TOLERANCE:
        return None
    return (
        f"model incoherence: long and short win probabilities sum to {total:.3f}, but with a "
        f"take-profit at {barriers.take_profit_atr:.2f} ATR and a stop at {barriers.stop_loss_atr:.2f} "
        "ATR only one side can win; treat this confidence as unreliable"
    )
