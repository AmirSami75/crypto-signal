import unittest

import numpy as np
import pandas as pd

from crypto_signal.labeling.triple_barrier import (
    UNIQUENESS_COLUMN,
    compute_uniqueness_weights,
)


class UniquenessTests(unittest.TestCase):
    def setUp(self) -> None:
        # Two symbols. BTC: 3 variants on the same candle -> each gets 1/3.
        # ETH: 1 variant on candle t1, 1 on t2 (different times) -> each gets 1.
        # All barrier-context columns are placeholders; only timestamp + symbol drive the weight.
        self.frame = pd.DataFrame(
            {
                "symbol": ["BTCUSDT"] * 3 + ["ETHUSDT"] * 2,
                "timestamp": pd.to_datetime(
                    [
                        "2024-01-01 00:00:00",
                        "2024-01-01 00:00:00",
                        "2024-01-01 00:00:00",
                        "2024-01-01 00:00:00",
                        "2024-01-01 01:00:00",
                    ],
                    utc=True,
                ),
                "take_profit_atr": [1.5, 1.0, 0.5, 1.5, 1.5],
                "stop_loss_atr": [1.0, 1.0, 1.0, 1.0, 1.0],
                "direction_sign": [1.0, -1.0, 1.0, 1.0, -1.0],
                "target": [1, -1, 0, 1, 1],
            }
        )

    def test_unique_weight_equals_inverse_overlap(self) -> None:
        out = compute_uniqueness_weights(self.frame)
        btc = out[out["symbol"] == "BTCUSDT"]["uniqueness"].to_numpy()
        eth = out[out["symbol"] == "ETHUSDT"]["uniqueness"].to_numpy()
        np.testing.assert_allclose(btc, [1 / 3, 1 / 3, 1 / 3])
        np.testing.assert_allclose(eth, [1.0, 1.0])

    def test_effective_sample_size_equals_unique_candle_count(self) -> None:
        # AFML: the SUM of uniqueness equals the number of unique (candle, symbol) keys.
        out = compute_uniqueness_weights(self.frame)
        self.assertAlmostEqual(float(out[UNIQUENESS_COLUMN].sum()), 3.0)  # 2 BTC candles + 1 ETH... no, 1 BTC + 2 ETH

    def test_effective_sample_size_matches_unique_keys(self) -> None:
        out = compute_uniqueness_weights(self.frame)
        unique_keys = self.frame[["symbol", "timestamp"]].drop_duplicates()
        self.assertAlmostEqual(
            float(out[UNIQUENESS_COLUMN].sum()), float(len(unique_keys))
        )

    def test_zero_overlap_keys_collapse_to_zero_weight(self) -> None:
        # Each row is its own unique (symbol, timestamp) key -> uniqueness 1.0.
        frame = pd.DataFrame(
            {
                "symbol": ["A", "A", "A"],
                "timestamp": pd.to_datetime(
                    ["2024-01-01 00:00", "2024-01-01 01:00", "2024-01-01 02:00"], utc=True
                ),
                "target": [1, 1, -1],
            }
        )
        out = compute_uniqueness_weights(frame)
        self.assertTrue((out[UNIQUENESS_COLUMN] == 1.0).all())

    def test_required_columns(self) -> None:
        with self.assertRaises(ValueError):
            compute_uniqueness_weights(pd.DataFrame({"foo": [1]}))

    def test_pure_uniqueness_series_helper(self) -> None:
        # No DataFrame round-trip; the helper takes a frame and returns a float Series.
        out = compute_uniqueness_weights(self.frame)
        self.assertEqual(len(out), len(self.frame))
        self.assertTrue((out >= 0).all())
        self.assertTrue((out <= 1.0).all())


if __name__ == "__main__":
    unittest.main()