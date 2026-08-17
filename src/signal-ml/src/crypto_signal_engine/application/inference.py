from __future__ import annotations

from datetime import UTC, timedelta
import hashlib
import math
import re
import time

import numpy as np
import pandas as pd

from crypto_signal.data import INTERVAL_SECONDS
from crypto_signal.features import make_features
from crypto_signal.model import ALL_CLASSES, probabilities_to_signals
from crypto_signal.pipeline import SIGNAL_NAMES
from crypto_signal_engine.application.errors import InvalidInferenceRequest
from crypto_signal_engine.application.models import PredictionInput, PredictionResult
from crypto_signal_engine.infrastructure.model_repository import JoblibModelRepository


_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._-]{1,29}$")
_READINESS_COLUMNS = (
    "log_return_1",
    "volatility_168",
    "sma_ratio_168",
    "volume_ratio_168",
)


class InferenceService:
    def __init__(
        self,
        repository: JoblibModelRepository,
        minimum_candles: int,
        maximum_candles: int,
    ) -> None:
        self._repository = repository
        self._minimum_candles = minimum_candles
        self._maximum_candles = maximum_candles

    @property
    def model_ready(self) -> bool:
        return self._repository.is_ready

    def model_info(self):
        return self._repository.snapshot().info

    def predict(self, request: PredictionInput) -> PredictionResult:
        started = time.perf_counter()
        snapshot = self._repository.snapshot()
        symbol = request.symbol.strip().upper()
        interval = request.interval.strip()

        self._validate_identity(request.request_id, symbol, interval)
        if symbol != snapshot.info.symbol or interval != snapshot.info.interval:
            raise InvalidInferenceRequest(
                f"Loaded model supports {snapshot.info.symbol} {snapshot.info.interval}, "
                f"not {symbol} {interval}"
            )
        if (
            request.expected_model_version
            and request.expected_model_version != snapshot.info.model_version
        ):
            raise InvalidInferenceRequest("The requested model version is not loaded")

        candles = request.candles
        if not self._minimum_candles <= len(candles) <= self._maximum_candles:
            raise InvalidInferenceRequest(
                f"candles must contain {self._minimum_candles} to "
                f"{self._maximum_candles} completed bars"
            )

        rows: list[dict[str, object]] = []
        previous_time = None
        digest = hashlib.sha256()
        digest.update(f"{symbol}|{interval}|".encode())
        for index, candle in enumerate(candles):
            timestamp = candle.open_time
            if timestamp.tzinfo is None:
                raise InvalidInferenceRequest(f"candles[{index}].open_time must be UTC")
            timestamp = timestamp.astimezone(UTC)
            values = (candle.open, candle.high, candle.low, candle.close, candle.volume)
            if not all(math.isfinite(value) for value in values):
                raise InvalidInferenceRequest(f"candles[{index}] contains a non-finite value")
            if min(candle.open, candle.high, candle.low, candle.close) <= 0:
                raise InvalidInferenceRequest(f"candles[{index}] prices must be positive")
            if candle.volume < 0:
                raise InvalidInferenceRequest(f"candles[{index}].volume cannot be negative")
            if candle.high < max(candle.open, candle.close) or candle.low > min(
                candle.open, candle.close
            ):
                raise InvalidInferenceRequest(f"candles[{index}] violates OHLC bounds")
            if previous_time is not None and timestamp <= previous_time:
                raise InvalidInferenceRequest("candle open times must be strictly increasing")
            previous_time = timestamp
            rows.append(
                {
                    "timestamp": timestamp,
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                }
            )
            digest.update(
                (
                    f"{timestamp.isoformat()}|{candle.open:.17g}|{candle.high:.17g}|"
                    f"{candle.low:.17g}|{candle.close:.17g}|{candle.volume:.17g};"
                ).encode()
            )

        expected_step = timedelta(seconds=INTERVAL_SECONDS[interval])
        warmup_times = pd.Series(
            [item.open_time for item in candles[-self._minimum_candles :]]
        )
        if not warmup_times.diff().dropna().eq(expected_step).all():
            raise InvalidInferenceRequest(
                "The final feature warm-up window contains missing or irregular candles"
            )

        frame = pd.DataFrame(rows)
        features = make_features(frame)
        latest_index = features.dropna(subset=list(_READINESS_COLUMNS)).index.max()
        if pd.isna(latest_index) or int(latest_index) != len(frame) - 1:
            raise InvalidInferenceRequest("The newest candle cannot produce complete features")
        latest = features.loc[[int(latest_index)], list(snapshot.feature_columns)]
        raw_probabilities = self._repository.run_prediction(latest)
        probabilities = self._align_probabilities(
            raw_probabilities, self._repository.snapshot().model.classes_
        )
        numeric_signal = int(
            probabilities_to_signals(
                probabilities, snapshot.info.probability_threshold
            )[0]
        )
        return PredictionResult(
            request_id=request.request_id,
            signal_name=SIGNAL_NAMES[numeric_signal],
            numeric_signal=numeric_signal,
            probability_sell=float(probabilities[0, 0]),
            probability_hold=float(probabilities[0, 1]),
            probability_buy=float(probabilities[0, 2]),
            confidence=float(np.max(probabilities[0])),
            close_price=float(frame.iloc[-1]["close"]),
            candle_open_time=frame.iloc[-1]["timestamp"].to_pydatetime(),
            symbol=symbol,
            interval=interval,
            model=snapshot.info,
            input_digest_sha256=digest.hexdigest(),
            processing_milliseconds=(time.perf_counter() - started) * 1_000,
        )

    @staticmethod
    def _validate_identity(request_id: str, symbol: str, interval: str) -> None:
        if not request_id.strip() or len(request_id) > 128:
            raise InvalidInferenceRequest("request_id is required and limited to 128 characters")
        if not _SYMBOL_PATTERN.fullmatch(symbol):
            raise InvalidInferenceRequest("symbol has an invalid format")
        if interval not in INTERVAL_SECONDS:
            raise InvalidInferenceRequest(f"Unsupported candle interval: {interval}")

    @staticmethod
    def _align_probabilities(raw: np.ndarray, classes: np.ndarray) -> np.ndarray:
        aligned = np.zeros((len(raw), len(ALL_CLASSES)), dtype=float)
        class_to_index = {int(label): index for index, label in enumerate(ALL_CLASSES)}
        for raw_index, label in enumerate(classes):
            aligned[:, class_to_index[int(label)]] = raw[:, raw_index]
        return aligned
