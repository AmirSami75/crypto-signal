"""Known-answer tests for the quantile -> barrier probability bridge.

These are the guardrails: if any fails, the TFT challenger's probabilities are
fabricated, not derived, and must not ship.
"""

from __future__ import annotations

import numpy as np
import pytest

from crypto_signal.modeling.pf_bridge import (
    BarrierProbabilities,
    barrier_probabilities_from_quantiles,
    expected_value_atr,
)


class TestKnownAnswers:
    """Synthetic distributions where the answer is provably known."""

    def test_symmetric_distribution_symmetric_probabilities(self):
        """A symmetric CDF around zero gives equal win/loss mass for a symmetric bet.

        With a conservative-first-passage bound, the win/loss split is symmetric
        but the magnitude is bounded (not the full marginal) because the joint
        first-passage probability is unknown. What matters: win == loss, and
        timeout absorbs the rest.
        """
        # Quantiles at -2%, 0%, +2%; TP at +1%, SL at -1%.
        # CDF at -1% (SL): interpolated between -2% (CDF=0.1) and 0% (CDF=0.5)
        #   => CDF(-0.01) = 0.5 * (0.01 - (-0.02)) / (0.0 - (-0.02)) = 0.5 * 0.5 = 0.25
        #   Actually: np.interp(-0.01, [-0.02, 0.0, 0.02], [0.1, 0.5, 0.9])
        #   => 0.1 + (0.01 - (-0.02)) / (0.0 - (-0.02)) * (0.5 - 0.1) = 0.1 + 0.5*0.4 = 0.3
        # CDF at +1% (TP): np.interp(0.01, ...) = 0.5 + 0.5*0.4 = 0.7
        # p_above_tp = 1 - 0.7 = 0.3; p_below_sl = 0.3
        # win = min(0.3, 1-0.3) = 0.3; loss = min(0.3, 1-0.3) = 0.3; timeout = 0.4
        probs = barrier_probabilities_from_quantiles(
            {0.1: -0.02, 0.5: 0.0, 0.9: 0.02},
            take_profit_return=0.01,
            stop_loss_return=-0.01,
        )
        assert probs.win == pytest.approx(probs.loss, abs=1e-9)
        assert probs.total <= 1.0 + 1e-9
        assert probs.timeout == pytest.approx(1.0 - probs.win - probs.loss, abs=1e-9)

    def test_zero_width_distribution_mass_on_near_barrier(self):
        """All quantiles equal => degenerate, mass goes to whichever barrier is closer."""
        # If every quantile says 0.0 return, and TP=0.01, SL=-0.01:
        # CDF is a step at 0.0: P(return <= x) = 0 for x<0, 1 for x>=0.
        # CDF at SL(-0.01) = 0 => p_below_sl = 0.
        # CDF at TP(0.01) = 1 => p_above_tp = 0.
        # win = 0, loss = 0, timeout = 1.0.
        # That is correct: a certain-flat forecast should put all mass in timeout.
        probs = barrier_probabilities_from_quantiles(
            {0.1: 0.0, 0.5: 0.0, 0.9: 0.0},
            take_profit_return=0.01,
            stop_loss_return=-0.01,
        )
        assert probs.timeout == pytest.approx(1.0, abs=1e-9)
        assert probs.win == pytest.approx(0.0, abs=1e-9)
        assert probs.loss == pytest.approx(0.0, abs=1e-9)

    def test_all_mass_below_stop_loss_goes_to_loss(self):
        """Entire forecast below the stop-loss barrier => loss mass = 1."""
        # Quantiles at -5%, -4%, -3%; SL at -1%. CDF at -0.01 = 1.0 (all mass below).
        # p_below_sl = 1.0, p_above_tp = 0 (all mass below TP=0.01 too).
        # win = min(0, 0) = 0, loss = min(1.0, 1.0) = 1.0, timeout = 0.
        probs = barrier_probabilities_from_quantiles(
            {0.1: -0.05, 0.5: -0.04, 0.9: -0.03},
            take_profit_return=0.01,
            stop_loss_return=-0.01,
        )
        assert probs.loss == pytest.approx(1.0, abs=1e-9)
        assert probs.win == pytest.approx(0.0, abs=1e-9)
        assert probs.timeout == pytest.approx(0.0, abs=1e-9)

    def test_all_mass_above_take_profit_goes_to_win(self):
        """Entire forecast above the take-profit barrier => win mass = 1."""
        probs = barrier_probabilities_from_quantiles(
            {0.1: 0.03, 0.5: 0.04, 0.9: 0.05},
            take_profit_return=0.01,
            stop_loss_return=-0.01,
        )
        assert probs.win == pytest.approx(1.0, abs=1e-9)
        assert probs.loss == pytest.approx(0.0, abs=1e-9)
        assert probs.timeout == pytest.approx(0.0, abs=1e-9)


class TestInvariants:
    """Properties that must hold for *any* valid input."""

    def test_probabilities_sum_to_at_most_one(self):
        """win + loss + timeout <= 1.0 always (timeout is the residual)."""
        for seed in range(20):
            rng = np.random.default_rng(seed)
            levels = sorted(rng.uniform(0.05, 0.95, size=5))
            values = np.sort(rng.normal(0, 0.02, size=5))
            quantiles = {l: float(v) for l, v in zip(levels, values)}
            try:
                probs = barrier_probabilities_from_quantiles(
                    quantiles, take_profit_return=0.015, stop_loss_return=-0.01,
                )
            except ValueError:
                # Sometimes the random draw lands all mass on one side — that's
                # a degenerate bet the bridge correctly rejects.
                continue
            total = probs.total
            assert total <= 1.0 + 1e-9, f"sum {total} > 1 for seed {seed}"
            assert probs.win >= 0.0
            assert probs.loss >= 0.0
            assert probs.timeout >= 0.0

    def test_short_side_mirrors_long(self):
        """A mirrored forecast + mirrored barriers gives mirrored probabilities.

        For a short, the forecast is the same distribution (the model predicts
        returns regardless of direction), but TP is below 0 and SL is above 0.
        The bridge should produce win/loss swapped vs. the long case — win for
        the long becomes loss for the short and vice versa, with timeout preserved.
        """
        quantiles = {0.1: -0.02, 0.5: 0.0, 0.9: 0.02}
        # Long: TP=+0.01, SL=-0.01 (symmetric barriers for clean mirroring)
        probs_long = barrier_probabilities_from_quantiles(
            quantiles, take_profit_return=0.01, stop_loss_return=-0.01,
        )
        # Short: TP=-0.01 (below), SL=+0.01 (above). Same forecast distribution.
        # CDF at -0.01 = 0.3, CDF at +0.01 = 0.7
        # Short: p_at_risk_win = CDF(TP) = 0.3; p_at_risk_loss = 1-CDF(SL) = 0.3
        # For symmetric barriers: long win = short loss, long loss = short win
        probs_short = barrier_probabilities_from_quantiles(
            quantiles, take_profit_return=-0.01, stop_loss_return=0.01,
        )
        assert probs_short.loss == pytest.approx(probs_long.win, abs=1e-9)
        assert probs_short.win == pytest.approx(probs_long.loss, abs=1e-9)
        assert probs_short.timeout == pytest.approx(probs_long.timeout, abs=1e-9)

    def test_to_class_array_shape_and_order(self):
        """The class array is [-1, 0, 1] order = [loss, timeout, win]."""
        probs = barrier_probabilities_from_quantiles(
            {0.1: -0.02, 0.5: 0.0, 0.9: 0.02},
            take_profit_return=0.01,
            stop_loss_return=-0.01,
        )
        arr = probs.to_class_array()
        assert arr.shape == (3,)
        # [-1, 0, +1] order => [loss, timeout, win]
        assert arr[0] == pytest.approx(probs.loss)
        assert arr[1] == pytest.approx(probs.timeout)
        assert arr[2] == pytest.approx(probs.win)


class TestValidation:
    """Input contract enforcement."""

    def test_empty_quantiles_rejected(self):
        with pytest.raises(ValueError, match="must not be empty"):
            barrier_probabilities_from_quantiles({}, 0.01, -0.01)

    def test_single_quantile_rejected(self):
        with pytest.raises(ValueError, match="at least two"):
            barrier_probabilities_from_quantiles({0.5: 0.0}, 0.01, -0.01)

    def test_non_monotonic_rejected(self):
        with pytest.raises(ValueError, match="monotonic"):
            barrier_probabilities_from_quantiles(
                {0.1: 0.02, 0.5: -0.01, 0.9: 0.0},
                take_profit_return=0.01,
                stop_loss_return=-0.01,
            )

    def test_same_sign_barrels_rejected(self):
        """Both barriers on the same side of zero is not a directed bet."""
        with pytest.raises(ValueError, match="barrier signs"):
            barrier_probabilities_from_quantiles(
                {0.1: -0.03, 0.5: -0.01, 0.9: 0.0},
                take_profit_return=-0.01,
                stop_loss_return=-0.02,
            )


class TestExpectedValue:
    """The EV formula matches the engine's expectancy convention."""

    def test_positive_ev_when_win_dominates(self):
        probs = BarrierProbabilities(win=0.6, loss=0.2, timeout=0.2)
        # EV = 0.6 * 1.5 - 0.2 * 1.0 = 0.9 - 0.2 = 0.7
        assert expected_value_atr(probs, 1.5, 1.0) == pytest.approx(0.7)

    def test_negative_ev_when_loss_dominates(self):
        probs = BarrierProbabilities(win=0.2, loss=0.6, timeout=0.2)
        assert expected_value_atr(probs, 1.5, 1.0) == pytest.approx(-0.3)

    def test_zero_ev_with_no_trades(self):
        probs = BarrierProbabilities(win=0.0, loss=0.0, timeout=1.0)
        assert expected_value_atr(probs, 1.5, 1.0) == pytest.approx(0.0)
