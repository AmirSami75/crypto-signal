"""The gRPC surface: four RPCs, each of which parses, delegates, and maps a status code.

Deliberately thin. No barrier arithmetic, no model resolution, no validation beyond what parsing a
protobuf message requires — those live in `application/`, where they can be tested without a wire and
where the bot advisor and the signal service share one implementation. What this layer owns is the
translation of a Python exception into a status code, and that is a real decision rather than plumbing:

| Exception | Status | What the caller should do |
| --- | --- | --- |
| `InvalidInferenceRequest`, `ValueError` | `INVALID_ARGUMENT` | fix the request; retrying is pointless |
| `ModelUnavailable` | `FAILED_PRECONDITION` | the engine is up, this market is not answerable |
| anything else | `INTERNAL` | a bug here; the detail is deliberately generic |

`ValueError` maps to `INVALID_ARGUMENT` because that is what the domain validators and `parse_money`
raise. Letting those fall through to `INTERNAL` would tell an orchestrator to retry a malformed price
forever, and would put a stack trace in the log for what is a client error.

The `INTERNAL` detail is a fixed string while the traceback goes to the log. An unexpected exception's
message can contain a file path or a fragment of the model bundle, and a private contract is still not
a place to leak the server's internals.
"""

from __future__ import annotations

from dataclasses import replace
import logging
import time
from typing import Callable, NoReturn, TypeVar
import uuid

import grpc

from crypto_signal_engine.application.bot_advisor import BotAdvisorService
from crypto_signal_engine.application.errors import (
    InvalidInferenceRequest,
    ModelUnavailable,
)
from crypto_signal_engine.application.online_service import (
    OnlineLearningService,
    TradeOutcomeInput,
)
from crypto_signal_engine.application.signal_service import SignalService
from crypto_signal_engine.contracts.v1 import ml_engine_pb2_grpc
from crypto_signal_engine.transport.grpc import mappers


logger = logging.getLogger(__name__)
SERVICE_NAME = "crypto_signal.ml.v1.MlEngineService"

Response = TypeVar("Response")
Request = TypeVar("Request")


def _request_id(value: str) -> str:
    """The caller's correlation id, or a fresh one.

    Generated rather than left blank so that every log line and every response can be joined back to a
    request. .NET always sends one; `grpcurl` and the health prober do not.
    """
    normalised = value.strip()
    return normalised if normalised else str(uuid.uuid4())


class MlEngineServicer(ml_engine_pb2_grpc.MlEngineServiceServicer):
    def __init__(
        self,
        signals: SignalService,
        advisor: BotAdvisorService,
        online: OnlineLearningService | None = None,
    ) -> None:
        self._signals = signals
        self._advisor = advisor
        self._online = online

    def GetCapabilities(self, request, context):
        request_id = _request_id(request.request_id)
        return self._dispatch(
            "GetCapabilities",
            request_id,
            context,
            lambda: mappers.capabilities_to_proto(self._signals.get_capabilities(request_id)),
        )

    def GetModelInfo(self, request, context):
        request_id = _request_id(request.request_id)
        return self._dispatch(
            "GetModelInfo",
            request_id,
            context,
            lambda: mappers.model_info_to_proto(
                self._signals.get_model_info(
                    request_id=request_id,
                    symbol=request.symbol,
                    interval=request.interval,
                )
            ),
        )

    def GetSignal(self, request, context):
        request_id = _request_id(request.request_id)

        def work():
            # `_with_request_id` substitutes only the correlation id. Everything else is the caller's
            # request verbatim — in particular the candle tuple, which the audit digest is computed over
            # and which nothing between parsing and hashing may touch.
            parsed = _with_request_id(mappers.signal_request_from_proto(request), request_id)
            return mappers.signal_to_proto(self._signals.get_signal(parsed))

        return self._dispatch("GetSignal", request_id, context, work)

    def EvaluateBotDecision(self, request, context):
        request_id = _request_id(request.request_id)

        def work():
            parsed = _with_request_id(mappers.bot_decision_request_from_proto(request), request_id)
            return mappers.bot_decision_to_proto(self._advisor.evaluate(parsed))

        return self._dispatch("EvaluateBotDecision", request_id, context, work)

    def RecordTradeOutcome(self, request, context):
        request_id = _request_id(request.request_id)

        def work():
            if self._online is None:
                return mappers.trade_outcome_to_proto(
                    request_id,
                    "rejected: online learning is not configured on this engine",
                    0,
                    False,
                )
            parsed = TradeOutcomeInput(
                request_id=request_id,
                bot_id=request.bot_id,
                symbol=request.symbol,
                interval=request.interval,
                model_id=request.model_id,
                model_version=request.model_version,
                direction=mappers.trade_direction_name(request.direction),
                candles=tuple(
                    {
                        "open_time": c.open_time.ToDatetime().isoformat(),
                        "open": c.open,
                        "high": c.high,
                        "low": c.low,
                        "close": c.close,
                        "volume": c.volume,
                    }
                    for c in request.candles
                ),
                take_profit_percent=request.take_profit_percent,
                stop_loss_percent=request.stop_loss_percent,
                close_reason=request.close_reason,
                realized_pnl=request.realized_pnl,
                bars_held=request.bars_held,
                decision_candle_open_time=(
                    request.decision_candle_open_time.ToDatetime().isoformat()
                    if request.HasField("decision_candle_open_time")
                    else ""
                ),
                closed_at=(
                    request.closed_at.ToDatetime().isoformat()
                    if request.HasField("closed_at")
                    else ""
                ),
            )
            result = self._online.record_trade_outcome(parsed)
            return mappers.trade_outcome_to_proto(
                result.request_id,
                result.status,
                result.samples_stored,
                result.training_triggered,
            )

        return self._dispatch("RecordTradeOutcome", request_id, context, work)

    def GetTrainingStatus(self, request, context):
        request_id = _request_id(request.request_id)

        def work():
            if self._online is None:
                return mappers.training_status_to_proto(request_id, False, ())
            result = self._online.training_status(
                request_id,
                symbols=tuple(request.symbols),
                intervals=tuple(request.intervals),
            )
            return mappers.training_status_to_proto(
                result.request_id,
                result.online_learning_enabled,
                result.markets,
            )

        return self._dispatch("GetTrainingStatus", request_id, context, work)

    def ScanSymbols(self, request, context):
        request_id = _request_id(request.request_id)

        def work():
            from crypto_signal_engine.application.scan_service import (
                ScanRequest,
                ScanService,
            )
            svc = ScanService()
            symbols = tuple(
                (msg.symbol, tuple(mappers.candles_from_proto(msg.candles)))
                for msg in request.symbols
            )
            strategies = tuple(
                (spec.name, spec.take_profit_atr, spec.stop_loss_atr)
                for spec in request.strategies
            )
            parsed = ScanRequest(
                request_id=request_id,
                interval=request.interval,
                symbols=symbols,
                strategies=strategies,
            )
            result = svc.scan(parsed)
            return mappers.scan_symbols_response_to_proto(
                result.request_id, result.results, result.warning
            )

        return self._dispatch("ScanSymbols", request_id, context, work)

    # ── error handling ────────────────────────────────────────────────────────────

    def _dispatch(
        self,
        method: str,
        request_id: str,
        context,
        work: Callable[[], Response],
    ) -> Response:
        """Run one RPC's body under the single error policy documented at the top of this module.

        A callable rather than a context manager so there is no question about what the RPC returns on
        the failure paths: `_abort` never returns, and every success path returns `work()`.
        """
        started = time.perf_counter()
        try:
            result = work()
        except (InvalidInferenceRequest, ValueError) as error:
            self._abort(context, grpc.StatusCode.INVALID_ARGUMENT, str(error), method, request_id)
        except ModelUnavailable as error:
            self._abort(context, grpc.StatusCode.FAILED_PRECONDITION, str(error), method, request_id)
        except Exception:
            logger.exception(
                "Unhandled ML engine failure",
                extra={"request_id": request_id, "rpc_method": method, "status": "INTERNAL"},
            )
            self._abort(
                context,
                grpc.StatusCode.INTERNAL,
                "The ML engine could not complete the request",
                method,
                request_id,
            )
        logger.info(
            "gRPC request completed",
            extra={
                "request_id": request_id,
                "rpc_method": method,
                "status": "OK",
                "duration_ms": round((time.perf_counter() - started) * 1_000, 3),
            },
        )
        return result

    @staticmethod
    def _abort(
        context,
        status: grpc.StatusCode,
        detail: str,
        method: str,
        request_id: str,
    ) -> NoReturn:
        logger.warning(
            "gRPC request rejected",
            extra={
                "request_id": request_id or "missing",
                "rpc_method": method,
                "status": status.name,
                "detail": detail,
            },
        )
        context.abort(status, detail)
        # Unreachable: `abort` raises. Present so a reader — and a type checker — can see that this
        # function never falls through to a caller expecting a response.
        raise AssertionError("grpc context.abort did not raise")


def _with_request_id(request: Request, request_id: str) -> Request:
    """The same request carrying a non-empty correlation id.

    `dataclasses.replace` rather than mutation because the request shapes are frozen, which is itself
    deliberate: the candle tuple is what the audit digest is computed over.
    """
    return replace(request, request_id=request_id)


__all__ = ["SERVICE_NAME", "MlEngineServicer"]
