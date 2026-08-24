"""Writing a training run's artifacts to disk.

Extracted so both pipelines share one serializer. A `metadata.json` whose numbers are formatted one way
by the legacy run and another way by the barrier run is a file two readers disagree about, and the
readers here are a human comparing reports and a program parsing them.
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..log_setup import get_logger

logger = get_logger(__name__)


def json_default(value: Any) -> Any:
    """Serialize the handful of non-JSON types a training run produces, and refuse the rest.

    Refusing rather than falling back on `str()` is deliberate: a silent stringification is how a numpy
    array ends up in `metadata.json` as `"[0.1 0.2 ...]"`, which parses as a string forever after.
    """
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=json_default),
        encoding="utf-8",
    )
    logger.debug("JSON artifact written | path=%s", path)


def write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    logger.debug("Text artifact written | path=%s", path)
