from __future__ import annotations

import unittest
from decimal import Decimal

import numpy as np

from crypto_signal.domain.direction import Direction, direction_from_wire, direction_to_wire
from crypto_signal.domain.levels import atr_multiple, barrier_prices, levels_for, percent_from_atr
from crypto_signal.domain.money import format_decimal, parse_decimal, quantize


class LevelArithmeticTests(unittest.TestCase):
    def test_a_long_targets_above_and_stops_below(self) -> None:
        levels = levels_for(Direction.LONG, entry_price=100.0, take_profit_percent=2.0,
                            stop_loss_percent=1.0, atr=1.0)

        self.assertAlmostEqual(levels.take_profit_price, 102.0)
        self.assertAlmostEqual(levels.stop_loss_price, 99.0)

    def test_a_short_targets_below_and_stops_above(self) -> None:
        levels = levels_for(Direction.SHORT, entry_price=100.0, take_profit_percent=2.0,
                            stop_loss_percent=1.0, atr=1.0)

        self.assertAlmostEqual(levels.take_profit_price, 98.0)
        self.assertAlmostEqual(levels.stop_loss_price, 101.0)

    def test_risk_reward_comes_from_the_requested_distances(self) -> None:
        levels = levels_for(Direction.LONG, entry_price=50_000.0, take_profit_percent=3.0,
                            stop_loss_percent=1.5, atr=250.0)

        self.assertAlmostEqual(levels.risk_reward_ratio, 2.0)

    def test_atr_multiples_make_two_markets_comparable(self) -> None:
        """The whole reason barriers reach the model in ATR units and not as percentages."""
        # 2% on a quiet market is a long reach; on a violent one it is noise.
        quiet = levels_for(Direction.LONG, entry_price=100.0, take_profit_percent=2.0,
                           stop_loss_percent=1.0, atr=0.5)
        violent = levels_for(Direction.LONG, entry_price=100.0, take_profit_percent=2.0,
                             stop_loss_percent=1.0, atr=4.0)

        self.assertAlmostEqual(quiet.take_profit_atr, 4.0)
        self.assertAlmostEqual(violent.take_profit_atr, 0.5)

    def test_atr_conversion_round_trips(self) -> None:
        entry, atr = 27_431.19, 183.4
        multiple = atr_multiple(entry, percent=1.75, atr=atr)

        self.assertAlmostEqual(percent_from_atr(entry, multiple, atr), 1.75)

    def test_barrier_prices_are_vectorised_over_rows(self) -> None:
        entries = np.array([100.0, 200.0, 400.0])
        take_profit, stop_loss = barrier_prices(Direction.LONG, entries, 2.0, 1.0)

        np.testing.assert_allclose(take_profit, [102.0, 204.0, 408.0])
        np.testing.assert_allclose(stop_loss, [99.0, 198.0, 396.0])


class LevelGuardTests(unittest.TestCase):
    def test_a_short_cannot_profit_at_a_price_of_zero(self) -> None:
        with self.assertRaises(ValueError):
            levels_for(Direction.SHORT, entry_price=100.0, take_profit_percent=100.0,
                       stop_loss_percent=1.0, atr=1.0)

    def test_a_long_cannot_stop_out_at_a_price_of_zero(self) -> None:
        with self.assertRaises(ValueError):
            levels_for(Direction.LONG, entry_price=100.0, take_profit_percent=2.0,
                       stop_loss_percent=100.0, atr=1.0)

    def test_a_zero_atr_cannot_be_expressed_in_atr_units(self) -> None:
        with self.assertRaises(ValueError):
            levels_for(Direction.LONG, entry_price=100.0, take_profit_percent=2.0,
                       stop_loss_percent=1.0, atr=0.0)

    def test_non_positive_requests_are_refused(self) -> None:
        for take_profit, stop_loss in ((0.0, 1.0), (2.0, 0.0), (-2.0, 1.0), (np.nan, 1.0)):
            with self.subTest(request=(take_profit, stop_loss)), self.assertRaises(ValueError):
                levels_for(Direction.LONG, entry_price=100.0, take_profit_percent=take_profit,
                           stop_loss_percent=stop_loss, atr=1.0)

    def test_flat_has_no_levels(self) -> None:
        with self.assertRaises(ValueError):
            barrier_prices(Direction.FLAT, 100.0, 2.0, 1.0)


class DirectionTests(unittest.TestCase):
    def test_signs_agree_with_a_signed_position(self) -> None:
        self.assertEqual(Direction.LONG.sign, 1)
        self.assertEqual(Direction.SHORT.sign, -1)
        self.assertEqual(Direction.FLAT.sign, 0)

    def test_flat_is_not_an_open_position(self) -> None:
        self.assertFalse(Direction.FLAT.is_open)
        self.assertTrue(Direction.LONG.is_open)
        self.assertTrue(Direction.SHORT.is_open)

    def test_wire_translation_round_trips(self) -> None:
        for direction in (Direction.LONG, Direction.SHORT, Direction.FLAT):
            with self.subTest(direction=direction):
                self.assertEqual(direction_from_wire(direction_to_wire(direction)), direction)

    def test_an_unset_direction_reads_as_flat_not_long(self) -> None:
        """A request that never said which way it faces is not carrying a position."""
        self.assertEqual(direction_from_wire(0), Direction.FLAT)

    def test_an_unknown_wire_value_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            direction_from_wire(9)


class MoneyTests(unittest.TestCase):
    def test_prices_render_with_fixed_places(self) -> None:
        self.assertEqual(format_decimal(77483.99), "77483.99000000")
        self.assertEqual(format_decimal(100), "100.00000000")

    def test_float_noise_does_not_reach_the_wire(self) -> None:
        """`Decimal(0.1)` is not 0.1; the shortest round-trip repr is the honest reading of a float."""
        self.assertEqual(format_decimal(0.1, places=4), "0.1000")
        self.assertEqual(quantize(0.1, places=18), Decimal("0.100000000000000000"))

    def test_small_prices_survive_eight_places(self) -> None:
        self.assertEqual(format_decimal(0.00000812), "0.00000812")

    def test_never_scientific_notation(self) -> None:
        rendered = format_decimal(1e-7)
        self.assertNotIn("e", rendered.lower())
        self.assertEqual(rendered, "0.00000010")

    def test_a_non_finite_price_is_refused(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                format_decimal(value)

    def test_parsing_accepts_the_venue_format(self) -> None:
        self.assertAlmostEqual(parse_decimal("77483.99000000"), 77483.99)

    def test_an_empty_price_is_not_zero(self) -> None:
        """A missing price is missing; a zero price is a free trade."""
        for text in ("", None):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_decimal(text, field="close")

    def test_garbage_is_refused_rather_than_coerced(self) -> None:
        for text in ("abc", "1.2.3", "nan", "Infinity"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_decimal(text, field="close")

    def test_round_trip_is_byte_stable(self) -> None:
        """The audit chain compares the characters, so formatting must be idempotent."""
        rendered = format_decimal(27_431.193456789)
        self.assertEqual(format_decimal(parse_decimal(rendered)), rendered)


if __name__ == "__main__":
    unittest.main()
