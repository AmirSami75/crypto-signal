"""The gRPC-facing online-learning service: record an outcome, report training status.

`RecordTradeOutcome` validates and stores one resolved trade, then asks the trainer whether the
threshold for a background retrain has been crossed. `GetTrainingStatus` reads the trainer's
bookkeeping. Both are deliberately small: validation lives here because it decides whether a sample
is *admissible*, and everything that needs the model code lives in `online_learning`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from pathlib import Path

from crypto_signal_engine.application.online_learning import (
    BET_DIRECTIONS,
    KNOWN_CLOSE_REASONS,
    OnlineTrainer,
    StoredSample,
    TradeSampleStore,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TradeOutcomeInput:
    """A parsed RecordTradeOutcome request."""

    request_id: str
    bot_id: str
    symbol: str
    interval: str
    model_id: str
    model_version: str
    direction: str
    candles: tuple[dict[str, str], ...]
    take_profit_percent: str
    stop_loss_percent: str
    close_reason: str
    realized_pnl: str
    bars_held: int
    decision_candle_open_time: str
    closed_at: str


@dataclass(frozen=True, slots=True)
class TradeOutcomeResult:
    request_id: str
    status: str
    samples_stored: int
    training_triggered: bool


@dataclass(frozen=True, slots=True)
class MarketStatus:
    symbol: str
    interval: str
    samples_stored: int
    samples_since_training: int
    last_trained_at: str
    last_challenger_version: str
    last_verdict: str
    last_verdict_reason: str
    training_in_progress: bool


@dataclass(frozen=True, slots=True)
class TrainingStatusResult:
    request_id: str
    online_learning_enabled: bool
    markets: tuple[MarketStatus, ...]


class OnlineLearningService:
    """Admits or rejects outcome samples and reports training state."""

    def __init__(
        self,
        store: TradeSampleStore,
        trainer: OnlineTrainer,
        enabled: bool,
    ) -> None:
        self._store = store
        self._trainer = trainer
        self._enabled = enabled

    def record_trade_outcome(self, request: TradeOutcomeInput) -> TradeOutcomeResult:
        """Validate and store one resolved trade; maybe trigger a background retrain."""
        if not self._enabled:
            return TradeOutcomeResult(
                request_id=request.request_id,
                status="rejected: online learning is disabled (ML_ONLINE_LEARNING=false)",
                samples_stored=self._store.count(),
                training_triggered=False,
            )

        # -- admission checks -------------------------------------------------
        if request.direction not in BET_DIRECTIONS:
            return _rejected(request, "direction must be LONG or SHORT; a flat bot has no outcome")
        if request.close_reason not in KNOWN_CLOSE_REASONS:
            return _rejected(
                request,
                f"close_reason {request.close_reason!r} is not one of {sorted(KNOWN_CLOSE_REASONS)}",
            )
        if not request.bot_id.strip():
            return _rejected(request, "bot_id is required")
        symbol = request.symbol.strip().upper()
        if not symbol:
            return _rejected(request, "symbol is required")
        if not request.candles:
            return _rejected(request, "the decision candle window is required for training reuse")
        if not request.decision_candle_open_time.strip():
            return _rejected(request, "decision_candle_open_time is required (idempotency key)")

        try:
            take_profit = float(request.take_profit_percent)
            stop_loss = float(request.stop_loss_percent)
            realized = float(request.realized_pnl)
        except ValueError:
            return _rejected(request, "percent and pnl values must parse as numbers")
        if not (take_profit > 0 and stop_loss > 0):
            return _rejected(request, "take_profit_percent and stop_loss_percent must be positive")

        sample = StoredSample(
            bot_id=request.bot_id.strip(),
            symbol=symbol,
            interval=request.interval.strip(),
            direction=request.direction,
            close_reason=request.close_reason,
            realized_pnl=realized,
            bars_held=request.bars_held,
            take_profit_percent=take_profit,
            stop_loss_percent=stop_loss,
            decision_candle_open_time=request.decision_candle_open_time,
            closed_at=request.closed_at or _now_iso(),
            model_id=request.model_id,
            model_version=request.model_version,
            candles=request.candles,
        )

        status, stored = self._store.add(sample)
        triggered = False
        if status == "stored":
            try:
                triggered = self._trainer.maybe_trigger(symbol, sample.interval)
            except Exception:  # noqa: BLE001 — triggering must not fail the RPC
                logger.exception("Online training trigger check failed")

        return TradeOutcomeResult(
            request_id=request.request_id,
            status=status,
            samples_stored=stored,
            training_triggered=triggered,
        )

    def training_status(
        self,
        request_id: str,
        symbols: tuple[str, ...] = (),
        intervals: tuple[str, ...] = (),
    ) -> TrainingStatusResult:
        statuses = self._trainer.status(list(symbols) or None, list(intervals) or None)
        markets = []
        for state in statuses:
            markets.append(
                MarketStatus(
                    symbol=state.market[0],
                    interval=state.market[1],
                    samples_stored=self._store.count(*state.market),
                    samples_since_training=state.samples_since_training,
                    last_trained_at=state.last_trained_at,
                    last_challenger_version=state.last_challenger_version,
                    last_verdict=state.last_verdict,
                    last_verdict_reason=state.last_verdict_reason,
                    training_in_progress=state.training_in_progress,
                )
            )
        return TrainingStatusResult(
            request_id=request_id,
            online_learning_enabled=self._enabled,
            markets=tuple(markets),
        )


def _rejected(request: TradeOutcomeInput, reason: str) -> TradeOutcomeResult:
    logger.warning("Trade outcome rejected | request_id=%s | %s", request.request_id, reason)
    return TradeOutcomeResult(
        request_id=request.request_id,
        status=f"rejected: {reason}",
        samples_stored=0,
        training_triggered=False,
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
