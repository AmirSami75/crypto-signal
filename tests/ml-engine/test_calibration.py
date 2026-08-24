"""Expected value, calibration selection, and the direction choice built on top of them.

Three questions decide whether a confidence number is worth anything downstream, and each one has a
failure mode that looks like success:

* **Is the arithmetic honest?** Dropping the timeout branch and renormalising the remaining two
  probabilities inflates every expected value toward the nearer barrier — 25% on a 2:1 bet. It also
  makes the numbers tidier, which is why it happens.
* **Is the correction worth applying?** A monotone calibrator cannot add resolution, only remove it. On
  an already-calibrated model isotonic regression *empties* the top of the range rather than fixing it,
  and every bin-based error measure reads the vacancy as an improvement because the bin it was failing
  in no longer holds rows. So the comparison has to be weighted by coverage and restricted to the scores
  a threshold would actually select.
* **Does the answer clear the bar it was given?** A minimum confidence set above what the model can
  reach produces silence, and silence is indistinguishable from safety from the outside.

The direction tests cover the other half: one model, two forward passes differing only in
`direction_sign`, selected by expected value rather than probability — because probability alone cannot
compare a likely small win against an unlikely large one.
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from crypto_signal.domain import (
    BarrierPair,
    Direction,
    OutcomeProbabilities,
    break_even_win_rate,
    expected_value,
)
from crypto_signal.labeling import BARRIER_FEATURE_COLUMNS
from crypto_signal.modeling import (
    ALL_CLASSES,
    CalibrationReport,
    ConfidenceReach,
    ReliabilityCurve,
    barrier_variants,
    choose_direction,
    chronological_blocks,
    measure_confidence_reach,
    reliability_curve,
)
from crypto_signal.modeling.calibration import (
    DECISION_FLOOR,
    MAX_COVERAGE_LOSS,
    MIN_BIN_COUNT_FOR_ERROR,
)


class OutcomeProbabilityTests(unittest.TestCase):
    """The distribution has three outcomes, and collapsing it to two is a silent EV inflation."""

    def test_a_distribution_over_only_two_outcomes_is_accepted_when_it_is_honest(self) -> None:
        """A genuine zero timeout probability is fine. It is the *missing* branch that is refused."""
        probabilities = OutcomeProbabilities(win=0.6, loss=0.4, timeout=0.0)
        self.assertEqual(probabilities.resolved, 1.0)

    def test_probabilities_that_do_not_sum_to_one_name_the_likely_cause(self) -> None:
        with self.assertRaises(ValueError) as caught:
            OutcomeProbabilities(win=0.375, loss=0.625, timeout=0.5)
        message = str(caught.exception)
        self.assertIn("renormalised", message)
        self.assertIn("nearer barrier", message, "the error should say which way the bias runs")

    def test_renormalising_away_the_timeout_inflates_expected_value(self) -> None:
        """The bug the constructor exists to prevent, priced in ATR.

        Renormalising scales both resolved probabilities by `1/resolved`, so it scales the expected value
        by exactly the same factor — the whole unresolved mass is silently reallocated in proportion to
        the bet already on the table. Half the paths timing out therefore *doubles* the reported edge,
        and the inflation is invisible because the result is still a valid-looking probability triple.
        """
        barriers = BarrierPair(take_profit_atr=2.0, stop_loss_atr=1.0)
        for win, loss, timeout in ((0.30, 0.20, 0.50), (0.30, 0.50, 0.20), (0.25, 0.25, 0.50)):
            with self.subTest(timeout=timeout):
                honest = OutcomeProbabilities(win=win, loss=loss, timeout=timeout)
                resolved = honest.resolved
                renormalised = OutcomeProbabilities(
                    win=win / resolved, loss=loss / resolved, timeout=0.0
                )
                truth = expected_value(honest, barriers)
                inflated = expected_value(renormalised, barriers)
                self.assertAlmostEqual(inflated, truth / resolved, places=9)
                self.assertGreater(inflated, truth, "the shortcut always flatters the bet")

        # Priced concretely: a 2:1 bet, 30% win / 20% loss / 50% timeout.
        honest = OutcomeProbabilities(win=0.30, loss=0.20, timeout=0.50)
        self.assertAlmostEqual(expected_value(honest, barriers), 0.40, places=9)
        self.assertAlmostEqual(
            expected_value(OutcomeProbabilities(win=0.60, loss=0.40, timeout=0.0), barriers),
            0.80,
            places=9,
        )

    def test_a_timeout_is_worth_nothing_unless_told_otherwise(self) -> None:
        barriers = BarrierPair(take_profit_atr=1.0, stop_loss_atr=1.0)
        probabilities = OutcomeProbabilities(win=0.4, loss=0.4, timeout=0.2)
        self.assertAlmostEqual(expected_value(probabilities, barriers), 0.0, places=9)
        # A backtest walking real candles *observes* the horizon close and may pass what it saw.
        self.assertAlmostEqual(
            expected_value(probabilities, barriers, timeout_value_atr=0.5), 0.1, places=9
        )

    def test_class_probabilities_are_read_in_the_estimators_own_order(self) -> None:
        """`[P(-1), P(0), P(+1)]` — getting this backwards silently swaps wins for losses."""
        probabilities = OutcomeProbabilities.from_class_probabilities([0.2, 0.3, 0.5])
        self.assertEqual((probabilities.loss, probabilities.timeout, probabilities.win), (0.2, 0.3, 0.5))
        self.assertEqual(list(ALL_CLASSES), [-1, 0, 1])

    def test_a_probability_outside_the_unit_interval_is_refused(self) -> None:
        for kwargs in (
            {"win": -0.1, "loss": 0.6, "timeout": 0.5},
            {"win": 1.2, "loss": 0.0, "timeout": -0.2},
            {"win": float("nan"), "loss": 0.5, "timeout": 0.5},
        ):
            with self.subTest(**kwargs):
                with self.assertRaises(ValueError):
                    OutcomeProbabilities(**kwargs)

    def test_break_even_matches_the_barrier_geometry(self) -> None:
        self.assertAlmostEqual(
            break_even_win_rate(BarrierPair(take_profit_atr=2.0, stop_loss_atr=1.0)), 1 / 3, places=9
        )
        self.assertAlmostEqual(
            break_even_win_rate(BarrierPair(take_profit_atr=1.0, stop_loss_atr=1.0)), 0.5, places=9
        )

    def test_break_even_rises_once_some_paths_time_out(self) -> None:
        """A timeout worth nothing is a wasted slot, so the wins have to cover more ground."""
        barriers = BarrierPair(take_profit_atr=1.0, stop_loss_atr=1.0)
        without = break_even_win_rate(barriers)
        with_timeouts = break_even_win_rate(barriers, timeout_share=0.3)
        self.assertAlmostEqual(without, with_timeouts, places=9)  # a zero-valued timeout is neutral
        credited = break_even_win_rate(barriers, timeout_share=0.3, timeout_value_atr=0.4)
        self.assertLess(credited, without)

    def test_a_bet_that_always_times_out_has_no_break_even(self) -> None:
        with self.assertRaises(ValueError):
            break_even_win_rate(BarrierPair(1.0, 1.0), timeout_share=1.0)


class ChronologicalBlockTests(unittest.TestCase):
    """The three-way split the calibrator needs, cut on candle boundaries and purged in candles."""

    @staticmethod
    def times(candles: int = 1_000, per_candle: int = 12) -> np.ndarray:
        return np.repeat(np.arange(candles, dtype=np.int64) * 3_600_000, per_candle)

    def test_blocks_tile_the_series_without_overlapping(self) -> None:
        times = self.times()
        first, second, third = chronological_blocks(times, (0.6, 0.2, 0.2), gap=24)
        self.assertEqual(len(set(first) & set(second)), 0)
        self.assertEqual(len(set(second) & set(third)), 0)
        self.assertEqual([len(first), len(second), len(third)], [6_912, 2_112, 2_400])

    def test_the_purge_is_counted_in_candles_not_rows(self) -> None:
        times = self.times()
        first, second, third = chronological_blocks(times, (0.6, 0.2, 0.2), gap=24)
        unique = np.unique(times)
        for earlier, later in ((first, second), (second, third)):
            gap = int(
                np.searchsorted(unique, times[later].min())
                - np.searchsorted(unique, times[earlier].max())
                - 1
            )
            self.assertEqual(gap, 24, "a barrier label reaches 24 candles forward, so 24 must be dropped")

    def test_no_candle_is_divided_across_a_boundary(self) -> None:
        times = self.times()
        blocks = chronological_blocks(times, (0.5, 0.25, 0.25), gap=10)
        for index, block in enumerate(blocks):
            for other in blocks[index + 1 :]:
                shared = set(times[block]) & set(times[other])
                self.assertEqual(shared, set(), "every row of a candle belongs to one block")

    def test_fractions_that_do_not_describe_a_partition_are_refused(self) -> None:
        times = self.times(200)
        for fractions in ((0.6, 0.2), (0.5, 0.5, 0.5), (0.6, 0.0, 0.4), (0.7, -0.1, 0.4)):
            with self.subTest(fractions=fractions):
                with self.assertRaises(ValueError):
                    chronological_blocks(times, fractions, gap=0)
        with self.assertRaises(ValueError):
            chronological_blocks(times, (1.0,), gap=0)

    def test_a_purge_larger_than_a_block_is_refused_with_advice(self) -> None:
        times = self.times(120)
        with self.assertRaises(ValueError) as caught:
            chronological_blocks(times, (0.6, 0.2, 0.2), gap=40)
        message = str(caught.exception)
        self.assertIn("came out empty", message)
        self.assertIn("max_horizon", message, "the error should name the knob that fixes it")


def curve(counts, predicted, observed, label: int = 1, brier: float = 0.2) -> ReliabilityCurve:
    """A hand-built reliability curve, so the criteria can be tested without fitting anything."""
    bins = len(counts)
    edges = tuple(float(edge) for edge in np.linspace(0.0, 1.0, bins + 1))
    return ReliabilityCurve(
        label=label,
        bin_edges=edges,
        predicted=tuple(float(value) for value in predicted),
        observed=tuple(float(value) for value in observed),
        counts=tuple(int(value) for value in counts),
        brier=brier,
    )


class ReliabilityCurveTests(unittest.TestCase):
    def test_a_curve_always_has_the_same_shape(self) -> None:
        """Empty bins are reported at their midpoint, so two runs stay comparable."""
        probabilities = np.tile([0.2, 0.3, 0.5], (40, 1))
        result = reliability_curve(np.ones(40, dtype=int), probabilities, label=1, bins=10)
        self.assertEqual(len(result.counts), 10)
        self.assertEqual(len(result.bin_edges), 11)
        self.assertEqual(sum(result.counts), 40)
        self.assertEqual(result.counts[5], 40, "0.5 lands in the sixth bin")

    def test_a_perfectly_confident_prediction_lands_inside_a_bin(self) -> None:
        probabilities = np.tile([0.0, 0.0, 1.0], (10, 1))
        result = reliability_curve(np.ones(10, dtype=int), probabilities, label=1, bins=10)
        self.assertEqual(sum(result.counts), 10, "1.0 must belong to the last bin, not fall outside")
        self.assertEqual(result.counts[-1], 10)

    def test_a_thin_bin_is_reported_but_excluded_from_the_worst_case(self) -> None:
        """One row that happened to win reads as a 0.45 gap. That is noise, not a defect."""
        thin = MIN_BIN_COUNT_FOR_ERROR - 1
        result = curve(
            counts=[0, 0, 0, 0, 0, 5_000, 0, thin, 0, 0],
            predicted=[0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95],
            observed=[0.05, 0.15, 0.25, 0.35, 0.45, 0.56, 0.65, 0.30, 0.85, 0.95],
        )
        self.assertAlmostEqual(result.maximum_calibration_error, 0.01, places=9)
        self.assertIn(7, result.as_dict()["thin_bins"])

    def test_the_worst_case_falls_back_when_no_bin_is_thick_enough(self) -> None:
        result = curve(
            counts=[0] * 9 + [7],
            predicted=[0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95],
            observed=[0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.55],
        )
        self.assertAlmostEqual(result.maximum_calibration_error, 0.40, places=9)

    def test_the_decision_region_ignores_scores_nobody_would_act_on(self) -> None:
        """A model wrong below the floor and right above it is fit to serve; global ECE disagrees."""
        result = curve(
            counts=[0, 0, 0, 0, 90_000, 5_000, 5_000, 0, 0, 0],
            predicted=[0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95],
            observed=[0.05, 0.15, 0.25, 0.35, 0.20, 0.55, 0.65, 0.75, 0.85, 0.95],
        )
        self.assertAlmostEqual(result.decision_region_error(), 0.0, places=9)
        self.assertGreater(result.expected_calibration_error, 0.2)
        self.assertEqual(result.coverage(), 10_000)

    def test_the_decision_floor_sits_at_a_coin_flip(self) -> None:
        self.assertEqual(DECISION_FLOOR, 0.50)


def report_over(
    before: ReliabilityCurve,
    after: ReliabilityCurve,
    reach: ConfidenceReach | None = None,
    **metrics,
) -> CalibrationReport:
    """A report over hand-built curves, so selection and rendering are testable without fitting."""
    others = [curve([1] * 10, [0.5] * 10, [0.5] * 10, label=label) for label in (-1, 0)]
    return CalibrationReport(
        method="isotonic",
        blocks=(0.6, 0.2, 0.2),
        gap_candles=24,
        fit_rows=100,
        calibration_rows=50,
        assessment_rows=50,
        before={"log_loss": metrics.get("log_loss_before", 0.80)},
        after={"log_loss": metrics.get("log_loss_after", 0.79)},
        curves_before=tuple(others) + (before,),
        curves_after=tuple(others) + (after,),
        reach=reach,
    )


class SelectionTests(unittest.TestCase):
    """Whether a correction is applied, and the three ways it can fail to earn its place."""

    def test_a_correction_that_lowers_decision_region_error_is_accepted(self) -> None:
        worse = curve(
            counts=[0, 0, 0, 0, 0, 6_000, 6_000, 0, 0, 0],
            predicted=[0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95],
            observed=[0.05, 0.15, 0.25, 0.35, 0.45, 0.45, 0.55, 0.75, 0.85, 0.95],
            brier=0.23,
        )
        better = curve(
            counts=[0, 0, 0, 0, 0, 6_000, 6_000, 0, 0, 0],
            predicted=[0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95],
            observed=[0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95],
            brier=0.22,
        )
        report = report_over(worse, better)
        self.assertTrue(report.improved)
        self.assertEqual(report.selected, "isotonic")
        self.assertEqual(report.selected_metrics["log_loss"], 0.79)

    def test_a_correction_that_empties_the_top_of_the_range_is_rejected(self) -> None:
        """The failure this criterion exists for: isotonic vacating a bin it was failing in.

        Measured on BTCUSDT 1h, the 0.70-0.80 bin went from 753 rows to 2. Worst-case error 'improved'
        from 0.054 to 0.023 purely because the bin holding the error stopped holding rows, while the
        rows above 0.60 confidence fell from 17,867 to 12,898 — a quieter model, not a safer one.
        """
        wide = curve(
            counts=[0, 0, 0, 0, 0, 20_408, 17_867, 753, 0, 0],
            predicted=[0.05, 0.15, 0.25, 0.35, 0.45, 0.548, 0.642, 0.718, 0.85, 0.95],
            observed=[0.05, 0.15, 0.25, 0.35, 0.45, 0.550, 0.635, 0.664, 0.85, 0.95],
            brier=0.2217,
        )
        vacated = curve(
            counts=[0, 0, 0, 0, 0, 23_208, 12_898, 2, 0, 0],
            predicted=[0.05, 0.15, 0.25, 0.35, 0.45, 0.548, 0.626, 0.709, 0.85, 0.95],
            observed=[0.05, 0.15, 0.25, 0.35, 0.45, 0.567, 0.649, 0.500, 0.85, 0.95],
            brier=0.2220,
        )
        report = report_over(wide, vacated, log_loss_before=0.7910, log_loss_after=0.7916)
        self.assertLess(
            vacated.maximum_calibration_error,
            wide.maximum_calibration_error,
            "the naive comparison prefers the correction, which is the trap",
        )
        self.assertGreater(
            vacated.decision_region_error(),
            wide.decision_region_error(),
            "coverage-weighted error over the decision region sees through it",
        )
        self.assertFalse(report.improved)
        self.assertEqual(report.selected, "identity")

    def test_a_correction_may_not_buy_accuracy_with_reach(self) -> None:
        """Lower error over a much smaller slice of the distribution is not an improvement."""
        wide = curve(
            counts=[0, 0, 0, 0, 0, 10_000, 10_000, 0, 0, 0],
            predicted=[0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95],
            observed=[0.05, 0.15, 0.25, 0.35, 0.45, 0.57, 0.67, 0.75, 0.85, 0.95],
            brier=0.22,
        )
        narrow = curve(
            counts=[0, 0, 0, 0, 0, 10_000, 1_000, 0, 0, 0],
            predicted=[0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95],
            observed=[0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95],
            brier=0.22,
        )
        self.assertLess(narrow.decision_region_error(), wide.decision_region_error())
        retained = narrow.coverage() / wide.coverage()
        self.assertLess(retained, 1.0 - MAX_COVERAGE_LOSS)
        self.assertFalse(report_over(wide, narrow).improved)

    def test_a_correction_that_worsens_a_proper_scoring_rule_is_rejected(self) -> None:
        equal = dict(
            counts=[0, 0, 0, 0, 0, 6_000, 6_000, 0, 0, 0],
            predicted=[0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95],
            observed=[0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95],
        )
        before = curve(brier=0.22, **equal)
        after = curve(brier=0.24, **equal)
        self.assertFalse(report_over(before, after).improved, "Brier regressed")
        self.assertFalse(
            report_over(
                curve(brier=0.22, **equal),
                curve(brier=0.22, **equal),
                log_loss_before=0.79,
                log_loss_after=0.81,
            ).improved,
            "log loss regressed",
        )

    def test_metrics_point_at_the_model_that_shipped(self) -> None:
        """`before`/`after` name the candidates; when the correction loses, `before` is what ships."""
        equal = dict(
            counts=[0, 0, 0, 0, 0, 6_000, 0, 0, 0, 0],
            predicted=[0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95],
            observed=[0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95],
        )
        rejected = report_over(
            curve(brier=0.22, **equal), curve(brier=0.30, **equal),
            log_loss_before=0.79, log_loss_after=0.90,
        )
        self.assertFalse(rejected.improved)
        self.assertEqual(rejected.selected_metrics, rejected.before)
        self.assertIs(rejected.selected_curves, rejected.curves_before)
        self.assertEqual(rejected.as_dict()["selected"], "identity")

    def test_a_report_without_curves_declines_rather_than_guesses(self) -> None:
        report = CalibrationReport(
            method="isotonic", blocks=(0.6, 0.2, 0.2), gap_candles=24,
            fit_rows=1, calibration_rows=1, assessment_rows=1,
        )
        self.assertFalse(report.improved)
        self.assertEqual(report.selected, "identity")


class ConfidenceReachTests(unittest.TestCase):
    """An unreachable threshold has to be detectable, because silence looks like safety."""

    def reach(self) -> ConfidenceReach:
        # The shape measured on BTCUSDT 1h: usable to about 0.65, empty past 0.70.
        return ConfidenceReach(
            ceiling=0.688,
            maximum=0.814,
            attainment=(
                (0.50, 0.2812), (0.55, 0.2033), (0.60, 0.1342),
                (0.65, 0.0538), (0.70, 0.0055), (0.75, 0.0004),
            ),
        )

    def test_a_threshold_past_the_ceiling_is_reported_unreachable(self) -> None:
        reach = self.reach()
        self.assertTrue(reach.is_reachable(0.65))
        self.assertTrue(reach.is_reachable(0.70))
        self.assertFalse(reach.is_reachable(0.75), "0.04% of bets is silence in practice")

    def test_an_unmeasured_threshold_reads_the_level_below_it(self) -> None:
        """A floor between two measured points cannot be more attainable than the lower one."""
        reach = self.reach()
        self.assertEqual(reach.share_above(0.62), reach.share_above(0.60))
        self.assertEqual(reach.share_above(0.99), reach.share_above(0.75))
        self.assertEqual(reach.share_above(0.10), 1.0)

    def test_the_ceiling_is_a_percentile_not_the_maximum(self) -> None:
        """One outlier row in a 138k-row block is not a level an operator can plan around."""
        wins = np.concatenate([np.full(9_999, 0.40), [0.99]])
        probabilities = np.column_stack([1.0 - wins, np.zeros_like(wins), wins])
        measured = measure_confidence_reach(probabilities, thresholds=(0.50, 0.95))
        self.assertAlmostEqual(measured.maximum, 0.99, places=9)
        self.assertLess(measured.ceiling, 0.5, "the ceiling must not be dragged up by one row")
        self.assertAlmostEqual(measured.attainment[1][1], 1e-4, places=9)

    def test_reach_is_measured_on_the_win_column(self) -> None:
        wins = np.linspace(0.0, 1.0, 1_001)
        probabilities = np.column_stack([1.0 - wins, np.zeros_like(wins), wins])
        measured = measure_confidence_reach(probabilities, thresholds=(0.50,))
        self.assertAlmostEqual(measured.attainment[0][1], 501 / 1_001, places=9)

    def test_an_empty_block_cannot_be_measured(self) -> None:
        with self.assertRaises(ValueError):
            measure_confidence_reach(np.empty((0, 3)))


class ReportRenderingTests(unittest.TestCase):
    """The section a human reads before choosing a threshold.

    Rendering is tested because it makes judgement calls, not just formatting ones: which of the two
    candidate curves it shows, whether a bin holds enough rows for its observed frequency to mean
    anything, and whether a threshold in the table can ever fire. Each of those getting it wrong
    produces a report that reads as reassurance.
    """

    def curves(self) -> tuple[ReliabilityCurve, ReliabilityCurve]:
        """The measured BTCUSDT shape: honest raw scores, isotonic vacating the top bin."""
        wide = curve(
            counts=[0, 0, 0, 0, 0, 20_408, 17_867, 753, 0, 0],
            predicted=[0.05, 0.15, 0.25, 0.35, 0.45, 0.548, 0.642, 0.718, 0.85, 0.95],
            observed=[0.05, 0.15, 0.25, 0.35, 0.45, 0.550, 0.635, 0.664, 0.85, 0.95],
            brier=0.2217,
        )
        vacated = curve(
            counts=[0, 0, 0, 0, 0, 23_208, 12_898, 2, 0, 0],
            predicted=[0.05, 0.15, 0.25, 0.35, 0.45, 0.548, 0.626, 0.709, 0.85, 0.95],
            observed=[0.05, 0.15, 0.25, 0.35, 0.45, 0.567, 0.649, 0.500, 0.85, 0.95],
            brier=0.2220,
        )
        return wide, vacated

    def test_a_rejected_correction_renders_the_shipped_model_not_the_candidate(self) -> None:
        """The trap `selected_curves` exists for: a report describing the model that lost.

        When the correction is rejected the shipped model is the *before* curve, so those are the row
        counts and observed frequencies that belong in the table. Rendering `curves_after` would
        publish reliability figures for an artifact nobody can call.
        """
        wide, vacated = self.curves()
        rendered = report_over(wide, vacated, log_loss_before=0.7910, log_loss_after=0.7916).markdown()
        self.assertIn("Shipped the estimator uncorrected", rendered)
        self.assertIn("17,867", rendered, "the shipped model's bin count")
        self.assertIn("753", rendered)
        self.assertNotIn("12,898", rendered, "the discarded candidate's counts must not appear as fact")
        self.assertIn(
            f"{wide.decision_region_error():.4f}",
            rendered,
            "both candidates' decision-region errors, so the choice is auditable",
        )
        self.assertIn(f"{vacated.decision_region_error():.4f}", rendered)

    def test_an_accepted_correction_says_so(self) -> None:
        wide, _ = self.curves()
        better = curve(
            counts=[0, 0, 0, 0, 0, 20_408, 17_867, 753, 0, 0],
            predicted=[0.05, 0.15, 0.25, 0.35, 0.45, 0.550, 0.636, 0.665, 0.85, 0.95],
            observed=[0.05, 0.15, 0.25, 0.35, 0.45, 0.550, 0.635, 0.664, 0.85, 0.95],
            brier=0.2200,
        )
        rendered = report_over(wide, better, log_loss_before=0.7910, log_loss_after=0.7880).markdown()
        self.assertIn("Applied the isotonic correction", rendered)
        self.assertNotIn("Shipped the estimator uncorrected", rendered)

    def test_a_bin_too_thin_to_believe_is_marked(self) -> None:
        """The 7-row 0.80 bin from the real fit claims 0.807 and observes 0.571.

        That gap is sampling noise, and the worst-case figure already excludes it. Printing the row
        unmarked would invite someone to conclude the model is 24 points overconfident at the top.
        """
        thin = curve(
            counts=[0, 0, 0, 0, 0, 20_408, 17_867, 753, 7, 0],
            predicted=[0.05, 0.15, 0.25, 0.35, 0.45, 0.548, 0.642, 0.718, 0.807, 0.95],
            observed=[0.05, 0.15, 0.25, 0.35, 0.45, 0.550, 0.635, 0.664, 0.571, 0.95],
            brier=0.2217,
        )
        rendered = report_over(thin, thin, log_loss_before=0.79, log_loss_after=0.79).markdown()
        self.assertRegex(rendered, r"\| 0\.807 \| 0\.571 \| 7 ⚠ \|")
        self.assertIn(f"Fewer than {MIN_BIN_COUNT_FOR_ERROR} rows", rendered)
        self.assertNotIn("| 0.000 | 0.000 | 0 |", rendered, "empty bins are not rows of evidence")

    def test_an_unreachable_threshold_is_marked_in_the_reach_table(self) -> None:
        """Without this the table reads as six available thresholds, two of which are fiction."""
        wide, vacated = self.curves()
        reach = ConfidenceReach(
            ceiling=0.688,
            maximum=0.814,
            attainment=((0.50, 0.2812), (0.60, 0.1342), (0.70, 0.0055), (0.75, 0.0004)),
        )
        rendered = report_over(wide, vacated, reach=reach).markdown()
        self.assertIn("Ceiling (p99) **0.688**", rendered)
        self.assertRegex(rendered, r"\| 0\.60 \| 13\.42% \|\s+\|")
        self.assertRegex(rendered, r"\| 0\.75 \| 0\.04% \| \*\*never fires\*\* \|")

    def test_the_reach_section_is_absent_rather_than_empty_when_unmeasured(self) -> None:
        wide, vacated = self.curves()
        rendered = report_over(wide, vacated).markdown()
        self.assertNotIn("never fires", rendered)
        self.assertNotIn("Ceiling", rendered)
        self.assertIn("## Calibration", rendered, "the rest of the section still renders")

    def test_the_split_that_produced_the_numbers_is_stated(self) -> None:
        """A reliability figure is meaningless without which candles it was measured on."""
        wide, vacated = self.curves()
        rendered = report_over(wide, vacated).markdown()
        self.assertIn("24-candle purge", rendered)
        self.assertIn("neither stage was fitted to", rendered)


class StubModel:
    """A model whose answer is a stated function of `direction_sign`, so selection can be tested exactly.

    Returns `[P(-1), P(0), P(+1)]`, the estimator's own class order.
    """

    def __init__(self, by_sign: dict[float, tuple[float, float, float]]) -> None:
        self.by_sign = by_sign
        self.calls: list[pd.DataFrame] = []

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        self.calls.append(X.copy())
        return np.array([self.by_sign[float(sign)] for sign in X["direction_sign"]], dtype=float)

    @property
    def classes_(self) -> np.ndarray:
        return np.array([-1, 0, 1], dtype=int)


class BarrierVariantTests(unittest.TestCase):
    def test_the_four_barrier_columns_arrive_in_the_trained_order(self) -> None:
        """A fitted tree addresses its inputs by position; a permuted order answers wrongly, confidently."""
        features = pd.DataFrame({"rsi_14": [0.5], "momentum_4": [-0.1]})
        variants = barrier_variants(features, BarrierPair(take_profit_atr=2.0, stop_loss_atr=1.0))
        self.assertEqual(tuple(variants.columns[-4:]), BARRIER_FEATURE_COLUMNS)
        self.assertEqual(len(variants), 2, "one row per direction")
        self.assertEqual(list(variants["direction_sign"]), [1.0, -1.0])

    def test_both_directions_carry_the_same_favourable_barrier(self) -> None:
        """The parameterisation is direction-relative: take_profit_atr is the favourable side, always."""
        features = pd.DataFrame({"rsi_14": [0.5]})
        variants = barrier_variants(features, BarrierPair(take_profit_atr=2.0, stop_loss_atr=1.0))
        self.assertEqual(list(variants["take_profit_atr"]), [2.0, 2.0])
        self.assertEqual(list(variants["stop_loss_atr"]), [1.0, 1.0])
        self.assertEqual(list(variants["risk_reward_ratio"]), [2.0, 2.0])

    def test_the_two_rows_differ_only_in_the_direction(self) -> None:
        features = pd.DataFrame({"rsi_14": [0.5], "momentum_4": [-0.1]})
        variants = barrier_variants(features, BarrierPair(1.5, 1.5))
        shared = [column for column in variants.columns if column != "direction_sign"]
        self.assertTrue(variants[shared].iloc[0].equals(variants[shared].iloc[1]))


class DirectionChoiceTests(unittest.TestCase):
    FEATURES = pd.DataFrame({"rsi_14": [0.42], "momentum_4": [-0.03]})

    def choose(self, model: StubModel, barriers: BarrierPair, **kwargs):
        return choose_direction(model, self.FEATURES, barriers, **kwargs)

    def test_one_forward_pass_scores_both_directions(self) -> None:
        """Batched deliberately: a registry may swap the artifact between calls, and the two sides of one
        answer must come from one model state."""
        model = StubModel({1.0: (0.2, 0.2, 0.6), -1.0: (0.6, 0.2, 0.2)})
        self.choose(model, BarrierPair(1.0, 1.0))
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(len(model.calls[0]), 2)

    def test_the_better_expected_value_wins_even_at_lower_confidence(self) -> None:
        """Probability alone cannot compare a likely small win against an unlikely large one."""
        model = StubModel({1.0: (0.30, 0.30, 0.40), -1.0: (0.28, 0.14, 0.58)})
        # Long: 0.40 * 3 - 0.30 * 1 = +0.90.  Short: 0.58 * 3 - 0.28 * 1 = +1.46.
        choice = self.choose(model, BarrierPair(take_profit_atr=3.0, stop_loss_atr=1.0))
        self.assertIs(choice.direction, Direction.SHORT)

        # Same probabilities, symmetric barriers: now the long's higher win rate is what matters.
        model = StubModel({1.0: (0.20, 0.10, 0.70), -1.0: (0.45, 0.10, 0.45)})
        choice = self.choose(model, BarrierPair(1.0, 1.0))
        self.assertIs(choice.direction, Direction.LONG)

    def test_a_declined_side_is_still_reported(self) -> None:
        """A FLAT answer is only auditable if you can see what was considered and why it lost."""
        model = StubModel({1.0: (0.45, 0.10, 0.45), -1.0: (0.45, 0.10, 0.45)})
        choice = self.choose(model, BarrierPair(1.0, 1.0), minimum_confidence=0.60)
        self.assertIs(choice.direction, Direction.FLAT)
        self.assertIsNone(choice.chosen)
        self.assertEqual({candidate.direction for candidate in choice.candidates},
                         {Direction.LONG, Direction.SHORT})
        self.assertTrue(any("0.60" in line for line in choice.rationale))

    def test_a_confidence_floor_above_the_reach_yields_flat_not_an_error(self) -> None:
        model = StubModel({1.0: (0.20, 0.10, 0.70), -1.0: (0.70, 0.10, 0.20)})
        choice = self.choose(model, BarrierPair(1.0, 1.0), minimum_confidence=0.95)
        self.assertIs(choice.direction, Direction.FLAT)

    def test_a_negative_expected_value_is_declined_however_confident(self) -> None:
        """0.60 to win 1 while risking 2 is a losing bet, and confidence does not change that."""
        model = StubModel({1.0: (0.35, 0.05, 0.60), -1.0: (0.60, 0.05, 0.35)})
        choice = self.choose(
            model, BarrierPair(take_profit_atr=1.0, stop_loss_atr=2.0), minimum_confidence=0.55
        )
        long_side = next(c for c in choice.candidates if c.direction is Direction.LONG)
        self.assertAlmostEqual(long_side.expected_value_atr, 0.60 - 0.70, places=9)
        self.assertGreater(long_side.confidence, 0.55)
        self.assertIs(choice.direction, Direction.FLAT)

    def test_shorting_can_be_forbidden_without_hiding_that_it_was_better(self) -> None:
        model = StubModel({1.0: (0.45, 0.10, 0.45), -1.0: (0.20, 0.10, 0.70)})
        allowed = self.choose(model, BarrierPair(1.0, 1.0), allow_short=True, minimum_confidence=0.50)
        self.assertIs(allowed.direction, Direction.SHORT)

        refused = self.choose(model, BarrierPair(1.0, 1.0), allow_short=False, minimum_confidence=0.50)
        self.assertIs(refused.direction, Direction.FLAT)
        self.assertEqual(len(refused.candidates), 2, "the short is reported even though it was excluded")
        self.assertTrue(any("short" in line.lower() for line in refused.rationale))

    def test_incoherent_probabilities_are_flagged_not_silently_served(self) -> None:
        """With tp >= sl the two sides cannot both win: reaching +1 requires passing the short's stop."""
        model = StubModel({1.0: (0.10, 0.10, 0.80), -1.0: (0.10, 0.10, 0.80)})
        choice = self.choose(model, BarrierPair(1.0, 1.0), minimum_confidence=0.50)
        self.assertIsNotNone(choice.warning)
        self.assertIn("1.60", choice.warning)

    def test_coherence_is_not_checked_where_both_sides_genuinely_can_win(self) -> None:
        """tp < sl: price can clip a near target in each direction before either far stop."""
        model = StubModel({1.0: (0.10, 0.10, 0.80), -1.0: (0.10, 0.10, 0.80)})
        choice = self.choose(
            model, BarrierPair(take_profit_atr=0.5, stop_loss_atr=2.0), minimum_confidence=0.50
        )
        self.assertIsNone(choice.warning)

    def test_a_timeout_is_not_credited_to_either_side_by_default(self) -> None:
        model = StubModel({1.0: (0.30, 0.40, 0.30), -1.0: (0.30, 0.40, 0.30)})
        choice = self.choose(model, BarrierPair(1.0, 1.0), minimum_confidence=0.0,
                             minimum_expected_value_atr=-9.0)
        for candidate in choice.candidates:
            self.assertAlmostEqual(candidate.expected_value_atr, 0.0, places=9)

    def test_the_edge_measures_clearance_over_the_barrier_geometry(self) -> None:
        model = StubModel({1.0: (0.20, 0.10, 0.70), -1.0: (0.70, 0.10, 0.20)})
        choice = self.choose(model, BarrierPair(1.0, 1.0), minimum_confidence=0.50)
        long_side = next(c for c in choice.candidates if c.direction is Direction.LONG)
        self.assertAlmostEqual(long_side.break_even, 0.5, places=9)
        self.assertAlmostEqual(long_side.edge, 0.70 - 0.5 * 0.90, places=9)
        self.assertGreater(long_side.edge, 0.0)


class FittedCalibrationTests(unittest.TestCase):
    """`fit_calibrated_model` against a real fit, on a synthetic market small enough to be quick.

    The hand-built curves above test the criteria; this tests that the pipeline honours them — that the
    model handed back is the one the report says shipped, and that the reach describes *it* rather than
    the candidate that lost.
    """

    @classmethod
    def setUpClass(cls) -> None:
        from test_triple_barrier import synthetic_market  # same directory

        from crypto_signal.config import ModelConfig
        from crypto_signal.labeling import build_barrier_dataset
        from crypto_signal.modeling import fit_calibrated_model

        dataset = build_barrier_dataset(
            {"AAAUSDT": synthetic_market(periods=2_600, seed=17)}, interval="1h", max_horizon=12
        )
        cls.dataset = dataset
        cls.X = dataset.frame[list(dataset.feature_columns)]
        cls.y = dataset.frame[dataset.label_column]
        cls.times = dataset.frame[dataset.time_column].to_numpy()
        cls.config = ModelConfig(
            test_fraction=0.20, cv_splits=3, probability_threshold=0.50, random_state=42,
            max_iter=40, learning_rate=0.1, max_leaf_nodes=8, min_samples_leaf=40,
            l2_regularization=1.0,
        )
        cls.model, cls.report = fit_calibrated_model(
            cls.X, cls.y, cls.times, cls.config, gap=12
        )

    def test_the_three_blocks_are_disjoint_and_purged(self) -> None:
        report = self.report
        self.assertEqual(report.gap_candles, 12)
        total = report.fit_rows + report.calibration_rows + report.assessment_rows
        self.assertLess(total, len(self.X), "the purge gaps must cost rows")
        self.assertGreater(report.fit_rows, report.calibration_rows)

    def test_the_returned_model_is_the_one_the_report_names(self) -> None:
        from sklearn.calibration import CalibratedClassifierCV

        is_calibrator = isinstance(self.model, CalibratedClassifierCV)
        self.assertEqual(is_calibrator, self.report.improved)
        self.assertEqual(self.report.selected, "isotonic" if is_calibrator else "identity")

    def test_the_shipped_model_scores_the_features_it_was_trained_on(self) -> None:
        probabilities = self.model.predict_proba(self.X.iloc[:5])
        self.assertEqual(probabilities.shape, (5, 3))
        np.testing.assert_allclose(probabilities.sum(axis=1), 1.0, atol=1e-9)

    def test_the_reach_describes_the_shipped_model(self) -> None:
        """Measuring it on the discarded candidate would tell an operator a floor is reachable when it
        is not — the ceiling moved 0.649 -> 0.688 between the two on BTCUSDT 1h."""
        from crypto_signal.modeling import aligned_probabilities

        reach = self.report.reach
        self.assertIsNotNone(reach)
        blocks = chronological_blocks(self.times, self.report.blocks, gap=self.report.gap_candles)
        assessed = aligned_probabilities(self.model, self.X.iloc[blocks[2]])
        recomputed = measure_confidence_reach(assessed)
        self.assertAlmostEqual(reach.ceiling, recomputed.ceiling, places=9)
        self.assertAlmostEqual(reach.maximum, recomputed.maximum, places=9)

    def test_the_report_survives_a_round_trip_to_plain_data(self) -> None:
        """It goes into REPORT.md and into a joblib payload the serving layer reads."""
        import json

        payload = self.report.as_dict()
        restored = json.loads(json.dumps(payload))
        self.assertEqual(restored["selected"], self.report.selected)
        self.assertEqual(restored["gap_candles"], 12)
        self.assertIn("attainment", restored["reach"])
        self.assertEqual(restored["selected_metrics"], payload["selected_metrics"])
        self.assertEqual(len(restored["curves_after"]), 3, "one curve per class")

    def test_a_calibration_block_missing_a_class_is_refused_clearly(self) -> None:
        """Isotonic fits one mapping per class; a class absent here gets no mapping at all."""
        from crypto_signal.modeling import fit_calibrated_model

        y = self.y.copy()
        blocks = chronological_blocks(self.times, (0.6, 0.2, 0.2), gap=12)
        y.iloc[blocks[1]] = y.iloc[blocks[1]].replace(0, 1)
        with self.assertRaises(ValueError) as caught:
            fit_calibrated_model(self.X, y, self.times, self.config, gap=12)
        self.assertIn("calibration block", str(caught.exception))

    def test_times_must_line_up_with_the_rows(self) -> None:
        from crypto_signal.modeling import fit_calibrated_model

        with self.assertRaises(ValueError):
            fit_calibrated_model(self.X, self.y, self.times[:-1], self.config, gap=12)
        with self.assertRaises(ValueError):
            fit_calibrated_model(
                self.X, self.y, self.times, self.config, gap=12, blocks=(0.8, 0.2)
            )


if __name__ == "__main__":
    unittest.main()
