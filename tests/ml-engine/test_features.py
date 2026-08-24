from __future__ import annotations

import unittest

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

import crypto_signal.features as features_module
from crypto_signal.features import WARMUP_COLUMNS, build_features
from crypto_signal.features.indicators import average_true_range
from crypto_signal.labeling import label_horizon_return


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

        before = build_features(original).frame.iloc[: cutoff + 1]
        after = build_features(changed).frame.iloc[: cutoff + 1]
        assert_frame_equal(before, after)

    def test_target_leaves_unknown_future_as_nan(self) -> None:
        close = pd.Series([100.0, 101.0, 99.0, 104.0, 105.0])
        target = label_horizon_return(close, prediction_horizon=2, threshold=0.01)
        self.assertTrue(target["target"].iloc[-2:].isna().all())
        self.assertEqual(int(target["target"].iloc[0]), -1)
        self.assertEqual(int(target["target"].iloc[1]), 1)

    def test_every_feature_is_scale_free(self) -> None:
        """Doubling every price must leave the features alone.

        This is what makes one model answer a market it was never trained on, and therefore what makes
        "signal for the requested currency" work for a symbol with no dedicated model. A feature that
        carried an absolute price would fail here, and would otherwise only be caught by a model that
        works on BTC and is quietly wrong on everything cheaper.
        """
        original = sample_frame()
        scaled = original.copy()
        scaled[["open", "high", "low", "close"]] *= 7.0

        assert_frame_equal(
            build_features(original).frame.drop(columns=["volume_log_change_1"]),
            build_features(scaled).frame.drop(columns=["volume_log_change_1"]),
            atol=1e-9,
        )


class FeatureFrameTests(unittest.TestCase):
    """The columns travel with the frame instead of through a module-level global."""

    def test_the_mutable_module_global_is_gone(self) -> None:
        """`make_features` used to publish its columns by reassigning a module attribute.

        Under the eight-worker gRPC server that is a write race: whichever request finished last decided
        what every other request thought the columns were. Its absence is worth asserting, because
        re-adding it would look like a convenience.
        """
        self.assertFalse(hasattr(features_module, "FEATURE_COLUMNS"))

    def test_columns_cannot_be_appended_to_by_a_caller(self) -> None:
        self.assertIsInstance(build_features(sample_frame()).columns, tuple)

    def test_two_calls_do_not_share_column_state(self) -> None:
        wide = build_features(sample_frame())
        narrow_frame = sample_frame().drop(columns=["volume"]).assign(volume=1.0)
        narrow = build_features(narrow_frame)

        self.assertEqual(wide.columns, narrow.columns)
        self.assertIsNot(wide.frame, narrow.frame)

    def test_the_atr_comes_back_in_price_units(self) -> None:
        """Barrier distances are measured against this, so it must not be the normalised feature."""
        frame = sample_frame()
        built = build_features(frame)

        pd.testing.assert_series_equal(built.atr, average_true_range(frame, 14).rename("atr"))
        self.assertGreater(built.atr.iloc[-1], 0.0)

    def test_the_normalised_atr_feature_is_the_raw_atr_over_close(self) -> None:
        frame = sample_frame()
        built = build_features(frame)

        pd.testing.assert_series_equal(
            built.frame["atr_14_normalized"],
            (built.atr / frame["close"].astype(float)).rename("atr_14_normalized"),
        )

    def test_warm_up_columns_are_all_present_in_the_frame(self) -> None:
        built = build_features(sample_frame())
        for column in WARMUP_COLUMNS:
            with self.subTest(column=column):
                self.assertIn(column, built.columns)

    def test_select_returns_the_columns_in_training_order(self) -> None:
        built = build_features(sample_frame())
        selected = built.select(built.frame.index[-3:])

        self.assertEqual(tuple(selected.columns), built.columns)
        self.assertEqual(len(selected), 3)


if __name__ == "__main__":
    unittest.main()

