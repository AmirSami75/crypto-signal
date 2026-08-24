"""Estimator construction, leakage-aware validation, calibration and direction selection."""

from .calibration import (
    CalibrationReport,
    ConfidenceReach,
    DEFAULT_BINS,
    DEFAULT_BLOCKS,
    ReliabilityCurve,
    fit_calibrated_model,
    measure_confidence_reach,
    reliability_curve,
)
from .direction import (
    DirectionCandidate,
    DirectionChoice,
    barrier_variants,
    choose_direction,
)
from .estimator import (
    ALL_CLASSES,
    aligned_probabilities,
    build_model,
    classification_metrics,
    fit_model,
    probabilities_to_signals,
    walk_forward_validation,
    walk_forward_validation_by_time,
)
from .splitting import TimeGroupedSplit, candles_between, chronological_blocks

__all__ = [
    "ALL_CLASSES",
    "CalibrationReport",
    "ConfidenceReach",
    "DEFAULT_BINS",
    "DEFAULT_BLOCKS",
    "DirectionCandidate",
    "DirectionChoice",
    "ReliabilityCurve",
    "TimeGroupedSplit",
    "aligned_probabilities",
    "barrier_variants",
    "build_model",
    "candles_between",
    "choose_direction",
    "chronological_blocks",
    "classification_metrics",
    "fit_calibrated_model",
    "fit_model",
    "measure_confidence_reach",
    "probabilities_to_signals",
    "reliability_curve",
    "walk_forward_validation",
    "walk_forward_validation_by_time",
]
