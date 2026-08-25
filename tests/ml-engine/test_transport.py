"""The wire boundary: what a protobuf message and an application dataclass promise each other.

Three properties are worth a test each, and none of them are visible from inside the application layer:

**Prices cross as decimal strings.** The contract's header says so, and the reason is the audit chain:
.NET stores money as `decimal`, and a price that went through a float on the way out cannot be proven
to be the price the engine computed. A test that asserts the *type* on the wire is the only place that
can catch a well-meaning `float()` added to a mapper.

**An unset submessage is not a zeroed one.** proto3 reads an absent message and one full of zeros
identically, so the mappers check `HasField` wherever the two mean different things — an absent
`OpenPosition` is a flat bot, a zeroed one is a position of zero size at a price of zero, and treating
them as the same thing is how a flat bot gets told to close something.

**A status code is a caller instruction.** `INVALID_ARGUMENT` means "fix the request", so retrying is
pointless; `FAILED_PRECONDITION` means the engine is fine and this market is not answerable;
`INTERNAL` means a bug here. An orchestrator with a retry policy acts on these, so mapping a malformed
price to `INTERNAL` would have it retry the same bad request forever.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import re
import unittest

import grpc

from crypto_signal.domain import Direction
from crypto_signal_engine.application.errors import InvalidInferenceRequest, ModelUnavailable
from crypto_signal_engine.application.models import (
    REASON_CODES,
    BarrierProbabilitiesResult,
    BotAction,
    BotDecisionResult,
    LevelsResult,
    ModelStamp,
    SignalResult,
)
from crypto_signal_engine.contracts.v1 import ml_engine_pb2 as pb
from crypto_signal_engine.transport.grpc import mappers
from crypto_signal_engine.transport.grpc.servicer import MlEngineServicer, _request_id

MOMENT = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
STAMP = ModelStamp(
    model_id="pooled-1h", model_version="4bca77500e0c", trained_at=MOMENT, used_wildcard=True
)
LEVELS = LevelsResult(
    entry_price=Decimal("60123.50000000"),
    take_profit_price=Decimal("61325.97000000"),
    stop_loss_price=Decimal("59522.26500000"),
    atr=Decimal("401.25000000"),
    risk_reward_ratio=2.0,
    take_profit_atr=2.996,
    stop_loss_atr=1.498,
)
PROBABILITIES = BarrierProbabilitiesResult(take_profit_first=0.61, stop_loss_first=0.30, timeout=0.09)


def signal_result(**overrides) -> SignalResult:
    fields = dict(
        request_id="req-1",
        symbol="BTCUSDT",
        interval="1h",
        direction=Direction.LONG,
        levels=LEVELS,
        confidence=0.61,
        probabilities=PROBABILITIES,
        expected_value=0.0412,
        long_confidence=0.61,
        short_confidence=0.31,
        candle_open_time=MOMENT,
        valid_until=MOMENT,
        model=STAMP,
        input_digest_sha256="a" * 64,
        rationale=("long: confidence 0.610 clears floor 0.500",),
    )
    fields.update(overrides)
    return SignalResult(**fields)


def decision_result(**overrides) -> BotDecisionResult:
    fields = dict(
        request_id="req-1",
        symbol="BTCUSDT",
        interval="1h",
        action=BotAction.OPEN,
        direction=Direction.LONG,
        reason_code="no_edge",
        confidence=0.61,
        probabilities=PROBABILITIES,
        expected_value=0.0412,
        candle_open_time=MOMENT,
        valid_until=MOMENT,
        model=STAMP,
        input_digest_sha256="a" * 64,
        levels=LEVELS,
    )
    fields.update(overrides)
    return BotDecisionResult(**fields)


class DecimalBoundaryTests(unittest.TestCase):
    def test_every_price_leaves_as_a_string_of_digits(self) -> None:
        """The type is the test. A float here would round-trip through the dashboard looking correct and
        still fail to match, byte for byte, what .NET wrote to the database."""
        levels = mappers.levels_to_proto(LEVELS)
        for field in ("entry_price", "take_profit_price", "stop_loss_price", "atr"):
            value = getattr(levels, field)
            with self.subTest(field=field):
                self.assertIsInstance(value, str)
                # Fixed places, no exponent: `1E+2` is a valid Decimal repr and not a price .NET parses.
                self.assertRegex(value, r"^-?\d+\.\d{8}$")

    def test_only_dimensionless_quantities_are_floating_point(self) -> None:
        levels = mappers.levels_to_proto(LEVELS)
        for field in ("risk_reward_ratio", "take_profit_atr", "stop_loss_atr"):
            with self.subTest(field=field):
                self.assertIsInstance(getattr(levels, field), float)


class UnsetVersusZeroTests(unittest.TestCase):
    def test_a_hold_with_nothing_to_hold_leaves_the_levels_unset(self) -> None:
        """Not a zeroed `TradeLevels`. A bracket at a price of zero is a level no market reaches, and a
        caller reading one would draw it on a chart."""
        response = mappers.bot_decision_to_proto(
            decision_result(action=BotAction.HOLD, direction=Direction.FLAT, levels=None)
        )
        self.assertFalse(response.HasField("levels"))

    def test_an_unrecorded_training_date_is_unset_rather_than_the_epoch(self) -> None:
        response = mappers.signal_to_proto(
            signal_result(model=ModelStamp("m", "v", None, False))
        )
        self.assertFalse(response.HasField("model_trained_at"))

    def test_an_epoch_timestamp_that_was_actually_sent_is_read_as_a_date(self) -> None:
        """The mirror of the test above: `HasField` must distinguish the two, not suppress both."""
        message = pb.Candle()
        message.open_time.FromDatetime(datetime(1970, 1, 1, tzinfo=timezone.utc))
        self.assertIsNotNone(mappers.optional_datetime(message, "open_time"))
        self.assertIsNone(mappers.optional_datetime(pb.Candle(), "open_time"))

    def test_a_flat_bot_sends_no_position_and_a_zeroed_one_is_not_the_same_message(self) -> None:
        flat = pb.EvaluateBotDecisionRequest(
            symbol="BTCUSDT",
            interval="1h",
            parameters=pb.TradeParameters(take_profit_percent="2", stop_loss_percent="1"),
        )
        self.assertIsNone(mappers.bot_decision_request_from_proto(flat).position)

        # A zeroed OpenPosition is a valid protobuf message and must not read as "flat". It is rejected
        # instead, and by the price rather than by `HasField`: an entry of "" is a missing price, and
        # `parse_money` refuses to read a missing price as zero. So the caller is told which field it
        # failed to fill rather than being quietly told its real position does not exist.
        zeroed = pb.EvaluateBotDecisionRequest(
            symbol="BTCUSDT",
            interval="1h",
            parameters=pb.TradeParameters(take_profit_percent="2", stop_loss_percent="1"),
            position=pb.OpenPosition(),
        )
        with self.assertRaises(ValueError) as raised:
            mappers.bot_decision_request_from_proto(zeroed)
        self.assertIn("position.entry_price", str(raised.exception))

    def test_a_bracket_half_managed_at_the_venue_reads_the_missing_half_as_absent(self) -> None:
        """A bot whose stop rests at the venue and whose take-profit does not is a real configuration.
        The empty string is "not supplied", not a price of zero."""
        position = mappers.position_from_proto(
            pb.OpenPosition(
                direction=pb.TRADE_DIRECTION_LONG,
                entry_price="60000",
                quantity="0.5",
                stop_loss_price="59000",
            )
        )
        self.assertIsNone(position.take_profit_price)
        self.assertEqual(position.stop_loss_price, Decimal("59000"))


class ExtrapolationFlagTests(unittest.TestCase):
    """Field 21 on both responses, deliberately the same number."""

    def test_both_responses_carry_the_flag(self) -> None:
        self.assertTrue(mappers.signal_to_proto(signal_result(barrier_extrapolated=True)).barrier_extrapolated)
        self.assertTrue(
            mappers.bot_decision_to_proto(decision_result(barrier_extrapolated=True)).barrier_extrapolated
        )

    def test_the_field_number_matches_on_both_so_one_mapper_reads_one_number(self) -> None:
        """The proto says the numbers match on purpose. If they drift, a shared .NET mapper reads the
        flag from one message and something else from the other — and the failure is silent, because
        both fields are bools with a plausible default."""
        numbers = {
            message.DESCRIPTOR.fields_by_name["barrier_extrapolated"].number
            for message in (pb.GetSignalResponse, pb.EvaluateBotDecisionResponse)
        }
        self.assertEqual(numbers, {21})

    def test_the_flag_is_not_the_warning(self) -> None:
        """A risk engine must be able to gate on extrapolation without matching English prose. The two
        travel independently, and this pins that the flag survives an empty warning."""
        response = mappers.signal_to_proto(signal_result(barrier_extrapolated=True, warning=""))
        self.assertTrue(response.barrier_extrapolated)
        self.assertEqual(response.warning, "")


class ReasonCodeVocabularyTests(unittest.TestCase):
    def test_the_engine_sends_exactly_the_codes_the_contract_documents(self) -> None:
        """The proto comment is what .NET writes its switch from. A code in one and not the other is
        either a branch that never fires or an audit row with a token nothing can interpret."""
        source = (
            __import__("pathlib")
            .Path(pb.__file__)
            .parents[6]
            .joinpath("contracts/crypto_signal_engine/contracts/v1/ml_engine.proto")
        )
        if not source.exists():  # installed without the contracts tree beside it
            self.skipTest("proto source not available from the installed package")
        text = source.read_text()
        documented = set(re.findall(r'"([a-z_]+)"', text.split("Why, in one machine-readable token")[1]))
        self.assertEqual(documented, set(REASON_CODES))


class _RecordingContext:
    """A gRPC context that records the abort and raises, as the real one does."""

    def __init__(self) -> None:
        self.status: grpc.StatusCode | None = None
        self.detail: str | None = None

    def abort(self, status, detail):
        self.status = status
        self.detail = detail
        raise grpc.RpcError(detail)


class _FailingService:
    """A service whose every entry point raises one prepared exception."""

    def __init__(self, error: BaseException) -> None:
        self.error = error

    def __getattr__(self, _name):
        def raise_it(*_args, **_kwargs):
            raise self.error

        return raise_it


class ErrorPolicyTests(unittest.TestCase):
    def dispatch(self, error: BaseException) -> _RecordingContext:
        servicer = MlEngineServicer(_FailingService(error), _FailingService(error))
        context = _RecordingContext()
        with self.assertRaises(grpc.RpcError):
            servicer.GetCapabilities(pb.GetCapabilitiesRequest(request_id="req-1"), context)
        return context

    def test_a_malformed_request_is_the_callers_to_fix_not_to_retry(self) -> None:
        for error in (
            InvalidInferenceRequest("candles[3].close is not a decimal number"),
            ValueError("parse_money: 'abc'"),
        ):
            with self.subTest(error=type(error).__name__):
                context = self.dispatch(error)
                self.assertIs(context.status, grpc.StatusCode.INVALID_ARGUMENT)
                # The detail is the validator's own message: a caller sending 500 candles needs to know
                # which one was malformed, and only the engine knows.
                self.assertIn(str(error), context.detail)

    def test_an_unanswerable_market_is_a_precondition_not_an_argument(self) -> None:
        """`FAILED_PRECONDITION` says the engine is up and this market has no model — a state that can
        change without the request changing, which is precisely why it is not INVALID_ARGUMENT."""
        context = self.dispatch(ModelUnavailable("no model for FOOUSDT 1h; loaded: BTCUSDT 1h"))
        self.assertIs(context.status, grpc.StatusCode.FAILED_PRECONDITION)
        self.assertIn("FOOUSDT", context.detail)

    def test_an_unexpected_failure_says_nothing_about_the_server(self) -> None:
        """The traceback belongs in the log. An arbitrary exception's message can carry a filesystem
        path or a fragment of a model bundle, and a private contract is still not a place to leak them."""
        context = self.dispatch(RuntimeError("/srv/artifacts/models/BTCUSDT_1h.joblib is corrupt"))
        self.assertIs(context.status, grpc.StatusCode.INTERNAL)
        self.assertEqual(context.detail, "The ML engine could not complete the request")
        self.assertNotIn("joblib", context.detail)

    def test_a_keyboard_interrupt_is_not_swallowed_as_an_internal_error(self) -> None:
        """`except Exception` and not `except BaseException`, so a shutdown signal still stops the
        server instead of being reported to the caller as a bug in the engine."""
        servicer = MlEngineServicer(_FailingService(KeyboardInterrupt()), _FailingService(KeyboardInterrupt()))
        with self.assertRaises(KeyboardInterrupt):
            servicer.GetCapabilities(pb.GetCapabilitiesRequest(), _RecordingContext())


class RequestIdTests(unittest.TestCase):
    def test_a_caller_that_sends_no_correlation_id_is_given_one(self) -> None:
        """grpcurl and the health prober send none. Without this, every such line in the log is
        unjoinable to the response it produced."""
        generated = _request_id("   ")
        self.assertTrue(generated)
        self.assertRegex(generated, r"^[0-9a-f-]{36}$")

    def test_a_caller_that_sends_one_keeps_it(self) -> None:
        self.assertEqual(_request_id(" req-7 "), "req-7")


if __name__ == "__main__":
    unittest.main()
