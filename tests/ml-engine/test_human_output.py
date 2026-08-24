from __future__ import annotations

import unittest

from crypto_signal.human_output import (
    _bracket_lines,
    duration,
    format_barrier_signal_summary,
    format_signal_summary,
    percent,
)


def bracket(**overrides: object) -> dict:
    """One symbol's bracket statistics, with only the keys `_bracket_lines` actually reads."""
    statistics = {
        "trades": 23,
        "win_rate_resolved": 0.4783,
        "expectancy_atr": -0.3309,
        "mean_fee_atr": 0.3854,
        "profit_factor": 0.63,
        "break_even_win_rate_before_fees": 0.4570,
        "break_even_win_rate": 0.6123,
    }
    statistics.update(overrides)
    return {
        "take_profit_atr": 1.5,
        "stop_loss_atr": 1.0,
        "minimum_confidence": 0.5,
        "symbols": {"BTCUSDT": {"trades": statistics}},
    }


def signal_payload(**overrides: object) -> dict:
    payload = {
        "symbol": "BTCUSDT",
        "interval": "1h",
        "candle_open_time": "2026-08-16T12:00:00+00:00",
        "direction": "LONG",
        "confidence": 0.61,
        "expected_value_atr": 0.0412,
        "bundle": "_pooled_1h",
        "calibration_method": "identity",
        "levels": {
            "entry_price": "60123.50000000",
            "take_profit_price": "61325.97000000",
            "stop_loss_price": "59522.26500000",
            "risk_reward_ratio": 1.5,
            "atr": "401.25000000",
        },
        "requested": {
            "take_profit_percent": 2.0,
            "stop_loss_percent": 1.0,
            "take_profit_atr": 2.9963,
            "stop_loss_atr": 1.4981,
        },
        "candidates": [
            {
                "direction": "LONG",
                "confidence": 0.61,
                "expected_value_atr": 0.0412,
                "break_even": 0.4,
                "probabilities": {"timeout": 0.09},
            },
            {
                "direction": "SHORT",
                "confidence": 0.31,
                "expected_value_atr": -0.2100,
                "break_even": 0.4,
                "probabilities": {"timeout": 0.09},
            },
        ],
        "rationale": ["long: confidence 0.610 clears floor 0.500"],
    }
    payload.update(overrides)
    return payload


class HumanOutputTests(unittest.TestCase):
    def test_percentage_is_human_readable(self) -> None:
        self.assertEqual(percent(0.5234), "52.34%")
        self.assertEqual(percent(0.1234, signed=True), "+12.34%")

    def test_duration_is_human_readable(self) -> None:
        self.assertEqual(duration(0.2), "200 ms")
        self.assertEqual(duration(75), "1m 15s")

    def test_signal_summary_formats_probabilities_as_percentages(self) -> None:
        summary = format_signal_summary(
            {
                "symbol": "BTCUSDT",
                "interval": "1h",
                "candle_open_time_utc": "2026-08-16T12:00:00+00:00",
                "close_price": 60_123.5,
                "signal": "BUY",
                "probabilities": {"SELL": 0.10, "HOLD": 0.20, "BUY": 0.70},
                "probability_threshold": 0.50,
                "data_source": "test",
                "sell_semantics": "SELL exits to cash",
            }
        )
        self.assertIn("Signal:        BUY", summary)
        self.assertIn("BUY chance:    70.00%", summary)
        self.assertIn("Close price:   60,123.50000000", summary)

    def test_the_bracket_summary_names_the_toll_and_both_rungs(self) -> None:
        """The operator's one-screen read of whether a bracket is economic at all.

        The fee is on the line because it is the figure that decides it: at an ATR worth 0.6% of price
        against a 0.25% round trip the toll approaches 0.4 of a 1-ATR stop, and a summary that reports
        expectancy without it says a strategy lost without saying it never could have won.
        """
        lines = _bracket_lines(bracket())
        joined = "\n".join(lines)
        self.assertIn("fee 0.385 ATR", joined)
        self.assertIn("expectancy -0.3309 ATR", joined)
        # Both rungs, in the order they erode: the model cleared the first and missed the second, which is
        # the difference between a bracket to widen and a model to retrain.
        self.assertIn("break-even: 45.70% before fees, 61.23% net", joined)

    def test_a_rung_that_could_not_be_solved_is_omitted_rather_than_guessed(self) -> None:
        """A side with no realised win has no magnitude to average, and substituting the requested
        distance there would report a bar the strategy never had to clear."""
        lines = _bracket_lines(
            bracket(break_even_win_rate_before_fees=None, break_even_win_rate=None)
        )
        joined = "\n".join(lines)
        self.assertNotIn("break-even", joined)
        # The trade line still prints: two trades and no winner is a fact worth showing.
        self.assertIn("fee 0.385 ATR", joined)

    def test_the_signal_summary_leads_with_direction_and_prices_the_other_side_too(self) -> None:
        summary = format_barrier_signal_summary(signal_payload())
        self.assertIn("Direction:     LONG", summary)
        self.assertIn("Entry:         60123.50000000", summary)
        self.assertIn("(+2%, 3.00 ATR)", summary)
        self.assertIn("(-1%, 1.50 ATR)", summary)
        self.assertIn("Confidence:    61.00%", summary)
        self.assertIn("Expected value: +0.0412 ATR per unit risked", summary)
        # Both sides are always priced, so a reader can see the rejected one rather than infer it.
        self.assertIn("SHORT  confidence 31.00%", summary)

    def test_a_flat_answer_labels_its_prices_as_the_bet_that_was_declined(self) -> None:
        """FLAT is an answer, not a failure — but printing its levels under the same heading a live
        signal uses is how a reader places the trade the model refused."""
        summary = format_barrier_signal_summary(
            signal_payload(
                direction="FLAT",
                levels_are_hypothetical=True,
                quoted_direction="LONG",
                rationale=["flat: expected value -0.0210 ATR below zero"],
            )
        )
        self.assertIn("No bet taken — flat: expected value -0.0210 ATR below zero.", summary)
        self.assertIn("the LONG the model priced and rejected", summary)
        self.assertIn("Confidence:    n/a — no bet was chosen", summary)
        # No expected value either: quoting one for a bet nobody took is the same mistake twice.
        self.assertNotIn("Expected value:", summary)


if __name__ == "__main__":
    unittest.main()

