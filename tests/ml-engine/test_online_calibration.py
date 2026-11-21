"""The fast learning loop: does a market's stated confidence match what actually happened?

The slow loop trains a challenger; this one only asks whether the incumbent's *number* can be trusted
on this market, and corrects it when it cannot. The tests pin the four properties that make that safe:

* nothing changes before a market has enough resolved trades,
* a curve that would barely move anything is not applied at all,
* the map is monotone (isotonic), so a higher raw score never becomes a lower probability,
* the corrected probability row still sums to one — no outcome mass is invented or lost.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from crypto_signal.domain import BarrierPair, Direction
from crypto_signal.modeling.direction import choose_direction
from crypto_signal_engine.application.online_calibration import (
    MIN_SAMPLES,
    CalibrationPoint,
    CalibrationStore,
    fit_curve,
)
from crypto_signal_engine.application.online_learning import TradeSampleStore
from crypto_signal_engine.application.online_service import OnlineLearningService, TradeOutcomeInput


def points(predicted: float, wins: int, total: int) -> list[CalibrationPoint]:
    return [
        CalibrationPoint(predicted=predicted, won=index < wins, at="2026-11-09T00:00:00Z")
        for index in range(total)
    ]


class CurveTests(unittest.TestCase):
    def test_not_enough_samples_is_not_a_curve(self) -> None:
        self.assertIsNone(fit_curve(points(0.60, wins=10, total=MIN_SAMPLES - 1)))

    def test_a_constant_outcome_cannot_be_calibrated(self) -> None:
        self.assertIsNone(fit_curve(points(0.60, wins=MIN_SAMPLES, total=MIN_SAMPLES)))

    def test_overconfidence_is_corrected_downwards(self) -> None:
        # 60 % predicted, 20 % observed -> the corrected 0.60 must sit well below 0.60.
        curve = fit_curve(points(0.60, wins=40, total=200))
        self.assertIsNotNone(curve)
        self.assertLess(curve(0.60), 0.45)
        self.assertGreater(curve(0.60), 0.10)

    def test_the_map_never_inverts_the_ranking(self) -> None:
        sample = points(0.55, wins=60, total=100) + points(0.75, wins=40, total=100)
        curve = fit_curve(sample)
        self.assertIsNotNone(curve)
        adjusted = [curve(value) for value in np.linspace(0.0, 1.0, 101)]
        self.assertTrue(all(a <= b + 1e-9 for a, b in zip(adjusted, adjusted[1:])))

    def test_a_flat_curve_is_not_worth_applying(self) -> None:
        # Well-calibrated data: observed rate equals the predicted rate in every bin.
        sample = points(0.40, wins=40, total=100) + points(0.60, wins=60, total=100) + points(0.80, wins=80, total=100)
        self.assertIsNone(fit_curve(sample))


class StoreTests(unittest.TestCase):
    def test_points_survive_a_restart(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "calibration.json"
            store = CalibrationStore(path)
            store.add("BTCUSDT", "1h", 0.61, True)
            store.add("BTCUSDT", "1h", 0.58, False)

            reloaded = CalibrationStore(path)
            status = reloaded.status()
            self.assertEqual(len(status), 1)
            self.assertEqual(status[0]["samples"], 2)
            self.assertFalse(status[0]["ready"])

    def test_the_adjuster_waits_for_enough_samples(self) -> None:
        with TemporaryDirectory() as directory:
            store = CalibrationStore(Path(directory) / "calibration.json")
            for index in range(MIN_SAMPLES - 1):
                store.add("ETHUSDT", "5m", 0.60, index % 5 == 0)
            self.assertIsNone(store.adjuster("ETHUSDT", "5m"))

    def test_a_ready_adjuster_keeps_rows_normalised(self) -> None:
        with TemporaryDirectory() as directory:
            store = CalibrationStore(Path(directory) / "calibration.json")
            for index in range(200):
                store.add("SOLUSDT", "1h", 0.60, index % 5 == 0)
            adjuster = store.adjuster("SOLUSDT", "1h")
            self.assertIsNotNone(adjuster)

            rows = np.array([[0.30, 0.10, 0.60], [0.50, 0.05, 0.45]])
            adjusted = adjuster(rows)
            np.testing.assert_allclose(adjusted.sum(axis=1), 1.0, atol=1e-9)
            # The overconfident win mass moved down, and the loss branch absorbed the difference.
            self.assertLess(adjusted[0, 2], 0.60)
            self.assertGreater(adjusted[0, 0], 0.30)


class _ClassifierStub:
    classes_ = np.array([-1, 0, 1])
    is_sequence = False

    def predict_proba(self, rows: pd.DataFrame) -> np.ndarray:
        return np.tile(np.array([0.20, 0.10, 0.70]), (len(rows), 1))


class DirectionAdjustmentTests(unittest.TestCase):
    """The correction has to reach the decision, not just the report."""

    def test_an_adjusted_probability_can_turn_a_qualified_bet_flat(self) -> None:
        pair = BarrierPair(take_profit_atr=2.0, stop_loss_atr=1.0)
        features = pd.DataFrame({"momentum_24": [0.01]})

        # Unadjusted: confidence 0.70 clears a 0.60 floor.
        unadjusted = choose_direction(
            _ClassifierStub(), features, pair, minimum_confidence=0.60, feature_columns=None
        )
        self.assertTrue(unadjusted.direction.is_open)

        # Correction maps 0.70 -> 0.30; the same floor now refuses it.
        def adjuster(probabilities: np.ndarray) -> np.ndarray:
            matrix = probabilities.copy()
            matrix[:, 2] = 0.30
            matrix[:, 0] = 0.60
            matrix[:, 1] = 0.10
            return matrix

        corrected = choose_direction(
            _ClassifierStub(), features, pair, minimum_confidence=0.60, probability_adjuster=adjuster
        )
        self.assertEqual(corrected.direction.name, "FLAT")
        self.assertAlmostEqual(corrected.candidate_for(Direction.LONG).confidence, 0.30, places=6)


class _TrainerStub:
    def maybe_trigger(self, symbol: str, interval: str) -> bool:
        return False

    def status(self):
        return ()


def _outcome(symbol: str = "BTCUSDT", pnl: str = "12.5") -> TradeOutcomeInput:
    return TradeOutcomeInput(
        request_id="req-1",
        bot_id="bot-1",
        symbol=symbol,
        interval="1h",
        model_id="_pooled:1h",
        model_version="v1",
        direction="LONG",
        candles=(
            {"open_time": "2026-11-09T10:00:00+00:00", "open": "1", "high": "2", "low": "0.5",
             "close": "1.5", "volume": "10"},
        ),
        take_profit_percent="2.0",
        stop_loss_percent="1.0",
        close_reason="take_profit_touched",
        realized_pnl=pnl,
        bars_held=4,
        decision_candle_open_time="2026-11-09T10:00:00+00:00",
        closed_at="2026-11-09T14:00:00+00:00",
    )


class ServiceWiringTests(unittest.TestCase):
    """The fast loop has to fire from the RPC path, not only from a direct store call."""

    def _service(self, directory: str, probe):
        samples = TradeSampleStore(Path(directory) / "samples.jsonl")
        calibration = CalibrationStore(Path(directory) / "calibration.json")
        service = OnlineLearningService(
            samples,
            _TrainerStub(),
            enabled=True,
            calibration=calibration,
            probability_probe=probe,
        )
        return service, calibration

    def test_a_closed_trade_records_its_prediction(self) -> None:
        with TemporaryDirectory() as directory:
            seen = {}

            def probe(symbol, interval, candles, direction, take_profit, stop_loss):
                seen.update(symbol=symbol, interval=interval, direction=direction,
                            take_profit=take_profit, stop_loss=stop_loss, candles=len(candles))
                return 0.72

            service, calibration = self._service(directory, probe)
            result = service.record_trade_outcome(_outcome())

            self.assertEqual(result.status, "stored")
            self.assertEqual(seen["symbol"], "BTCUSDT")
            self.assertEqual(seen["direction"], "LONG")
            self.assertEqual(seen["candles"], 1)
            self.assertEqual(calibration.status()[0]["samples"], 1)

    def test_a_losing_trade_is_recorded_as_a_loss(self) -> None:
        with TemporaryDirectory() as directory:
            service, calibration = self._service(directory, lambda *args: 0.66)
            service.record_trade_outcome(_outcome(pnl="-8.0"))
            points = calibration._points[("BTCUSDT", "1h")]
            self.assertFalse(points[0].won)
            self.assertAlmostEqual(points[0].predicted, 0.66, places=6)

    def test_an_unanswerable_probe_leaves_calibration_untouched(self) -> None:
        with TemporaryDirectory() as directory:
            service, calibration = self._service(directory, lambda *args: None)
            result = service.record_trade_outcome(_outcome())
            self.assertEqual(result.status, "stored")
            self.assertEqual(calibration.status(), [])


if __name__ == "__main__":
    unittest.main()
