from __future__ import annotations

import unittest

from crypto_signal.human_output import duration, format_signal_summary, percent


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


if __name__ == "__main__":
    unittest.main()

