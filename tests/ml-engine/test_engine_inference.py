from __future__ import annotations

from datetime import UTC
from pathlib import Path
import unittest

import pandas as pd

from crypto_signal_engine.application.errors import InvalidInferenceRequest
from crypto_signal_engine.application.inference import InferenceService
from crypto_signal_engine.application.models import CandleInput, PredictionInput
from crypto_signal_engine.infrastructure.model_repository import JoblibModelRepository


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ML_ROOT = REPOSITORY_ROOT / "src" / "signal-ml"


class EngineInferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = JoblibModelRepository(
            ML_ROOT / "artifacts" / "model.joblib"
        )
        cls.model_info = cls.repository.load()
        cls.service = InferenceService(cls.repository, 169, 2_000)
        frame = pd.read_csv(ML_ROOT / "data" / "BTCUSDT_1h.csv").tail(300)
        timestamps = pd.to_datetime(frame["timestamp"], utc=True)
        cls.candles = tuple(
            CandleInput(
                open_time=timestamp.to_pydatetime().astimezone(UTC),
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
            )
            for timestamp, row in zip(timestamps, frame.itertuples(index=False), strict=True)
        )

    def test_model_metadata_is_loaded_and_versioned(self) -> None:
        self.assertEqual("BTCUSDT", self.model_info.symbol)
        self.assertEqual("1h", self.model_info.interval)
        self.assertEqual(64, len(self.model_info.model_version))
        self.assertGreater(self.model_info.feature_count, 20)

    def test_predict_returns_auditable_probabilities(self) -> None:
        result = self.service.predict(
            PredictionInput(
                request_id="test-prediction",
                symbol="BTCUSDT",
                interval="1h",
                candles=self.candles,
                expected_model_version=self.model_info.model_version,
            )
        )
        self.assertIn(result.signal_name, {"SELL", "HOLD", "BUY"})
        self.assertAlmostEqual(
            1.0,
            result.probability_sell + result.probability_hold + result.probability_buy,
            places=8,
        )
        self.assertEqual(64, len(result.input_digest_sha256))
        self.assertEqual(self.model_info.model_version, result.model.model_version)

    def test_predict_rejects_a_model_market_mismatch(self) -> None:
        with self.assertRaisesRegex(InvalidInferenceRequest, "Loaded model supports"):
            self.service.predict(
                PredictionInput(
                    request_id="wrong-market",
                    symbol="ETHUSDT",
                    interval="1h",
                    candles=self.candles,
                )
            )


if __name__ == "__main__":
    unittest.main()
