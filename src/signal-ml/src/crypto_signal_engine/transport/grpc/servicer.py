from __future__ import annotations

from datetime import UTC
import logging
import time
import uuid

import grpc
from google.protobuf.timestamp_pb2 import Timestamp

from crypto_signal_engine import __version__
from crypto_signal_engine.application.errors import (
    InvalidInferenceRequest,
    ModelUnavailable,
)
from crypto_signal_engine.application.inference import InferenceService
from crypto_signal_engine.application.models import CandleInput, PredictionInput
from crypto_signal_engine.contracts.v1 import ml_engine_pb2, ml_engine_pb2_grpc


logger = logging.getLogger(__name__)
SERVICE_NAME = "crypto_signal.ml.v1.MlEngineService"
PROTOCOL_VERSION = "v1"
WARNING = "Advisory ML output only; never an exchange execution instruction."


def _timestamp(value) -> Timestamp:
    result = Timestamp()
    result.FromDatetime(value.astimezone(UTC))
    return result


def _request_id(value: str) -> str:
    normalized = value.strip()
    return normalized if normalized else str(uuid.uuid4())


class MlEngineServicer(ml_engine_pb2_grpc.MlEngineServiceServicer):
    def __init__(
        self,
        inference: InferenceService,
        minimum_candles: int,
        maximum_candles: int,
    ) -> None:
        self._inference = inference
        self._minimum_candles = minimum_candles
        self._maximum_candles = maximum_candles

    def GetCapabilities(self, request, context):
        request_id = _request_id(request.request_id)
        started = time.perf_counter()
        response = ml_engine_pb2.GetCapabilitiesResponse(
            request_id=request_id,
            service="python-ml-engine",
            service_version=__version__,
            protocol_version=PROTOCOL_VERSION,
            capabilities=[
                "causal-feature-engineering",
                "version-pinned-model-inference",
                "model-artifact-inspection",
                "input-and-model-audit-digests",
            ],
            supported_operations=[
                "GET_CAPABILITIES",
                "GET_MODEL_INFO",
                "PREDICT_SIGNAL",
            ],
            model_ready=self._inference.model_ready,
            minimum_candles=self._minimum_candles,
            maximum_candles=self._maximum_candles,
        )
        self._log_success("GetCapabilities", request_id, started)
        return response

    def GetModelInfo(self, request, context):
        request_id = _request_id(request.request_id)
        started = time.perf_counter()
        try:
            info = self._inference.model_info()
            response = ml_engine_pb2.GetModelInfoResponse(
                request_id=request_id,
                ready=True,
                model_id=info.model_id,
                model_version=info.model_version,
                project_version=info.project_version,
                symbol=info.symbol,
                interval=info.interval,
                trained_at=_timestamp(info.trained_at),
                feature_count=info.feature_count,
                probability_threshold=info.probability_threshold,
                sell_semantics=info.sell_semantics,
            )
            self._log_success("GetModelInfo", request_id, started)
            return response
        except ModelUnavailable as exc:
            self._abort(context, grpc.StatusCode.FAILED_PRECONDITION, str(exc), request_id)

    def PredictSignal(self, request, context):
        request_id = request.request_id.strip()
        started = time.perf_counter()
        try:
            prediction = self._inference.predict(
                PredictionInput(
                    request_id=request_id,
                    symbol=request.symbol,
                    interval=request.interval,
                    candles=tuple(
                        CandleInput(
                            open_time=candle.open_time.ToDatetime(tzinfo=UTC),
                            open=candle.open,
                            high=candle.high,
                            low=candle.low,
                            close=candle.close,
                            volume=candle.volume,
                        )
                        for candle in request.candles
                    ),
                    expected_model_version=(
                        request.expected_model_version.strip() or None
                    ),
                )
            )
            signal = {
                "SELL": ml_engine_pb2.SIGNAL_SELL,
                "HOLD": ml_engine_pb2.SIGNAL_HOLD,
                "BUY": ml_engine_pb2.SIGNAL_BUY,
            }[prediction.signal_name]
            response = ml_engine_pb2.PredictSignalResponse(
                request_id=prediction.request_id,
                signal=signal,
                numeric_signal=prediction.numeric_signal,
                probabilities=ml_engine_pb2.SignalProbabilities(
                    sell=prediction.probability_sell,
                    hold=prediction.probability_hold,
                    buy=prediction.probability_buy,
                ),
                confidence=prediction.confidence,
                close_price=prediction.close_price,
                candle_open_time=_timestamp(prediction.candle_open_time),
                symbol=prediction.symbol,
                interval=prediction.interval,
                model_id=prediction.model.model_id,
                model_version=prediction.model.model_version,
                model_trained_at=_timestamp(prediction.model.trained_at),
                probability_threshold=prediction.model.probability_threshold,
                input_digest_sha256=prediction.input_digest_sha256,
                sell_semantics=prediction.model.sell_semantics,
                warning=WARNING,
                processing_milliseconds=prediction.processing_milliseconds,
            )
            self._log_success("PredictSignal", request_id, started)
            return response
        except InvalidInferenceRequest as exc:
            self._abort(context, grpc.StatusCode.INVALID_ARGUMENT, str(exc), request_id)
        except ModelUnavailable as exc:
            self._abort(context, grpc.StatusCode.FAILED_PRECONDITION, str(exc), request_id)
        except Exception:
            logger.exception(
                "Unhandled prediction failure",
                extra={"request_id": request_id, "rpc_method": "PredictSignal"},
            )
            self._abort(
                context,
                grpc.StatusCode.INTERNAL,
                "The ML engine could not complete inference",
                request_id,
            )

    @staticmethod
    def _abort(context, status: grpc.StatusCode, detail: str, request_id: str):
        logger.warning(
            "gRPC request rejected",
            extra={
                "request_id": request_id or "missing",
                "status": status.name,
            },
        )
        context.abort(status, detail)

    @staticmethod
    def _log_success(method: str, request_id: str, started: float) -> None:
        logger.info(
            "gRPC request completed",
            extra={
                "request_id": request_id,
                "rpc_method": method,
                "status": "OK",
                "duration_ms": round((time.perf_counter() - started) * 1_000, 3),
            },
        )
