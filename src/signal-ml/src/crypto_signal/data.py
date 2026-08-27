from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import time
from typing import Any
from urllib.parse import urlencode
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError
from urllib.request import Request


TRANSIENT_HTTP_STATUS = {408, 425, 429, 500, 502, 503, 504}
MAX_REQUEST_ATTEMPTS = 5


def _is_transient(error: Exception) -> bool:
    if isinstance(error, HTTPError):
        return error.code in TRANSIENT_HTTP_STATUS
    if isinstance(error, (URLError, TimeoutError)):
        return True
    return error.__class__.__name__ in {"RemoteDisconnected", "ConnectionResetError"}

import numpy as np
import pandas as pd

from .config import DEFAULT_PROXY_URL
from .log_setup import get_logger


BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
logger = get_logger(__name__)
INTERVAL_SECONDS: dict[str, int] = {
    "1m": 60,
    "3m": 3 * 60,
    "5m": 5 * 60,
    "15m": 15 * 60,
    "30m": 30 * 60,
    "1h": 60 * 60,
    "2h": 2 * 60 * 60,
    "4h": 4 * 60 * 60,
    "6h": 6 * 60 * 60,
    "8h": 8 * 60 * 60,
    "12h": 12 * 60 * 60,
    "1d": 24 * 60 * 60,
    "3d": 3 * 24 * 60 * 60,
    "1w": 7 * 24 * 60 * 60,
}

COLUMNS = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore",
]

NUMERIC_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
]


def interval_milliseconds(interval: str) -> int:
    try:
        return INTERVAL_SECONDS[interval] * 1000
    except KeyError as exc:
        supported = ", ".join(INTERVAL_SECONDS)
        raise ValueError(f"Unsupported interval {interval!r}. Use one of: {supported}") from exc


def interval_periods_per_year(interval: str) -> float:
    return (365.0 * 24 * 60 * 60) / INTERVAL_SECONDS[interval]


def iso_to_milliseconds(value: str | None) -> int | None:
    if value is None:
        return None
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _get_json(
    url: str,
    params: dict[str, Any],
    timeout: int = 30,
    proxy_url: str | None = DEFAULT_PROXY_URL,
) -> Any:
    """GET JSON through the configured V2RayN HTTP proxy."""
    full_url = f"{url}?{urlencode(params)}"
    request = Request(
        full_url,
        headers={"User-Agent": "crypto-ml-signal/0.2"},
    )
    if proxy_url:
        proxy_handler = urllib_request.ProxyHandler(
            {"http": proxy_url, "https": proxy_url}
        )
        logger.debug("HTTP GET via proxy=%s | endpoint=%s | params=%s", proxy_url, url, params)
    else:
        proxy_handler = urllib_request.ProxyHandler({})
        logger.debug("HTTP GET without proxy | endpoint=%s | params=%s", url, params)
    opener = urllib_request.build_opener(proxy_handler)
    started = time.perf_counter()
    try:
        with opener.open(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        logger.debug(
            "HTTP response received | endpoint=%s | elapsed=%.3fs",
            url,
            time.perf_counter() - started,
        )
        return payload
    except Exception:
        logger.exception(
            "HTTP request failed | endpoint=%s | proxy=%s | timeout=%ss",
            url,
            proxy_url or "disabled",
            timeout,
        )
        raise


def _rows_to_frame(rows: list[list[Any]], interval: str) -> pd.DataFrame:
    if not rows:
        raise ValueError("No candles returned by Binance")
    frame = pd.DataFrame(rows, columns=COLUMNS)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    frame["close_time"] = pd.to_datetime(frame["close_time"], unit="ms", utc=True)
    for column in NUMERIC_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.drop(columns=["ignore"])
    frame = frame.drop_duplicates(subset="timestamp", keep="last")
    frame = frame.sort_values("timestamp").reset_index(drop=True)

    now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    bar_ms = interval_milliseconds(interval)
    open_ms = frame["timestamp"].astype("int64") // 1_000_000
    frame = frame.loc[(open_ms + bar_ms) <= now_ms].reset_index(drop=True)
    quality = validate_ohlcv(frame, interval)
    logger.info(
        "Converted API candles | rows=%s | gaps=%s | interval=%s",
        f"{quality['rows']:,}",
        f"{quality['gap_count']:,}",
        interval,
    )
    return frame


def fetch_historical_ohlcv(
    symbol: str,
    interval: str,
    start: str,
    end: str | None = None,
    pause_seconds: float = 0.08,
    proxy_url: str | None = DEFAULT_PROXY_URL,
    timeout: int = 30,
) -> pd.DataFrame:
    """Download all closed Binance spot candles in an inclusive time range."""
    bar_ms = interval_milliseconds(interval)
    cursor = iso_to_milliseconds(start)
    if cursor is None:
        raise ValueError("A start timestamp is required")
    end_ms = iso_to_milliseconds(end)
    now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    effective_end = min(end_ms or now_ms, now_ms)
    rows: list[list[Any]] = []
    page = 0
    started = time.perf_counter()
    logger.info(
        "Historical download started | symbol=%s | interval=%s | start=%s | end=%s | proxy=%s",
        symbol.upper(),
        interval,
        start,
        end or "now",
        proxy_url or "disabled",
    )

    while cursor < effective_end:
        page += 1
        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "startTime": cursor,
            "endTime": effective_end,
            "limit": 1000,
        }
        batch = None
        for attempt in range(1, MAX_REQUEST_ATTEMPTS + 1):
            try:
                batch = _get_json(
                    BINANCE_KLINES_URL,
                    params,
                    timeout=timeout,
                    proxy_url=proxy_url,
                )
                break
            except Exception as error:
                if attempt == MAX_REQUEST_ATTEMPTS or not _is_transient(error):
                    raise
                delay = min(8.0, 0.5 * (2 ** (attempt - 1)))
                logger.warning(
                    "Transient historical-download failure; retrying | symbol=%s | page=%s | attempt=%s/%s | delay=%.1fs | error=%s",
                    symbol.upper(), page, attempt, MAX_REQUEST_ATTEMPTS, delay, error.__class__.__name__,
                )
                time.sleep(delay)

        if batch is None:
            raise RuntimeError("Historical download produced no response")

        if isinstance(batch, dict):
            raise RuntimeError(f"Binance API error: {batch}")
        if not batch:
            break
        rows.extend(batch)
        last_time = pd.to_datetime(int(batch[-1][0]), unit="ms", utc=True)
        logger.info(
            "Download page %s complete | received=%s | total=%s | last_candle=%s",
            page,
            f"{len(batch):,}",
            f"{len(rows):,}",
            last_time.isoformat(),
        )
        next_cursor = int(batch[-1][0]) + bar_ms
        if next_cursor <= cursor:
            raise RuntimeError("Pagination stopped advancing")
        cursor = next_cursor
        if len(batch) < 1000:
            break
        time.sleep(pause_seconds)

    frame = _rows_to_frame(rows, interval)
    logger.info(
        "Historical download finished | closed_rows=%s | pages=%s | elapsed=%.1fs",
        f"{len(frame):,}",
        page,
        time.perf_counter() - started,
    )
    return frame


def fetch_recent_ohlcv(
    symbol: str,
    interval: str,
    limit: int = 1000,
    proxy_url: str | None = DEFAULT_PROXY_URL,
    timeout: int = 30,
) -> pd.DataFrame:
    if not 1 <= limit <= 1000:
        raise ValueError("Binance recent candle limit must be between 1 and 1000")
    logger.info(
        "Recent candle request started | symbol=%s | interval=%s | limit=%s | proxy=%s",
        symbol.upper(),
        interval,
        f"{limit:,}",
        proxy_url or "disabled",
    )
    rows = _get_json(
        BINANCE_KLINES_URL,
        {"symbol": symbol.upper(), "interval": interval, "limit": limit},
        timeout=timeout,
        proxy_url=proxy_url,
    )
    if isinstance(rows, dict):
        raise RuntimeError(f"Binance API error: {rows}")
    frame = _rows_to_frame(rows, interval)
    logger.info("Recent candle request finished | closed_rows=%s", f"{len(frame):,}")
    return frame


def save_ohlcv(frame: pd.DataFrame, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(destination, index=False)
    logger.info("OHLCV CSV saved | rows=%s | path=%s", f"{len(frame):,}", destination)
    return destination


def load_ohlcv(path: str | Path, interval: str) -> pd.DataFrame:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Market data not found: {source}")
    # Binance CSVs can legitimately mix timestamps with and without fractional
    # seconds, for example `01:59:59+00:00` and `02:59:59.999000+00:00`.
    # pandas otherwise infers one strict format from the first values and fails
    # later when the representation changes.
    logger.info("Loading OHLCV CSV | path=%s", source)
    frame = pd.read_csv(source)
    for column in ("timestamp", "close_time"):
        if column not in frame:
            raise ValueError(f"Missing OHLCV timestamp column: {column}")
        original = frame[column].copy()
        frame[column] = pd.to_datetime(
            original,
            format="mixed",
            utc=True,
            errors="coerce",
        )
        invalid = frame[column].isna()
        if invalid.any():
            examples = original.loc[invalid].astype(str).head(3).tolist()
            raise ValueError(
                f"Could not parse {column} as ISO-8601 timestamps. "
                f"Invalid examples: {examples}"
            )
    for column in NUMERIC_COLUMNS:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.drop_duplicates(subset="timestamp", keep="last")
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    quality = validate_ohlcv(frame, interval)
    logger.info(
        "OHLCV CSV loaded | rows=%s | gaps=%s | first=%s | last=%s",
        f"{quality['rows']:,}",
        f"{quality['gap_count']:,}",
        frame["timestamp"].iloc[0].isoformat(),
        frame["timestamp"].iloc[-1].isoformat(),
    )
    return frame


def validate_ohlcv(frame: pd.DataFrame, interval: str) -> dict[str, int]:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing OHLCV columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError("OHLCV data is empty")
    if frame["timestamp"].duplicated().any():
        raise ValueError("OHLCV data contains duplicate timestamps")
    if not frame["timestamp"].is_monotonic_increasing:
        raise ValueError("OHLCV timestamps must be sorted")
    if (frame[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("OHLC prices must be positive")
    if (frame["volume"] < 0).any():
        raise ValueError("Volume cannot be negative")
    invalid_high = frame["high"] < frame[["open", "close", "low"]].max(axis=1)
    invalid_low = frame["low"] > frame[["open", "close", "high"]].min(axis=1)
    if invalid_high.any() or invalid_low.any():
        raise ValueError("OHLC price relationships are invalid")

    expected = timedelta(milliseconds=interval_milliseconds(interval))
    deltas = frame["timestamp"].diff().dropna()
    result = {"rows": len(frame), "gap_count": int((deltas != expected).sum())}
    if result["gap_count"]:
        logger.warning("OHLCV validation found %s timestamp gaps", result["gap_count"])
    else:
        logger.debug("OHLCV validation passed with no timestamp gaps")
    return result
