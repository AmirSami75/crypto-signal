"""Vocabulary shared by training, evaluation and serving.

Nothing in here imports from the training or serving layers, and nothing in here touches disk or the
network. It exists so that the labeller, the backtester and the gRPC servicer cannot quietly disagree
about what "take-profit was reached first" means — a disagreement that shows up as a model that looks
profitable in the report and loses money in the market.
"""

from .barriers import (
    ADVERSE_WINS_TIE_BREAK,
    BarrierPair,
    Outcome,
    OUTCOME_CLASSES,
    TouchResult,
    first_touch,
    resolve_first_touch,
    resolve_first_touch_scalar,
)
from .direction import Direction, direction_from_wire, direction_to_wire
from .expectancy import (
    OutcomeProbabilities,
    PROBABILITY_TOLERANCE,
    break_even_win_rate,
    expected_value,
)
from .levels import (
    TradeLevels,
    atr_multiple,
    barrier_prices,
    barrier_prices_from_atr,
    levels_for,
    percent_from_atr,
)
from .money import format_decimal, parse_decimal, parse_money, quantize

__all__ = [
    "ADVERSE_WINS_TIE_BREAK",
    "BarrierPair",
    "Direction",
    "OUTCOME_CLASSES",
    "Outcome",
    "OutcomeProbabilities",
    "PROBABILITY_TOLERANCE",
    "TouchResult",
    "TradeLevels",
    "atr_multiple",
    "barrier_prices",
    "barrier_prices_from_atr",
    "break_even_win_rate",
    "direction_from_wire",
    "direction_to_wire",
    "expected_value",
    "first_touch",
    "format_decimal",
    "levels_for",
    "parse_decimal",
    "parse_money",
    "percent_from_atr",
    "quantize",
    "resolve_first_touch",
    "resolve_first_touch_scalar",
]
