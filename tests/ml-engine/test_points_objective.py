"""The points objective: realized-R labels, the mistake-weighting, and the R-based decision.

Three separate promises are under test here, and they fail in different ways:

* **The label.** `r_multiple` is the number the product optimizes — +reward:risk for a take-profit,
  exactly -1 for a stop, and the mark-to-market divided by the stop distance on a timeout. If the
  sign or the denominator is wrong, every downstream average is wrong in a way that still looks like
  a plausible number.
* **The gate metric.** `regression_metrics` must report the *realized* R of the rows the policy would
  actually trade, with a lower bound, so a promotion cannot be argued from a lucky handful of trades.
* **The decision.** When a bundle carries a points head, the side with the higher expected R wins and
  the `minimum_expected_points` floor refuses the bet — while a bundle without the head keeps deciding
  on ATR expected value exactly as it did before.
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from crypto_signal.domain import BarrierPair
from crypto_signal.labeling import R_MULTIPLE_COLUMN, build_barrier_dataset
from crypto_signal.modeling.direction import choose_direction
from crypto_signal.modeling.estimator import regression_metrics
from crypto_signal.training.barrier_pipeline import training_weights


def synthetic_candles(count: int = 600, seed: int = 0) -> pd.DataFrame:
    """A random walk with a stable ATR, enough of both barriers to label all three outcomes."""
    generator = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(generator.normal(0.0, 0.002, count)))
    span = close * 0.004
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=count, freq="h", tz="UTC"),
            "open": close * 1.0001,
            "high": close + span,
            "low": close - span,
            "close": close,
            "volume": generator.uniform(1.0, 10.0, count),
        }
    )


def labelled_dataset():
    return build_barrier_dataset(
        {"BTCUSDT": synthetic_candles()},
        "1h",
        max_horizon=24,
        pairs_per_candle=3,
        grid=[BarrierPair(1.0, 1.0), BarrierPair(1.5, 1.0), BarrierPair(2.0, 1.0)],
        atr_window=14,
    )


class RMultipleLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = labelled_dataset()
        cls.frame = cls.dataset.frame

    def test_every_outcome_is_present(self) -> None:
        self.assertEqual(set(self.dataset.class_counts), {-1, 0, 1})

    def test_a_take_profit_pays_the_bracket_risk_reward(self) -> None:
        wins = self.frame[self.frame["target"] == 1]
        self.assertGreater(len(wins), 0)
        np.testing.assert_allclose(
            wins[R_MULTIPLE_COLUMN].to_numpy(),
            wins["risk_reward_ratio"].to_numpy(),
            atol=1e-6,
            err_msg="a win must pay the bracket it was labelled at, not a fixed +1",
        )

    def test_a_stop_costs_exactly_one_r(self) -> None:
        losses = self.frame[self.frame["target"] == -1]
        self.assertGreater(len(losses), 0)
        np.testing.assert_allclose(losses[R_MULTIPLE_COLUMN].to_numpy(), -1.0, atol=1e-6)

    def test_a_timeout_pays_its_mark_to_market_over_the_stop(self) -> None:
        timeouts = self.frame[self.frame["target"] == 0]
        self.assertGreater(len(timeouts), 0)
        expected = (timeouts["timeout_return_atr"] / timeouts["stop_loss_atr"]).to_numpy()
        np.testing.assert_allclose(timeouts[R_MULTIPLE_COLUMN].to_numpy(), expected, atol=1e-5)

    def test_the_r_target_is_never_a_model_feature(self) -> None:
        self.assertNotIn(R_MULTIPLE_COLUMN, self.dataset.feature_columns)


class TrainingWeightTests(unittest.TestCase):
    def test_losses_are_weighted_and_wins_are_not(self) -> None:
        weights = training_weights(np.array([-1.0, 0.0, 2.0, -0.4]), mistake_weight=3.0)
        np.testing.assert_allclose(weights, [3.0, 1.0, 1.0, 3.0])

    def test_a_non_positive_mistake_weight_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            training_weights(np.array([-1.0, 1.0]), mistake_weight=0.0)


class RegressionMetricTests(unittest.TestCase):
    def test_expectancy_counts_only_the_rows_the_policy_trades(self) -> None:
        actual = np.array([-1.0, -1.0, 1.5, 1.5, 0.0])
        predicted = np.array([-0.5, -0.2, 0.2, 0.6, 0.1])
        metrics = regression_metrics(actual, predicted, threshold=0.05)
        expectancy = metrics["expectancy_at_threshold"]
        self.assertEqual(expectancy["trades"], 3)
        self.assertAlmostEqual(expectancy["mean_r"], (1.5 + 1.5 + 0.0) / 3, places=6)
        self.assertLess(expectancy["lower_bound_95"], expectancy["mean_r"])

    def test_an_empty_selection_reports_zero_trades_instead_of_nan(self) -> None:
        metrics = regression_metrics(np.array([-1.0, 1.0]), np.array([-2.0, -1.0]), threshold=0.0)
        self.assertEqual(metrics["expectancy_at_threshold"]["trades"], 0)
        self.assertFalse(np.isnan(metrics["expectancy_at_threshold"]["mean_r"]))

    def test_ranking_is_measured_not_assumed(self) -> None:
        actual = np.array([1.0, 2.0, 3.0, 4.0])
        self.assertAlmostEqual(regression_metrics(actual, actual)["spearman"], 1.0, places=9)
        self.assertAlmostEqual(regression_metrics(actual, -actual)["spearman"], -1.0, places=9)


class _ClassifierStub:
    """Both directions priced identically, so only the points head can break the tie."""

    classes_ = np.array([-1, 0, 1])
    is_sequence = False

    def predict_proba(self, rows: pd.DataFrame) -> np.ndarray:
        return np.tile(np.array([0.4, 0.1, 0.5]), (len(rows), 1))


class _PointsStub:
    def __init__(self, long_points: float, short_points: float) -> None:
        self.long_points = long_points
        self.short_points = short_points

    def predict(self, rows: pd.DataFrame) -> np.ndarray:
        signs = rows["direction_sign"].to_numpy()
        return np.where(signs > 0, self.long_points, self.short_points)


class _BrokenPointsStub:
    def predict(self, rows: pd.DataFrame) -> np.ndarray:
        raise RuntimeError("head is unusable")


PAIR = BarrierPair(take_profit_atr=2.0, stop_loss_atr=1.0)
FEATURES = pd.DataFrame({"momentum_24": [0.01]})


class PointsDecisionTests(unittest.TestCase):
    def test_the_higher_expected_r_side_is_chosen(self) -> None:
        choice = choose_direction(
            _ClassifierStub(),
            FEATURES,
            PAIR,
            points_model=_PointsStub(long_points=0.05, short_points=0.30),
            minimum_expected_points=0.0,
        )
        self.assertEqual(choice.direction.name, "SHORT")
        self.assertAlmostEqual(choice.chosen.expected_points, 0.30)
        self.assertTrue(any("expected points" in line for line in choice.rationale))

    def test_the_points_floor_refuses_a_bet_the_classifier_would_take(self) -> None:
        choice = choose_direction(
            _ClassifierStub(),
            FEATURES,
            PAIR,
            points_model=_PointsStub(long_points=0.20, short_points=0.05),
            minimum_expected_points=0.25,
        )
        self.assertEqual(choice.direction.name, "FLAT")
        self.assertTrue(any("expected points" in line for line in choice.rationale))

    def test_without_a_head_the_old_expected_value_rule_still_decides(self) -> None:
        choice = choose_direction(_ClassifierStub(), FEATURES, PAIR)
        self.assertTrue(choice.direction.is_open)
        self.assertIsNone(choice.chosen.expected_points)
        self.assertAlmostEqual(choice.chosen.expected_value_atr, 0.5 * 2.0 - 0.4 * 1.0)

    def test_a_broken_head_degrades_instead_of_refusing(self) -> None:
        choice = choose_direction(_ClassifierStub(), FEATURES, PAIR, points_model=_BrokenPointsStub())
        self.assertTrue(choice.direction.is_open)
        self.assertIsNone(choice.chosen.expected_points)


if __name__ == "__main__":
    unittest.main()
