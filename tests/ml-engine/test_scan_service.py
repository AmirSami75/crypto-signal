"""Tests for the engine-side market scan service and its gRPC wiring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from crypto_signal_engine.application.models import CandleInput
from crypto_signal_engine.application.scan_service import ScanRequest, ScanService


def _candles(close: list[float], start: datetime | None = None) -> tuple[CandleInput, ...]:
    start = start or datetime(2026, 1, 1, tzinfo=UTC)
    out = []
    price = 100.0
    for i, target in enumerate(close):
        # walk the open toward the target close so the series is continuous
        open_ = price
        price = target
        high = max(open_, price) * 1.001
        low = min(open_, price) * 0.999
        out.append(CandleInput(
            open_time=start + timedelta(minutes=5 * i),
            open=str(open_),
            high=str(high),
            low=str(low),
            close=str(price),
            volume="1000",
        ))
    return tuple(out)


def _flat(n: int = 60) -> tuple[CandleInput, ...]:
    return _candles([100.0] * n)


class TestScanService:
    def test_unknown_strategy_is_reported_not_fatal(self):
        svc = ScanService()
        result = svc.scan(ScanRequest(
            request_id="r1",
            interval="5m",
            symbols=(("BTCUSDT", _flat()),),
            strategies=(("no_such_strategy", 1.5, 1.0),),
        ))

        assert result.results == ()
        assert "no_such_strategy" in result.warning

    def test_short_window_is_skipped_with_warning(self):
        svc = ScanService()
        result = svc.scan(ScanRequest(
            request_id="r1",
            interval="5m",
            symbols=(("BTCUSDT", _flat(20)),),
            strategies=(("rsi", 1.5, 1.0),),
        ))

        assert result.results == ()
        assert "need >= 30" in result.warning

    def test_flat_series_produces_no_signal(self):
        svc = ScanService()
        result = svc.scan(ScanRequest(
            request_id="r1",
            interval="5m",
            symbols=(("BTCUSDT", _flat()),),
            strategies=tuple((name, 1.5, 1.0) for name in (
                "rsi", "bollinger", "macd", "ema_cross", "supertrend",
                "donchian", "rsi_pullback", "keltner_breakout", "triple_ema")),
        ))

        # A dead-flat market must not trip trend or momentum entries.
        assert result.results == ()
        assert result.warning == ""

    @pytest.mark.parametrize("strategy", ["rsi", "bollinger", "macd", "ema_cross",
                                          "supertrend", "donchian", "rsi_pullback",
                                          "keltner_breakout", "triple_ema"])
    def test_each_registered_strategy_runs_without_error(self, strategy):
        # A realistic up-down walk: every strategy must either fire or stay silent,
        # never raise.
        closes = []
        price = 100.0
        for i in range(120):
            step = 1.5 if (i // 10) % 2 == 0 else -1.2
            price = max(5.0, price + step)
            closes.append(price)

        svc = ScanService()
        result = svc.scan(ScanRequest(
            request_id="r1",
            interval="5m",
            symbols=(("TESTUSDT", _candles(closes)),),
            strategies=((strategy, 1.5, 1.0),),
        ))

        for r in result.results:
            assert r.symbol == "TESTUSDT"
            assert r.strategy == strategy
            assert r.direction in ("LONG", "SHORT")
            assert r.confidence == 1.0
            assert r.reason

    def test_results_carry_symbol_and_strategy(self):
        closes = [100 + (i % 7) * (1 if (i // 5) % 2 == 0 else -1) for i in range(80)]
        svc = ScanService()
        result = svc.scan(ScanRequest(
            request_id="r9",
            interval="5m",
            symbols=(("AAAUSDT", _candles(closes)), ("BBBUSDT", _candles(closes))),
            strategies=(("rsi", 1.5, 1.0), ("ema_cross", 1.5, 1.0)),
        ))

        for r in result.results:
            assert r.symbol in ("AAAUSDT", "BBBUSDT")
            assert r.strategy in ("rsi", "ema_cross")
