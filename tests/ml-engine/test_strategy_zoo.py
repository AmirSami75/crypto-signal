"""Strategy Zoo tests: registry round-trip, per-strategy triggers, and league ranking."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from crypto_signal.features.indicators import average_true_range
from crypto_signal.strategies import STRATEGIES, Signal, register


def make_frame(closes, start="2024-01-01") -> pd.DataFrame:
    """An OHLCV frame from a close path: open = previous close, symmetric wicks, ATR attached."""
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range(start, periods=n, freq="15min", tz="UTC"),
            "open": np.concatenate([[closes[0]], closes[:-1]]),
            "high": closes + 0.5,
            "low": closes - 0.5,
            "close": closes,
            "volume": np.full(n, 1000.0),
        }
    )
    frame["atr"] = average_true_range(frame, 14)
    return frame


class RegistryTests(unittest.TestCase):
    def test_registry_roundtrip(self) -> None:
        @register("test_dummy_roundtrip")
        def dummy(frame: pd.DataFrame):
            return None

        try:
            self.assertIn("test_dummy_roundtrip", STRATEGIES)
            self.assertIs(STRATEGIES["test_dummy_roundtrip"], dummy)
        finally:
            del STRATEGIES["test_dummy_roundtrip"]  # keep the production registry clean

    def test_nine_strategies_registered(self) -> None:
        expected = {
            "rsi",
            "bollinger",
            "macd",
            "ema_cross",
            "supertrend",
            "donchian",
            "rsi_pullback",
            "keltner_breakout",
            "triple_ema",
        }
        self.assertTrue(expected.issubset(STRATEGIES.keys()), f"missing: {expected - set(STRATEGIES)}")


def strategy(name: str, frame: pd.DataFrame):
    """Run one registered strategy and return its Signal or None."""
    return STRATEGIES[name](frame)


class StrategyTriggerTests(unittest.TestCase):
    """One synthetic frame per strategy that provably fires the rule, plus a flat frame that must not.

    Signals are evaluated on the last candle of each frame: every strategy reads closed candles and
    fires on the transition into its setup, so the trigger lives at the final bar.
    """

    # -- RSI: a long downtrend into the final bars drives RSI below 30; the flat frame stays ~50.

    def test_rsi_triggers_on_oversold(self) -> None:
        closes = list(np.linspace(120, 60, 55)) + list(np.linspace(60, 68, 6)) + [64.0, 62.0]
        signal = strategy("rsi", make_frame(closes))
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.direction, "LONG")
        self.assertEqual(signal.entry_index, len(closes) - 1)

    def test_rsi_quiet_on_neutral(self) -> None:
        self.assertIsNone(strategy("rsi", make_frame([100.0 - 0.001 * i for i in range(60)])))

    # -- Bollinger: a close far below the lower band is a mean-reversion LONG.

    def test_bollinger_triggers_below_lower_band(self) -> None:
        closes = [100.0] * 30 + list(np.linspace(100, 92, 14)) + [86.0]
        signal = strategy("bollinger", make_frame(closes))
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.direction, "LONG")
        self.assertEqual(signal.entry_index, len(closes) - 1)

    def test_bollinger_quiet_inside_band(self) -> None:
        self.assertIsNone(strategy("bollinger", make_frame([100.0] * 45)))

    # -- MACD: a V-shaped reversal (deep drop, then 12+ rising bars) flips the histogram positive.

    def test_macd_triggers_on_bullish_cross(self) -> None:
        closes = (
            list(np.linspace(130, 90, 55))
            + list(np.linspace(90, 104, 13))
            + [104.0, 95.0, 88.0, 85.0, 95.0, 108.0]  # mini-V: histogram re-crosses 0 on the final bar
        )
        signal = strategy("macd", make_frame(closes))
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.direction, "LONG")
        self.assertEqual(signal.entry_index, len(closes) - 1)

    def test_macd_quiet_on_trend(self) -> None:
        closes = [100.0] * 35 + list(np.linspace(100, 130, 26))
        self.assertIsNone(strategy("macd", make_frame(closes)))

    # -- EMA cross: fast EMA crosses above slow after a reversal; stays crossed on a steady trend.

    def test_ema_cross_triggers_on_golden_cross(self) -> None:
        closes = list(np.linspace(140, 80, 55)) + [82.0] * 6 + [84.0, 95.0, 105.0, 115.0]
        signal = strategy("ema_cross", make_frame(closes))
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.direction, "LONG")
        self.assertEqual(signal.entry_index, len(closes) - 1)

    def test_ema_cross_quiet_on_steady_trend(self) -> None:
        closes = list(np.linspace(80, 140, 60)) + [140.0]
        self.assertIsNone(strategy("ema_cross", make_frame(closes)))

    # -- Supertrend: a deep downtrend followed by a strong rally flips the direction band to LONG.

    def test_supertrend_triggers_after_reversal_up(self) -> None:
        closes = list(np.linspace(150, 90, 50)) + [90.0] * 6 + [92.0, 125.0]
        signal = strategy("supertrend", make_frame(closes))
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.direction, "LONG")

    def test_supertrend_quiet_on_pure_trend(self) -> None:
        closes = list(np.linspace(80, 150, 60)) + [150.0]
        self.assertIsNone(strategy("supertrend", make_frame(closes)))

    # -- Donchian: the final close pokes above the prior 20-bar high.

    def test_donchian_triggers_on_channel_breakout(self) -> None:
        closes = [100.0] * 40 + list(np.linspace(100, 100.5, 5)) + [109.0]
        signal = strategy("donchian", make_frame(closes))
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.direction, "LONG")
        self.assertEqual(signal.entry_index, len(closes) - 1)

    def test_donchian_quiet_inside_channel(self) -> None:
        closes = [100.0] * 30 + list(np.linspace(100, 104, 15)) + [104.0]
        self.assertIsNone(strategy("donchian", make_frame(closes)))

    # -- RSI pullback: uptrend, pullback to RSI < 40, last bar resumes with a higher close.

    def test_rsi_pullback_triggers_on_uptrend_dip(self) -> None:
        closes = (
            list(np.linspace(80, 130, 40))  # uptrend: RSI high
            + list(np.linspace(130, 112, 12))  # pullback: RSI < 40
            + [112.0, 116.0]  # resume: rising close on the final bar
        )
        signal = strategy("rsi_pullback", make_frame(closes))
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.direction, "LONG")

    def test_rsi_pullback_quiet_when_no_uptrend(self) -> None:
        closes = list(np.linspace(130, 80, 40)) + list(np.linspace(80, 70, 14))
        self.assertIsNone(strategy("rsi_pullback", make_frame(closes)))

    # -- Keltner: close breaks the upper band (EMA + 2*ATR) after sitting inside it.

    def test_keltner_triggers_on_upper_break(self) -> None:
        closes = [100.0] * 40 + [100.0, 102.0, 107.0]
        signal = strategy("keltner_breakout", make_frame(closes))
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.direction, "LONG")

    def test_keltner_quiet_inside_band(self) -> None:
        self.assertIsNone(strategy("keltner_breakout", make_frame([100.0] * 45)))

    # -- Triple EMA: downtrend then a strong rally in which TEMA flips from below to above price.

    def test_triple_ema_triggers_on_trend_flip(self) -> None:
        closes = list(np.linspace(150, 80, 45)) + list(np.linspace(80, 140, 16)) + [130.0, 141.0]
        signal = strategy("triple_ema", make_frame(closes))
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.direction, "LONG")

    def test_triple_ema_quiet_on_pure_trend(self) -> None:
        closes = list(np.linspace(80, 150, 60)) + [150.0]
        self.assertIsNone(strategy("triple_ema", make_frame(closes)))


if __name__ == "__main__":
    unittest.main()
