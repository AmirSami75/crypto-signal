"""What the bracket simulator books, on candles whose answer can be worked out by hand.

A backtest is the one component nobody can check by using the product: it reports its own grade. Every
test here fixes a number that a plausible-looking implementation would get wrong in the profitable
direction — booking a gapped entry as an instant win, dropping the trades that never resolved, slipping
a limit order, resolving an ambiguous candle in the trade's favour, or letting one candle's move be
counted by two open positions.

The two invariants worth stating outright, because they are what tie this simulator to the model it
scores: with costs switched off, a take-profit win must return exactly `take_profit_atr` and a stop-loss
loss exactly `-stop_loss_atr`. Those are the values `domain.expectancy` multiplies by the model's
probabilities, so if the simulator disagreed with them the reported expectancy and the model's own
expected value would be quoted in different units while looking comparable.
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from crypto_signal.domain import Direction, Outcome
from crypto_signal.evaluation import BracketCosts, run_bracket_backtest


FREE = BracketCosts(fee_rate=0.0, slippage_rate=0.0)
ATR = 1.0


def candles(
    rows: list[tuple[float, float, float, float]],
    signals: dict[int, int] | None = None,
    take_profit_percent: float = 2.0,
    stop_loss_percent: float = 1.0,
) -> pd.DataFrame:
    """A decision frame from `(open, high, low, close)` rows and the bars carrying a signal.

    ATR is pinned at 1.0 against a price near 100, so a 2% barrier is 2 ATR and the ATR-unit assertions
    read directly off the percentages.
    """
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=len(rows), freq="1h", tz="UTC"),
            "open": [row[0] for row in rows],
            "high": [row[1] for row in rows],
            "low": [row[2] for row in rows],
            "close": [row[3] for row in rows],
            "atr": [ATR] * len(rows),
            "direction": [(signals or {}).get(index, 0) for index in range(len(rows))],
            "take_profit_percent": [take_profit_percent] * len(rows),
            "stop_loss_percent": [stop_loss_percent] * len(rows),
        }
    )


def flat(price: float) -> tuple[float, float, float, float]:
    """A candle that goes nowhere, for padding a fixture without touching a barrier."""
    return (price, price, price, price)


def run(frame: pd.DataFrame, max_horizon: int = 6, costs: BracketCosts = FREE):
    return run_bracket_backtest(frame, "1h", max_horizon=max_horizon, costs=costs)


class ResolutionTests(unittest.TestCase):
    def test_a_take_profit_returns_exactly_the_reward_it_was_promised(self) -> None:
        """The invariant tying this simulator to the model's expected value."""
        frame = candles(
            [flat(100), (100, 101, 99.5, 100.5), (100.5, 102.5, 100, 102), flat(102)],
            signals={0: Direction.LONG},
        )
        trades, _ = run(frame)
        trade = trades.iloc[0]
        self.assertEqual(trade.outcome, Outcome.TAKE_PROFIT_FIRST)
        self.assertEqual(trade.exit_price, 102.0, "a limit order fills at its own price")
        self.assertAlmostEqual(trade.return_atr, trade.take_profit_atr, places=9)

    def test_a_stop_loss_returns_exactly_the_risk_it_was_told_to_take(self) -> None:
        frame = candles(
            [flat(100), (100, 100.5, 99.5, 100), (100, 100, 98.9, 99), flat(99)],
            signals={0: Direction.LONG},
        )
        trades, _ = run(frame)
        trade = trades.iloc[0]
        self.assertEqual(trade.outcome, Outcome.STOP_LOSS_FIRST)
        self.assertAlmostEqual(trade.return_atr, -trade.stop_loss_atr, places=9)

    def test_a_candle_that_reached_both_barriers_is_booked_as_the_loss(self) -> None:
        """The rule the labeller uses, and the one place optimism would be free money.

        Intrabar order is unknowable from an OHLC candle. Resolving it in the trade's favour would credit
        the strategy for a coin flip it never won, on exactly the candles where the market was violent.
        """
        for direction in (Direction.LONG, Direction.SHORT):
            with self.subTest(direction=direction.name):
                frame = candles(
                    [flat(100), (100, 102.5, 97.5, 100), flat(100)], signals={0: direction}
                )
                trades, _ = run(frame)
                trade = trades.iloc[0]
                self.assertEqual(trade.outcome, Outcome.STOP_LOSS_FIRST)
                self.assertTrue(trade.ambiguous, "and it is recorded as a tie-break, not as an observation")

    def test_a_short_watches_the_same_two_prices_from_the_other_side(self) -> None:
        frame = candles(
            [flat(100), (100, 100.5, 99, 100), (100, 100, 97.5, 98), flat(98)],
            signals={0: Direction.SHORT},
        )
        trades, _ = run(frame)
        trade = trades.iloc[0]
        self.assertEqual((trade.take_profit_price, trade.stop_loss_price), (98.0, 101.0))
        self.assertEqual(trade.outcome, Outcome.TAKE_PROFIT_FIRST)
        self.assertAlmostEqual(trade.return_atr, trade.take_profit_atr, places=9)

    def test_a_timeout_exits_at_the_horizon_close_rather_than_disappearing(self) -> None:
        """Dropping unresolved trades keeps the paths that drifted toward the far barrier.

        That is the same selection bias `domain.expectancy` refuses at the probability level; arriving
        through the simulator instead would be no less flattering.
        """
        frame = candles([flat(100)] + [(100, 100.5, 99.5, 100.25)] * 5, signals={0: Direction.LONG})
        trades, metrics = run(frame, max_horizon=3)
        trade = trades.iloc[0]
        self.assertEqual(trade.outcome, Outcome.TIMEOUT)
        self.assertEqual(trade.bars_held, 3)
        self.assertEqual(trade.exit_price, 100.25, "the close of the last candle it was allowed to hold")
        self.assertTrue(trade.resolved, "three of three candles is a real timeout")
        self.assertEqual(metrics["trades"]["timeouts"], 1)
        self.assertAlmostEqual(trade.net_return, 0.0025, places=9)

    def test_a_position_still_open_when_the_data_ends_is_liquidated_not_credited(self) -> None:
        """A horizon the data cannot cover proves nothing, so the trade is marked rather than trusted."""
        frame = candles([flat(100)] + [(100, 100.5, 99.5, 100.4)] * 2, signals={0: Direction.LONG})
        trades, metrics = run(frame, max_horizon=10)
        trade = trades.iloc[0]
        self.assertEqual(trade.outcome, Outcome.TIMEOUT)
        self.assertFalse(trade.resolved)
        self.assertEqual(trade.exit_index, 2, "the last candle there is")
        self.assertEqual(metrics["trades"]["unresolved_at_end"], 1)


class EntryTests(unittest.TestCase):
    def test_a_decision_is_filled_on_the_candle_after_it(self) -> None:
        """The decision is computed from a closed candle, so the next open is the earliest fill."""
        frame = candles([flat(100), (101, 101, 101, 101), flat(101)], signals={0: Direction.LONG})
        trades, _ = run(frame)
        trade = trades.iloc[0]
        self.assertEqual((trade.decision_index, trade.fill_index), (0, 1))
        self.assertEqual(trade.decision_close, 100.0)
        self.assertEqual(trade.fill_price, 101.0)

    def test_a_fill_that_has_already_gapped_past_the_target_is_not_a_trade(self) -> None:
        """Booking it would turn latency into profit; booking it as a loss would invent one too."""
        frame = candles([flat(100), (103, 104, 103, 103.5), flat(103.5)], signals={0: Direction.LONG})
        trades, metrics = run(frame)
        self.assertTrue(trades.empty)
        self.assertEqual(metrics["trades"]["stale_entries_skipped"], 1)

    def test_a_fill_that_has_already_gapped_past_the_stop_is_not_a_trade_either(self) -> None:
        frame = candles([flat(100), (98, 98, 97, 97.5), flat(97.5)], signals={0: Direction.LONG})
        trades, metrics = run(frame)
        self.assertTrue(trades.empty)
        self.assertEqual(metrics["trades"]["stale_entries_skipped"], 1)

    def test_the_bracket_stays_anchored_to_the_decision_close(self) -> None:
        """What the orchestrator places is computed from the signal, so the entry gap eats into the bet.

        Here the fill is 0.5 above the close, which for a long moves it toward the target: the realised
        ratio is (102 - 100.5) / (100.5 - 99) = 1.0 against a requested 2.0. Re-anchoring the levels to
        the fill would report 2.0 and hide the whole effect.
        """
        frame = candles([flat(100), (100.5, 100.6, 100.4, 100.5), flat(100.5)], signals={0: Direction.LONG})
        trades, metrics = run(frame)
        trade = trades.iloc[0]
        self.assertEqual((trade.take_profit_price, trade.stop_loss_price), (102.0, 99.0))
        self.assertAlmostEqual(trade.realised_risk_reward, 1.0, places=9)
        self.assertAlmostEqual(trade.entry_gap_percent, 0.5, places=9)
        self.assertEqual(metrics["trades"]["requested_risk_reward"], 2.0)


class CostTests(unittest.TestCase):
    PAID = BracketCosts(fee_rate=0.001, slippage_rate=0.0005)

    def test_slippage_moves_a_market_entry_against_the_position(self) -> None:
        for direction, expected in ((Direction.LONG, 100.05), (Direction.SHORT, 99.95)):
            with self.subTest(direction=direction.name):
                frame = candles([flat(100), flat(100), flat(100)], signals={0: direction})
                trades, _ = run(frame, costs=self.PAID)
                self.assertAlmostEqual(trades.iloc[0].fill_price, expected, places=9)

    def test_a_take_profit_does_not_slip_because_a_limit_order_cannot(self) -> None:
        """Charging slippage here would penalise precisely the trades the strategy got right."""
        frame = candles(
            [flat(100), (100, 101, 99.5, 100.5), (100.5, 102.5, 100, 102), flat(102)],
            signals={0: Direction.LONG},
        )
        trades, _ = run(frame, costs=self.PAID)
        self.assertEqual(trades.iloc[0].exit_price, 102.0)

    def test_a_stop_loss_slips_because_it_becomes_a_market_order(self) -> None:
        frame = candles(
            [flat(100), (100, 100.5, 99.5, 100), (100, 100, 98.9, 99), flat(99)],
            signals={0: Direction.LONG},
        )
        trades, _ = run(frame, costs=self.PAID)
        self.assertAlmostEqual(trades.iloc[0].exit_price, 99.0 * (1 - 0.0005), places=9)

    def test_a_candle_that_opened_through_the_stop_is_filled_at_that_open(self) -> None:
        """The gap is charged to the trade, which is where a real venue puts it."""
        frame = candles([flat(100), flat(100), (95, 100, 94, 96), flat(96)], signals={0: Direction.LONG})
        trades, _ = run(frame)
        trade = trades.iloc[0]
        self.assertEqual(trade.outcome, Outcome.STOP_LOSS_FIRST)
        self.assertEqual(trade.exit_price, 95.0, "not the 99.0 the stop asked for")
        self.assertLess(trade.net_return, -0.04)

    def test_a_timeout_exit_slips_because_it_is_a_market_order(self) -> None:
        frame = candles([flat(100)] + [(100, 100.5, 99.5, 100.25)] * 4, signals={0: Direction.LONG})
        trades, _ = run(frame, max_horizon=3, costs=self.PAID)
        self.assertAlmostEqual(trades.iloc[0].exit_price, 100.25 * (1 - 0.0005), places=9)

    def test_the_fee_is_charged_on_both_notionals(self) -> None:
        """Approximating the exit notional by the entry one would understate a winner's cost."""
        frame = candles(
            [flat(100), (100, 101, 99.5, 100.5), (100.5, 102.5, 100, 102), flat(102)],
            signals={0: Direction.LONG},
        )
        trades, _ = run(frame, costs=self.PAID)
        trade = trades.iloc[0]
        self.assertAlmostEqual(trade.fee_cost, 0.001 * (2 + trade.gross_return), places=12)
        self.assertAlmostEqual(trade.net_return, trade.gross_return - trade.fee_cost, places=12)


class SequencingTests(unittest.TestCase):
    def test_a_signal_arriving_mid_trade_is_ignored(self) -> None:
        """Overlapping positions on one symbol count a single move once per open trade."""
        frame = candles(
            [flat(100), (100, 100.5, 99.5, 100), (100, 100, 98.9, 99), flat(99), flat(99)],
            signals={0: Direction.LONG, 1: Direction.LONG},
        )
        trades, _ = run(frame)
        self.assertEqual(len(trades), 1)

    def test_the_next_decision_read_is_the_one_on_the_bar_the_exit_happened(self) -> None:
        """The position closed intrabar, so that bar's close is actionable — no invented cooldown."""
        frame = candles(
            [
                flat(100),
                (100, 100.5, 99.5, 100),
                (100, 100, 98.9, 99),  # stop hit here; this close is the next decision
                (99, 99, 98.01, 98.1),
                flat(98.1),
            ],
            signals={0: Direction.LONG, 2: Direction.LONG},
        )
        trades, _ = run(frame)
        self.assertEqual(len(trades), 2)
        self.assertEqual(trades.iloc[0].exit_index, 2)
        self.assertEqual(trades.iloc[1].decision_index, 2)
        self.assertEqual(trades.iloc[1].fill_index, 3)

    def test_a_signal_on_the_final_candle_cannot_be_filled(self) -> None:
        frame = candles([flat(100), flat(100)], signals={1: Direction.LONG})
        trades, metrics = run(frame)
        self.assertTrue(trades.empty)
        self.assertEqual(metrics["trades"]["stale_entries_skipped"], 0, "unfillable is not stale")

    def test_the_frame_is_read_in_time_order_however_it_arrives(self) -> None:
        frame = candles(
            [flat(100), (100, 100.5, 99.5, 100), (100, 100, 98.9, 99), flat(99)],
            signals={0: Direction.LONG},
        )
        shuffled = frame.iloc[[2, 0, 3, 1]].reset_index(drop=True)
        trades, _ = run(shuffled)
        self.assertEqual(trades.iloc[0].decision_index, 0)
        self.assertEqual(trades.iloc[0].outcome, Outcome.STOP_LOSS_FIRST)


class ExcursionTests(unittest.TestCase):
    def test_the_worst_the_trade_looked_is_measured_over_the_bars_it_was_held(self) -> None:
        frame = candles(
            [flat(100), (100, 100.2, 99.2, 100), (100, 102.5, 100, 102), (102, 110, 90, 102)],
            signals={0: Direction.LONG},
        )
        trades, metrics = run(frame)
        trade = trades.iloc[0]
        self.assertAlmostEqual(trade.adverse_excursion_percent, -0.8, places=9)
        self.assertAlmostEqual(trade.favourable_excursion_percent, 2.5, places=9)
        self.assertEqual(trade.exit_index, 2, "the fourth candle's 90/110 range is after the exit")
        self.assertAlmostEqual(metrics["trades"]["worst_adverse_excursion_percent"], -0.8, places=9)

    def test_an_adverse_excursion_is_negative_for_a_short_as_well(self) -> None:
        """Otherwise the worst-case figure, taken as a minimum, would report a short's best moment."""
        frame = candles(
            [flat(100), (100, 100.8, 99.8, 100), (100, 100, 97.5, 98), flat(98)],
            signals={0: Direction.SHORT},
        )
        trades, _ = run(frame)
        self.assertAlmostEqual(trades.iloc[0].adverse_excursion_percent, -0.8, places=9)
        self.assertAlmostEqual(trades.iloc[0].favourable_excursion_percent, 2.5, places=9)


class MetricTests(unittest.TestCase):
    def test_the_win_rate_the_account_sees_and_the_one_the_model_predicts_are_both_reported(self) -> None:
        """A timeout closing a hair up is a winning trade but not a predicted win; they are not the same.

        Two long signals: the first times out slightly profitable, the second stops out. So the account
        won one of two, while the model got none of the one bet that resolved.
        """
        frame = candles(
            [
                flat(100),
                (100, 100.4, 99.6, 100.2),
                (100.2, 100.4, 99.8, 100.3),  # timeout exits here at max_horizon=2
                (100.3, 100.4, 98.9, 99),
                flat(99),
            ],
            signals={0: Direction.LONG, 2: Direction.LONG},
        )
        trades, metrics = run(frame, max_horizon=2)
        self.assertEqual(len(trades), 2)
        self.assertEqual(metrics["trades"]["win_rate"], 0.5)
        self.assertEqual(metrics["trades"]["win_rate_resolved"], 0.0)

    def test_a_run_with_no_losses_reports_no_profit_factor_rather_than_infinity(self) -> None:
        """Infinity is not a number a report can carry, and it reads as a bug rather than as a clean run."""
        frame = candles(
            [flat(100), (100, 101, 99.5, 100.5), (100.5, 102.5, 100, 102), flat(102)],
            signals={0: Direction.LONG},
        )
        _, metrics = run(frame)
        self.assertEqual(metrics["trades"]["take_profit_first"], 1)
        self.assertIsNone(metrics["trades"]["profit_factor"])

    def test_the_break_even_rate_values_timeouts_at_what_they_actually_did(self) -> None:
        """`timeout_value_atr` exists for this caller: a simulator sees the horizon close, it does not guess.

        A 2:1 bet whose timeouts closed *up* needs a lower win rate to pay than one whose timeouts closed
        flat, and the yardstick has to move with them or it flatters a strategy that loses slowly.

        Both runs are the same two trades — one stop-loss, one timeout — and differ only in the final
        candle's close, which is where the timeout exits and which anchors nothing else.
        """

        def two_trades(final_close: float) -> pd.DataFrame:
            return candles(
                [
                    flat(100),
                    (100, 100.2, 98.5, 99),  # stops out at 99, and this close is the next decision
                    (99, 99.5, 98.5, 99.2),
                    (99, 99.5, 98.5, final_close),  # the timeout leaves here
                ],
                signals={0: Direction.LONG, 1: Direction.LONG},
            )

        rising, rising_metrics = run(two_trades(99.4), max_horizon=2)
        flat_run, flat_metrics = run(two_trades(99.0), max_horizon=2)
        for trades, metrics in ((rising, rising_metrics), (flat_run, flat_metrics)):
            self.assertEqual(list(trades["outcome"]), [Outcome.STOP_LOSS_FIRST, Outcome.TIMEOUT])
            self.assertEqual(metrics["trades"]["timeouts"], 1)
        self.assertAlmostEqual(rising.iloc[1].return_atr, 0.4, places=6)
        self.assertAlmostEqual(flat_run.iloc[1].return_atr, 0.0, places=9)
        # Read off the requested rung: neither run has a winning trade, so the realised rungs have no
        # realised win magnitude to average and correctly report nothing at all.
        self.assertIsNone(rising_metrics["trades"]["break_even_win_rate"])
        self.assertLess(
            rising_metrics["trades"]["break_even_win_rate_requested"],
            flat_metrics["trades"]["break_even_win_rate_requested"],
        )

    def test_the_break_even_rate_and_the_expectancy_can_never_disagree(self) -> None:
        """The property the requested-distance rung lacked, and the reason this one replaced it.

        Grading a costed result against a cost-free bar let the report claim a positive edge over
        break-even beside a negative expectancy — which is how a losing strategy reads as a working one.
        Solving for the rate at which the *realised* means cancel makes the two the same arithmetic, so
        `win_rate_resolved > break_even_win_rate` and `expectancy_atr > 0` agree by construction.

        Same three bets under three fee schedules. The first pays, the last does not, and the crossing is
        the fee — nothing about the model or the candles changes.
        """
        frame = candles(
            [
                flat(100),
                (100, 102.5, 99.5, 102),  # takes profit at 102
                (102, 102.5, 100.5, 101),  # decision; 2% target 103.02, 1% stop 99.99
                (101, 101.5, 99.5, 100),  # stops out at 99.99
                (100, 102.5, 99.8, 102.1),  # decision
                (102.1, 102.5, 99, 99.5),  # stops out at 99
                flat(99),
            ],
            signals={0: Direction.LONG, 2: Direction.LONG, 4: Direction.LONG},
        )
        for fee in (0.0, 0.002, 0.006):
            with self.subTest(fee=fee):
                _, metrics = run(frame, max_horizon=3, costs=BracketCosts(fee, 0.0))
                statistics = metrics["trades"]
                bar = statistics["break_even_win_rate"]
                self.assertIsNotNone(bar)
                self.assertEqual(
                    statistics["expectancy_atr"] > 0,
                    statistics["win_rate_resolved"] > bar,
                    msg=f"expectancy {statistics['expectancy_atr']:+.4f} disagrees with edge "
                    f"{statistics['edge_over_break_even']:+.4f}",
                )

    def test_the_bar_rises_with_the_fee_while_the_before_fees_bar_does_not(self) -> None:
        """The rung that separates a model that is wrong from a bracket that is too cheap to pay for.

        A win rate above the before-fees bar and below the net one is a real directional edge being eaten
        by the venue — a bracket problem, whose remedy (a wider target) is the opposite of the remedy for
        a model problem. Holding the before-fees rung still across three fee schedules is what makes the
        distinction readable rather than a coincidence of one run.
        """
        frame = candles(
            [flat(100), (100, 102.5, 99.5, 102), (102, 102.5, 101, 101.5), (101.5, 101.6, 99, 99.2)],
            signals={0: Direction.LONG, 2: Direction.LONG},
        )
        bars = {}
        for fee in (0.0, 0.001, 0.003):
            _, metrics = run(frame, max_horizon=3, costs=BracketCosts(fee, 0.0))
            bars[fee] = (
                metrics["trades"]["break_even_win_rate"],
                metrics["trades"]["break_even_win_rate_before_fees"],
                metrics["trades"]["mean_fee_atr"],
            )
        net = [bars[fee][0] for fee in (0.0, 0.001, 0.003)]
        self.assertEqual(net, sorted(net))
        self.assertLess(net[0], net[-1])
        before = [bars[fee][1] for fee in (0.0, 0.001, 0.003)]
        for value in before[1:]:
            self.assertAlmostEqual(value, before[0], places=9)
        # With no fee the two rungs are the same bar, and the fee in ATR units is what separates them.
        self.assertAlmostEqual(bars[0.0][0], bars[0.0][1], places=12)
        self.assertAlmostEqual(bars[0.0][2], 0.0, places=12)
        self.assertGreater(bars[0.003][2], bars[0.001][2])

    def test_the_atr_averages_reconstruct_the_expectancy_the_percent_ones_cannot(self) -> None:
        """Why the ATR-unit pair was added beside the percent pair rather than instead of it.

        A percent average mixes trades whose barriers sat at different fractions of price, so on a model
        that wins in quiet bars and loses in volatile ones the mean win comes out *smaller* than the mean
        loss on a bracket that requested the reverse — the shape of an inverted bracket, from a simulator
        that never inverted one. Here the two winners' ATR is a quarter of the loser's, which is enough to
        put the percent pair on the wrong side of each other while the ATR pair stays ordered.
        """
        frame = candles(
            [
                flat(100),
                (100, 100.6, 99.9, 100.5),  # the quiet winner: reaches a 0.5% target
                flat(100),
                (100, 100.5, 97.5, 98),  # the volatile loser: through a 2% stop
                flat(98),
            ],
            signals={0: Direction.LONG, 2: Direction.LONG},
        )
        # Barriers in percent are *derived* from ATR upstream, so a quiet bar carries a narrow bracket and
        # a volatile one a wide bracket. Both bets here are the same 2:1 request in ATR units.
        frame.loc[0, ["atr", "take_profit_percent", "stop_loss_percent"]] = [0.25, 0.5, 0.25]
        frame.loc[2, ["atr", "take_profit_percent", "stop_loss_percent"]] = [2.0, 4.0, 2.0]
        trades, metrics = run(frame, max_horizon=3)
        statistics = metrics["trades"]
        self.assertEqual(list(trades["outcome"]), [Outcome.TAKE_PROFIT_FIRST, Outcome.STOP_LOSS_FIRST])
        # The percent pair says the win was smaller than the loss; the ATR pair says the opposite, and the
        # ATR pair is the one whose units the barriers were requested in.
        self.assertLess(
            statistics["average_win_percent"], abs(statistics["average_loss_percent"])
        )
        self.assertGreater(statistics["average_win_atr"], abs(statistics["average_loss_atr"]))
        # And they reconstruct the headline exactly, which the percent pair cannot be made to do.
        resolved = statistics["take_profit_first"] + statistics["stop_loss_first"]
        rebuilt = (
            statistics["take_profit_first"] * statistics["average_win_atr"]
            + statistics["stop_loss_first"] * statistics["average_loss_atr"]
        ) / resolved
        self.assertAlmostEqual(rebuilt, statistics["expectancy_atr"], places=12)

    def test_a_bracket_whose_fee_exceeds_its_target_has_no_reachable_break_even(self) -> None:
        """Not a rate to aim at but a bet that cannot pay, and the honest report of it is silence.

        A fee larger than the take-profit turns every winning trade into a loss, at which point no win
        rate makes the strategy break even. Returning a number here — 1.0, say — would read as a hard but
        achievable target rather than as a bracket nobody should place.
        """
        frame = candles(
            [flat(100), (100, 102.5, 99.5, 102), (102, 102.5, 101.5, 102), (102, 102.5, 99, 99.4)],
            signals={0: Direction.LONG, 2: Direction.LONG},
        )
        _, metrics = run(frame, max_horizon=3, costs=BracketCosts(fee_rate=0.02, slippage_rate=0.0))
        self.assertLess(metrics["trades"]["average_win_atr"], 0)
        self.assertIsNone(metrics["trades"]["break_even_win_rate"])
        self.assertIsNone(metrics["trades"]["edge_over_break_even"])
        # The requested rung still answers, because it never knew about the fee in the first place.
        self.assertIsNotNone(metrics["trades"]["break_even_win_rate_requested"])

    def test_a_set_of_bets_that_all_timed_out_has_no_break_even_rate(self) -> None:
        """No win rate makes a bet pay when none of it ever resolves; the honest answer is silence."""
        frame = candles([flat(100)] + [(100, 100.5, 99.5, 100.1)] * 3, signals={0: Direction.LONG})
        _, metrics = run(frame, max_horizon=2)
        self.assertEqual(metrics["trades"]["timeouts"], 1)
        self.assertIsNone(metrics["trades"]["break_even_win_rate"])
        self.assertIsNone(metrics["trades"]["edge_over_break_even"])

    def test_the_realised_risk_reward_is_a_median_because_its_denominator_can_approach_zero(self) -> None:
        """One fill that opened a whisker above its stop must not become the headline ratio.

        The realised ratio divides by the distance from the fill to the stop. Three trades here: two land
        exactly on the requested 2.0, and the third fills a cent above its stop, which sends its ratio past
        290. A mean would report roughly 98 for a strategy that never asked for more than 2.0, and read as
        an improvement rather than as the instability it is.
        """
        frame = candles(
            [
                flat(100),
                (100, 100.2, 98.5, 99),  # trade 1 stops out; fill was the decision close, so 2.0
                (99, 99.2, 97.5, 98.01),  # trade 2 the same
                (97.04, 97.2, 96.9, 97.0),  # trade 3 fills a cent above its stop
            ],
            signals={0: Direction.LONG, 1: Direction.LONG, 2: Direction.LONG},
        )
        trades, metrics = run(frame, max_horizon=2)
        ratios = list(trades["realised_risk_reward"])
        self.assertEqual(len(ratios), 3)
        self.assertAlmostEqual(ratios[0], 2.0, places=9)
        self.assertAlmostEqual(ratios[1], 2.0, places=9)
        self.assertGreater(ratios[2], 200.0, "the unstable one, and it is a real trade, not a bug")
        self.assertAlmostEqual(metrics["trades"]["median_realised_risk_reward"], 2.0, places=9)
        self.assertGreater(float(np.mean(ratios)), 90.0, "which is what the mean would have reported")

    def test_expectancy_is_reported_in_the_same_atr_units_the_model_predicts_in(self) -> None:
        """So the achieved edge and the model's own expected value can be held against each other.

        `domain.expectancy` quotes expected value in ATR multiples. If the backtest only reported percent,
        comparing the two would need a conversion nobody would remember to apply.
        """
        frame = candles(
            [
                flat(100),
                (100, 100.2, 98.5, 99),
                (99, 99.2, 97.5, 98.01),
                (98.01, 100.5, 98, 100),
                flat(100),
            ],
            signals={0: Direction.LONG, 1: Direction.LONG},
        )
        trades, metrics = run(frame, max_horizon=2)
        self.assertAlmostEqual(
            metrics["trades"]["expectancy_atr"], float(trades["return_atr"].mean()), places=12
        )
        self.assertAlmostEqual(
            metrics["trades"]["expectancy_percent"], float(trades["net_return"].mean() * 100), places=12
        )
        # Both trades stopped out, so the achieved expectancy is exactly minus their mean risk — a shade
        # under one ATR, because the second bet's 1% stop hangs off a decision close of 99 rather than 100.
        self.assertEqual(list(trades["outcome"]), [Outcome.STOP_LOSS_FIRST] * 2)
        self.assertAlmostEqual(
            metrics["trades"]["expectancy_atr"], -float(trades["stop_loss_atr"].mean()), places=9
        )

    def test_a_run_that_never_traded_reports_zeros_rather_than_failing(self) -> None:
        trades, metrics = run(candles([flat(100)] * 5))
        self.assertTrue(trades.empty)
        self.assertEqual(metrics["trades"]["trades"], 0)
        self.assertEqual(metrics["trades"]["win_rate"], 0.0)
        self.assertIsNone(metrics["trades"]["break_even_win_rate"])
        self.assertIsNone(metrics["trades"]["edge_over_break_even"])
        self.assertEqual(metrics["equity"]["cumulative_return"], 0.0)

    def test_the_tie_break_rule_travels_with_the_numbers(self) -> None:
        """A reader has to be able to tell which rulebook produced the result."""
        _, metrics = run(candles([flat(100)] * 3))
        self.assertIn("adverse barrier wins", metrics["rule"])
        self.assertEqual(metrics["max_horizon"], 6)

    def test_exposure_counts_the_bars_a_position_was_actually_held(self) -> None:
        frame = candles(
            [flat(100), (100, 100.5, 99.5, 100), (100, 100, 98.9, 99), flat(99), flat(99)],
            signals={0: Direction.LONG},
        )
        _, metrics = run(frame)
        self.assertAlmostEqual(metrics["equity"]["exposure"], 2 / 5, places=9)

    def test_the_equity_curve_compounds_the_trades_in_the_order_they_closed(self) -> None:
        """A drawdown depends on sequence, so the returns land on the bar each trade exited."""
        frame = candles(
            [
                flat(100),
                (100, 100.5, 99.5, 100),
                (100, 100, 98.9, 99),  # loss
                (99, 99, 98.5, 98.8),
                (98.8, 98.8, 98.8, 98.8),
                (98.8, 101, 98.8, 100.9),  # win on the second trade
                flat(100.9),
            ],
            signals={0: Direction.LONG, 2: Direction.LONG},
        )
        trades, metrics = run(frame)
        self.assertEqual(len(trades), 2)
        self.assertEqual(list(trades["outcome"]), [Outcome.STOP_LOSS_FIRST, Outcome.TAKE_PROFIT_FIRST])
        self.assertLess(metrics["equity"]["max_drawdown"], 0.0, "the loss came first")


class ContractTests(unittest.TestCase):
    def test_a_missing_column_is_named(self) -> None:
        frame = candles([flat(100)] * 3).drop(columns=["atr", "take_profit_percent"])
        with self.assertRaises(ValueError) as raised:
            run(frame)
        message = str(raised.exception)
        self.assertIn("atr", message)
        self.assertIn("take_profit_percent", message)

    def test_a_horizon_of_zero_candles_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            run(candles([flat(100)] * 3), max_horizon=0)

    def test_a_negative_cost_is_refused(self) -> None:
        """A negative fee is a rebate, and a negative slippage is a fill better than the market."""
        for kwargs in ({"fee_rate": -0.001}, {"slippage_rate": -0.001}):
            with self.subTest(**kwargs):
                with self.assertRaises(ValueError):
                    BracketCosts(**{"fee_rate": 0.0, "slippage_rate": 0.0, **kwargs})

    def test_every_declared_trade_column_is_present_even_with_no_trades(self) -> None:
        """The report and the tests both index by name, so an empty run keeps the same shape."""
        empty, _ = run(candles([flat(100)] * 3))
        populated, _ = run(
            candles([flat(100), (100, 102.5, 100, 102), flat(102)], signals={0: Direction.LONG})
        )
        self.assertEqual(list(empty.columns), list(populated.columns))


if __name__ == "__main__":
    unittest.main()
