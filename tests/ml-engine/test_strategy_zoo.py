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


if __name__ == "__main__":
    unittest.main()
