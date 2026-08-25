"""What the engine says about a bet it was not trained to price.

The model is barrier-conditional, so any take-profit / stop-loss pair gets an answer — including pairs
far outside the ATR grid the estimator was fitted across. Refusing those would be defensible; answering
them silently would not, because the request that lands outside the grid is not exotic. Barriers arrive
as *percentages* and are consumed as *ATR multiples*, so the same 2%/1% request that is a 2.0/1.0 ATR
bracket in a normal market becomes an 18.5/9.2 ATR bracket when volatility collapses — and at that
distance the model reports an expected value of over +4 per unit risked, which is an extension of the
fitted surface rather than a measurement on it. A risk engine that sized on that number would treat the
quietest market of the year as the best opportunity it had ever seen.

So the caveat travels two ways: as prose in `warning`, for a human, and as `barrier_extrapolated`, for
the risk engine — which must never have to gate on a substring of an English sentence. The tests below
pin the two to each other, because the failure that matters is not either one being wrong on its own
but the pair disagreeing: a response whose bool says "measured" and whose prose says "extrapolated"
gets believed in whichever half the reader looked at first.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

import joblib

from crypto_signal_engine.application.evaluator import MarketEvaluator
from crypto_signal_engine.application.models import CandleInput, TradeParametersInput
from crypto_signal_engine.infrastructure.model_registry import ModelRegistry

from test_model_registry import bundle

#: The bounds every test here is written against, matching `ML_BARRIER_ATR_BOUNDS`'s default and the
#: grid `barrier_pipeline` actually trains over. Named rather than repeated so a test cannot drift into
#: asserting against a span the model was never fitted on.
BOUNDS = (0.5, 4.0)

#: A candle series built so its ATR is exactly `RANGE`, which makes every ATR multiple below hand
#: computable instead of read back from the code under test. Each candle spans `RANGE` high to low and
#: closes at its midpoint, and consecutive closes move by `STEP`, so every leg of the true range —
#: `high - low`, `|high - previous close|`, `|low - previous close|` — resolves to `RANGE` or less, with
#: the first winning outright. Wilder's EWM of a constant is that constant.
CLOSE = Decimal("10000")
RANGE = Decimal("100")
STEP = Decimal("20")

#: The close walks a triangle rather than a sawtooth. A sawtooth would be simpler to write and wrong:
#: its wrap from the top of the ramp to the bottom is a gap wider than the candle's own range, so the
#: previous-close leg of the true range wins on that bar and the ATR is no longer `RANGE`. The first
#: draft of this fixture had exactly that bug, and it showed up as a 4% target measuring 3.79 ATR.
PERIOD = 8


def window(count: int = 203) -> tuple[CandleInput, ...]:
    """`count` hourly candles ending on a close of exactly `CLOSE` with an ATR of exactly `RANGE`.

    The default count is chosen so the triangle lands on its zero crossing at the final candle: the
    entry price is the last close, and every assertion below reads better against a round number.
    """
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    assert (count - 1) % PERIOD == 2, "the last candle must sit on the triangle's zero crossing"
    candles = []
    for index in range(count):
        # -40, -20, 0, +20, +40, +20, 0, -20 and around again: enough variation that the scale-free
        # features are not degenerate, and never a step the candle's own range cannot cover.
        close = CLOSE + STEP * Decimal(2 - abs(4 - index % PERIOD))
        candles.append(
            CandleInput(
                open_time=start + timedelta(hours=index),
                open=close,
                high=close + RANGE / 2,
                low=close - RANGE / 2,
                close=close,
                volume=Decimal(100 + index % 7),
            )
        )
    return tuple(candles)


class ExtrapolationTests(unittest.TestCase):
    """`barrier_extrapolated` against the bounds, and against the prose that duplicates it."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        joblib.dump(bundle(("BTCUSDT",), "1h"), directory / "BTCUSDT_1h.joblib")
        self.evaluator = MarketEvaluator(
            registry=ModelRegistry(directory),
            minimum_candles=169,
            maximum_candles=2_000,
            default_max_holding_periods=24,
            default_minimum_confidence=0.5,
            barrier_atr_bounds=BOUNDS,
        )
        self.candles = window()

    def assess(self, take_profit: str, stop_loss: str):
        return self.evaluator.assess(
            request_id="test",
            symbol="BTCUSDT",
            interval="1h",
            candles=self.candles,
            parameters=TradeParametersInput(
                take_profit_percent=Decimal(take_profit),
                stop_loss_percent=Decimal(stop_loss),
                allow_short=True,
            ),
        )

    def test_the_fixture_puts_the_barriers_where_the_arithmetic_says(self) -> None:
        """The premise every case below rests on: ATR is 1% of price, so percent equals ATR multiple."""
        assessment = self.assess("2", "1")
        self.assertEqual(assessment.window.entry_price, CLOSE)
        self.assertAlmostEqual(assessment.window.atr, float(RANGE), places=6)
        self.assertAlmostEqual(assessment.barriers.take_profit_atr, 2.0, places=6)
        self.assertAlmostEqual(assessment.barriers.stop_loss_atr, 1.0, places=6)

    def test_a_bracket_inside_the_fitted_span_is_not_flagged(self) -> None:
        assessment = self.assess("2", "1")
        self.assertFalse(assessment.barrier_extrapolated)
        self.assertNotIn("barrier extrapolation", assessment.warning)

    def test_a_bracket_the_model_never_saw_is_flagged_and_says_which_side(self) -> None:
        """20% of price at this ATR is a 20-ATR target — five times the widest barrier ever trained."""
        assessment = self.assess("20", "1")
        self.assertTrue(assessment.barrier_extrapolated)
        self.assertIn("barrier extrapolation: take_profit_atr=20.00", assessment.warning)
        # The stop is inside the span and must not be named: "which barrier" is the whole diagnostic
        # value of the clause, and a caller widening the wrong leg fixes nothing.
        self.assertNotIn("stop_loss_atr", assessment.warning)

    def test_a_stop_too_tight_to_have_been_trained_is_flagged_too(self) -> None:
        """Extrapolation is not only a wide-target problem: a 0.2 ATR stop is inside the noise the
        model was never asked to resolve, and it is the leg that decides whether the bet survives."""
        assessment = self.assess("2", "0.2")
        self.assertTrue(assessment.barrier_extrapolated)
        self.assertIn("stop_loss_atr=0.20", assessment.warning)
        self.assertNotIn("take_profit_atr", assessment.warning)

    def test_the_bounds_are_inclusive_at_both_ends(self) -> None:
        """The endpoints were trained on. Flagging them would cry extrapolation at the grid itself."""
        low, high = BOUNDS
        assessment = self.assess(str(high), str(low))
        self.assertAlmostEqual(assessment.barriers.take_profit_atr, high, places=6)
        self.assertAlmostEqual(assessment.barriers.stop_loss_atr, low, places=6)
        self.assertFalse(assessment.barrier_extrapolated)

    def test_the_flag_and_the_prose_agree_across_the_whole_range(self) -> None:
        """The failure this pair exists to prevent, swept rather than sampled.

        One method answers both, so the only way they can disagree is if someone splits it back into two
        inequalities — which is precisely the change this test is here to fail on.
        """
        for take_profit, stop_loss in (
            ("0.4", "1"),  # target below the grid
            ("0.5", "1"),  # exactly the floor
            ("2", "1"),  # comfortably inside
            ("4", "4"),  # exactly the ceiling, both legs
            ("4.01", "1"),  # a hair over
            ("20", "9"),  # the quiet-market case, both legs out
        ):
            with self.subTest(take_profit=take_profit, stop_loss=stop_loss):
                assessment = self.assess(take_profit, stop_loss)
                self.assertEqual(
                    assessment.barrier_extrapolated,
                    "barrier extrapolation" in assessment.warning,
                )


if __name__ == "__main__":
    unittest.main()
