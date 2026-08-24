"""Turning a request's candles into something a model may be shown, or refusing to.

Both RPCs take the same window and must judge it the same way, so the checks live here once. They are
almost all about one failure mode: a feature computed from a window that is not what it claims to be.
`volatility_168` over 168 candles with a gap in them is a 168-candle number describing 200 candles of
time, and nothing downstream can tell — it arrives as a plausible float and moves the prediction.

Two distinctions this module draws that the old single-model path did not:

* **A gap inside the warm-up window is fatal; a gap before it is a warning.** The newest row's features
  read the last `minimum_candles` bars and nothing earlier, so a hole at position 10 of a 500-candle
  request cannot reach them. Refusing that request would reject good data; ignoring a hole in the last
  169 would answer from bad data. The line is drawn where the arithmetic actually is.
* **The digest is over canonical decimal strings, not float formatting.** `%.17g` of a parsed float
  makes the digest a function of the parse, so `"100.5"` and `"100.50"` hash differently while
  `"0.1"` hashes to seventeen digits of noise. Quantizing first makes it a function of the *values*,
  which is what a replay check needs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib
import re

import numpy as np
import pandas as pd

from crypto_signal.data import INTERVAL_SECONDS
from crypto_signal.domain import format_decimal
from crypto_signal.features import WARMUP_COLUMNS, FeatureFrame, build_features

from .errors import InvalidInferenceRequest
from .models import CandleInput, TradeParametersInput


#: Loose enough for any venue's ticker, tight enough that a path or a SQL fragment is not a symbol.
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._-]{1,29}$")

_MAX_REQUEST_ID = 128


def normalise_market(symbol: str, interval: str) -> tuple[str, str]:
    """Validate and canonicalise a market identity.

    Symbols are uppercased because venues quote them that way and a registry keyed on `btcusdt` would
    miss `BTCUSDT`. Intervals are **not** case-folded: Binance's `1m` is a minute and `1M` is a month,
    so folding them would silently answer a monthly question with a minute model.
    """
    canonical_symbol = symbol.strip().upper()
    canonical_interval = interval.strip()
    if not _SYMBOL_PATTERN.fullmatch(canonical_symbol):
        raise InvalidInferenceRequest(
            f"symbol has an invalid format: {symbol!r}; expected a ticker like 'BTCUSDT'"
        )
    if canonical_interval not in INTERVAL_SECONDS:
        raise InvalidInferenceRequest(
            f"Unsupported candle interval: {interval!r}; expected one of "
            f"{', '.join(sorted(INTERVAL_SECONDS))}"
        )
    return canonical_symbol, canonical_interval


def validate_request_id(request_id: str) -> str:
    if not request_id or not request_id.strip():
        raise InvalidInferenceRequest("request_id is required")
    if len(request_id) > _MAX_REQUEST_ID:
        raise InvalidInferenceRequest(
            f"request_id is limited to {_MAX_REQUEST_ID} characters, got {len(request_id)}"
        )
    return request_id


@dataclass(frozen=True, slots=True)
class CandleWindow:
    """A validated window, its features, and the two clocks a signal is judged against.

    `entry_price` is the newest close as a `Decimal` — the number that came off the wire, not a
    round-trip through float64 — because it anchors every level the response quotes.
    """

    symbol: str
    interval: str
    candles: tuple[CandleInput, ...]
    features: FeatureFrame
    latest_index: int
    entry_price: Decimal
    atr: float
    candle_open_time: datetime
    valid_until: datetime
    input_digest_sha256: str
    warnings: tuple[str, ...] = ()

    def latest_features(self, columns: tuple[str, ...]) -> pd.DataFrame:
        """The single newest feature row, in the column order the model was trained on."""
        return self.features.frame.loc[[self.latest_index], list(columns)]

    def path_from(self, entry_index: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """`(high, low, open)` as float arrays, for feeding `domain.barriers.first_touch`.

        The validated candles are kept on the window rather than discarded after feature building
        because the bot advisor has to ask a question features cannot answer: did the *price path*
        cross a bracket while the position was open. That needs highs and lows bar by bar, and it has
        to read them from the same rows the digest was computed over — deriving them from a second
        source is how a decision stops being replayable.

        Floats here, deliberately: `first_touch` is comparison arithmetic over a path, not money that
        gets stored. The prices that leave the engine stay `Decimal` and never come through this.
        """
        held = self.candles[entry_index:]
        return (
            np.fromiter((float(candle.high) for candle in held), dtype=np.float64, count=len(held)),
            np.fromiter((float(candle.low) for candle in held), dtype=np.float64, count=len(held)),
            np.fromiter((float(candle.open) for candle in held), dtype=np.float64, count=len(held)),
        )


def _validate_candles(candles: tuple[CandleInput, ...]) -> list[dict[str, object]]:
    """Per-candle sanity, and the rows the feature builder consumes.

    Every check here has the same shape: reject an input whose arithmetic would succeed and whose
    meaning would be wrong. A negative price divides into a nonsense ratio; a high below the close is
    not a candle any venue produced; a repeated timestamp means the caller concatenated two pages of
    klines and the second page's features would be computed over duplicated bars.
    """
    rows: list[dict[str, object]] = []
    previous_time: datetime | None = None

    for index, candle in enumerate(candles):
        timestamp = candle.open_time
        if timestamp is None:
            raise InvalidInferenceRequest(f"candles[{index}].open_time is required")
        if timestamp.tzinfo is None:
            raise InvalidInferenceRequest(
                f"candles[{index}].open_time must carry a UTC offset; a naive timestamp is ambiguous"
            )
        timestamp = timestamp.astimezone(UTC)

        prices = (candle.open, candle.high, candle.low, candle.close)
        for name, value in zip(("open", "high", "low", "close", "volume"), (*prices, candle.volume)):
            if not value.is_finite():
                raise InvalidInferenceRequest(f"candles[{index}].{name} is not finite: {value}")
        if min(prices) <= 0:
            raise InvalidInferenceRequest(
                f"candles[{index}] has a non-positive price; prices must be > 0"
            )
        if candle.volume < 0:
            raise InvalidInferenceRequest(f"candles[{index}].volume cannot be negative")
        if candle.high < max(candle.open, candle.close) or candle.low > min(candle.open, candle.close):
            raise InvalidInferenceRequest(
                f"candles[{index}] violates OHLC bounds: high must be >= max(open, close) and "
                f"low <= min(open, close)"
            )
        if previous_time is not None and timestamp <= previous_time:
            raise InvalidInferenceRequest(
                f"candle open times must be strictly increasing; candles[{index}] at "
                f"{timestamp.isoformat()} does not follow {previous_time.isoformat()}"
            )
        previous_time = timestamp

        rows.append(
            {
                "timestamp": timestamp,
                "open": float(candle.open),
                "high": float(candle.high),
                "low": float(candle.low),
                "close": float(candle.close),
                "volume": float(candle.volume),
            }
        )
    return rows


def _digest(
    symbol: str,
    interval: str,
    candles: tuple[CandleInput, ...],
    parameters: TradeParametersInput,
) -> str:
    """SHA-256 over the whole question: the market, every candle, and the bet.

    The parameters are in here alongside the candles because the digest's job is to make a stored
    decision checkable, and the same window at 2%/1% is a different decision from the same window at
    4%/1%. A digest over candles alone would collide those two and certify the wrong one as replayed.
    """
    accumulator = hashlib.sha256()
    accumulator.update(f"{symbol}|{interval}|".encode())
    for candle in candles:
        accumulator.update(
            (
                f"{candle.open_time.astimezone(UTC).isoformat()}"
                f"|{format_decimal(candle.open)}"
                f"|{format_decimal(candle.high)}"
                f"|{format_decimal(candle.low)}"
                f"|{format_decimal(candle.close)}"
                f"|{format_decimal(candle.volume)};"
            ).encode()
        )
    accumulator.update(
        (
            f"|tp={format_decimal(parameters.take_profit_percent)}"
            f"|sl={format_decimal(parameters.stop_loss_percent)}"
            f"|short={int(parameters.allow_short)}"
            f"|hold={parameters.max_holding_periods}"
            f"|floor={parameters.minimum_confidence:.6f}"
        ).encode()
    )
    return accumulator.hexdigest()


def build_window(
    symbol: str,
    interval: str,
    candles: tuple[CandleInput, ...],
    parameters: TradeParametersInput,
    minimum_candles: int,
    maximum_candles: int,
    atr_window: int = 14,
) -> CandleWindow:
    """Validate a request's candles and compute the newest feature row from them."""
    canonical_symbol, canonical_interval = normalise_market(symbol, interval)

    if not minimum_candles <= len(candles) <= maximum_candles:
        raise InvalidInferenceRequest(
            f"candles must contain {minimum_candles} to {maximum_candles} completed bars, "
            f"got {len(candles)}"
        )

    rows = _validate_candles(candles)
    frame = pd.DataFrame(rows)
    step = timedelta(seconds=INTERVAL_SECONDS[canonical_interval])
    warnings: list[str] = []

    # The warm-up window is what the newest row's longest rolling window actually reads. A hole in it
    # is a feature that misdescribes its own span, so it is fatal rather than advisory.
    times = pd.Series([row["timestamp"] for row in rows])
    warmup_gaps = times.tail(minimum_candles).diff().dropna().ne(step)
    if bool(warmup_gaps.any()):
        raise InvalidInferenceRequest(
            f"The final {minimum_candles}-candle feature warm-up window contains "
            f"{int(warmup_gaps.sum())} missing or irregular step(s); the newest features would be "
            "computed over a span they do not describe"
        )
    earlier_gaps = int(times.head(len(times) - minimum_candles + 1).diff().dropna().ne(step).sum())
    if earlier_gaps:
        warnings.append(
            f"{earlier_gaps} irregular candle step(s) before the warm-up window; the newest "
            "features do not read that far back, so the answer stands"
        )

    features = build_features(frame, atr_window=atr_window)
    complete = features.frame.dropna(subset=list(WARMUP_COLUMNS)).index
    if len(complete) == 0 or int(complete.max()) != len(frame) - 1:
        raise InvalidInferenceRequest(
            "The newest candle cannot produce complete features; supply a longer history"
        )
    latest_index = int(complete.max())

    atr = float(features.atr.iloc[latest_index])
    if not atr > 0:
        raise InvalidInferenceRequest(
            f"The average true range over the newest {atr_window} candles is {atr}, so no barrier can "
            "be expressed in ATR units; the window has no price movement in it"
        )

    last_open = frame.iloc[-1]["timestamp"].to_pydatetime()
    return CandleWindow(
        symbol=canonical_symbol,
        interval=canonical_interval,
        candles=candles,
        features=features,
        latest_index=latest_index,
        entry_price=candles[-1].close,
        atr=atr,
        candle_open_time=last_open,
        # The newest candle opened at `last_open` and closed one step later, which is already past. The
        # answer stops describing the market when the *next* candle closes — two steps from the open.
        valid_until=last_open + 2 * step,
        input_digest_sha256=_digest(canonical_symbol, canonical_interval, candles, parameters),
        warnings=tuple(warnings),
    )
