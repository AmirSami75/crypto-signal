from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
from pathlib import Path
from threading import RLock
from typing import Any

import joblib

from crypto_signal_engine.application.errors import ModelUnavailable
from crypto_signal_engine.application.models import ModelInfo


@dataclass(frozen=True, slots=True)
class ModelSnapshot:
    model: Any
    feature_columns: tuple[str, ...]
    info: ModelInfo


class JoblibModelRepository:
    """Loads and validates one immutable production model bundle."""

    def __init__(self, artifact_path: Path) -> None:
        self._artifact_path = artifact_path
        self._lock = RLock()
        self._snapshot: ModelSnapshot | None = None

    @property
    def is_ready(self) -> bool:
        return self._snapshot is not None

    def load(self) -> ModelInfo:
        if not self._artifact_path.is_file():
            raise ModelUnavailable(f"Model artifact not found: {self._artifact_path}")

        try:
            bundle = joblib.load(self._artifact_path)
            model = bundle["model"]
            feature_columns = tuple(str(item) for item in bundle["feature_columns"])
            metadata = bundle["metadata"]
            trained_at = datetime.fromisoformat(str(metadata["trained_at_utc"]))
            symbol = str(metadata["symbol"]).upper()
            interval = str(metadata["interval"])
            probability_threshold = float(
                metadata["config"]["model"]["probability_threshold"]
            )
            sell_semantics = str(metadata["sell_semantics"])
            project_version = str(metadata.get("project_version", "unknown"))
        except (KeyError, TypeError, ValueError, OSError) as exc:
            raise ModelUnavailable("The model artifact is invalid or incomplete") from exc

        if not feature_columns or not hasattr(model, "predict_proba"):
            raise ModelUnavailable("The model artifact cannot serve probability inference")

        digest = hashlib.sha256(self._artifact_path.read_bytes()).hexdigest()
        info = ModelInfo(
            model_id=f"{symbol}:{interval}",
            model_version=digest,
            project_version=project_version,
            symbol=symbol,
            interval=interval,
            trained_at=trained_at,
            feature_count=len(feature_columns),
            probability_threshold=probability_threshold,
            sell_semantics=sell_semantics,
        )
        with self._lock:
            self._snapshot = ModelSnapshot(model, feature_columns, info)
        return info

    def snapshot(self) -> ModelSnapshot:
        with self._lock:
            if self._snapshot is None:
                raise ModelUnavailable("No production model is loaded")
            return self._snapshot

    def run_prediction(self, features: Any) -> Any:
        """Serialize model access to avoid estimator-specific thread-safety assumptions."""
        with self._lock:
            if self._snapshot is None:
                raise ModelUnavailable("No production model is loaded")
            return self._snapshot.model.predict_proba(features)
