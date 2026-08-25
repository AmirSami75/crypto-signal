"""The order the bot advisor asks its questions in, which is the whole of its design.

Several of its conditions can hold on the same candle — a position can have hit its stop *and* be past
its holding limit *and* have the model favouring the other side — and each wrong precedence has a
distinct cost:

* Asking the model before checking the bracket is how a stopped-out position gets held on a fresh
  opinion. The bracket resolved; nothing the model now thinks changes that.
* Treating faded conviction as a reversal closes winners early. Only the *opposite* side clearing the
  same bar the entry had to clear is a reversal.
* Trailing a stop that has not yet reached break-even converts ordinary noise into a realised loss, so
  the trail waits for the position to be in profit before it moves at all.

The model's opinion is stubbed here rather than fitted. The advisor's job is to weigh an opinion against
a position, and a real estimator would make the opinion the thing under test instead of the weighing —
the tests that pin what the model itself says live in `test_direction.py` and `test_evaluator.py`. The
*window* is real: the price path the bracket resolves against comes from `build_window`, over the same
candles the audit digest is computed from.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

import joblib

from crypto_signal.domain import BarrierPair, Direction
from crypto_signal.modeling.direction import (
    DirectionCandidate,
    DirectionChoice,
    OutcomeProbabilities,
)
from crypto_signal_engine.application.bot_advisor import BotAdvisorService
from crypto_signal_engine.application.errors import InvalidInferenceRequest
from crypto_signal_engine.application.evaluator import MarketEvaluator
from crypto_signal_engine.application.models import (
    BotAction,
    BotDecisionRequest,
    OpenPositionInput,
    TradeParametersInput,
)
from crypto_signal_engine.infrastructure.model_registry import ModelRegistry

from test_evaluator import BOUNDS, CLOSE, window
from test_model_registry import bundle


def probabilities(win: float, timeout: float = 0.05) -> OutcomeProbabilities:
    return OutcomeProbabilities(win=win, loss=1.0 - win - timeout, timeout=timeout)


def choice(direction: Direction, *, long: float = 0.30, short: float = 0.30) -> DirectionChoice:
    """A stubbed verdict carrying both sides, as the real one always does.

    Both sides are always present even when one was declined, because a FLAT answer is only auditable
    if the response shows what it turned down — and because `_flat_reason` distinguishes "saw nothing"
    from "found a short it was not allowed to take" by reading the side it did not choose.
    """
    barriers = BarrierPair(take_profit_atr=2.0, stop_loss_atr=1.0)
    candidates = tuple(
        DirectionCandidate(
            direction=side,
            barriers=barriers,
            probabilities=probabilities(confidence),
            expected_value_atr=confidence * 2.0 - (1.0 - confidence),
        )
        for side, confidence in ((Direction.LONG, long), (Direction.SHORT, short))
    )
    chosen = next((c for c in candidates if c.direction is direction), None)
    return DirectionChoice(
        direction=direction,
        chosen=chosen,
        candidates=candidates,
        rationale=(f"stub: {direction.name}",),
    )


class _FixedEvaluator:
    """An evaluator that hands back one prepared assessment, whatever it is asked."""

    def __init__(self, assessment) -> None:
        self.assessment = assessment

    def assess(self, **_: object):
        return self.assessment


class AdvisorTestCase(unittest.TestCase):
    """A real window and a stubbed opinion, recombined per test."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.TemporaryDirectory()
        directory = Path(cls._temporary.name)
        joblib.dump(bundle(("BTCUSDT",), "1h"), directory / "BTCUSDT_1h.joblib")
        evaluator = MarketEvaluator(
            registry=ModelRegistry(directory),
            minimum_candles=169,
            maximum_candles=2_000,
            default_max_holding_periods=24,
            default_minimum_confidence=0.5,
            barrier_atr_bounds=BOUNDS,
        )
        cls.candles = window()
        cls.parameters = TradeParametersInput(
            take_profit_percent=Decimal("2"),
            stop_loss_percent=Decimal("1"),
            allow_short=True,
        )
        # One real assessment, built once: the window, its digest and its price path are what the
        # advisor reads, and none of them depend on the stubbed verdict swapped in per test.
        cls.baseline = evaluator.assess(
            request_id="setup",
            symbol="BTCUSDT",
            interval="1h",
            candles=cls.candles,
            parameters=cls.parameters,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary.cleanup()

    def decide(
        self,
        verdict: DirectionChoice,
        position: OpenPositionInput | None = None,
        *,
        allow_short: bool = True,
        max_holding_periods: int = 24,
        stop_loss_percent: Decimal | None = None,
    ):
        parameters = replace(
            self.parameters,
            allow_short=allow_short,
            **({} if stop_loss_percent is None else {"stop_loss_percent": stop_loss_percent}),
        )
        assessment = replace(
            self.baseline,
            choice=verdict,
            parameters=parameters,
            max_holding_periods=max_holding_periods,
            minimum_confidence=0.5,
        )
        advisor = BotAdvisorService(_FixedEvaluator(assessment))
        return advisor.evaluate(
            BotDecisionRequest(
                request_id="test",
                bot_id="bot-1",
                symbol="BTCUSDT",
                interval="1h",
                candles=self.candles,
                parameters=assessment.parameters,
                position=position,
            )
        )


class FlatTests(AdvisorTestCase):
    def test_an_edge_from_flat_is_an_open_with_the_levels_to_open_at(self) -> None:
        result = self.decide(choice(Direction.LONG, long=0.62))
        self.assertEqual(result.action, BotAction.OPEN)
        self.assertIs(result.direction, Direction.LONG)
        self.assertEqual(result.levels.entry_price, CLOSE)
        # A long's target sits above the entry and its stop below — the check that catches a mapper or a
        # sign error, which is otherwise a plausible-looking response that loses money on the first fill.
        self.assertGreater(result.levels.take_profit_price, result.levels.entry_price)
        self.assertLess(result.levels.stop_loss_price, result.levels.entry_price)

    def test_a_short_prices_its_barriers_on_the_other_side_of_the_entry(self) -> None:
        result = self.decide(choice(Direction.SHORT, short=0.64))
        self.assertEqual(result.action, BotAction.OPEN)
        self.assertLess(result.levels.take_profit_price, result.levels.entry_price)
        self.assertGreater(result.levels.stop_loss_price, result.levels.entry_price)

    def test_no_edge_holds_flat_and_carries_no_levels(self) -> None:
        result = self.decide(choice(Direction.FLAT, long=0.55, short=0.52))
        self.assertEqual(result.action, BotAction.HOLD)
        self.assertIs(result.direction, Direction.FLAT)
        self.assertIsNone(result.levels)
        self.assertEqual(result.reason_code, "no_edge")

    def test_a_floor_nobody_cleared_is_named_as_the_floor_not_as_silence(self) -> None:
        """`confidence_below_minimum` and `no_edge` are the difference between a threshold to lower and
        a market with nothing in it. Collapsing them makes a misconfigured floor undiagnosable."""
        result = self.decide(choice(Direction.FLAT, long=0.31, short=0.28))
        self.assertEqual(result.reason_code, "confidence_below_minimum")

    def test_a_trade_the_configuration_forbade_says_so_rather_than_reporting_nothing(self) -> None:
        result = self.decide(
            choice(Direction.FLAT, long=0.20, short=0.70), allow_short=False
        )
        self.assertEqual(result.reason_code, "short_not_allowed")

    def test_both_sides_are_reported_even_though_one_was_declined(self) -> None:
        result = self.decide(choice(Direction.LONG, long=0.62, short=0.33))
        self.assertEqual(len(result.rationale), 1)
        self.assertGreater(result.confidence, 0.6)


class BracketPrecedenceTests(AdvisorTestCase):
    """The resolved bracket outranks every opinion, and the reasons are ordered underneath it."""

    def position(self, direction: Direction, **overrides) -> OpenPositionInput:
        defaults = dict(
            direction=direction,
            entry_price=CLOSE,
            quantity=Decimal("0.5"),
            bars_held=4,
        )
        defaults.update(overrides)
        return OpenPositionInput(**defaults)

    def test_a_stop_that_was_hit_closes_the_position_whatever_the_model_now_thinks(self) -> None:
        """The precedence that costs the most to get wrong: the bracket resolved, so the trade is over.

        The model is deliberately still bullish here. An advisor that asked it first would answer HOLD on
        a position the venue has already closed, and the orchestrator would carry a phantom position.
        """
        result = self.decide(
            choice(Direction.LONG, long=0.80),
            self.position(Direction.LONG, stop_loss_price=Decimal("9990")),
        )
        self.assertEqual(result.action, BotAction.CLOSE)
        self.assertEqual(result.reason_code, "stop_loss_touched")
        self.assertIs(result.direction, Direction.LONG)

    def test_a_take_profit_that_was_hit_closes_it_too(self) -> None:
        result = self.decide(
            choice(Direction.FLAT),
            self.position(
                Direction.LONG,
                take_profit_price=Decimal("10010"),
                stop_loss_price=Decimal("9000"),
            ),
        )
        self.assertEqual(result.action, BotAction.CLOSE)
        self.assertEqual(result.reason_code, "take_profit_touched")

    def test_a_candle_that_reached_both_barriers_is_booked_against_the_trade(self) -> None:
        """The adverse-wins tie-break, and the rationale says it was a tie-break rather than a sequence.

        Intrabar order is unknowable. Resolving it in the trade's favour here while the labeller resolves
        it against would train the model on one rule and operate it under another, and the gap would
        surface as live results quietly worse than the backtest — with nothing in the audit trail to
        explain the difference.
        """
        result = self.decide(
            choice(Direction.LONG, long=0.80),
            self.position(
                Direction.LONG,
                take_profit_price=Decimal("10010"),
                stop_loss_price=Decimal("9990"),
            ),
        )
        self.assertEqual(result.reason_code, "stop_loss_touched")
        self.assertTrue(any("tie-break" in line for line in result.rationale))

    def test_a_bracket_neither_barrier_touched_keeps_the_position_open(self) -> None:
        """A regression test for a shipped defect, and the reason `TouchResult.resolved` is not the
        predicate step 1 branches on.

        `_resolve_bracket` scans the held span and passes `max_horizon=len(high)`, so the scan window
        always *is* the horizon and `resolved` comes back True for a timeout as readily as for a touch.
        Branching on it closed every open position on its next tick, reporting `stop_loss_touched` at an
        `exit_price` of nan — a bot that could never hold a trade for more than one candle, and an audit
        trail claiming a stop was reached at a price that is not a number.
        """
        result = self.decide(
            choice(Direction.FLAT),
            self.position(
                Direction.LONG,
                take_profit_price=Decimal("99000"),
                stop_loss_price=Decimal("100"),
            ),
        )
        self.assertEqual(result.action, BotAction.HOLD)
        self.assertNotIn(result.reason_code, {"stop_loss_touched", "take_profit_touched"})
        # The bracket in force is still reported, so .NET can see nothing moved.
        self.assertEqual(result.levels.stop_loss_price, Decimal("100.00000000"))

    def test_an_unresolved_bet_past_its_horizon_is_closed_as_expired(self) -> None:
        result = self.decide(
            choice(Direction.LONG, long=0.80),
            self.position(
                Direction.LONG,
                take_profit_price=Decimal("99000"),
                stop_loss_price=Decimal("100"),
                bars_held=30,
            ),
            max_holding_periods=24,
        )
        self.assertEqual(result.action, BotAction.CLOSE)
        self.assertEqual(result.reason_code, "max_holding_periods_reached")

    def test_a_reversal_closes_the_position_and_reports_the_side_it_reversed_to(self) -> None:
        result = self.decide(
            choice(Direction.SHORT, long=0.20, short=0.70),
            self.position(
                Direction.LONG,
                take_profit_price=Decimal("99000"),
                stop_loss_price=Decimal("100"),
            ),
        )
        self.assertEqual(result.action, BotAction.CLOSE)
        self.assertEqual(result.reason_code, "direction_reversed")
        # The direction is the position being closed, not the new opinion — .NET closes a LONG here. The
        # new side is in the rationale and the confidence, which is where a human reads it.
        self.assertIs(result.direction, Direction.LONG)
        self.assertTrue(any("SHORT" in line for line in result.rationale))

    def test_conviction_merely_fading_is_not_a_reversal(self) -> None:
        """FLAT is the model declining to bet, not the model betting against. Closing on it would exit
        every position the moment the edge stopped clearing the floor, which is most candles."""
        result = self.decide(
            choice(Direction.FLAT, long=0.40, short=0.30),
            self.position(
                Direction.LONG,
                take_profit_price=Decimal("99000"),
                stop_loss_price=Decimal("100"),
            ),
        )
        self.assertEqual(result.action, BotAction.HOLD)
        self.assertEqual(result.reason_code, "no_edge")

    def test_a_short_held_under_a_configuration_that_forbids_shorting_is_closed(self) -> None:
        result = self.decide(
            choice(Direction.FLAT),
            self.position(
                Direction.SHORT,
                take_profit_price=Decimal("100"),
                stop_loss_price=Decimal("99000"),
            ),
            allow_short=False,
        )
        self.assertEqual(result.action, BotAction.CLOSE)
        self.assertEqual(result.reason_code, "short_not_allowed")


class TrailingStopTests(AdvisorTestCase):
    def position(self, **overrides) -> OpenPositionInput:
        defaults = dict(
            direction=Direction.LONG,
            entry_price=Decimal("9800"),
            quantity=Decimal("0.5"),
            bars_held=6,
            take_profit_price=Decimal("99000"),
            stop_loss_price=Decimal("9000"),
        )
        defaults.update(overrides)
        return OpenPositionInput(**defaults)

    def test_a_stop_behind_a_profitable_position_is_advanced_never_the_take_profit(self) -> None:
        result = self.decide(choice(Direction.FLAT), self.position())
        self.assertEqual(result.action, BotAction.ADJUST_BRACKET)
        self.assertEqual(result.reason_code, "trailing_stop_advanced")
        self.assertGreater(result.levels.stop_loss_price, Decimal("9000"))
        self.assertEqual(result.levels.take_profit_price, Decimal("99000.00000000"))

    def test_the_new_stop_stays_below_the_current_price(self) -> None:
        """Advancing a stop through the market manufactures an instant stop-out — a "risk reduction"
        that realises the loss it was meant to cap."""
        result = self.decide(choice(Direction.FLAT), self.position())
        self.assertLess(result.levels.stop_loss_price, CLOSE)

    def test_a_stop_already_tighter_than_the_trail_is_left_alone(self) -> None:
        """The trail may only ever reduce risk. A stop that has been advanced must not retreat when
        price pulls back, which is the property a naive recompute-from-the-close implementation loses.

        The wider stop distance is what makes the guard reachable at all, and the reason is worth
        stating: the trail sits one stop-distance below the window's highest high, so with a stop
        narrower than the candles' own range it lands *inside* the path the position already traversed.
        A working stop tighter than that is a stop those same candles touched, step 1 resolves the
        bracket, and the trail is never consulted — the test would be pinning precedence, not the guard.
        """
        result = self.decide(
            choice(Direction.FLAT),
            self.position(entry_price=Decimal("9700"), stop_loss_price=Decimal("9850")),
            stop_loss_percent=Decimal("3"),
        )
        self.assertEqual(result.action, BotAction.HOLD)
        self.assertEqual(result.reason_code, "no_edge")

    def test_a_position_not_yet_in_profit_is_not_tightened(self) -> None:
        """Trailing into a loss converts noise into a realised loss. Break-even is the gate."""
        result = self.decide(choice(Direction.FLAT), self.position(entry_price=Decimal("10500")))
        self.assertEqual(result.action, BotAction.HOLD)
        self.assertEqual(result.reason_code, "no_edge")

    def test_a_short_trails_downward(self) -> None:
        result = self.decide(
            choice(Direction.FLAT),
            self.position(
                direction=Direction.SHORT,
                entry_price=Decimal("10200"),
                take_profit_price=Decimal("100"),
                stop_loss_price=Decimal("11000"),
            ),
        )
        self.assertEqual(result.action, BotAction.ADJUST_BRACKET)
        self.assertLess(result.levels.stop_loss_price, Decimal("11000"))
        self.assertGreater(result.levels.stop_loss_price, CLOSE)


class PositionValidationTests(AdvisorTestCase):
    def test_a_flat_position_is_refused_rather_than_read_as_no_position(self) -> None:
        """`position` absent means flat. `position.direction == FLAT` means the caller built a position
        message it could not fill in, and guessing which it meant is how a real position gets ignored."""
        with self.assertRaises(InvalidInferenceRequest):
            self.decide(
                choice(Direction.LONG, long=0.62),
                OpenPositionInput(
                    direction=Direction.FLAT, entry_price=CLOSE, quantity=Decimal("1")
                ),
            )

    def test_a_position_with_no_size_or_no_entry_is_refused(self) -> None:
        for overrides in ({"quantity": Decimal("0")}, {"entry_price": Decimal("0")}):
            with self.subTest(**overrides):
                fields = dict(
                    direction=Direction.LONG, entry_price=CLOSE, quantity=Decimal("1"), bars_held=2
                )
                fields.update(overrides)
                with self.assertRaises(InvalidInferenceRequest):
                    self.decide(choice(Direction.FLAT), OpenPositionInput(**fields))

    def test_more_bars_held_than_candles_supplied_scans_the_window_it_has(self) -> None:
        """A bot restarted after an outage legitimately reports more bars than it sends candles for.
        Unclamped, the entry index goes negative and silently wraps to the far end of the array —
        resolving the bracket against candles from before the position existed."""
        result = self.decide(
            choice(Direction.FLAT),
            OpenPositionInput(
                direction=Direction.LONG,
                entry_price=CLOSE,
                quantity=Decimal("1"),
                bars_held=10_000,
                take_profit_price=Decimal("99000"),
                stop_loss_price=Decimal("100"),
            ),
            max_holding_periods=99_999,
        )
        self.assertIn(result.action, {BotAction.HOLD, BotAction.ADJUST_BRACKET})


if __name__ == "__main__":
    unittest.main()
