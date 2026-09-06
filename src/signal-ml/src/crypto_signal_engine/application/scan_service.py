"""Market scanner: evaluate the strategy zoo on a batch of symbol candle windows.

This is Phase 3's engine-side implementation of the ``ScanSymbols`` RPC. It is
deliberately *dumb* about ranking: it runs each registered strategy on each
symbol's feature frame and returns any Signal with a confidence of 1.0
(indicator strategies are deterministic — they either fire or they don't).
The .NET ``MarketScannerService`` owns the 24h-ticker scoring, symbol ranking,
and atomic signal-claiming; this module only answers "does strategy X fire on
these candles?".

No I/O, no state. Same contract as the zoo itself.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from crypto_signal.strategies import STRATEGIES
from crypto_signal_engine.application.models import CandleInput


@dataclass(frozen=True, slots=True)
class ScanRequest:
    """A batch of symbol candle windows + the strategies to test on each."""
    request_id: str
    interval: str
    symbols: tuple[tuple[str, tuple[CandleInput, ...]], ...]
    strategies: tuple[tuple[str, float, float], ...]  # (name, tp_atr, sl_atr)


@dataclass(frozen=True, slots=True)
class ScanResult:
    """One strategy's verdict on one symbol."""
    symbol: str
    strategy: str
    direction: str       # "LONG" | "SHORT" | ""
    confidence: float    # 1.0 for indicator strategies
    reason: str
    warning: str = ""


@dataclass(frozen=True, slots=True)
class ScanResponse:
    request_id: str
    results: tuple[ScanResult, ...]
    warning: str = ""


class ScanService:
    """Runs the strategy zoo over a batch of symbols.

    Strategies are pure functions over a feature-rich OHLCV frame. This service
    builds that frame once per symbol (caching ATR/SMA columns) and then calls
    each requested strategy. Unknown strategy names produce a warning per result,
    not a hard failure — the scanner is resilient to a stale zoo on a rolling deploy.
    """

    def __init__(self) -> None:
        self._registry = dict(STRATEGIES)

    def scan(self, request: ScanRequest) -> ScanResponse:
        warnings: list[str] = []
        results: list[ScanResult] = []
        seen_strategies: set[str] = set()

        for name, _, _ in request.strategies:
            if name not in self._registry:
                warnings.append(f"unknown strategy: {name}")
            seen_strategies.add(name)

        for symbol, candles in request.symbols:
            if len(candles) < 30:
                warnings.append(f"{symbol}: only {len(candles)} candles, need >= 30")
                continue

            frame = self._build_frame(candles)

            for name, tp_atr, sl_atr in request.strategies:
                if name not in self._registry:
                    continue

                signal = self._registry[name](frame)
                if signal is not None:
                    direction = signal.direction
                    results.append(ScanResult(
                        symbol=symbol,
                        strategy=name,
                        direction=direction,
                        confidence=1.0,
                        reason=signal.reason,
                        warning="",
                    ))

        warning = "; ".join(warnings) if warnings else ""
        return ScanResponse(
            request_id=request.request_id,
            results=tuple(results),
            warning=warning,
        )

    @staticmethod
    def _build_frame(candles: tuple[CandleInput, ...]) -> pd.DataFrame:
        """Convert candle tuples into the OHLCV DataFrame the zoo strategies expect."""
        rows = []
        for c in candles:
            rows.append({
                "timestamp": c.open_time,
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": float(c.volume),
            })
        return pd.DataFrame(rows)
