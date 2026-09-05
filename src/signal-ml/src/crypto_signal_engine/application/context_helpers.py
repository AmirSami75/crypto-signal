"""Helpers for attaching higher-timeframe context in the evaluator.

These convert between the engine's internal ``CandleInput`` list and the
``pd.DataFrame`` shape that ``crypto_signal.features.mtf`` expects.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd

from ..application.models import CandleInput


_INTERVAL_SECONDS: dict[str, int] = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800,
    "12h": 43200, "1d": 86400, "3d": 259200, "1w": 604800, "1M": 2592000,
}


def _candles_to_dataframe(
    candles: tuple[CandleInput, ...], interval: str,
) -> pd.DataFrame:
    """Build a DataFrame with ``timestamp`` and ``close_time`` columns plus OHLCV.

    ``attach_higher_tf_features`` joins on ``close_time = timestamp + interval``,
    so both columns must be present and in UTC.
    """
    if not candles:
        return pd.DataFrame(
            columns=["timestamp", "close_time", "open", "high", "low", "close", "volume"]
        )

    interval_seconds = _INTERVAL_SECONDS.get(interval, 0)
    if interval_seconds == 0:
        # Fall back: parse the interval string (e.g. "4h", "15m", "1d").
        raise ValueError(f"unknown interval: {interval}")

    rows = []
    for candle in candles:
        ts = candle.open_time
        close_time = ts + pd.Timedelta(seconds=interval_seconds)
        rows.append({
            "timestamp": ts,
            "close_time": close_time,
            "open": float(candle.open),
            "high": float(candle.high),
            "low": float(candle.low),
            "close": float(candle.close),
            "volume": float(candle.volume),
        })
    return pd.DataFrame(rows)


def _candle_close_time(candle: CandleInput) -> pd.Timestamp:
    """Return the close time (open_time + interval) as a timezone-aware Timestamp.

    The interval is not stored on CandleInput, so this helper accepts it
    separately where needed.  For the evaluator's context attachment we only
    need the open_time of each lower candle, which ``attach_higher_tf_features``
    already uses as its join key.
    """
    ts = candle.open_time
    return pd.Timestamp(ts) if not isinstance(ts, pd.Timestamp) else ts
