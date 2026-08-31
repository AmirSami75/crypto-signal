"""Unit tests for the real `LstmBundle`.

These need torch, which is an optional dependency. They are skipped automatically when it is not
installed, so the suite stays green on machines without the deep-learning dependency. Run them once
`pip install torch` (CPU build is sufficient) has completed.
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

try:
    import torch  # noqa: F401

    from crypto_signal.modeling.lstm import LstmBundle, LstmConfig, LstmSignalModel

    HAS_TORCH = True
except ImportError:  # pragma: no cover - exercised only without torch
    HAS_TORCH = False


@unittest.skipUnless(HAS_TORCH, "torch is required for the LSTM bundle tests")
class LstmBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = LstmConfig(lookback=8, hidden_size=16, num_layers=1, epochs=1)
        self.feature_columns = ("log_return_1", "rsi_14", "atr_14_normalized")
        model = LstmSignalModel(n_features=len(self.feature_columns), config=self.config)
        self.bundle = LstmBundle(model, self.feature_columns, self.config)

    def _window(self) -> pd.DataFrame:
        rng = np.random.default_rng(0)
        return pd.DataFrame(rng.normal(size=(self.config.lookback, len(self.feature_columns))), columns=list(self.feature_columns))

    def test_predict_proba_returns_long_bet_probabilities(self) -> None:
        probs = self.bundle.predict_proba(self._window())
        self.assertEqual(probs.shape, (1, 3))
        self.assertAlmostEqual(float(probs.sum()), 1.0, places=5)
        # Classes are stop / timeout / take-profit first, in ALL_CLASSES order.
        self.assertTrue(np.allclose(self.bundle.classes_, np.array([-1, 0, 1])))

    def test_wrong_window_length_is_rejected(self) -> None:
        bad = pd.DataFrame(np.zeros((4, len(self.feature_columns))), columns=list(self.feature_columns))
        with self.assertRaises(ValueError):
            self.bundle.predict_proba(bad)

    def test_serialise_roundtrip_restores_a_working_model(self) -> None:
        import io

        import joblib

        buffer = io.BytesIO()
        joblib.dump(self.bundle, buffer)
        buffer.seek(0)
        loaded = joblib.load(buffer)
        self.assertTrue(loaded.is_sequence)
        self.assertEqual(loaded.config.lookback, self.config.lookback)
        before = self.bundle.predict_proba(self._window())
        after = loaded.predict_proba(self._window())
        np.testing.assert_allclose(before, after, atol=1e-6)


if __name__ == "__main__":
    unittest.main()
