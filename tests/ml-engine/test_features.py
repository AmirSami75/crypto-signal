from __future__ import annotations

import unittest

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from crypto_signal.features import make_features, make_target


def sample_frame(rows: int = 260) -> pd.DataFrame:
    timestamp = pd.date_range("2024-01-01", periods=rows, freq="h", tz="UTC")
    close = pd.Series(100 + np.arange(rows) * 0.1 + np.sin(np.arange(rows) / 5))
    open_ = close.shift(1).fillna(close.iloc[0])
    return pd.DataFrame(
        {
            "timestamp": timestamp,
            "open": open_,
            "high": np.maximum(open_, close) + 0.5,
            "low": np.minimum(open_, close) - 0.5,
            "close": close,
            "volume": 1_000 + np.arange(rows),
        }
    )


class FeatureTests(unittest.TestCase):
    def test_future_mutation_does_not_change_past_features(self) -> None:
        original = sample_frame()
        changed = original.copy()
        cutoff = 210
        changed.loc[cutoff + 1 :, ["open", "high", "low", "close"]] *= 5
        changed.loc[cutoff + 1 :, "volume"] *= 10

        before = make_features(original).iloc[: cutoff + 1]
        after = make_features(changed).iloc[: cutoff + 1]
        assert_frame_equal(before, after)

    def test_target_leaves_unknown_future_as_nan(self) -> None:
        close = pd.Series([100.0, 101.0, 99.0, 104.0, 105.0])
        target = make_target(close, prediction_horizon=2, threshold=0.01)
        self.assertTrue(target["target"].iloc[-2:].isna().all())
        self.assertEqual(int(target["target"].iloc[0]), -1)
        self.assertEqual(int(target["target"].iloc[1]), 1)


if __name__ == "__main__":
    unittest.main()

