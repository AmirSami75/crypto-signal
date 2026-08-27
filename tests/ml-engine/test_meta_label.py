import unittest

import numpy as np
import pandas as pd

from crypto_signal.labeling.meta_label import (
    META_PROFITABLE_COLUMN,
    add_meta_labels,
    build_meta_features,
    realised_return_atr,
)


class RealisedReturnTests(unittest.TestCase):
    """The net return must be the gross ATR multiple minus the round-trip fee, signed per bet."""

    def test_take_profit_first_earns_tp_minus_fee(self) -> None:
        out = realised_return_atr(
            np.array([1]), np.array([1.5]), np.array([1.0]), np.array([0.0]), fee_atr=0.3
        )
        self.assertAlmostEqual(float(out[0]), 1.5 - 0.3)

    def test_stop_loss_first_loses_sl_plus_fee(self) -> None:
        out = realised_return_atr(
            np.array([-1]), np.array([1.5]), np.array([1.0]), np.array([0.0]), fee_atr=0.3
        )
        self.assertAlmostEqual(float(out[0]), -1.0 - 0.3)

    def test_timeout_uses_timeout_mark_minus_fee(self) -> None:
        out = realised_return_atr(
            np.array([0]), np.array([1.5]), np.array([1.0]), np.array([0.2]), fee_atr=0.3
        )
        self.assertAlmostEqual(float(out[0]), 0.2 - 0.3)

    def test_vectorised_all_three_outcomes(self) -> None:
        out = realised_return_atr(
            np.array([1, -1, 0]),
            np.array([1.5, 1.5, 1.5]),
            np.array([1.0, 1.0, 1.0]),
            np.array([0.0, 0.0, 0.1]),
            fee_atr=0.25,
        )
        np.testing.assert_allclose(out, [1.25, -1.25, -0.15])


class BuildMetaFeaturesTests(unittest.TestCase):
    def test_feature_matrix_has_context_plus_p_win(self) -> None:
        frame = pd.DataFrame(
            {
                "take_profit_atr": [1.5, 1.0],
                "stop_loss_atr": [1.0, 1.0],
                "risk_reward_ratio": [1.5, 1.0],
                "direction_sign": [1.0, -1.0],
            }
        )
        features = build_meta_features(frame, np.array([0.6, 0.4]))
        self.assertEqual(list(features.columns), ["take_profit_atr", "stop_loss_atr",
                                                   "risk_reward_ratio", "direction_sign", "p_win"])
        np.testing.assert_allclose(features["p_win"].to_numpy(), [0.6, 0.4])

    def test_missing_context_column_raises(self) -> None:
        frame = pd.DataFrame({"take_profit_atr": [1.5], "direction_sign": [1.0]})
        with self.assertRaises(ValueError):
            build_meta_features(frame, np.array([0.5]))


class AddMetaLabelsTests(unittest.TestCase):
    def make_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "target": [1, -1, 0],
                "take_profit_atr": [1.5, 1.5, 1.5],
                "stop_loss_atr": [1.0, 1.0, 1.0],
                "timeout_return_atr": [0.0, 0.0, 0.6],
            }
        )

    def test_profitable_only_when_net_strictly_positive(self) -> None:
        out = add_meta_labels(self.make_frame(), np.array([0.6, 0.6, 0.6]), fee_atr=0.5)
        # tp_first: 1.5-0.5=1.0 >0 True; stop: -1.5 False; timeout: 0.6-0.5=0.1>0 True
        np.testing.assert_array_equal(out[META_PROFITABLE_COLUMN].to_numpy(), [True, False, True])

    def test_zero_net_is_not_profitable(self) -> None:
        # A tp-first that exactly eats the fee (net == 0.0) must be excluded.
        frame = pd.DataFrame(
            {"target": [1], "take_profit_atr": [0.5], "stop_loss_atr": [1.0],
             "timeout_return_atr": [0.0]}
        )
        out = add_meta_labels(frame, np.array([0.5]), fee_atr=0.5)
        self.assertFalse(bool(out[META_PROFITABLE_COLUMN].iloc[0]))

    def test_missing_label_column_raises(self) -> None:
        frame = pd.DataFrame({"target": [1], "take_profit_atr": [1.5], "stop_loss_atr": [1.0]})
        with self.assertRaises(ValueError):
            add_meta_labels(frame, np.array([0.5]), fee_atr=0.3)

    def test_input_not_mutated(self) -> None:
        frame = self.make_frame()
        before = frame.columns.tolist()
        add_meta_labels(frame, np.array([0.6, 0.6, 0.6]), fee_atr=0.3)
        self.assertEqual(frame.columns.tolist(), before)


if __name__ == "__main__":
    unittest.main()