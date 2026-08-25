"""The gate every request passes through, and the one class of bad input it exists to stop.

Almost every check in `application.candles` has the same shape: reject an input whose *arithmetic*
would succeed and whose *meaning* would be wrong. That is what makes this surface worth its own file.
A malformed price raises somewhere obvious. A window with a missing hour in it does not — every
feature computes, every number is finite and plausible, and `volatility_168` arrives as a 168-candle
statistic describing 200 candles of time. Nothing downstream can tell, and it moves the prediction.

Three properties the tests below are really about:

* **Where the gap is decides whether it is fatal.** The newest row's features read the last
  `minimum_candles` bars and nothing earlier, so a hole at position 10 of a 500-candle request cannot
  reach them. Refusing that would throw away good data; ignoring a hole in the final 169 would answer
  from bad data. The line is drawn where the arithmetic actually is, and both sides of it are tested.
* **The digest is over values, not formatting.** It has one job — letting a stored decision be
  replayed and checked — and it fails at that job in both directions: if `"100.5"` and `"100.50"`
  hash differently, a faithful replay reads as tampering; if two genuinely different bets hash the
  same, tampering reads as faithful. Both directions are pinned below.
* **`1m` and `1M` are a minute and a month.** Symbols are uppercased because venues quote them that
  way; intervals must not be, and the test says so, because case-folding them is a one-character
  change that answers a monthly question with a minute model.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest

from crypto_signal_engine.application.candles import (
    build_window,
    normalise_market,
    validate_request_id,
)
from crypto_signal_engine.application.errors import InvalidInferenceRequest
from crypto_signal_engine.application.models import CandleInput, TradeParametersInput

from test_evaluator import window

#: The warm-up length the engine's default configuration uses: 168 bars for `volatility_168` plus the
#: one bar being described. A window shorter than this cannot produce a complete newest feature row.
MINIMUM = 169
MAXIMUM = 2_000

PARAMETERS = TradeParametersInput(
    take_profit_percent=Decimal("2"),
    stop_loss_percent=Decimal("1"),
    allow_short=True,
    max_holding_periods=24,
    minimum_confidence=0.5,
)


def built(candles: tuple[CandleInput, ...], **overrides):
    return build_window(
        symbol=overrides.pop("symbol", "BTCUSDT"),
        interval=overrides.pop("interval", "1h"),
        candles=candles,
        parameters=overrides.pop("parameters", PARAMETERS),
        minimum_candles=overrides.pop("minimum_candles", MINIMUM),
        maximum_candles=overrides.pop("maximum_candles", MAXIMUM),
        **overrides,
    )


def with_candle(candles: tuple[CandleInput, ...], index: int, **changes) -> tuple[CandleInput, ...]:
    mutated = list(candles)
    mutated[index] = replace(mutated[index], **changes)
    return tuple(mutated)


class MarketIdentityTests(unittest.TestCase):
    def test_a_symbol_is_uppercased_and_an_interval_is_not(self) -> None:
        """Binance's `1m` is a minute and `1M` is a month. Folding the interval's case would resolve a
        monthly request to a minute model and answer it without a word — so only the symbol is folded."""
        self.assertEqual(normalise_market("  btcusdt ", " 1h "), ("BTCUSDT", "1h"))
        with self.assertRaises(InvalidInferenceRequest):
            normalise_market("BTCUSDT", "1H")

    def test_a_symbol_that_is_a_path_or_a_query_fragment_is_refused(self) -> None:
        """The symbol reaches a filename in the registry and a log line in the audit trail. Neither is a
        reason to accept `../` — the pattern is what keeps a ticker from being either of those things."""
        for bad in ("../secrets", "BTC/USDT", "BTC USDT", "'; DROP TABLE", "", "B"):
            with self.subTest(symbol=bad), self.assertRaises(InvalidInferenceRequest):
                normalise_market(bad, "1h")

    def test_an_unsupported_interval_names_what_is_supported(self) -> None:
        with self.assertRaises(InvalidInferenceRequest) as raised:
            normalise_market("BTCUSDT", "3s")
        self.assertIn("1h", str(raised.exception))

    def test_a_request_id_is_required_and_bounded(self) -> None:
        self.assertEqual(validate_request_id("abc"), "abc")
        for bad in ("", "   ", "x" * 129):
            with self.subTest(request_id=len(bad)), self.assertRaises(InvalidInferenceRequest):
                validate_request_id(bad)


class CandleShapeTests(unittest.TestCase):
    """Per-candle checks: an input no venue produced, rejected before it becomes a feature."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.candles = window()

    def test_a_valid_window_builds(self) -> None:
        result = built(self.candles)
        self.assertEqual(result.symbol, "BTCUSDT")
        self.assertEqual(result.entry_price, Decimal("10000"))
        self.assertEqual(result.latest_index, len(self.candles) - 1)
        self.assertEqual(result.warnings, ())

    def test_the_window_length_is_bounded_at_both_ends(self) -> None:
        """A floor because features need history; a ceiling because a request is a memory allocation, and
        an unbounded `repeated Candle` is a denial-of-service with a valid schema."""
        with self.assertRaises(InvalidInferenceRequest):
            built(self.candles[: MINIMUM - 1])
        with self.assertRaises(InvalidInferenceRequest):
            built(self.candles, maximum_candles=len(self.candles) - 1)

    def test_a_naive_timestamp_is_refused_rather_than_assumed_utc(self) -> None:
        """Assuming UTC would be right most of the time and wrong silently: a caller sending local time
        would get an answer stamped hours from the candle it describes, and `valid_until` would lie."""
        naive = with_candle(self.candles, -1, open_time=datetime(2026, 8, 9, 10))
        with self.assertRaises(InvalidInferenceRequest) as raised:
            built(naive)
        self.assertIn("naive", str(raised.exception))

    def test_a_missing_timestamp_is_refused(self) -> None:
        with self.assertRaises(InvalidInferenceRequest) as raised:
            built(with_candle(self.candles, 5, open_time=None))
        self.assertIn("candles[5].open_time", str(raised.exception))

    def test_a_non_positive_price_is_refused(self) -> None:
        """Every ratio feature divides by a price. A zero makes them infinite and a negative makes them
        confidently backwards, and both survive as float64 all the way to the model."""
        for field in ("open", "high", "low", "close"):
            with self.subTest(field=field), self.assertRaises(InvalidInferenceRequest):
                built(with_candle(self.candles, 3, **{field: Decimal("0")}))

    def test_a_non_finite_number_is_refused_and_names_its_field(self) -> None:
        with self.assertRaises(InvalidInferenceRequest) as raised:
            built(with_candle(self.candles, 7, volume=Decimal("NaN")))
        self.assertIn("candles[7].volume", str(raised.exception))

    def test_negative_volume_is_refused(self) -> None:
        with self.assertRaises(InvalidInferenceRequest):
            built(with_candle(self.candles, 2, volume=Decimal("-1")))

    def test_a_candle_that_violates_ohlc_bounds_is_refused(self) -> None:
        """A high below the close is not a candle; it is two rows of a join that went wrong. Letting it
        through gives the true range a negative leg and the ATR a value no market produced."""
        low_high = with_candle(self.candles, 4, high=self.candles[4].close - Decimal("1"))
        high_low = with_candle(self.candles, 4, low=self.candles[4].close + Decimal("1"))
        for candles in (low_high, high_low):
            with self.assertRaises(InvalidInferenceRequest) as raised:
                built(candles)
            self.assertIn("OHLC bounds", str(raised.exception))

    def test_a_repeated_timestamp_is_refused(self) -> None:
        """Two identical open times mean the caller concatenated two pages of klines and the overlap was
        not trimmed. Every rolling window then reads a bar twice, and none of them says so."""
        duplicated = with_candle(self.candles, 9, open_time=self.candles[8].open_time)
        with self.assertRaises(InvalidInferenceRequest) as raised:
            built(duplicated)
        self.assertIn("strictly increasing", str(raised.exception))

    def test_candles_out_of_order_are_refused_rather_than_sorted(self) -> None:
        """Sorting would be helpful and wrong: a window arriving out of order is a caller whose data
        pipeline is broken, and the sorted result would be a window it never intended to send."""
        reversed_pair = list(self.candles)
        reversed_pair[20], reversed_pair[21] = reversed_pair[21], reversed_pair[20]
        with self.assertRaises(InvalidInferenceRequest):
            built(tuple(reversed_pair))


class GapTests(unittest.TestCase):
    """Where the hole is decides whether the request is answerable. This is the whole distinction."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.candles = window(count = 203 + 8)

    def shifted(self, index: int) -> tuple[CandleInput, ...]:
        """Punch a one-hour hole by moving every candle from `index` onward an hour later.

        A shift rather than a deletion, so the window keeps its length and the *only* thing under test is
        the irregular step. Deleting a candle would change the count too, and a failure could then be
        either check.
        """
        mutated = list(self.candles)
        for position in range(index, len(mutated)):
            mutated[position] = replace(
                mutated[position], open_time=mutated[position].open_time + timedelta(hours=1)
            )
        return tuple(mutated)

    def test_a_gap_inside_the_warm_up_window_is_fatal(self) -> None:
        inside = self.shifted(len(self.candles) - 10)
        with self.assertRaises(InvalidInferenceRequest) as raised:
            built(inside)
        message = str(raised.exception)
        self.assertIn("warm-up", message)
        self.assertIn("do not describe", message)

    def test_a_gap_before_the_warm_up_window_is_a_warning_and_the_answer_stands(self) -> None:
        """The newest row's longest rolling window does not read this far back, so refusing would reject
        good data. Saying nothing would be worse than either — the caller cannot see its own hole."""
        before = self.shifted(3)
        result = built(before)
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("before the warm-up window", result.warnings[0])
        self.assertIn("the answer stands", result.warnings[0])
        # And it is still a real answer, not a degraded one.
        self.assertEqual(result.latest_index, len(before) - 1)
        self.assertGreater(result.atr, 0)

    def test_a_window_with_no_price_movement_is_refused(self) -> None:
        """A flat window has an ATR of zero, and every barrier the engine quotes is a multiple of it. The
        request is not answerable in the units the model consumes, so it is refused rather than divided by."""
        start = datetime(2026, 8, 1, tzinfo=timezone.utc)
        flat = tuple(
            CandleInput(
                open_time=start + timedelta(hours=index),
                open=Decimal("100"),
                high=Decimal("100"),
                low=Decimal("100"),
                close=Decimal("100"),
                volume=Decimal("1"),
            )
            for index in range(MINIMUM + 40)
        )
        with self.assertRaises(InvalidInferenceRequest) as raised:
            built(flat)
        self.assertIn("average true range", str(raised.exception))


class ClockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.candles = window()
        cls.result = built(cls.candles)

    def test_candle_open_time_is_the_newest_candle_supplied(self) -> None:
        self.assertEqual(self.result.candle_open_time, self.candles[-1].open_time)

    def test_validity_runs_to_the_close_of_the_next_candle_not_this_one(self) -> None:
        """The newest candle closed one step after it opened, which is already in the past by the time
        the caller reads the answer. What the answer describes stops being true when the *next* candle
        closes — two steps from the open — and a `valid_until` one step earlier would expire on arrival."""
        self.assertEqual(
            self.result.valid_until, self.candles[-1].open_time + timedelta(hours=2)
        )

    def test_the_path_starts_where_it_is_asked_to(self) -> None:
        """The bot advisor resolves a bracket against the same rows the digest was computed over. Reading
        the path from a second source is how a decision stops being replayable."""
        high, low, open_ = self.result.path_from(len(self.candles) - 3)
        self.assertEqual(len(high), 3)
        self.assertEqual(high[-1], float(self.candles[-1].high))
        self.assertEqual(low[0], float(self.candles[-3].low))
        self.assertEqual(open_[1], float(self.candles[-2].open))


class DigestTests(unittest.TestCase):
    """A digest that is a function of the *values*, in both directions it can fail."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.candles = window()

    def digest(self, candles=None, **overrides) -> str:
        return built(self.candles if candles is None else candles, **overrides).input_digest_sha256

    def test_the_same_question_twice_digests_identically(self) -> None:
        self.assertEqual(self.digest(), self.digest())

    def test_trailing_zeros_do_not_change_the_digest(self) -> None:
        """`Decimal("100.5")` and `Decimal("100.50")` are the same price and compare equal. A digest over
        their `str()` would differ, and a replay of a faithfully-stored decision would read as tampering."""
        padded = with_candle(
            self.candles, 40, close=self.candles[40].close.quantize(Decimal("0.00000000"))
        )
        self.assertNotEqual(str(padded[40].close), str(self.candles[40].close))
        self.assertEqual(padded[40].close, self.candles[40].close)
        self.assertEqual(self.digest(padded), self.digest())

    def test_the_bet_is_inside_the_digest_not_only_the_candles(self) -> None:
        """The same window at 2%/1% is a different decision from the same window at 4%/1%. A digest over
        candles alone would collide the two and certify the wrong one as replayed."""
        baseline = self.digest()
        for change in (
            {"take_profit_percent": Decimal("4")},
            {"stop_loss_percent": Decimal("2")},
            {"allow_short": False},
            {"max_holding_periods": 48},
            {"minimum_confidence": 0.6},
        ):
            with self.subTest(**change):
                self.assertNotEqual(
                    baseline, self.digest(parameters=replace(PARAMETERS, **change))
                )

    def test_a_changed_price_changes_the_digest(self) -> None:
        moved = with_candle(self.candles, 100, volume=self.candles[100].volume + Decimal("1"))
        self.assertNotEqual(self.digest(), self.digest(moved))

    def test_the_market_is_inside_the_digest(self) -> None:
        self.assertNotEqual(self.digest(), self.digest(symbol="ETHUSDT"))


if __name__ == "__main__":
    unittest.main()
