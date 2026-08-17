import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Signal(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SIGNAL_UNSPECIFIED: _ClassVar[Signal]
    SIGNAL_SELL: _ClassVar[Signal]
    SIGNAL_HOLD: _ClassVar[Signal]
    SIGNAL_BUY: _ClassVar[Signal]
SIGNAL_UNSPECIFIED: Signal
SIGNAL_SELL: Signal
SIGNAL_HOLD: Signal
SIGNAL_BUY: Signal

class GetCapabilitiesRequest(_message.Message):
    __slots__ = ("request_id",)
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    def __init__(self, request_id: _Optional[str] = ...) -> None: ...

class GetCapabilitiesResponse(_message.Message):
    __slots__ = ("request_id", "service", "service_version", "protocol_version", "capabilities", "supported_operations", "model_ready", "minimum_candles", "maximum_candles")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    SERVICE_FIELD_NUMBER: _ClassVar[int]
    SERVICE_VERSION_FIELD_NUMBER: _ClassVar[int]
    PROTOCOL_VERSION_FIELD_NUMBER: _ClassVar[int]
    CAPABILITIES_FIELD_NUMBER: _ClassVar[int]
    SUPPORTED_OPERATIONS_FIELD_NUMBER: _ClassVar[int]
    MODEL_READY_FIELD_NUMBER: _ClassVar[int]
    MINIMUM_CANDLES_FIELD_NUMBER: _ClassVar[int]
    MAXIMUM_CANDLES_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    service: str
    service_version: str
    protocol_version: str
    capabilities: _containers.RepeatedScalarFieldContainer[str]
    supported_operations: _containers.RepeatedScalarFieldContainer[str]
    model_ready: bool
    minimum_candles: int
    maximum_candles: int
    def __init__(self, request_id: _Optional[str] = ..., service: _Optional[str] = ..., service_version: _Optional[str] = ..., protocol_version: _Optional[str] = ..., capabilities: _Optional[_Iterable[str]] = ..., supported_operations: _Optional[_Iterable[str]] = ..., model_ready: _Optional[bool] = ..., minimum_candles: _Optional[int] = ..., maximum_candles: _Optional[int] = ...) -> None: ...

class GetModelInfoRequest(_message.Message):
    __slots__ = ("request_id",)
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    def __init__(self, request_id: _Optional[str] = ...) -> None: ...

class GetModelInfoResponse(_message.Message):
    __slots__ = ("request_id", "ready", "model_id", "model_version", "project_version", "symbol", "interval", "trained_at", "feature_count", "probability_threshold", "sell_semantics")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    READY_FIELD_NUMBER: _ClassVar[int]
    MODEL_ID_FIELD_NUMBER: _ClassVar[int]
    MODEL_VERSION_FIELD_NUMBER: _ClassVar[int]
    PROJECT_VERSION_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    INTERVAL_FIELD_NUMBER: _ClassVar[int]
    TRAINED_AT_FIELD_NUMBER: _ClassVar[int]
    FEATURE_COUNT_FIELD_NUMBER: _ClassVar[int]
    PROBABILITY_THRESHOLD_FIELD_NUMBER: _ClassVar[int]
    SELL_SEMANTICS_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    ready: bool
    model_id: str
    model_version: str
    project_version: str
    symbol: str
    interval: str
    trained_at: _timestamp_pb2.Timestamp
    feature_count: int
    probability_threshold: float
    sell_semantics: str
    def __init__(self, request_id: _Optional[str] = ..., ready: _Optional[bool] = ..., model_id: _Optional[str] = ..., model_version: _Optional[str] = ..., project_version: _Optional[str] = ..., symbol: _Optional[str] = ..., interval: _Optional[str] = ..., trained_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., feature_count: _Optional[int] = ..., probability_threshold: _Optional[float] = ..., sell_semantics: _Optional[str] = ...) -> None: ...

class Candle(_message.Message):
    __slots__ = ("open_time", "open", "high", "low", "close", "volume")
    OPEN_TIME_FIELD_NUMBER: _ClassVar[int]
    OPEN_FIELD_NUMBER: _ClassVar[int]
    HIGH_FIELD_NUMBER: _ClassVar[int]
    LOW_FIELD_NUMBER: _ClassVar[int]
    CLOSE_FIELD_NUMBER: _ClassVar[int]
    VOLUME_FIELD_NUMBER: _ClassVar[int]
    open_time: _timestamp_pb2.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float
    def __init__(self, open_time: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., open: _Optional[float] = ..., high: _Optional[float] = ..., low: _Optional[float] = ..., close: _Optional[float] = ..., volume: _Optional[float] = ...) -> None: ...

class SignalProbabilities(_message.Message):
    __slots__ = ("sell", "hold", "buy")
    SELL_FIELD_NUMBER: _ClassVar[int]
    HOLD_FIELD_NUMBER: _ClassVar[int]
    BUY_FIELD_NUMBER: _ClassVar[int]
    sell: float
    hold: float
    buy: float
    def __init__(self, sell: _Optional[float] = ..., hold: _Optional[float] = ..., buy: _Optional[float] = ...) -> None: ...

class PredictSignalRequest(_message.Message):
    __slots__ = ("request_id", "symbol", "interval", "candles", "expected_model_version")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    INTERVAL_FIELD_NUMBER: _ClassVar[int]
    CANDLES_FIELD_NUMBER: _ClassVar[int]
    EXPECTED_MODEL_VERSION_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    symbol: str
    interval: str
    candles: _containers.RepeatedCompositeFieldContainer[Candle]
    expected_model_version: str
    def __init__(self, request_id: _Optional[str] = ..., symbol: _Optional[str] = ..., interval: _Optional[str] = ..., candles: _Optional[_Iterable[_Union[Candle, _Mapping]]] = ..., expected_model_version: _Optional[str] = ...) -> None: ...

class PredictSignalResponse(_message.Message):
    __slots__ = ("request_id", "signal", "numeric_signal", "probabilities", "confidence", "close_price", "candle_open_time", "symbol", "interval", "model_id", "model_version", "model_trained_at", "probability_threshold", "input_digest_sha256", "sell_semantics", "warning", "processing_milliseconds")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    SIGNAL_FIELD_NUMBER: _ClassVar[int]
    NUMERIC_SIGNAL_FIELD_NUMBER: _ClassVar[int]
    PROBABILITIES_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    CLOSE_PRICE_FIELD_NUMBER: _ClassVar[int]
    CANDLE_OPEN_TIME_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    INTERVAL_FIELD_NUMBER: _ClassVar[int]
    MODEL_ID_FIELD_NUMBER: _ClassVar[int]
    MODEL_VERSION_FIELD_NUMBER: _ClassVar[int]
    MODEL_TRAINED_AT_FIELD_NUMBER: _ClassVar[int]
    PROBABILITY_THRESHOLD_FIELD_NUMBER: _ClassVar[int]
    INPUT_DIGEST_SHA256_FIELD_NUMBER: _ClassVar[int]
    SELL_SEMANTICS_FIELD_NUMBER: _ClassVar[int]
    WARNING_FIELD_NUMBER: _ClassVar[int]
    PROCESSING_MILLISECONDS_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    signal: Signal
    numeric_signal: int
    probabilities: SignalProbabilities
    confidence: float
    close_price: float
    candle_open_time: _timestamp_pb2.Timestamp
    symbol: str
    interval: str
    model_id: str
    model_version: str
    model_trained_at: _timestamp_pb2.Timestamp
    probability_threshold: float
    input_digest_sha256: str
    sell_semantics: str
    warning: str
    processing_milliseconds: float
    def __init__(self, request_id: _Optional[str] = ..., signal: _Optional[_Union[Signal, str]] = ..., numeric_signal: _Optional[int] = ..., probabilities: _Optional[_Union[SignalProbabilities, _Mapping]] = ..., confidence: _Optional[float] = ..., close_price: _Optional[float] = ..., candle_open_time: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., symbol: _Optional[str] = ..., interval: _Optional[str] = ..., model_id: _Optional[str] = ..., model_version: _Optional[str] = ..., model_trained_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., probability_threshold: _Optional[float] = ..., input_digest_sha256: _Optional[str] = ..., sell_semantics: _Optional[str] = ..., warning: _Optional[str] = ..., processing_milliseconds: _Optional[float] = ...) -> None: ...
