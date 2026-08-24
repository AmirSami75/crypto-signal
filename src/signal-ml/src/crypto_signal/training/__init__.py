"""End-to-end training orchestration: download, label, validate, fit, report, persist.

Two pipelines live here and they answer different questions.

`barrier_pipeline` is the one that ships. It trains the barrier-conditional model the engine serves:
every row carries its own take-profit and stop-loss distance as features, so one artifact answers any
requested bracket, on either side of the market.

`pipeline` is the original close-to-close model — "will the next six candles move more than 0.35%" —
kept because its report is the historical baseline the barrier work is measured against. It writes into
`artifacts/legacy/` so the two runs cannot overwrite each other's reports, and nothing serves it.
"""

from .artifacts import json_default, write_json, write_text
from .barrier_pipeline import (
    POOLED_STEM,
    TrainedBundle,
    download_barrier_candles,
    download_barrier_data,
    latest_barrier_signal,
    train_barrier_model,
)
from .pipeline import SIGNAL_NAMES, download_data, latest_signal, train_and_backtest

__all__ = [
    "POOLED_STEM",
    "SIGNAL_NAMES",
    "TrainedBundle",
    "download_barrier_candles",
    "download_barrier_data",
    "download_data",
    "json_default",
    "latest_barrier_signal",
    "latest_signal",
    "train_and_backtest",
    "train_barrier_model",
    "write_json",
    "write_text",
]
