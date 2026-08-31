"""Tests for the experimental LSTM sequence model's serving path.

The serving branch is exercised without torch via a fake sequence estimator, so the registry, the
`choose_direction` direction-pricing, and the evaluator windowing are all covered even when the optional
dependency is absent. `test_lstm_bundle.py` covers the real `LstmBundle` and is skipped when torch is not
installed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

import joblib
import numpy as np
import pandas as pd

from crypto_signal.domain import BarrierPair, Direction
from crypto_signal.modeling.direction import choose_direction
from crypto_signal_engine.application.errors import ModelUnavailable
from crypto_signal_engine.application.models import CandleInput, TradeParametersInput
from crypto_signal_engine.application.evaluator import MarketEvaluator
from crypto_signal_engine.infrastructure.model_registry import ModelRegistry


class _FakeSequenceEstimator:
    """A picklable torch-free stand-in for `LstmBundle`, just to drive the serving branch."""

    is_sequence = True
    classes_ = np.array([-1, 0, 1])

    def __init__(self, long_probs: np.ndarray) -> None:
        self._probs = np.asarray(long_probs, dtype=float).reshape(1, 3)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        # The serving layer feeds a window of candles; we ignore its contents and return the long-bet
        # probabilities we were constructed with. Direction is set by `choose_direction` via `direction_sign`.
        return self._probs


def _sequence_bundle(long_probs, feature_columns, lookback=10):
    return {
        "model": _FakeSequenceEstimator(long_probs),
        "feature_columns": list(feature_columns),
        "metadata": {
            "trained_at_utc": datetime(2026, 8, 1, tzinfo=timezone.utc).isoformat(),
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "interval": "1h",
            "atr_window": 14,
            "max_horizon": 24,
            "lookback": lookback,
            "is_sequence": True,
            "project_version": "0.4.0",
            "calibration": {"method": "none"},
        },
    }


def _barriers() -> BarrierPair:
    return BarrierPair(take_profit_atr=1.5, stop_loss_atr=1.0)


class ChooseDirectionSequenceTests(unittest.TestCase):
    def test_sequence_model_prices_long_and_short_from_one_window(self) -> None:
        """The long bet's probabilities come straight from the model; the short bet reuses them under the
        same barriers, and both candidates appear in the choice."""
        window = pd.DataFrame(
            np.random.default_rng(0).normal(size=(10, 3)),
            columns=["log_return_1", "rsi_14", "atr_14_normalized"],
        )
        estimator = _FakeSequenceEstimator([0.1, 0.2, 0.7])  # long bet favours take-profit
        barriers = _barriers()
        choice = choose_direction(
            estimator,
            window,
            barriers,
            allow_short=True,
            minimum_confidence=0.0,
            feature_columns=tuple(window.columns),
        )
        self.assertEqual(choice.direction, Direction.LONG)
        self.assertEqual(choice.candidates[0].direction, Direction.LONG)
        self.assertEqual(choice.candidates[1].direction, Direction.SHORT)
        # The model's long probabilities must be the LONG candidate's outcome probabilities.
        self.assertAlmostEqual(choice.candidates[0].probabilities.win, 0.7)

    def test_sequence_model_with_short_disallowed_returns_flat(self) -> None:
        window = pd.DataFrame(
            np.random.default_rng(1).normal(size=(10, 3)),
            columns=["log_return_1", "rsi_14", "atr_14_normalized"],
        )
        estimator = _FakeSequenceEstimator([0.7, 0.2, 0.1])
        choice = choose_direction(
            estimator,
            window,
            _barriers(),
            allow_short=False,
            minimum_confidence=0.0,
            feature_columns=tuple(window.columns),
        )
        self.assertEqual(choice.direction, Direction.FLAT)


class RegistrySequenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_sequence_bundle_is_loaded_with_is_sequence_and_lookback(self) -> None:
        joblib.dump(
            _sequence_bundle([0.1, 0.2, 0.7], ["log_return_1", "rsi_14"], lookback=10),
            self.directory / "_pooled_1h.joblib",
        )
        model = ModelRegistry(self.directory).resolve("SOLUSDT", "1h")
        self.assertTrue(model.descriptor.is_sequence)
        self.assertEqual(model.descriptor.lookback, 10)
        self.assertTrue(model.is_sequence)

    def test_sequence_bundle_skips_the_barrier_column_guard(self) -> None:
        """A sequence model carries only scale-free features, so the legacy barrier-input check is skipped."""
        joblib.dump(
            _sequence_bundle([0.1, 0.2, 0.7], ["log_return_1"], lookback=5),
            self.directory / "_pooled_1h.joblib",
        )
        # Would raise ModelUnavailable for a row model missing the barrier columns; must not here.
        model = ModelRegistry(self.directory).resolve("BTCUSDT", "1h")
        self.assertTrue(model.descriptor.is_sequence)


def _window(n: int):
    from datetime import timedelta
    from decimal import Decimal

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    close = 100.0
    candles = []
    for index in range(n):
        price = close + index * 0.01
        candles.append(
            CandleInput(
                open_time=start + timedelta(hours=index),
                open=Decimal(price),
                high=Decimal(price + 0.5),
                low=Decimal(price - 0.5),
                close=Decimal(price),
                volume=Decimal(100 + index % 7),
            )
        )
    return tuple(candles)


class EvaluatorSequenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)
        # `lookback` small enough to sit under the warm-up the evaluator requires.
        joblib.dump(
            _sequence_bundle(
                [0.15, 0.20, 0.65], ["log_return_1", "rsi_14", "atr_14_normalized"], lookback=10
            ),
            self.directory / "_pooled_1h.joblib",
        )
        self.evaluator = MarketEvaluator(
            registry=ModelRegistry(self.directory),
            minimum_candles=169,
            maximum_candles=2_000,
            default_max_holding_periods=24,
            default_minimum_confidence=0.5,
            barrier_atr_bounds=(0.4, 4.0),
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_sequence_request_is_assessed_from_a_window(self) -> None:
        assessment = self.evaluator.assess(
            request_id="seq",
            symbol="BTCUSDT",
            interval="1h",
            candles=_window(200),
            parameters=TradeParametersInput(
                take_profit_percent=__import__("decimal").Decimal("2"),
                stop_loss_percent=__import__("decimal").Decimal("1"),
                allow_short=True,
            ),
        )
        # The window is long enough; the model prices both directions and the choice is populated.
        self.assertIn(assessment.choice.direction, (Direction.LONG, Direction.SHORT, Direction.FLAT))


if __name__ == "__main__":
    unittest.main()
