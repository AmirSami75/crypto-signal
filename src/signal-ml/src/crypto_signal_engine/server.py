"""Process entry point: settings in, a listening gRPC server out.

Composition happens here and only here. The registry, the evaluator and the two application services
are constructed once and shared across every worker thread, which is safe because none of them holds
per-request state — the registry serialises inference behind a per-model lock, and everything above it
is a pure function of the request.

The one judgement call worth naming: **a start-up with no servable model is a warning, not a crash.**
It is tempting to refuse to boot, but the model directory is a mounted volume and the orchestrator
retries a failed container: a crash-loop turns "the artifact has not been copied in yet" into a service
that is never reachable long enough for anyone to copy it in. Instead the server comes up, reports an
empty inventory, answers `GetCapabilities` honestly, and fails individual requests with
FAILED_PRECONDITION until an artifact appears. Resolution reads the directory per request, so nothing
needs restarting once one does.
"""

from __future__ import annotations

from concurrent import futures
import logging
import os
import signal
from threading import Event

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from grpc_reflection.v1alpha import reflection

from crypto_signal_engine import __version__
from crypto_signal_engine.application.bot_advisor import BotAdvisorService
from crypto_signal_engine.application.evaluator import MarketEvaluator
from crypto_signal_engine.application.online_learning import OnlineTrainer, TradeSampleStore
from crypto_signal_engine.application.online_service import OnlineLearningService
from crypto_signal_engine.application.signal_service import SignalService
from crypto_signal_engine.contracts.v1 import ml_engine_pb2, ml_engine_pb2_grpc
from crypto_signal_engine.infrastructure.model_registry import ModelRegistry
from crypto_signal_engine.log_setup import configure_logging
from crypto_signal_engine.settings import EngineSettings
from crypto_signal_engine.transport.grpc.servicer import MlEngineServicer, SERVICE_NAME


logger = logging.getLogger(__name__)


def build_services(
    settings: EngineSettings,
) -> tuple[ModelRegistry, SignalService, BotAdvisorService, OnlineLearningService | None]:
    """The application layer, wired to the model registry.

    Returns the three objects it composed rather than assembled inline, so a test can drive the services
    directly without binding a port. The registry comes back too — start-up logging needs it, and
    reaching it through `service._evaluator._registry` would make two layers of encapsulation notional.
    The online-learning service comes back None when `ML_ONLINE_LEARNING` is unset/false: an operator
    who has not opted in gets no sample store and no trainer threads, exactly as before this existed.
    """
    registry = ModelRegistry(settings.model_directory, single_artifact=settings.model_path)
    evaluator = MarketEvaluator(
        registry,
        minimum_candles=settings.minimum_candles,
        maximum_candles=settings.maximum_candles,
        default_max_holding_periods=settings.default_max_holding_periods,
        default_minimum_confidence=settings.minimum_confidence,
        barrier_atr_bounds=settings.barrier_atr_bounds,
    )
    signals = SignalService(
        evaluator,
        service_name=SERVICE_NAME,
        service_version=__version__,
        operating_mode=settings.operating_mode,
    )
    advisor = BotAdvisorService(evaluator)

    online: OnlineLearningService | None = None
    if settings.online_learning_enabled:
        store = TradeSampleStore(settings.trade_samples_path)

        def _load_engine_config():
            """The engine's own training config, from the same source the batch pipeline uses."""
            from crypto_signal.config import load_config

            config_path = os.getenv("ML_TRAINING_CONFIG", "config.toml")
            return load_config(config_path)

        trainer = OnlineTrainer(
            store,
            model_dir=settings.model_directory,
            config_loader=_load_engine_config,
            sequence_builder=None,  # built lazily inside `_train_market`; kept for testability
            trainer=None,           # ditto — the trainer imports its own model code lazily
            min_samples=settings.online_training_min_samples,
            sample_weight=settings.online_training_sample_weight,
        )
        online = OnlineLearningService(store, trainer, enabled=True)
        logger.info(
            "Online learning enabled | samples=%s | min_samples=%s",
            settings.trade_samples_path,
            settings.online_training_min_samples,
        )

    return registry, signals, advisor, online


def _log_inventory(registry: ModelRegistry) -> None:
    """Report what the engine can actually answer for, before the first request asks.

    `available()` loads every artifact, so this doubles as an eager validation pass: a bundle whose
    metadata is wrong is named at start-up rather than at 3am on the request that needed it. Rejections
    are logged at WARNING by the registry itself; the count is repeated here so a healthy line and a
    degraded one are distinguishable at a glance.
    """
    descriptors = registry.available()
    rejected = registry.rejections()
    if not descriptors:
        logger.warning(
            "No servable model | directory=%s | rejected=%s | "
            "signal requests will fail with FAILED_PRECONDITION until an artifact appears",
            registry.directory,
            len(rejected),
        )
        return

    logger.info(
        "Model inventory | servable=%s | rejected=%s | directory=%s",
        len(descriptors),
        len(rejected),
        registry.directory,
    )
    for descriptor in descriptors:
        # A pooled bundle covers every symbol, so listing its training set would misreport its reach;
        # "*" is what `GetCapabilities` says and what the log should say too.
        coverage = "*" if descriptor.is_pooled else ",".join(descriptor.symbols)
        logger.info(
            "  %s %s | model=%s | version=%s | features=%s | atr_window=%s | max_horizon=%s | "
            "calibration=%s | trained=%s",
            coverage,
            descriptor.interval,
            descriptor.model_id,
            descriptor.model_version[:12],
            descriptor.feature_count,
            descriptor.atr_window,
            descriptor.max_horizon,
            descriptor.calibration_method or "unrecorded",
            descriptor.trained_at.date().isoformat(),
        )


def build_server(settings: EngineSettings) -> tuple[grpc.Server, health.HealthServicer]:
    registry, signals, advisor, online = build_services(settings)
    options = (
        ("grpc.max_receive_message_length", settings.max_receive_message_mb * 1_048_576),
        ("grpc.max_send_message_length", settings.max_send_message_mb * 1_048_576),
        ("grpc.so_reuseport", 1),
    )
    server = grpc.server(
        futures.ThreadPoolExecutor(
            max_workers=settings.workers,
            thread_name_prefix="ml-grpc",
        ),
        options=options,
    )
    ml_engine_pb2_grpc.add_MlEngineServiceServicer_to_server(
        MlEngineServicer(signals, advisor, online),
        server,
    )
    health_service = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_service, server)
    health_service.set("", health_pb2.HealthCheckResponse.SERVING)
    health_service.set(SERVICE_NAME, health_pb2.HealthCheckResponse.SERVING)

    if settings.enable_reflection:
        reflection.enable_server_reflection(
            (
                SERVICE_NAME,
                health.SERVICE_NAME,
                reflection.SERVICE_NAME,
            ),
            server,
        )

    address = f"{settings.host}:{settings.port}"
    if settings.tls_certificate_path is None:
        bound_port = server.add_insecure_port(address)
        transport = "h2c"
    else:
        private_key = settings.tls_private_key_path.read_bytes()
        certificate = settings.tls_certificate_path.read_bytes()
        root_certificates = (
            settings.tls_client_ca_path.read_bytes()
            if settings.tls_client_ca_path is not None
            else None
        )
        credentials = grpc.ssl_server_credentials(
            ((private_key, certificate),),
            root_certificates=root_certificates,
            require_client_auth=root_certificates is not None,
        )
        bound_port = server.add_secure_port(address, credentials)
        transport = "tls"
    if bound_port == 0:
        raise RuntimeError(f"Unable to bind the gRPC server to {address}")

    logger.info(
        "ML engine initialized",
        extra={
            "status": "READY",
            "request_id": "startup",
            "rpc_method": SERVICE_NAME,
        },
    )
    # The operating mode is on the start-up line because every record the orchestrator writes is bound
    # to one, and "which mode is this process serving" is the first question asked of a surprising fill.
    logger.info(
        "ML engine serving | version=%s | mode=%s | transport=%s | workers=%s",
        __version__,
        settings.operating_mode,
        transport,
        settings.workers,
    )
    _log_inventory(registry)
    return server, health_service


def serve(settings: EngineSettings) -> None:
    server, health_service = build_server(settings)
    stopped = Event()

    def request_shutdown(signum, _frame) -> None:
        logger.info("Shutdown requested by signal %s", signum)
        stopped.set()

    for signal_name in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signal_name, request_shutdown)

    server.start()
    logger.info("ML gRPC server listening on %s:%s", settings.host, settings.port)
    stopped.wait()
    health_service.set("", health_pb2.HealthCheckResponse.NOT_SERVING)
    health_service.set(SERVICE_NAME, health_pb2.HealthCheckResponse.NOT_SERVING)
    server.stop(settings.shutdown_grace_seconds).wait()
    logger.info("ML gRPC server stopped")


def main() -> None:
    settings = EngineSettings.from_environment()
    configure_logging(settings.log_level, settings.log_format)
    serve(settings)


if __name__ == "__main__":
    main()
