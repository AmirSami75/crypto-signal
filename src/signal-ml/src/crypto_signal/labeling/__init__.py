"""Turning candles into the thing a model can be trained against.

Two labellers live here, and they answer different questions:

- `triple_barrier` answers "for this bracket order, did the take-profit or the stop-loss come first?"
  This is what the barrier-conditional model is trained on, because it is the question a bot placing a
  bracket actually asks.
- `horizon_return` answers "did the close move more than a fixed threshold over a fixed horizon?" It is
  the legacy label, kept so the new model has an existing report to be compared against.
"""

from .horizon_return import build_horizon_dataset, label_horizon_return
from .triple_barrier import (
    BARRIER_FEATURE_COLUMNS,
    BARRIER_GRID_ATR,
    CONTEXT_COLUMNS,
    DEFAULT_MAX_HORIZON,
    DEFAULT_PAIRS_PER_CANDLE,
    LABEL_COLUMN,
    MAX_RISK_REWARD,
    MIN_RISK_REWARD,
    TIME_COLUMN,
    BarrierDataset,
    BarrierLabels,
    barrier_grid,
    build_barrier_dataset,
    label_triple_barrier,
    sample_barrier_pairs,
)

__all__ = [
    "BARRIER_FEATURE_COLUMNS",
    "BARRIER_GRID_ATR",
    "CONTEXT_COLUMNS",
    "DEFAULT_MAX_HORIZON",
    "DEFAULT_PAIRS_PER_CANDLE",
    "LABEL_COLUMN",
    "MAX_RISK_REWARD",
    "MIN_RISK_REWARD",
    "TIME_COLUMN",
    "BarrierDataset",
    "BarrierLabels",
    "barrier_grid",
    "build_barrier_dataset",
    "build_horizon_dataset",
    "label_horizon_return",
    "label_triple_barrier",
    "sample_barrier_pairs",
]
