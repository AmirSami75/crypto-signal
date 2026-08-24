"""Scale-free feature construction, shared by training and serving.

Both sides import `build_features` from here, because a feature computed one way at training time and
another way at serving time is the most expensive kind of bug in this system: the model is fine, the
data is fine, and the predictions are quietly wrong.
"""

from .builder import LONGEST_WINDOW, WARMUP_COLUMNS, FeatureFrame, build_features
from .indicators import (
    average_true_range,
    bollinger_z_score,
    relative_strength_index,
    stochastic_position,
)

__all__ = [
    "FeatureFrame",
    "LONGEST_WINDOW",
    "WARMUP_COLUMNS",
    "average_true_range",
    "bollinger_z_score",
    "build_features",
    "relative_strength_index",
    "stochastic_position",
]
