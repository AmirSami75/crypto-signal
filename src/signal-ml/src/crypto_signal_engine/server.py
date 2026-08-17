from __future__ import annotations

from concurrent import futures
import logging
import signal
from threading import Event

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from grpc_reflection.v1alpha import reflection

from crypto_signal_engine.application.inference import InferenceService
from crypto_signal_engine.contracts.v1 import ml_engine_pb2, ml_engine_pb2_grpc
from crypto_signal_engine.infrastructure.model_repository import JoblibModelRepository
from crypto_signal_engine.logging import configure_logging
from crypto_signal_engine.settings import EngineSettings
from crypto_signal_engine.transport.grpc.servicer import MlEngineServicer, SERVICE_NAME


logger = logging.getLogger(__name__)


def build_server(settings: EngineSettings) -> tuple[grpc.Server, health.HealthServicer]:
    repository = JoblibModelRepository(settings.model_path)
    model_info = repository.load()
    inference = InferenceService(
        repository,
        minimum_candles=settings.minimum_candles,
        maximum_candles=settings.maximum_candles,
    )
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
        MlEngineServicer(
            inference,
            minimum_candles=settings.minimum_candles,
            maximum_candles=settings.maximum_candles,
        ),
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
    logger.info(
        "Loaded production model %s version=%s symbol=%s interval=%s transport=%s",
        model_info.model_id,
        model_info.model_version[:12],
        model_info.symbol,
        model_info.interval,
        transport,
    )
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
