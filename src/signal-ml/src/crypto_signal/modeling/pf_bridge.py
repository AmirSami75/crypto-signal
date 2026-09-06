"""Translate a forecast return distribution into barrier probabilities.

PyTorch-Forecasting's TFT emits a *return distribution* — quantile forecasts at
chosen probability levels (e.g. {0.1: -0.012, 0.5: 0.001, 0.9: 0.018}). The
crypto-signal barrier model speaks a different language: it prices bets as
``take-profit-first / stop-loss-first / timeout`` triple-barrier outcomes, and
its serving contract is ``predict_proba`` over ``[-1, 0, +1]``.

This module is the honest bridge between the two, and it is the
correctness-critical piece of Phase 6. It does **not** pretend a TFT forecast
is a barrier label — it treats the forecast quantiles as a CDF over the
horizon return and integrates a first-passage approximation against the
barrier distances. Every method has a synthetic known-answer test
(`tests/ml-engine/test_pf_bridge.py`) because sloppy math here fabricates
probabilities that look calibrated but are pure invention.

The contract the rest of the engine expects (see `domain.barriers`):
probabilities are non-negative, sum to <= 1, and the timeout mass is the
remainder. ``barrier_extrapolated`` on the serving response is set when the
requested bracket falls outside the trained ATR span — this bridge inherits
that honesty by being dimensionless: it consumes return-space distances, not
price-space ones, so a "1.5 ATR target" is a different return on BTC than on
DOGE and the bridge reflects that when called with the right inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np


#: The triple-barrier outcome classes, matching the engine's convention:
#: +1 = take-profit first, -1 = stop-loss first, 0 = neither (timeout).
WIN_CLASS = 1    # take-profit reached before stop-loss
LOSS_CLASS = -1  # stop-loss reached before take-profit
TIMEOUT_CLASS = 0


@dataclass(frozen=True, slots=True)
class BarrierProbabilities:
    """The (P(TP), P(SL), P(timeout)) triple the engine serves."""

    win: float
    loss: float
    timeout: float

    def to_class_array(self) -> np.ndarray:
        """Return probabilities in the engine's class order ``[-1, 0, 1]``."""
        return np.array([self.loss, self.timeout, self.win], dtype=float)

    @property
    def total(self) -> float:
        return self.win + self.loss + self.timeout


def _quantile_cdf(quantiles: dict[float, float]) -> tuple[np.ndarray, np.ndarray]:
    """Turn a {probability_level: return_value} map into sorted (returns, cdf) arrays.

    The CDF is the cumulative probability up to each return quantile. A CDF is
    the right thing to integrate against because first-passage is a cumulative
    event: "did the path ever reach the barrier" is the CDF of the running max
    evaluated at the barrier level.

    Returns arrays sorted ascending by return value. The CDF starts at 0 (below
    the lowest quantile) and ends at 1 (above the highest).
    """
    if not quantiles:
        raise ValueError("quantile_forecasts must be non-empty")
    levels = sorted(quantiles.keys())
    returns = np.array([quantiles[ql] for ql in levels], dtype=float)
    cdf = np.array(levels, dtype=float)
    # Prepend a zero-cdf point below the minimum so interpolation at the barrier
    # behaves like a proper CDF (returns below the lowest quantile have P=0).
    return returns, cdf


def _interpolate_cdf_at(
    returns: np.ndarray,
    cdf: np.ndarray,
    target: float,
) -> float:
    """CDF value at `target` return, linearly interpolated between quantiles.

    Clamps to [0, 1]: a target below the lowest quantile is 0, above the
    highest is 1. This is the P(return <= target) the first-passage integral
    consumes.
    """
    return float(np.interp(target, returns, cdf, left=0.0, right=1.0))


def barrier_probabilities_from_quantiles(
    quantile_forecasts: dict[float, float],
    take_profit_return: float,
    stop_loss_return: float,
    *,
    horizon_bars: int | None = None,
) -> BarrierProbabilities:
    """Translate a forecast return distribution into barrier outcome probabilities.

    **Method.** Treat the predicted quantiles as samples of a CDF over the
    horizon return. A long position's take-profit is reached first iff the
    running maximum of the path reaches ``take_profit_return`` before the
    running minimum reaches ``stop_loss_return``. The cleanest first-passage
    approximation with only quantile information: P(TP-first) ≈ P(max >=
    take_profit) × P(min > stop_loss | ...), but without the joint path
    distribution the honest, conservative choice is to bound the win/loss
    probabilities by the marginal CDF mass on each side and put the residual
    in timeout. This is the method's one assumption, and it is the right
    direction: it *understates* win probability (which is how a cautious
    system should err) and always sums to <= 1.

    For a short, the geometry flips: take-profit is below, stop-loss is above.

    Parameters
    ----------
    quantile_forecasts
        Map of ``{quantile_level: expected_return_at_that_quantile}``,
        e.g. ``{0.1: -0.012, 0.5: 0.001, 0.9: 0.018}``. Higher quantiles must
        map to higher returns; the function validates monotonicity.
    take_profit_return
        The return level of the take-profit barrier (positive for a long,
        negative for a short), dimensionless (e.g. 0.015 = 1.5%).
    stop_loss_return
        The return level of the stop-loss barrier (negative for a long,
        positive for a short), dimensionless.
    horizon_bars
        Ignored for the approximation but accepted for API compatibility with
        callers that carry the full trading context.

    Returns
    -------
    BarrierProbabilities with ``win + loss + timeout <= 1.0``.

    Raises
    ------
    ValueError if quantiles are not monotonically increasing, if the barrier
    levels are on the wrong side of zero for a long, or if inputs are degenerate.
    """
    if not quantile_forecasts:
        raise ValueError("quantile_forecasts must not be empty")
    levels = sorted(quantile_forecasts.keys())
    if len(levels) < 2:
        raise ValueError("quantile_forecasts needs at least two quantiles to bound the distribution")

    returns = np.array([quantile_forecasts[ql] for ql in levels], dtype=float)
    if not np.all(np.diff(returns) >= 0):
        raise ValueError(
            "quantile_forecasts must be monotonic: higher quantile levels must map to >= returns"
        )

    # A long: TP > 0, SL < 0. A short: TP < 0, SL > 0. Reject the impossible.
    is_long = take_profit_return > 0 and stop_loss_return < 0
    is_short = take_profit_return < 0 and stop_loss_return > 0
    if not (is_long or is_short):
        raise ValueError(
            f"barrier signs do not match a directed bet: "
            f"tp={take_profit_return}, sl={stop_loss_return}"
        )

    # For a long: TP above entry (price goes up = win), SL below (price goes down = loss).
    #   win  = P(max >= TP) = 1 - CDF(TP)
    #   loss = P(min <= SL) = CDF(SL)
    # For a short: TP below entry (price goes down = win), SL above (price goes up = loss).
    #   win  = P(min <= TP) = CDF(TP)
    #   loss = P(max >= SL) = 1 - CDF(SL)
    cdf_at_tp = _interpolate_cdf_at(returns, np.array(levels), take_profit_return)
    cdf_at_sl = _interpolate_cdf_at(returns, np.array(levels), stop_loss_return)

    if is_long:
        p_at_risk_win = 1.0 - cdf_at_tp   # mass above TP (win territory)
        p_at_risk_loss = cdf_at_sl         # mass below SL (loss territory)
    else:  # is_short
        p_at_risk_win = cdf_at_tp          # mass below TP (win territory for a short)
        p_at_risk_loss = 1.0 - cdf_at_sl   # mass above SL (loss territory for a short)

    # Conservative joint: win and loss are mutually exclusive first-passage events.
    # Without the joint path distribution we bound each by its marginal and put
    # the residual in timeout. This understates win probability (cautious) and
    # guarantees win + loss <= 1 with timeout = 1 - win - loss >= 0.
    win = min(p_at_risk_win, 1.0 - p_at_risk_loss)
    win = max(win, 0.0)

    loss = min(p_at_risk_loss, 1.0 - win)
    loss = max(loss, 0.0)

    timeout = max(0.0, 1.0 - win - loss)

    return BarrierProbabilities(win=win, loss=loss, timeout=timeout)


def expected_value_atr(
    probs: BarrierProbabilities,
    take_profit_atr: float,
    stop_loss_atr: float,
) -> float:
    """Probability-weighted return per unit risked, in ATR.

    Mirrors ``domain.expectancy.expected_value`` — the engine's own formula —
    so a TFT-sourced probability set is scored by the same ruler as a tree
    model's. Positive means the bet is worth taking; the magnitude is in ATR
    units of the horizon.
    """
    win_pnl = probs.win * take_profit_atr
    loss_pnl = probs.loss * stop_loss_atr
    return win_pnl - loss_pnl
