"""The only place protobuf messages and application dataclasses know about each other.

Everything above this module — the evaluator, the two services, the domain — is transport-agnostic and
testable without a wire. Everything below it is generated code. Keeping the translation here means a
renamed proto field breaks in one file with an `AttributeError` at import-adjacent code, rather than
turning into a silently-defaulted zero in twenty response constructors.

Two rules the whole module exists to enforce:

**Prices cross as decimal strings.** Inbound, `parse_money` reads the digits that were sent into a
`Decimal`; outbound, `format_decimal` writes a fixed number of places with no exponent. A price never
passes through a float on this boundary. The contract requires it (see the header of `ml_engine.proto`)
because .NET stores money as `decimal` and the audit chain has to be able to prove the price the engine
computed is the price the database recorded.

**An unset message is not a zeroed message.** proto3 gives an absent submessage the same reading as one
full of zeros, so `HasField` is checked wherever the difference matters — an absent `OpenPosition` means
a flat bot, whereas a zeroed one would mean a position of zero size at a price of zero. Deciding those
are the same thing is how a flat bot gets told to close something.
"""

from __future__ import annotations

from datetime import UTC, datetime

from google.protobuf.timestamp_pb2 import Timestamp

from crypto_signal.domain import (
    direction_from_wire,
    direction_to_wire,
    format_decimal,
    parse_money,
)

from crypto_signal_engine.application.models import (
    BotAction,
    BotDecisionRequest,
    BotDecisionResult,
    CandleInput,
    Capabilities,
    LevelsResult,
    ModelDescription,
    OpenPositionInput,
    SignalRequest,
    SignalResult,
    TradeParametersInput,
)
from crypto_signal_engine.contracts.v1 import ml_engine_pb2 as pb


#: `BotAction` strings to their contract numbers. A literal table rather than `getattr` on the generated
#: enum so that a renamed proto value fails here at import time instead of at the first CLOSE.
_ACTION_TO_WIRE: dict[str, int] = {
    BotAction.HOLD: pb.BOT_ACTION_HOLD,
    BotAction.OPEN: pb.BOT_ACTION_OPEN,
    BotAction.CLOSE: pb.BOT_ACTION_CLOSE,
    BotAction.ADJUST_BRACKET: pb.BOT_ACTION_ADJUST_BRACKET,
}


# ── outbound scalars ──────────────────────────────────────────────────────────────


def to_timestamp(value: datetime | None) -> Timestamp | None:
    """A `Timestamp`, or None so the caller leaves the field unset.

    None rather than epoch: 1970-01-01 is a real instant and would be read as one. An unset timestamp
    reads as "not known", which is what an unrecorded training date actually is.
    """
    if value is None:
        return None
    result = Timestamp()
    result.FromDatetime(value.astimezone(UTC))
    return result


def optional_datetime(container, field: str) -> datetime | None:
    """Read an optional `Timestamp` field, distinguishing unset from the epoch.

    `ToDatetime` on an unset submessage returns 1970-01-01 with no complaint, and a candle timestamped
    1970 sails through every validation that only checks ordering. The `HasField` is the whole check.
    """
    if not container.HasField(field):
        return None
    return getattr(container, field).ToDatetime(tzinfo=UTC)


# ── inbound ───────────────────────────────────────────────────────────────────────


def candle_from_proto(message, index: int) -> CandleInput:
    """One `Candle`, with its prices read as exact decimals.

    The index is threaded through only so a rejection can say *which* candle was malformed. A caller
    sending 500 bars and getting "close is not a decimal number" back has no way to find it otherwise.
    """
    return CandleInput(
        open_time=optional_datetime(message, "open_time"),
        open=parse_money(message.open, f"candles[{index}].open"),
        high=parse_money(message.high, f"candles[{index}].high"),
        low=parse_money(message.low, f"candles[{index}].low"),
        close=parse_money(message.close, f"candles[{index}].close"),
        volume=parse_money(message.volume, f"candles[{index}].volume"),
    )


def candles_from_proto(messages) -> tuple[CandleInput, ...]:
    return tuple(candle_from_proto(message, index) for index, message in enumerate(messages))


def parameters_from_proto(message) -> TradeParametersInput:
    """`TradeParameters`, with the two percentages kept exact.

    The zero defaults for `max_holding_periods` and `minimum_confidence` are meaningful here and are
    left as zeros: the evaluator substitutes its configured defaults, which is what proto3's inability
    to distinguish "unset" from "0" forces. That is safe for these two because zero is not a usable
    value for either — a holding limit of zero candles and a confidence floor of zero both describe
    nothing an operator would ask for. It would not be safe for a price, which is why prices are strings.
    """
    return TradeParametersInput(
        take_profit_percent=parse_money(message.take_profit_percent, "parameters.take_profit_percent"),
        stop_loss_percent=parse_money(message.stop_loss_percent, "parameters.stop_loss_percent"),
        allow_short=bool(message.allow_short),
        max_holding_periods=int(message.max_holding_periods),
        minimum_confidence=float(message.minimum_confidence),
        take_profit_atr_multiple=float(message.take_profit_atr_multiple),
        stop_loss_atr_multiple=float(message.stop_loss_atr_multiple),
    )


def position_from_proto(message) -> OpenPositionInput:
    """`OpenPosition`, with the bracket prices optional because .NET may be managing the exit itself.

    An empty bracket string is read as "not supplied" rather than rejected: a bot whose stop lives at
    the venue and whose take-profit does not is a real configuration, and the advisor falls back to the
    configured percentages for whichever half is missing.
    """
    return OpenPositionInput(
        direction=direction_from_wire(int(message.direction)),
        entry_price=parse_money(message.entry_price, "position.entry_price"),
        quantity=parse_money(message.quantity, "position.quantity"),
        opened_at=optional_datetime(message, "opened_at"),
        take_profit_price=(
            parse_money(message.take_profit_price, "position.take_profit_price")
            if message.take_profit_price
            else None
        ),
        stop_loss_price=(
            parse_money(message.stop_loss_price, "position.stop_loss_price")
            if message.stop_loss_price
            else None
        ),
        bars_held=int(message.bars_held),
    )


def signal_request_from_proto(message) -> SignalRequest:
    return SignalRequest(
        request_id=message.request_id,
        symbol=message.symbol,
        interval=message.interval,
        candles=candles_from_proto(message.candles),
        parameters=parameters_from_proto(message.parameters),
        expected_model_version=message.expected_model_version.strip(),
    )


def bot_decision_request_from_proto(message) -> BotDecisionRequest:
    return BotDecisionRequest(
        request_id=message.request_id,
        symbol=message.symbol,
        interval=message.interval,
        candles=candles_from_proto(message.candles),
        parameters=parameters_from_proto(message.parameters),
        bot_id=message.bot_id.strip(),
        # HasField, not truthiness: a zeroed OpenPosition is a valid protobuf message and would be
        # read as a position of zero size at a price of zero. That is a flat bot being told to close.
        position=position_from_proto(message.position) if message.HasField("position") else None,
        expected_model_version=message.expected_model_version.strip(),
        context_candles=candles_from_proto(message.context_candles),
        context_interval=message.context_interval.strip(),
    )


# ── outbound ──────────────────────────────────────────────────────────────────────


def levels_to_proto(levels: LevelsResult | None) -> pb.TradeLevels | None:
    if levels is None:
        return None
    return pb.TradeLevels(
        entry_price=format_decimal(levels.entry_price),
        take_profit_price=format_decimal(levels.take_profit_price),
        stop_loss_price=format_decimal(levels.stop_loss_price),
        atr=format_decimal(levels.atr),
        risk_reward_ratio=levels.risk_reward_ratio,
        take_profit_atr=levels.take_profit_atr,
        stop_loss_atr=levels.stop_loss_atr,
    )


def probabilities_to_proto(probabilities) -> pb.BarrierProbabilities:
    return pb.BarrierProbabilities(
        take_profit_first=probabilities.take_profit_first,
        stop_loss_first=probabilities.stop_loss_first,
        timeout=probabilities.timeout,
    )


def signal_to_proto(result: SignalResult) -> pb.GetSignalResponse:
    return pb.GetSignalResponse(
        request_id=result.request_id,
        direction=direction_to_wire(result.direction),
        levels=levels_to_proto(result.levels),
        confidence=result.confidence,
        probabilities=probabilities_to_proto(result.probabilities),
        expected_value=result.expected_value,
        long_confidence=result.long_confidence,
        short_confidence=result.short_confidence,
        symbol=result.symbol,
        interval=result.interval,
        candle_open_time=to_timestamp(result.candle_open_time),
        valid_until=to_timestamp(result.valid_until),
        model_id=result.model.model_id,
        model_version=result.model.model_version,
        model_trained_at=to_timestamp(result.model.trained_at),
        used_wildcard_model=result.model.used_wildcard,
        input_digest_sha256=result.input_digest_sha256,
        rationale=list(result.rationale),
        warning=result.warning,
        processing_milliseconds=result.processing_milliseconds,
        barrier_extrapolated=result.barrier_extrapolated,
    )


def bot_decision_to_proto(result: BotDecisionResult) -> pb.EvaluateBotDecisionResponse:
    return pb.EvaluateBotDecisionResponse(
        request_id=result.request_id,
        action=_ACTION_TO_WIRE[result.action],
        direction=direction_to_wire(result.direction),
        levels=levels_to_proto(result.levels),
        confidence=result.confidence,
        probabilities=probabilities_to_proto(result.probabilities),
        expected_value=result.expected_value,
        reason_code=result.reason_code,
        rationale=list(result.rationale),
        symbol=result.symbol,
        interval=result.interval,
        candle_open_time=to_timestamp(result.candle_open_time),
        valid_until=to_timestamp(result.valid_until),
        model_id=result.model.model_id,
        model_version=result.model.model_version,
        model_trained_at=to_timestamp(result.model.trained_at),
        used_wildcard_model=result.model.used_wildcard,
        input_digest_sha256=result.input_digest_sha256,
        warning=result.warning,
        processing_milliseconds=result.processing_milliseconds,
        barrier_extrapolated=result.barrier_extrapolated,
    )


def model_info_to_proto(description: ModelDescription) -> pb.GetModelInfoResponse:
    return pb.GetModelInfoResponse(
        request_id=description.request_id,
        ready=description.ready,
        model_id=description.model_id,
        model_version=description.model_version,
        project_version=description.project_version,
        symbol=description.symbol,
        interval=description.interval,
        trained_at=to_timestamp(description.trained_at),
        feature_count=description.feature_count,
        is_wildcard=description.is_wildcard,
        label_scheme=description.label_scheme,
        calibration_method=description.calibration_method,
        default_max_holding_periods=description.default_max_holding_periods,
        minimum_barrier_atr=description.minimum_barrier_atr,
        maximum_barrier_atr=description.maximum_barrier_atr,
        confidence_ceiling=description.confidence_ceiling,
        confidence_reach=[
            pb.ConfidenceReach(threshold=threshold, share=share)
            for threshold, share in description.confidence_reach
        ],
    )


def capabilities_to_proto(capabilities: Capabilities) -> pb.GetCapabilitiesResponse:
    return pb.GetCapabilitiesResponse(
        request_id=capabilities.request_id,
        service=capabilities.service,
        service_version=capabilities.service_version,
        protocol_version=capabilities.protocol_version,
        capabilities=list(capabilities.capabilities),
        supported_operations=list(capabilities.supported_operations),
        model_ready=capabilities.model_ready,
        minimum_candles=capabilities.minimum_candles,
        maximum_candles=capabilities.maximum_candles,
        supported_markets=[
            pb.SupportedMarket(
                symbol=market.symbol,
                interval=market.interval,
                model_id=market.model_id,
                model_version=market.model_version,
                is_wildcard=market.is_wildcard,
            )
            for market in capabilities.supported_markets
        ],
        wildcard_model_ready=capabilities.wildcard_model_ready,
        operating_mode=capabilities.operating_mode,
    )


def trade_direction_name(value) -> str:
    """A proto TradeDirection enum to its plain name, for the online-learning admission checks."""
    names = {
        int(pb.TRADE_DIRECTION_LONG): "LONG",
        int(pb.TRADE_DIRECTION_SHORT): "SHORT",
        int(pb.TRADE_DIRECTION_FLAT): "FLAT",
        int(pb.TRADE_DIRECTION_UNSPECIFIED): "UNSPECIFIED",
    }
    return names.get(int(value), "UNSPECIFIED")


def trade_outcome_to_proto(
    request_id: str,
    status: str,
    samples_stored: int,
    training_triggered: bool,
) -> pb.RecordTradeOutcomeResponse:
    return pb.RecordTradeOutcomeResponse(
        request_id=request_id,
        status=status,
        samples_stored=samples_stored,
        training_triggered=training_triggered,
    )


def training_status_to_proto(
    request_id: str,
    enabled: bool,
    markets,
) -> pb.GetTrainingStatusResponse:
    return pb.GetTrainingStatusResponse(
        request_id=request_id,
        online_learning_enabled=enabled,
        markets=[
            pb.TrainingStatus(
                symbol=market.symbol,
                interval=market.interval,
                samples_stored=market.samples_stored,
                samples_since_training=market.samples_since_training,
                last_trained_at=market.last_trained_at,
                last_challenger_version=market.last_challenger_version,
                last_verdict=market.last_verdict,
                last_verdict_reason=market.last_verdict_reason,
                training_in_progress=market.training_in_progress,
            )
            for market in markets
        ],
    )


# ── market scan ─────────────────────────────────────────────────────────────

def scan_symbols_response_to_proto(
    request_id: str,
    results,
    warning: str = "",
) -> pb.ScanSymbolsResponse:
    """Build the ScanSymbolsResponse from a list of ScanResult dataclasses."""
    return pb.ScanSymbolsResponse(
        request_id=request_id,
        results=[
            pb.ScanSymbolResult(
                symbol=r.symbol,
                strategy=r.strategy,
                direction=r.direction,
                confidence=r.confidence,
                reason=r.reason,
                warning=r.warning or "",
            )
            for r in results
        ],
        warning=warning,
    )


__all__ = [
    "bot_decision_request_from_proto",
    "bot_decision_to_proto",
    "candles_from_proto",
    "capabilities_to_proto",
    "levels_to_proto",
    "model_info_to_proto",
    "parameters_from_proto",
    "position_from_proto",
    "probabilities_to_proto",
    "signal_request_from_proto",
    "signal_to_proto",
    "optional_datetime",
    "to_timestamp",
    "trade_direction_name",
    "trade_outcome_to_proto",
    "training_status_to_proto",
    "scan_symbols_response_to_proto",
]
