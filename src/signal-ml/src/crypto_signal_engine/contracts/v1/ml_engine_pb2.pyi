import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class TradeDirection(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TRADE_DIRECTION_UNSPECIFIED: _ClassVar[TradeDirection]
    TRADE_DIRECTION_LONG: _ClassVar[TradeDirection]
    TRADE_DIRECTION_SHORT: _ClassVar[TradeDirection]
    TRADE_DIRECTION_FLAT: _ClassVar[TradeDirection]

class BotAction(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    BOT_ACTION_UNSPECIFIED: _ClassVar[BotAction]
    BOT_ACTION_HOLD: _ClassVar[BotAction]
    BOT_ACTION_OPEN: _ClassVar[BotAction]
    BOT_ACTION_CLOSE: _ClassVar[BotAction]
    BOT_ACTION_ADJUST_BRACKET: _ClassVar[BotAction]
TRADE_DIRECTION_UNSPECIFIED: TradeDirection
TRADE_DIRECTION_LONG: TradeDirection
TRADE_DIRECTION_SHORT: TradeDirection
TRADE_DIRECTION_FLAT: TradeDirection
BOT_ACTION_UNSPECIFIED: BotAction
BOT_ACTION_HOLD: BotAction
BOT_ACTION_OPEN: BotAction
BOT_ACTION_CLOSE: BotAction
BOT_ACTION_ADJUST_BRACKET: BotAction

class Candle(_message.Message):
    __slots__ = ("open_time", "open", "high", "low", "close", "volume")
    OPEN_TIME_FIELD_NUMBER: _ClassVar[int]
    OPEN_FIELD_NUMBER: _ClassVar[int]
    HIGH_FIELD_NUMBER: _ClassVar[int]
    LOW_FIELD_NUMBER: _ClassVar[int]
    CLOSE_FIELD_NUMBER: _ClassVar[int]
    VOLUME_FIELD_NUMBER: _ClassVar[int]
    open_time: _timestamp_pb2.Timestamp
    open: str
    high: str
    low: str
    close: str
    volume: str
    def __init__(self, open_time: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., open: _Optional[str] = ..., high: _Optional[str] = ..., low: _Optional[str] = ..., close: _Optional[str] = ..., volume: _Optional[str] = ...) -> None: ...

class TradeParameters(_message.Message):
    __slots__ = ("take_profit_percent", "stop_loss_percent", "allow_short", "max_holding_periods", "minimum_confidence")
    TAKE_PROFIT_PERCENT_FIELD_NUMBER: _ClassVar[int]
    STOP_LOSS_PERCENT_FIELD_NUMBER: _ClassVar[int]
    ALLOW_SHORT_FIELD_NUMBER: _ClassVar[int]
    MAX_HOLDING_PERIODS_FIELD_NUMBER: _ClassVar[int]
    MINIMUM_CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    take_profit_percent: str
    stop_loss_percent: str
    allow_short: bool
    max_holding_periods: int
    minimum_confidence: float
    def __init__(self, take_profit_percent: _Optional[str] = ..., stop_loss_percent: _Optional[str] = ..., allow_short: _Optional[bool] = ..., max_holding_periods: _Optional[int] = ..., minimum_confidence: _Optional[float] = ...) -> None: ...

class TradeLevels(_message.Message):
    __slots__ = ("entry_price", "take_profit_price", "stop_loss_price", "atr", "risk_reward_ratio", "take_profit_atr", "stop_loss_atr")
    ENTRY_PRICE_FIELD_NUMBER: _ClassVar[int]
    TAKE_PROFIT_PRICE_FIELD_NUMBER: _ClassVar[int]
    STOP_LOSS_PRICE_FIELD_NUMBER: _ClassVar[int]
    ATR_FIELD_NUMBER: _ClassVar[int]
    RISK_REWARD_RATIO_FIELD_NUMBER: _ClassVar[int]
    TAKE_PROFIT_ATR_FIELD_NUMBER: _ClassVar[int]
    STOP_LOSS_ATR_FIELD_NUMBER: _ClassVar[int]
    entry_price: str
    take_profit_price: str
    stop_loss_price: str
    atr: str
    risk_reward_ratio: float
    take_profit_atr: float
    stop_loss_atr: float
    def __init__(self, entry_price: _Optional[str] = ..., take_profit_price: _Optional[str] = ..., stop_loss_price: _Optional[str] = ..., atr: _Optional[str] = ..., risk_reward_ratio: _Optional[float] = ..., take_profit_atr: _Optional[float] = ..., stop_loss_atr: _Optional[float] = ...) -> None: ...

class BarrierProbabilities(_message.Message):
    __slots__ = ("take_profit_first", "stop_loss_first", "timeout")
    TAKE_PROFIT_FIRST_FIELD_NUMBER: _ClassVar[int]
    STOP_LOSS_FIRST_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_FIELD_NUMBER: _ClassVar[int]
    take_profit_first: float
    stop_loss_first: float
    timeout: float
    def __init__(self, take_profit_first: _Optional[float] = ..., stop_loss_first: _Optional[float] = ..., timeout: _Optional[float] = ...) -> None: ...

class OpenPosition(_message.Message):
    __slots__ = ("direction", "entry_price", "quantity", "opened_at", "take_profit_price", "stop_loss_price", "bars_held")
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    ENTRY_PRICE_FIELD_NUMBER: _ClassVar[int]
    QUANTITY_FIELD_NUMBER: _ClassVar[int]
    OPENED_AT_FIELD_NUMBER: _ClassVar[int]
    TAKE_PROFIT_PRICE_FIELD_NUMBER: _ClassVar[int]
    STOP_LOSS_PRICE_FIELD_NUMBER: _ClassVar[int]
    BARS_HELD_FIELD_NUMBER: _ClassVar[int]
    direction: TradeDirection
    entry_price: str
    quantity: str
    opened_at: _timestamp_pb2.Timestamp
    take_profit_price: str
    stop_loss_price: str
    bars_held: int
    def __init__(self, direction: _Optional[_Union[TradeDirection, str]] = ..., entry_price: _Optional[str] = ..., quantity: _Optional[str] = ..., opened_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., take_profit_price: _Optional[str] = ..., stop_loss_price: _Optional[str] = ..., bars_held: _Optional[int] = ...) -> None: ...

class GetCapabilitiesRequest(_message.Message):
    __slots__ = ("request_id",)
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    def __init__(self, request_id: _Optional[str] = ...) -> None: ...

class SupportedMarket(_message.Message):
    __slots__ = ("symbol", "interval", "model_id", "model_version", "is_wildcard")
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    INTERVAL_FIELD_NUMBER: _ClassVar[int]
    MODEL_ID_FIELD_NUMBER: _ClassVar[int]
    MODEL_VERSION_FIELD_NUMBER: _ClassVar[int]
    IS_WILDCARD_FIELD_NUMBER: _ClassVar[int]
    symbol: str
    interval: str
    model_id: str
    model_version: str
    is_wildcard: bool
    def __init__(self, symbol: _Optional[str] = ..., interval: _Optional[str] = ..., model_id: _Optional[str] = ..., model_version: _Optional[str] = ..., is_wildcard: _Optional[bool] = ...) -> None: ...

class GetCapabilitiesResponse(_message.Message):
    __slots__ = ("request_id", "service", "service_version", "protocol_version", "capabilities", "supported_operations", "model_ready", "minimum_candles", "maximum_candles", "supported_markets", "wildcard_model_ready", "operating_mode")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    SERVICE_FIELD_NUMBER: _ClassVar[int]
    SERVICE_VERSION_FIELD_NUMBER: _ClassVar[int]
    PROTOCOL_VERSION_FIELD_NUMBER: _ClassVar[int]
    CAPABILITIES_FIELD_NUMBER: _ClassVar[int]
    SUPPORTED_OPERATIONS_FIELD_NUMBER: _ClassVar[int]
    MODEL_READY_FIELD_NUMBER: _ClassVar[int]
    MINIMUM_CANDLES_FIELD_NUMBER: _ClassVar[int]
    MAXIMUM_CANDLES_FIELD_NUMBER: _ClassVar[int]
    SUPPORTED_MARKETS_FIELD_NUMBER: _ClassVar[int]
    WILDCARD_MODEL_READY_FIELD_NUMBER: _ClassVar[int]
    OPERATING_MODE_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    service: str
    service_version: str
    protocol_version: str
    capabilities: _containers.RepeatedScalarFieldContainer[str]
    supported_operations: _containers.RepeatedScalarFieldContainer[str]
    model_ready: bool
    minimum_candles: int
    maximum_candles: int
    supported_markets: _containers.RepeatedCompositeFieldContainer[SupportedMarket]
    wildcard_model_ready: bool
    operating_mode: str
    def __init__(self, request_id: _Optional[str] = ..., service: _Optional[str] = ..., service_version: _Optional[str] = ..., protocol_version: _Optional[str] = ..., capabilities: _Optional[_Iterable[str]] = ..., supported_operations: _Optional[_Iterable[str]] = ..., model_ready: _Optional[bool] = ..., minimum_candles: _Optional[int] = ..., maximum_candles: _Optional[int] = ..., supported_markets: _Optional[_Iterable[_Union[SupportedMarket, _Mapping]]] = ..., wildcard_model_ready: _Optional[bool] = ..., operating_mode: _Optional[str] = ...) -> None: ...

class GetModelInfoRequest(_message.Message):
    __slots__ = ("request_id", "symbol", "interval")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    INTERVAL_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    symbol: str
    interval: str
    def __init__(self, request_id: _Optional[str] = ..., symbol: _Optional[str] = ..., interval: _Optional[str] = ...) -> None: ...

class ConfidenceReach(_message.Message):
    __slots__ = ("threshold", "share")
    THRESHOLD_FIELD_NUMBER: _ClassVar[int]
    SHARE_FIELD_NUMBER: _ClassVar[int]
    threshold: float
    share: float
    def __init__(self, threshold: _Optional[float] = ..., share: _Optional[float] = ...) -> None: ...

class GetModelInfoResponse(_message.Message):
    __slots__ = ("request_id", "ready", "model_id", "model_version", "project_version", "symbol", "interval", "trained_at", "feature_count", "is_wildcard", "label_scheme", "calibration_method", "default_max_holding_periods", "minimum_barrier_atr", "maximum_barrier_atr", "confidence_ceiling", "confidence_reach")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    READY_FIELD_NUMBER: _ClassVar[int]
    MODEL_ID_FIELD_NUMBER: _ClassVar[int]
    MODEL_VERSION_FIELD_NUMBER: _ClassVar[int]
    PROJECT_VERSION_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    INTERVAL_FIELD_NUMBER: _ClassVar[int]
    TRAINED_AT_FIELD_NUMBER: _ClassVar[int]
    FEATURE_COUNT_FIELD_NUMBER: _ClassVar[int]
    IS_WILDCARD_FIELD_NUMBER: _ClassVar[int]
    LABEL_SCHEME_FIELD_NUMBER: _ClassVar[int]
    CALIBRATION_METHOD_FIELD_NUMBER: _ClassVar[int]
    DEFAULT_MAX_HOLDING_PERIODS_FIELD_NUMBER: _ClassVar[int]
    MINIMUM_BARRIER_ATR_FIELD_NUMBER: _ClassVar[int]
    MAXIMUM_BARRIER_ATR_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_CEILING_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_REACH_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    ready: bool
    model_id: str
    model_version: str
    project_version: str
    symbol: str
    interval: str
    trained_at: _timestamp_pb2.Timestamp
    feature_count: int
    is_wildcard: bool
    label_scheme: str
    calibration_method: str
    default_max_holding_periods: int
    minimum_barrier_atr: float
    maximum_barrier_atr: float
    confidence_ceiling: float
    confidence_reach: _containers.RepeatedCompositeFieldContainer[ConfidenceReach]
    def __init__(self, request_id: _Optional[str] = ..., ready: _Optional[bool] = ..., model_id: _Optional[str] = ..., model_version: _Optional[str] = ..., project_version: _Optional[str] = ..., symbol: _Optional[str] = ..., interval: _Optional[str] = ..., trained_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., feature_count: _Optional[int] = ..., is_wildcard: _Optional[bool] = ..., label_scheme: _Optional[str] = ..., calibration_method: _Optional[str] = ..., default_max_holding_periods: _Optional[int] = ..., minimum_barrier_atr: _Optional[float] = ..., maximum_barrier_atr: _Optional[float] = ..., confidence_ceiling: _Optional[float] = ..., confidence_reach: _Optional[_Iterable[_Union[ConfidenceReach, _Mapping]]] = ...) -> None: ...

class GetSignalRequest(_message.Message):
    __slots__ = ("request_id", "symbol", "interval", "candles", "parameters", "expected_model_version")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    INTERVAL_FIELD_NUMBER: _ClassVar[int]
    CANDLES_FIELD_NUMBER: _ClassVar[int]
    PARAMETERS_FIELD_NUMBER: _ClassVar[int]
    EXPECTED_MODEL_VERSION_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    symbol: str
    interval: str
    candles: _containers.RepeatedCompositeFieldContainer[Candle]
    parameters: TradeParameters
    expected_model_version: str
    def __init__(self, request_id: _Optional[str] = ..., symbol: _Optional[str] = ..., interval: _Optional[str] = ..., candles: _Optional[_Iterable[_Union[Candle, _Mapping]]] = ..., parameters: _Optional[_Union[TradeParameters, _Mapping]] = ..., expected_model_version: _Optional[str] = ...) -> None: ...

class GetSignalResponse(_message.Message):
    __slots__ = ("request_id", "direction", "levels", "confidence", "probabilities", "expected_value", "long_confidence", "short_confidence", "symbol", "interval", "candle_open_time", "valid_until", "model_id", "model_version", "model_trained_at", "used_wildcard_model", "input_digest_sha256", "rationale", "warning", "processing_milliseconds", "barrier_extrapolated")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    LEVELS_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    PROBABILITIES_FIELD_NUMBER: _ClassVar[int]
    EXPECTED_VALUE_FIELD_NUMBER: _ClassVar[int]
    LONG_CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    SHORT_CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    INTERVAL_FIELD_NUMBER: _ClassVar[int]
    CANDLE_OPEN_TIME_FIELD_NUMBER: _ClassVar[int]
    VALID_UNTIL_FIELD_NUMBER: _ClassVar[int]
    MODEL_ID_FIELD_NUMBER: _ClassVar[int]
    MODEL_VERSION_FIELD_NUMBER: _ClassVar[int]
    MODEL_TRAINED_AT_FIELD_NUMBER: _ClassVar[int]
    USED_WILDCARD_MODEL_FIELD_NUMBER: _ClassVar[int]
    INPUT_DIGEST_SHA256_FIELD_NUMBER: _ClassVar[int]
    RATIONALE_FIELD_NUMBER: _ClassVar[int]
    WARNING_FIELD_NUMBER: _ClassVar[int]
    PROCESSING_MILLISECONDS_FIELD_NUMBER: _ClassVar[int]
    BARRIER_EXTRAPOLATED_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    direction: TradeDirection
    levels: TradeLevels
    confidence: float
    probabilities: BarrierProbabilities
    expected_value: float
    long_confidence: float
    short_confidence: float
    symbol: str
    interval: str
    candle_open_time: _timestamp_pb2.Timestamp
    valid_until: _timestamp_pb2.Timestamp
    model_id: str
    model_version: str
    model_trained_at: _timestamp_pb2.Timestamp
    used_wildcard_model: bool
    input_digest_sha256: str
    rationale: _containers.RepeatedScalarFieldContainer[str]
    warning: str
    processing_milliseconds: float
    barrier_extrapolated: bool
    def __init__(self, request_id: _Optional[str] = ..., direction: _Optional[_Union[TradeDirection, str]] = ..., levels: _Optional[_Union[TradeLevels, _Mapping]] = ..., confidence: _Optional[float] = ..., probabilities: _Optional[_Union[BarrierProbabilities, _Mapping]] = ..., expected_value: _Optional[float] = ..., long_confidence: _Optional[float] = ..., short_confidence: _Optional[float] = ..., symbol: _Optional[str] = ..., interval: _Optional[str] = ..., candle_open_time: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., valid_until: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., model_id: _Optional[str] = ..., model_version: _Optional[str] = ..., model_trained_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., used_wildcard_model: _Optional[bool] = ..., input_digest_sha256: _Optional[str] = ..., rationale: _Optional[_Iterable[str]] = ..., warning: _Optional[str] = ..., processing_milliseconds: _Optional[float] = ..., barrier_extrapolated: _Optional[bool] = ...) -> None: ...

class EvaluateBotDecisionRequest(_message.Message):
    __slots__ = ("request_id", "bot_id", "symbol", "interval", "candles", "parameters", "position", "expected_model_version", "context_candles", "context_interval")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    BOT_ID_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    INTERVAL_FIELD_NUMBER: _ClassVar[int]
    CANDLES_FIELD_NUMBER: _ClassVar[int]
    PARAMETERS_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    EXPECTED_MODEL_VERSION_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_CANDLES_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_INTERVAL_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    bot_id: str
    symbol: str
    interval: str
    candles: _containers.RepeatedCompositeFieldContainer[Candle]
    parameters: TradeParameters
    position: OpenPosition
    expected_model_version: str
    context_candles: _containers.RepeatedCompositeFieldContainer[Candle]
    context_interval: str
    def __init__(self, request_id: _Optional[str] = ..., bot_id: _Optional[str] = ..., symbol: _Optional[str] = ..., interval: _Optional[str] = ..., candles: _Optional[_Iterable[_Union[Candle, _Mapping]]] = ..., parameters: _Optional[_Union[TradeParameters, _Mapping]] = ..., position: _Optional[_Union[OpenPosition, _Mapping]] = ..., expected_model_version: _Optional[str] = ..., context_candles: _Optional[_Iterable[_Union[Candle, _Mapping]]] = ..., context_interval: _Optional[str] = ...) -> None: ...

class EvaluateBotDecisionResponse(_message.Message):
    __slots__ = ("request_id", "action", "direction", "levels", "confidence", "probabilities", "expected_value", "reason_code", "rationale", "symbol", "interval", "candle_open_time", "valid_until", "model_id", "model_version", "model_trained_at", "used_wildcard_model", "input_digest_sha256", "warning", "processing_milliseconds", "barrier_extrapolated")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    LEVELS_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    PROBABILITIES_FIELD_NUMBER: _ClassVar[int]
    EXPECTED_VALUE_FIELD_NUMBER: _ClassVar[int]
    REASON_CODE_FIELD_NUMBER: _ClassVar[int]
    RATIONALE_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    INTERVAL_FIELD_NUMBER: _ClassVar[int]
    CANDLE_OPEN_TIME_FIELD_NUMBER: _ClassVar[int]
    VALID_UNTIL_FIELD_NUMBER: _ClassVar[int]
    MODEL_ID_FIELD_NUMBER: _ClassVar[int]
    MODEL_VERSION_FIELD_NUMBER: _ClassVar[int]
    MODEL_TRAINED_AT_FIELD_NUMBER: _ClassVar[int]
    USED_WILDCARD_MODEL_FIELD_NUMBER: _ClassVar[int]
    INPUT_DIGEST_SHA256_FIELD_NUMBER: _ClassVar[int]
    WARNING_FIELD_NUMBER: _ClassVar[int]
    PROCESSING_MILLISECONDS_FIELD_NUMBER: _ClassVar[int]
    BARRIER_EXTRAPOLATED_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    action: BotAction
    direction: TradeDirection
    levels: TradeLevels
    confidence: float
    probabilities: BarrierProbabilities
    expected_value: float
    reason_code: str
    rationale: _containers.RepeatedScalarFieldContainer[str]
    symbol: str
    interval: str
    candle_open_time: _timestamp_pb2.Timestamp
    valid_until: _timestamp_pb2.Timestamp
    model_id: str
    model_version: str
    model_trained_at: _timestamp_pb2.Timestamp
    used_wildcard_model: bool
    input_digest_sha256: str
    warning: str
    processing_milliseconds: float
    barrier_extrapolated: bool
    def __init__(self, request_id: _Optional[str] = ..., action: _Optional[_Union[BotAction, str]] = ..., direction: _Optional[_Union[TradeDirection, str]] = ..., levels: _Optional[_Union[TradeLevels, _Mapping]] = ..., confidence: _Optional[float] = ..., probabilities: _Optional[_Union[BarrierProbabilities, _Mapping]] = ..., expected_value: _Optional[float] = ..., reason_code: _Optional[str] = ..., rationale: _Optional[_Iterable[str]] = ..., symbol: _Optional[str] = ..., interval: _Optional[str] = ..., candle_open_time: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., valid_until: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., model_id: _Optional[str] = ..., model_version: _Optional[str] = ..., model_trained_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., used_wildcard_model: _Optional[bool] = ..., input_digest_sha256: _Optional[str] = ..., warning: _Optional[str] = ..., processing_milliseconds: _Optional[float] = ..., barrier_extrapolated: _Optional[bool] = ...) -> None: ...

class RecordTradeOutcomeRequest(_message.Message):
    __slots__ = ("request_id", "bot_id", "symbol", "interval", "model_id", "model_version", "direction", "candles", "take_profit_percent", "stop_loss_percent", "close_reason", "realized_pnl", "bars_held", "decision_candle_open_time", "closed_at")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    BOT_ID_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    INTERVAL_FIELD_NUMBER: _ClassVar[int]
    MODEL_ID_FIELD_NUMBER: _ClassVar[int]
    MODEL_VERSION_FIELD_NUMBER: _ClassVar[int]
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    CANDLES_FIELD_NUMBER: _ClassVar[int]
    TAKE_PROFIT_PERCENT_FIELD_NUMBER: _ClassVar[int]
    STOP_LOSS_PERCENT_FIELD_NUMBER: _ClassVar[int]
    CLOSE_REASON_FIELD_NUMBER: _ClassVar[int]
    REALIZED_PNL_FIELD_NUMBER: _ClassVar[int]
    BARS_HELD_FIELD_NUMBER: _ClassVar[int]
    DECISION_CANDLE_OPEN_TIME_FIELD_NUMBER: _ClassVar[int]
    CLOSED_AT_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    bot_id: str
    symbol: str
    interval: str
    model_id: str
    model_version: str
    direction: TradeDirection
    candles: _containers.RepeatedCompositeFieldContainer[Candle]
    take_profit_percent: str
    stop_loss_percent: str
    close_reason: str
    realized_pnl: str
    bars_held: int
    decision_candle_open_time: _timestamp_pb2.Timestamp
    closed_at: _timestamp_pb2.Timestamp
    def __init__(self, request_id: _Optional[str] = ..., bot_id: _Optional[str] = ..., symbol: _Optional[str] = ..., interval: _Optional[str] = ..., model_id: _Optional[str] = ..., model_version: _Optional[str] = ..., direction: _Optional[_Union[TradeDirection, str]] = ..., candles: _Optional[_Iterable[_Union[Candle, _Mapping]]] = ..., take_profit_percent: _Optional[str] = ..., stop_loss_percent: _Optional[str] = ..., close_reason: _Optional[str] = ..., realized_pnl: _Optional[str] = ..., bars_held: _Optional[int] = ..., decision_candle_open_time: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., closed_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class RecordTradeOutcomeResponse(_message.Message):
    __slots__ = ("request_id", "status", "samples_stored", "training_triggered")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    SAMPLES_STORED_FIELD_NUMBER: _ClassVar[int]
    TRAINING_TRIGGERED_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    status: str
    samples_stored: int
    training_triggered: bool
    def __init__(self, request_id: _Optional[str] = ..., status: _Optional[str] = ..., samples_stored: _Optional[int] = ..., training_triggered: _Optional[bool] = ...) -> None: ...

class GetTrainingStatusRequest(_message.Message):
    __slots__ = ("request_id", "symbols", "intervals")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    SYMBOLS_FIELD_NUMBER: _ClassVar[int]
    INTERVALS_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    symbols: _containers.RepeatedScalarFieldContainer[str]
    intervals: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, request_id: _Optional[str] = ..., symbols: _Optional[_Iterable[str]] = ..., intervals: _Optional[_Iterable[str]] = ...) -> None: ...

class TrainingStatus(_message.Message):
    __slots__ = ("symbol", "interval", "samples_stored", "samples_since_training", "last_trained_at", "last_challenger_version", "last_verdict", "last_verdict_reason", "training_in_progress")
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    INTERVAL_FIELD_NUMBER: _ClassVar[int]
    SAMPLES_STORED_FIELD_NUMBER: _ClassVar[int]
    SAMPLES_SINCE_TRAINING_FIELD_NUMBER: _ClassVar[int]
    LAST_TRAINED_AT_FIELD_NUMBER: _ClassVar[int]
    LAST_CHALLENGER_VERSION_FIELD_NUMBER: _ClassVar[int]
    LAST_VERDICT_FIELD_NUMBER: _ClassVar[int]
    LAST_VERDICT_REASON_FIELD_NUMBER: _ClassVar[int]
    TRAINING_IN_PROGRESS_FIELD_NUMBER: _ClassVar[int]
    symbol: str
    interval: str
    samples_stored: int
    samples_since_training: int
    last_trained_at: str
    last_challenger_version: str
    last_verdict: str
    last_verdict_reason: str
    training_in_progress: bool
    def __init__(self, symbol: _Optional[str] = ..., interval: _Optional[str] = ..., samples_stored: _Optional[int] = ..., samples_since_training: _Optional[int] = ..., last_trained_at: _Optional[str] = ..., last_challenger_version: _Optional[str] = ..., last_verdict: _Optional[str] = ..., last_verdict_reason: _Optional[str] = ..., training_in_progress: _Optional[bool] = ...) -> None: ...

class GetTrainingStatusResponse(_message.Message):
    __slots__ = ("request_id", "online_learning_enabled", "markets")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    ONLINE_LEARNING_ENABLED_FIELD_NUMBER: _ClassVar[int]
    MARKETS_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    online_learning_enabled: bool
    markets: _containers.RepeatedCompositeFieldContainer[TrainingStatus]
    def __init__(self, request_id: _Optional[str] = ..., online_learning_enabled: _Optional[bool] = ..., markets: _Optional[_Iterable[_Union[TrainingStatus, _Mapping]]] = ...) -> None: ...

class ScanSymbolRequest(_message.Message):
    __slots__ = ("symbol", "candles")
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    CANDLES_FIELD_NUMBER: _ClassVar[int]
    symbol: str
    candles: _containers.RepeatedCompositeFieldContainer[Candle]
    def __init__(self, symbol: _Optional[str] = ..., candles: _Optional[_Iterable[_Union[Candle, _Mapping]]] = ...) -> None: ...

class ScanStrategySpec(_message.Message):
    __slots__ = ("name", "take_profit_atr", "stop_loss_atr")
    NAME_FIELD_NUMBER: _ClassVar[int]
    TAKE_PROFIT_ATR_FIELD_NUMBER: _ClassVar[int]
    STOP_LOSS_ATR_FIELD_NUMBER: _ClassVar[int]
    name: str
    take_profit_atr: float
    stop_loss_atr: float
    def __init__(self, name: _Optional[str] = ..., take_profit_atr: _Optional[float] = ..., stop_loss_atr: _Optional[float] = ...) -> None: ...

class ScanSymbolResult(_message.Message):
    __slots__ = ("symbol", "strategy", "direction", "confidence", "reason", "warning")
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    STRATEGY_FIELD_NUMBER: _ClassVar[int]
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    WARNING_FIELD_NUMBER: _ClassVar[int]
    symbol: str
    strategy: str
    direction: str
    confidence: float
    reason: str
    warning: str
    def __init__(self, symbol: _Optional[str] = ..., strategy: _Optional[str] = ..., direction: _Optional[str] = ..., confidence: _Optional[float] = ..., reason: _Optional[str] = ..., warning: _Optional[str] = ...) -> None: ...

class ScanSymbolsRequest(_message.Message):
    __slots__ = ("request_id", "symbols", "strategies", "interval")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    SYMBOLS_FIELD_NUMBER: _ClassVar[int]
    STRATEGIES_FIELD_NUMBER: _ClassVar[int]
    INTERVAL_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    symbols: _containers.RepeatedCompositeFieldContainer[ScanSymbolRequest]
    strategies: _containers.RepeatedCompositeFieldContainer[ScanStrategySpec]
    interval: str
    def __init__(self, request_id: _Optional[str] = ..., symbols: _Optional[_Iterable[_Union[ScanSymbolRequest, _Mapping]]] = ..., strategies: _Optional[_Iterable[_Union[ScanStrategySpec, _Mapping]]] = ..., interval: _Optional[str] = ...) -> None: ...

class ScanSymbolsResponse(_message.Message):
    __slots__ = ("request_id", "results", "warning")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    WARNING_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    results: _containers.RepeatedCompositeFieldContainer[ScanSymbolResult]
    warning: str
    def __init__(self, request_id: _Optional[str] = ..., results: _Optional[_Iterable[_Union[ScanSymbolResult, _Mapping]]] = ..., warning: _Optional[str] = ...) -> None: ...
