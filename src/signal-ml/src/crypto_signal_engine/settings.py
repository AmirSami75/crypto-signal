from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


def _integer(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _boolean(name: str, default: bool) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def _optional_path(name: str) -> Path | None:
    raw = os.getenv(name, "").strip()
    return Path(raw).resolve() if raw else None


@dataclass(frozen=True, slots=True)
class EngineSettings:
    environment: str
    operating_mode: str
    host: str
    port: int
    workers: int
    shutdown_grace_seconds: int
    model_path: Path
    minimum_candles: int
    maximum_candles: int
    max_receive_message_mb: int
    max_send_message_mb: int
    enable_reflection: bool
    log_level: str
    log_format: str
    tls_certificate_path: Path | None
    tls_private_key_path: Path | None
    tls_client_ca_path: Path | None

    @classmethod
    def from_environment(cls) -> EngineSettings:
        environment = os.getenv("ML_ENVIRONMENT", "production").strip().lower()
        operating_mode = os.getenv("OPERATING_MODE", "PAPER").strip().upper()
        if operating_mode not in {"PAPER", "LIVE"}:
            raise ValueError("OPERATING_MODE must be PAPER or LIVE")

        log_level = os.getenv("ML_LOG_LEVEL", "INFO").strip().upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("ML_LOG_LEVEL is invalid")

        log_format = os.getenv("ML_LOG_FORMAT", "json").strip().lower()
        if log_format not in {"json", "text"}:
            raise ValueError("ML_LOG_FORMAT must be json or text")

        certificate = _optional_path("ML_TLS_CERTIFICATE_PATH")
        private_key = _optional_path("ML_TLS_PRIVATE_KEY_PATH")
        client_ca = _optional_path("ML_TLS_CLIENT_CA_PATH")
        if (certificate is None) != (private_key is None):
            raise ValueError(
                "ML_TLS_CERTIFICATE_PATH and ML_TLS_PRIVATE_KEY_PATH must be set together"
            )
        if client_ca is not None and certificate is None:
            raise ValueError("A server certificate is required when client CA is configured")

        minimum_candles = _integer("ML_MINIMUM_CANDLES", 169, 169, 10_000)
        maximum_candles = _integer("ML_MAXIMUM_CANDLES", 2_000, minimum_candles, 100_000)

        return cls(
            environment=environment,
            operating_mode=operating_mode,
            host=os.getenv("ML_GRPC_HOST", "0.0.0.0").strip(),
            port=_integer("ML_GRPC_PORT", 50051, 1, 65_535),
            workers=_integer("ML_GRPC_WORKERS", 8, 1, 128),
            shutdown_grace_seconds=_integer("ML_SHUTDOWN_GRACE_SECONDS", 20, 0, 300),
            model_path=Path(
                os.getenv("ML_MODEL_PATH", "artifacts/model.joblib")
            ).resolve(),
            minimum_candles=minimum_candles,
            maximum_candles=maximum_candles,
            max_receive_message_mb=_integer("ML_MAX_RECEIVE_MESSAGE_MB", 16, 1, 256),
            max_send_message_mb=_integer("ML_MAX_SEND_MESSAGE_MB", 4, 1, 256),
            enable_reflection=_boolean(
                "ML_ENABLE_REFLECTION", environment == "development"
            ),
            log_level=log_level,
            log_format=log_format,
            tls_certificate_path=certificate,
            tls_private_key_path=private_key,
            tls_client_ca_path=client_ca,
        )
