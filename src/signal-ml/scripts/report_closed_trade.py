"""Re-send one real closed trade to the engine's online learner.

The trade happened on this machine (ZKUSDT, entry 0.00925, stop at 0.009197, filled out at
0.0091971 with slippage) but the report never left the API: the close was settled by the
reconciliation path, which did not call the reporter. This script sends the *actual* outcome — no
invented numbers — so the calibration store can start from a true sample instead of waiting for the
next trade to close.

Usage:  .venv/bin/python scripts/report_closed_trade.py
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone

import grpc

from crypto_signal_engine.contracts.v1 import ml_engine_pb2 as pb
from crypto_signal_engine.contracts.v1 import ml_engine_pb2_grpc as pb_grpc

PROXY = "http://127.0.0.1:10808"
TARGET = "127.0.0.1:50051"

# The closed position, read from BotPositions.
POSITION = {
    "bot_id": "01a076b4-d3cb-77d1-9cbb-68a67b707fea",
    "symbol": "ZKUSDT",
    "interval": "5m",
    "direction": "LONG",
    "entry": 0.00925,
    "exit": 0.0091971429,
    "quantity": 2164.0,
    "realized_pnl": -0.18963132,
    "opened_at": "2026-11-09T15:16:34+00:00",
    "closed_at": "2026-11-10T07:09:10+00:00",
    "close_reason": "stop_loss_touched",
}


def candles(symbol: str, interval: str, limit: int = 300) -> list[dict]:
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
    )
    url = (
        f"https://fapi.binance.com/fapi/v1/klines"
        f"?symbol={symbol}&interval={interval}&limit={limit}"
    )
    with opener.open(url, timeout=30) as response:
        rows = json.load(response)

    # Drop the forming candle: the engine prices closed candles only, and a window that ends on the
    # in-progress bar is rejected before it can answer.
    if rows:
        rows = rows[:-1]

    out = []
    for row in rows:
        out.append(
            {
                "open_time": datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc),
                "open": str(row[1]),
                "high": str(row[2]),
                "low": str(row[3]),
                "close": str(row[4]),
                "volume": str(row[5]),
            }
        )
    return out


def main() -> None:
    window = candles(POSITION["symbol"], POSITION["interval"])
    take_profit = abs(0.0093042857 - POSITION["entry"]) / POSITION["entry"] * 100
    stop_loss = abs(0.0091971429 - POSITION["entry"]) / POSITION["entry"] * 100

    request = pb.RecordTradeOutcomeRequest(
        request_id="reconcile-zkusdt-20261110b",
        bot_id=POSITION["bot_id"],
        symbol=POSITION["symbol"],
        interval=POSITION["interval"],
        model_id="scanner-exit",
        model_version=POSITION["close_reason"],
        direction=pb.TRADE_DIRECTION_LONG,
        candles=[pb.Candle(**candle) for candle in window],
        take_profit_percent=f"{take_profit:.6f}",
        stop_loss_percent=f"{stop_loss:.6f}",
        close_reason=POSITION["close_reason"],
        realized_pnl=f"{POSITION['realized_pnl']:.8f}",
        bars_held=190,
        decision_candle_open_time=datetime.fromisoformat(POSITION["opened_at"]),
        closed_at=datetime.fromisoformat(POSITION["closed_at"]),
    )

    with grpc.insecure_channel(TARGET) as channel:
        stub = pb_grpc.MlEngineServiceStub(channel)
        ack = stub.RecordTradeOutcome(request, timeout=120)

    print("ack:", ack.status, "| samples stored:", ack.samples_stored,
          "| training triggered:", ack.training_triggered)


if __name__ == "__main__":
    main()
