from __future__ import annotations

import unittest

import numpy as np

from crypto_signal.domain.barriers import (
    BarrierPair,
    Outcome,
    first_touch,
    resolve_first_touch,
    resolve_first_touch_scalar,
)
from crypto_signal.domain.direction import Direction
from crypto_signal.domain.levels import barrier_prices


def candles(rows: list[tuple[float, float, float, float]]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build (open, high, low, close) arrays from explicit OHLC rows."""
    array = np.asarray(rows, dtype=np.float64)
    return array[:, 0], array[:, 1], array[:, 2], array[:, 3]


def flat_barriers(rows: int, take_profit: float, stop_loss: float) -> tuple[np.ndarray, np.ndarray]:
    return np.full(rows, take_profit), np.full(rows, stop_loss)


class AmbiguousCandleTests(unittest.TestCase):
    """The rule that keeps a backtest from inventing profit: a tie goes to the adverse barrier."""

    def test_long_loses_a_candle_that_touches_both_barriers(self) -> None:
        # Candle 1 spans from below the stop to above the target. Which came first is unknowable.
        _, high, low, _ = candles([
            (100, 100, 100, 100),
            (100, 103, 98, 100),
            (100, 100, 100, 100),
        ])
        take_profit, stop_loss = flat_barriers(3, take_profit=102, stop_loss=99)

        outcome, resolved, bars_held, ambiguous = resolve_first_touch(
            high, low, take_profit, stop_loss, Direction.LONG, max_horizon=2
        )

        self.assertTrue(resolved[0])
        self.assertEqual(Outcome(outcome[0]), Outcome.STOP_LOSS_FIRST)
        self.assertTrue(ambiguous[0])
        self.assertEqual(bars_held[0], 1)

    def test_short_loses_a_candle_that_touches_both_barriers(self) -> None:
        """Adverse means the *upper* barrier for a short — the mirror, not the same barrier."""
        _, high, low, _ = candles([
            (100, 100, 100, 100),
            (100, 103, 98, 100),
            (100, 100, 100, 100),
        ])
        # Short: profit below at 99, stop above at 102 — the same two prices as the long above.
        take_profit, stop_loss = flat_barriers(3, take_profit=99, stop_loss=102)

        outcome, _, _, ambiguous = resolve_first_touch(
            high, low, take_profit, stop_loss, Direction.SHORT, max_horizon=2
        )

        self.assertEqual(Outcome(outcome[0]), Outcome.STOP_LOSS_FIRST)
        self.assertTrue(ambiguous[0])

    def test_a_tie_is_a_loss_for_both_sides_of_the_same_prices(self) -> None:
        """Why one label set cannot be read from both directions.

        Every unambiguous outcome mirrors: whoever touched first wins for one side and loses for the
        other. A tie does not mirror — it is a loss twice. A model trained on long-perspective labels
        and read backwards for shorts would therefore count every ambiguous candle as a short win.
        """
        entry = 100.0
        _, high, low, _ = candles([
            (100, 100, 100, 100),
            (100, 103, 98, 100),
            (100, 100, 100, 100),
        ])

        long_take_profit, long_stop_loss = barrier_prices(Direction.LONG, np.full(3, entry), 2.0, 1.0)
        short_take_profit, short_stop_loss = barrier_prices(Direction.SHORT, np.full(3, entry), 1.0, 2.0)

        # Same two prices, roles swapped.
        self.assertAlmostEqual(float(long_take_profit[0]), float(short_stop_loss[0]))
        self.assertAlmostEqual(float(long_stop_loss[0]), float(short_take_profit[0]))

        long_outcome, _, _, _ = resolve_first_touch(
            high, low, long_take_profit, long_stop_loss, Direction.LONG, max_horizon=2
        )
        short_outcome, _, _, _ = resolve_first_touch(
            high, low, short_take_profit, short_stop_loss, Direction.SHORT, max_horizon=2
        )

        self.assertEqual(Outcome(long_outcome[0]), Outcome.STOP_LOSS_FIRST)
        self.assertEqual(Outcome(short_outcome[0]), Outcome.STOP_LOSS_FIRST)


class FirstTouchOrderingTests(unittest.TestCase):
    def test_earlier_candle_wins(self) -> None:
        _, high, low, _ = candles([
            (100, 100, 100, 100),
            (100, 103, 100, 100),  # take-profit, alone
            (100, 100, 97, 100),   # stop-loss, later
        ])
        take_profit, stop_loss = flat_barriers(3, take_profit=102, stop_loss=99)

        outcome, _, bars_held, ambiguous = resolve_first_touch(
            high, low, take_profit, stop_loss, Direction.LONG, max_horizon=2
        )

        self.assertEqual(Outcome(outcome[0]), Outcome.TAKE_PROFIT_FIRST)
        self.assertEqual(bars_held[0], 1)
        self.assertFalse(ambiguous[0])

    def test_untouched_barriers_time_out_with_the_full_horizon_held(self) -> None:
        _, high, low, _ = candles([(100, 100.5, 99.5, 100)] * 5)
        take_profit, stop_loss = flat_barriers(5, take_profit=110, stop_loss=90)

        outcome, resolved, bars_held, _ = resolve_first_touch(
            high, low, take_profit, stop_loss, Direction.LONG, max_horizon=3
        )

        self.assertTrue(resolved[0])
        self.assertEqual(Outcome(outcome[0]), Outcome.TIMEOUT)
        self.assertEqual(bars_held[0], 3)

    def test_the_decision_candle_cannot_resolve_its_own_label(self) -> None:
        """Row i is a decision made on candle i; the scan starts at i+1.

        Candle 0 alone reaches the target. If the scan included it, row 0 would be labelled a win from
        a move that happened before the decision existed — look-ahead in its purest form.
        """
        _, high, low, _ = candles([
            (100, 105, 100, 100),  # only this candle touches 102
            (100, 100.2, 99.8, 100),
            (100, 100.2, 99.8, 100),
        ])
        take_profit, stop_loss = flat_barriers(3, take_profit=102, stop_loss=98)

        outcome, _, _, _ = resolve_first_touch(
            high, low, take_profit, stop_loss, Direction.LONG, max_horizon=2
        )

        self.assertEqual(Outcome(outcome[0]), Outcome.TIMEOUT)


class RightEdgeTests(unittest.TestCase):
    def test_rows_without_a_full_forward_window_are_unresolved(self) -> None:
        rows, horizon = 10, 3
        _, high, low, _ = candles([(100, 100.5, 99.5, 100)] * rows)
        take_profit, stop_loss = flat_barriers(rows, take_profit=110, stop_loss=90)

        _, resolved, _, _ = resolve_first_touch(
            high, low, take_profit, stop_loss, Direction.LONG, max_horizon=horizon
        )

        self.assertTrue(resolved[: rows - horizon].all())
        self.assertFalse(resolved[rows - horizon :].any())

    def test_a_window_shorter_than_the_horizon_resolves_nothing(self) -> None:
        _, high, low, _ = candles([(100, 100.5, 99.5, 100)] * 3)
        take_profit, stop_loss = flat_barriers(3, take_profit=110, stop_loss=90)

        _, resolved, _, _ = resolve_first_touch(
            high, low, take_profit, stop_loss, Direction.LONG, max_horizon=5
        )

        self.assertFalse(resolved.any())


class VectorisedMatchesReferenceTests(unittest.TestCase):
    """The strided implementation is fast and easy to get subtly wrong; the loop is the specification."""

    def _random_walk(self, rows: int, seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        generator = np.random.default_rng(seed)
        close = 100 * np.exp(np.cumsum(generator.normal(0, 0.01, rows)))
        open_ = np.concatenate([[close[0]], close[:-1]])
        wick = np.abs(generator.normal(0, 0.008, rows)) * close
        high = np.maximum(open_, close) + wick
        low = np.minimum(open_, close) - wick
        return open_, high, low, close

    def test_agreement_across_directions_and_horizons(self) -> None:
        _, high, low, close = self._random_walk(rows=400, seed=7)

        for direction in (Direction.LONG, Direction.SHORT):
            for take_profit_percent, stop_loss_percent in ((2.0, 1.0), (0.5, 0.5), (1.0, 3.0)):
                for horizon in (1, 4, 24):
                    take_profit, stop_loss = barrier_prices(
                        direction, close, take_profit_percent, stop_loss_percent
                    )
                    fast = resolve_first_touch(high, low, take_profit, stop_loss, direction, horizon)
                    slow = resolve_first_touch_scalar(
                        high, low, take_profit, stop_loss, direction, horizon
                    )

                    with self.subTest(direction=direction, horizon=horizon,
                                      barriers=(take_profit_percent, stop_loss_percent)):
                        for name, left, right in zip(
                            ("outcome", "resolved", "bars_held", "ambiguous"), fast, slow
                        ):
                            np.testing.assert_array_equal(left, right, err_msg=name)

    def test_tight_barriers_produce_ambiguous_candles(self) -> None:
        """Guards the assumption behind keeping ambiguity as a labelled outcome.

        If ties were vanishingly rare, dropping those rows would be the cleaner design. They are not:
        at half-ATR-scale barriers a large share of candles span both, and dropping them would delete
        exactly the violent candles a risk model most needs to have seen.
        """
        _, high, low, close = self._random_walk(rows=600, seed=11)
        take_profit, stop_loss = barrier_prices(Direction.LONG, close, 0.4, 0.4)

        _, resolved, _, ambiguous = resolve_first_touch(
            high, low, take_profit, stop_loss, Direction.LONG, max_horizon=12
        )

        share = ambiguous[resolved].mean()
        self.assertGreater(share, 0.05, "expected tight barriers to produce ties worth labelling")


class SinglePositionTests(unittest.TestCase):
    """`first_touch` is the backtester's path: it holds from the fill candle and models the fill price."""

    def test_the_entry_candle_can_resolve_the_position(self) -> None:
        open_, high, low, _ = candles([
            (100, 100, 100, 100),
            (100, 103, 100, 102),  # the candle we are filled on reaches the target
        ])

        result = first_touch(
            high, low, open_, entry_index=1, take_profit_price=102, stop_loss_price=99,
            direction=Direction.LONG, max_horizon=3,
        )

        self.assertEqual(result.outcome, Outcome.TAKE_PROFIT_FIRST)
        self.assertEqual(result.bars_held, 1)
        self.assertEqual(result.exit_price, 102)

    def test_take_profit_fills_at_its_own_price_however_far_the_candle_ran(self) -> None:
        open_, high, low, _ = candles([(100, 130, 100, 128)])

        result = first_touch(
            high, low, open_, entry_index=0, take_profit_price=102, stop_loss_price=99,
            direction=Direction.LONG, max_horizon=1,
        )

        self.assertEqual(result.exit_price, 102, "a resting limit order does not fill better than its price")

    def test_a_candle_that_gaps_through_the_stop_fills_at_the_open(self) -> None:
        """The gap is charged to the trade, because that is where the exchange charges it."""
        open_, high, low, _ = candles([
            (100, 100, 100, 100),
            (95, 96, 94, 95),  # opened below the 99 stop
        ])

        result = first_touch(
            high, low, open_, entry_index=1, take_profit_price=102, stop_loss_price=99,
            direction=Direction.LONG, max_horizon=2,
        )

        self.assertEqual(result.outcome, Outcome.STOP_LOSS_FIRST)
        self.assertEqual(result.exit_price, 95)

    def test_a_stop_touched_intrabar_fills_at_the_stop(self) -> None:
        open_, high, low, _ = candles([(100, 100.5, 98, 99.5)])

        result = first_touch(
            high, low, open_, entry_index=0, take_profit_price=102, stop_loss_price=99,
            direction=Direction.LONG, max_horizon=1,
        )

        self.assertEqual(result.exit_price, 99)

    def test_a_short_gapping_up_through_its_stop_fills_at_the_open(self) -> None:
        open_, high, low, _ = candles([(105, 106, 104, 105)])

        result = first_touch(
            high, low, open_, entry_index=0, take_profit_price=99, stop_loss_price=102,
            direction=Direction.SHORT, max_horizon=1,
        )

        self.assertEqual(result.outcome, Outcome.STOP_LOSS_FIRST)
        self.assertEqual(result.exit_price, 105)

    def test_a_truncated_window_does_not_count_as_a_timeout(self) -> None:
        open_, high, low, _ = candles([(100, 100.5, 99.5, 100)] * 2)

        result = first_touch(
            high, low, open_, entry_index=0, take_profit_price=110, stop_loss_price=90,
            direction=Direction.LONG, max_horizon=10,
        )

        self.assertEqual(result.outcome, Outcome.TIMEOUT)
        self.assertFalse(result.resolved)


class BarrierPairTests(unittest.TestCase):
    def test_mirroring_swaps_the_two_distances(self) -> None:
        pair = BarrierPair(take_profit_atr=2.0, stop_loss_atr=1.0)
        mirrored = pair.mirrored()

        self.assertEqual(mirrored.take_profit_atr, 1.0)
        self.assertEqual(mirrored.stop_loss_atr, 2.0)
        self.assertEqual(mirrored.mirrored(), pair)

    def test_risk_reward_is_reward_over_risk(self) -> None:
        self.assertAlmostEqual(BarrierPair(3.0, 1.5).risk_reward_ratio, 2.0)

    def test_a_zero_or_negative_or_infinite_distance_is_refused(self) -> None:
        for take_profit, stop_loss in ((0.0, 1.0), (1.0, 0.0), (-1.0, 1.0), (np.inf, 1.0), (1.0, np.nan)):
            with self.subTest(barriers=(take_profit, stop_loss)), self.assertRaises(ValueError):
                BarrierPair(take_profit_atr=take_profit, stop_loss_atr=stop_loss)


class GuardTests(unittest.TestCase):
    def test_flat_has_no_barriers(self) -> None:
        _, high, low, _ = candles([(100, 101, 99, 100)] * 3)
        take_profit, stop_loss = flat_barriers(3, take_profit=102, stop_loss=98)

        with self.assertRaises(ValueError):
            resolve_first_touch(high, low, take_profit, stop_loss, Direction.FLAT, max_horizon=2)

    def test_a_horizon_below_one_candle_is_refused(self) -> None:
        _, high, low, _ = candles([(100, 101, 99, 100)] * 3)
        take_profit, stop_loss = flat_barriers(3, take_profit=102, stop_loss=98)

        with self.assertRaises(ValueError):
            resolve_first_touch(high, low, take_profit, stop_loss, Direction.LONG, max_horizon=0)

    def test_mismatched_array_lengths_are_refused(self) -> None:
        _, high, low, _ = candles([(100, 101, 99, 100)] * 3)

        with self.assertRaises(ValueError):
            resolve_first_touch(high, low, np.full(2, 102.0), np.full(3, 98.0), Direction.LONG, 2)


if __name__ == "__main__":
    unittest.main()
