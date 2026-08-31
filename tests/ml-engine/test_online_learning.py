"""Tests for the online-learning sample store and promotion gate."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from crypto_signal_engine.application.online_learning import (
    StoredSample,
    TradeSampleStore,
    promotion_gate,
)


def _sample(bot_id: str = "bot-1", candle: str = "2026-08-31T10:00:00+00:00", **overrides) -> StoredSample:
    base = dict(
        bot_id=bot_id,
        symbol="BTCUSDT",
        interval="1h",
        direction="LONG",
        close_reason="take_profit_touched",
        realized_pnl=12.5,
        bars_held=4,
        take_profit_percent=2.0,
        stop_loss_percent=1.0,
        decision_candle_open_time=candle,
        closed_at="2026-08-31T14:00:00+00:00",
        model_id="_pooled:1h",
        model_version="abc123",
        candles=(_candle("2026-08-31T05:00:00+00:00"), _candle("2026-08-31T06:00:00+00:00")),
    )
    base.update(overrides)
    return StoredSample(**base)


def _candle(open_time: str) -> dict:
    return {
        "open_time": open_time,
        "open": "100", "high": "101", "low": "99", "close": "100.5", "volume": "10",
    }


class PromotionGateTests(unittest.TestCase):
    def test_promotes_only_when_no_metric_worse_and_one_better(self) -> None:
        ok, reason = promotion_gate({"log_loss": 1.05}, {"log_loss": 1.01})
        self.assertTrue(ok)
        self.assertIn("better", reason)

    def test_blocks_a_regression(self) -> None:
        ok, reason = promotion_gate({"log_loss": 1.05}, {"log_loss": 1.10})
        self.assertFalse(ok)
        self.assertIn("WORSE", reason)

    def test_blocks_when_identical(self) -> None:
        ok, reason = promotion_gate({"log_loss": 1.05}, {"log_loss": 1.05})
        self.assertFalse(ok)
        self.assertIn("no metric improved", reason)

    def test_blocks_when_no_shared_metrics(self) -> None:
        ok, reason = promotion_gate({"log_loss": 1.05}, {"edge": 0.1})
        self.assertFalse(ok)
        self.assertIn("no comparable metrics", reason)


class TradeSampleStoreTests(unittest.TestCase):
    def test_stores_and_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = TradeSampleStore(Path(tmp) / "samples.jsonl")
            status, count = store.add(_sample())
            self.assertEqual(status, "stored")
            self.assertEqual(count, 1)
            loaded = store.samples("BTCUSDT", "1h")
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].close_reason, "take_profit_touched")
            self.assertEqual(loaded[0].candles[0]["open"], "100")

    def test_duplicate_key_is_acknowledged_not_stored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = TradeSampleStore(Path(tmp) / "samples.jsonl")
            store.add(_sample())
            status, count = store.add(_sample())
            self.assertEqual(status, "duplicate")
            self.assertEqual(count, 1)
            self.assertEqual(store.count("BTCUSDT", "1h"), 1)

    def test_reload_from_disk_restores_dedup_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "samples.jsonl"
            store = TradeSampleStore(path)
            store.add(_sample())
            store.add(_sample(candle="2026-08-31T11:00:00+00:00"))

            reopened = TradeSampleStore(path)
            self.assertEqual(reopened.count("BTCUSDT", "1h"), 2)
            status, _ = reopened.add(_sample())  # first candle time again
            self.assertEqual(status, "duplicate")

    def test_filter_by_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = TradeSampleStore(Path(tmp) / "samples.jsonl")
            store.add(_sample())
            store.add(_sample(symbol="ETHUSDT", candle="2026-08-31T12:00:00+00:00"))
            self.assertEqual(len(store.samples("BTCUSDT", "1h")), 1)
            self.assertEqual(len(store.samples("ETHUSDT", "1h")), 1)
            self.assertEqual(store.count("BTCUSDT", "1h"), 1)

    def test_mark_trained_resets_counter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = TradeSampleStore(Path(tmp) / "samples.jsonl")
            store.add(_sample())
            store.add(_sample(candle="2026-08-31T11:00:00+00:00"))
            self.assertEqual(store.since_training("BTCUSDT", "1h"), 2)
            store.mark_trained("BTCUSDT", "1h")
            self.assertEqual(store.since_training("BTCUSDT", "1h"), 0)


if __name__ == "__main__":
    unittest.main()
