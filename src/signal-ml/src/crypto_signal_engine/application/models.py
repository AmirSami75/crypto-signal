from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CandleInput:
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class PredictionInput:
    request_id: str
    symbol: str
    interval: str
    candles: tuple[CandleInput, ...]
    expected_model_version: str | None = None


@dataclass(frozen=True, slots=True)
class ModelInfo:
    model_id: str
    model_version: str
    project_version: str
    symbol: str
    interval: str
    trained_at: datetime
    feature_count: int
    probability_threshold: float
    sell_semantics: str


@dataclass(frozen=True, slots=True)
class PredictionResult:
    request_id: str
    signal_name: str
    numeric_signal: int
    probability_sell: float
    probability_hold: float
    probability_buy: float
    confidence: float
    close_price: float
    candle_open_time: datetime
    symbol: str
    interval: str
    model: ModelInfo
    input_digest_sha256: str
    processing_milliseconds: float
