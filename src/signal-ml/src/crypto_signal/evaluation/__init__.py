"""Simulating what a set of signals would actually have earned.

`close_to_close` is the original position-based simulator, kept for the legacy report.
`bracket` walks the intrabar path against a take-profit and stop-loss, which is what the bot really
places, and shares its first-touch rule with the labeller through `crypto_signal.domain.barriers`.
"""

from .bracket import BracketCosts, run_bracket_backtest
from .close_to_close import performance_metrics, run_backtest, signals_to_positions

__all__ = [
    "BracketCosts",
    "performance_metrics",
    "run_backtest",
    "run_bracket_backtest",
    "signals_to_positions",
]
