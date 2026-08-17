from __future__ import annotations

import os

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc

from crypto_signal_engine.transport.grpc.servicer import SERVICE_NAME


def main() -> None:
    host = os.getenv("ML_HEALTHCHECK_HOST", "127.0.0.1")
    port = os.getenv("ML_GRPC_PORT", "50051")
    timeout = float(os.getenv("ML_HEALTHCHECK_TIMEOUT_SECONDS", "3"))
    with grpc.insecure_channel(f"{host}:{port}") as channel:
        response = health_pb2_grpc.HealthStub(channel).Check(
            health_pb2.HealthCheckRequest(service=SERVICE_NAME),
            timeout=timeout,
        )
    if response.status != health_pb2.HealthCheckResponse.SERVING:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
