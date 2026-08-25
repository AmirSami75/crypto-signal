"""The one rule that exists twice: which side to bet, given both sides' probabilities.

`modeling.direction.choose_direction` decides for a single live candle. `_decide_window` in the training
pipeline decides for a whole holdout at once, as vectorised numpy, because the holdout is tens of
thousands of candles and a per-candle `predict_proba` would dominate the training run. Two
implementations of one rule is a deliberate trade, and `_decide_window`'s own docstring names this test
as what keeps them from drifting.

Drift here is not a crash. It is a backtest that grades a strategy the engine will not run: every
reported number stays internally consistent while describing different trades than production takes,
and the discrepancy surfaces only as live results that do not match the report — the failure mode with
no error message and the longest feedback loop in the system.

The model is a stub returning a fixed probability table, so both paths receive *identical*
probabilities by construction. Anything the two then disagree about is the selection rule itself, which
is the only thing under test. A fitted estimator would make this a test of the estimator.
"""

from __future__ import annotations

from types import SimpleNamespace
import unittest

import numpy as np
import pandas as pd

from crypto_signal.domain import BarrierPair, Direction
from crypto_signal.features import build_features
from crypto_signal.labeling.triple_barrier import BARRIER_FEATURE_COLUMNS
from crypto_signal.modeling.direction import choose_direction
from crypto_signal.training.barrier_pipeline import _decide_window

#: `(long win, short win)` per holdout candle, chosen to hit every branch of the rule: each side
#: comfortably clearing alone, neither clearing, both clearing with a decided winner, and both clearing
#: on an exactly equal expected value so the confidence tie-break is what answers. `timeout` takes a
#: fixed slice of the remainder, so a win probability is not also a statement about the timeout mass.
LADDER: tuple[tuple[float, float], ...] = (
    (0.70, 0.10),  # long, comfortably
    (0.10, 0.70),  # short, comfortably
    (0.20, 0.20),  # neither side clears the floor
    (0.60, 0.60),  # both clear on an identical expected value -> the tie-break decides
    (0.55, 0.60),  # both clear, short is worth more
    (0.60, 0.55),  # both clear, long is worth more
    (0.49, 0.51),  # straddling the floor, from either side
    (0.51, 0.49),
)
FLOOR = 0.50
PAIR = BarrierPair(take_profit_atr=2.0, stop_loss_atr=1.0)
TIMEOUT = 0.05


class _TableModel:
    """A model whose answer depends only on a row's `direction_sign` and its place in the batch.

    `classes_` is deliberately not in ascending order. `aligned_probabilities` reorders columns by class
    label and both paths go through it, so a stub that happened to be pre-sorted would let a column
    mix-up pass unnoticed in both at once — which is precisely the agreement this file is asserting.

    The index arithmetic covers both call shapes without a special case. `_score_side` scores one side
    for the whole window, so its `position` *is* the candle index; `choose_direction` scores two rows of
    one candle, and the per-candle caller hands over a one-rung table, so both rows read rung zero.
    """

    classes_ = np.array([1, -1, 0])

    def __init__(self, table: tuple[tuple[float, float], ...]) -> None:
        self.table = table

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        signs = np.asarray(X["direction_sign"], dtype=float)
        rows = np.zeros((len(X), 3), dtype=float)
        for position, sign in enumerate(signs):
            win = self.table[position % len(self.table)][0 if sign > 0 else 1]
            rows[position] = (win, 1.0 - win - TIMEOUT, TIMEOUT)  # column order matches `classes_`
        return rows


def raw_candles(count: int) -> pd.DataFrame:
    """A price path with enough history for the feature warm-up, and a settled true range.

    The triangle keeps every candle's own high-low range wider than the gap between consecutive closes,
    so ATR converges on that range. A sawtooth would not — its wrap is a gap larger than one candle —
    and the barrier percentages derived from ATR would then be numbers nobody can check by hand.
    """
    closes = 10_000.0 + 20.0 * np.array([2 - abs(4 - index % 8) for index in range(count)], dtype=float)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=count, freq="1h", tz="UTC"),
            "open": closes,
            "high": closes + 50.0,
            "low": closes - 50.0,
            "close": closes,
            "volume": np.full(count, 100.0),
        }
    )


class DirectionAgreementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = raw_candles(240)
        cls.features = build_features(cls.raw, atr_window=14)
        #: What a fitted model's descriptor carries: the base features plus the four barrier columns, in
        #: the order the labeller wrote them. Both paths select by this list.
        cls.feature_columns = tuple(cls.features.columns) + tuple(BARRIER_FEATURE_COLUMNS)
        cls.offset = len(cls.raw) - len(LADDER)
        cls.window = pd.DataFrame({"timestamp": cls.raw["timestamp"].tail(len(LADDER)).to_numpy()})

    def vectorised(self, allow_short: bool) -> pd.DataFrame:
        config = SimpleNamespace(
            barrier=SimpleNamespace(
                atr_window=14,
                backtest_minimum_confidence=FLOOR,
                allow_short=allow_short,
            )
        )
        # Only `feature_columns` is read off the dataset on this path; a real `BarrierDataset` would also
        # carry the augmented training frame, which a decision has no use for.
        dataset = SimpleNamespace(feature_columns=self.feature_columns)
        return _decide_window(
            model=_TableModel(LADDER),
            raw=self.raw,
            window=self.window,
            pair=PAIR,
            dataset=dataset,
            config=config,
        )

    def per_candle(self, allow_short: bool) -> list[Direction]:
        answers = []
        for index, rung in enumerate(LADDER):
            answers.append(
                choose_direction(
                    _TableModel((rung,)),
                    self.features.frame.iloc[[self.offset + index]],
                    PAIR,
                    allow_short=allow_short,
                    minimum_confidence=FLOOR,
                    feature_columns=self.feature_columns,
                ).direction
            )
        return answers

    def test_direction_selection_matches_the_vectorised_backtest(self) -> None:
        for allow_short in (True, False):
            with self.subTest(allow_short=allow_short):
                vectorised = self.vectorised(allow_short)
                self.assertEqual(len(vectorised), len(LADDER))
                self.assertEqual(
                    list(vectorised["direction"].astype(int)),
                    [int(direction) for direction in self.per_candle(allow_short)],
                )

    def test_a_configuration_that_forbids_shorting_never_answers_short(self) -> None:
        """The backtest must grade the strategy the bot is allowed to run. Scoring short trades a
        spot-only bot cannot place is how a report promises an edge the venue will not let you take."""
        vectorised = self.vectorised(allow_short=False)
        self.assertNotIn(int(Direction.SHORT), set(vectorised["direction"].astype(int)))
        # And the two comfortable rungs still resolve the way the ladder intends, so this is not passing
        # because the whole window came back FLAT.
        self.assertEqual(int(vectorised["direction"].iloc[0]), int(Direction.LONG))
        self.assertEqual(int(vectorised["direction"].iloc[1]), 0)

    def test_a_bet_below_the_confidence_floor_is_flat_in_both(self) -> None:
        directions = list(self.vectorised(allow_short=True)["direction"].astype(int))
        # Rung 2 is (0.20, 0.20): neither side clears 0.50, so neither path may take a position.
        self.assertEqual(directions[2], 0)
        self.assertEqual(self.per_candle(allow_short=True)[2], Direction.FLAT)

    def test_an_exact_tie_on_expected_value_goes_to_confidence_in_both(self) -> None:
        """Rung 3 prices the two sides identically. The rule breaks that tie on confidence, which is also
        equal — so the documented `>=` in the long's favour is what decides, in both implementations."""
        self.assertEqual(int(self.vectorised(allow_short=True)["direction"].iloc[3]), int(Direction.LONG))
        self.assertEqual(self.per_candle(allow_short=True)[3], Direction.LONG)

    def test_the_barrier_percentages_are_the_same_distance_both_paths_priced(self) -> None:
        """The selection rule agreeing is not sufficient: the two must also be asking for the same bet.
        Both derive the percentages from `(atr multiple, atr, entry)`, unswapped for a short — the mirror
        lives in `direction_sign` and in where `levels_for` puts the prices, not in the pair."""
        vectorised = self.vectorised(allow_short=True)
        atr = vectorised["atr"].to_numpy()
        entry = vectorised["close"].to_numpy()
        np.testing.assert_allclose(
            vectorised["take_profit_percent"].to_numpy(),
            PAIR.take_profit_atr * atr / entry * 100.0,
            rtol=1e-9,
        )
        np.testing.assert_allclose(
            vectorised["stop_loss_percent"].to_numpy(),
            PAIR.stop_loss_atr * atr / entry * 100.0,
            rtol=1e-9,
        )


class ExpectedValueFloorTests(unittest.TestCase):
    """The floor that only bites on a bracket the shipped config does not use — which is why it drifted.

    `choose_direction` clears two floors: confidence, and expected value against a default of zero. The
    vectorised path checked only the first. At the shipped 1.5/1.0 bracket the gap is invisible, because
    any confidence at or above 0.5 is already worth +0.25 ATR or better, so the two rules agree on every
    row of every training run to date. Widen the bracket the other way — a 1.0 take-profit against a 2.0
    stop, which the config permits and a cautious operator might reasonably ask for — and a 0.55
    confidence is worth **-0.25 ATR**: a bet the engine answers FLAT to and the backtest was taking.

    A backtest that grades trades the engine refuses is worse than one that is merely wrong. It is wrong
    in the direction of the trades nobody chose to look at, and its numbers stay internally consistent
    the whole time.
    """

    #: Reward below risk, so clearing the confidence floor is not the same as being worth taking.
    PAIR = BarrierPair(take_profit_atr=1.0, stop_loss_atr=2.0)
    #: 0.55 clears a 0.50 confidence floor; 0.55*1.0 - 0.40*2.0 = -0.25 ATR does not clear zero.
    RUNG = (0.55, 0.10)

    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = raw_candles(240)
        cls.features = build_features(cls.raw, atr_window=14)
        cls.feature_columns = tuple(cls.features.columns) + tuple(BARRIER_FEATURE_COLUMNS)

    def test_a_bet_that_clears_confidence_but_not_expected_value_is_flat_in_both(self) -> None:
        config = SimpleNamespace(
            barrier=SimpleNamespace(atr_window=14, backtest_minimum_confidence=FLOOR, allow_short=True)
        )
        vectorised = _decide_window(
            model=_TableModel((self.RUNG,)),
            raw=self.raw,
            window=pd.DataFrame({"timestamp": self.raw["timestamp"].tail(1).to_numpy()}),
            pair=self.PAIR,
            dataset=SimpleNamespace(feature_columns=self.feature_columns),
            config=config,
        )
        choice = choose_direction(
            _TableModel((self.RUNG,)),
            self.features.frame.iloc[[len(self.raw) - 1]],
            self.PAIR,
            allow_short=True,
            minimum_confidence=FLOOR,
            feature_columns=self.feature_columns,
        )

        # The premise: the long really does clear the confidence floor, so this is the expected-value
        # floor doing the work and not a second confidence check in disguise.
        long_side = choice.candidate_for(Direction.LONG)
        self.assertGreaterEqual(long_side.confidence, FLOOR)
        self.assertLess(long_side.expected_value_atr, 0.0)

        self.assertEqual(choice.direction, Direction.FLAT)
        self.assertEqual(int(vectorised["direction"].iloc[0]), 0)


if __name__ == "__main__":
    unittest.main()
