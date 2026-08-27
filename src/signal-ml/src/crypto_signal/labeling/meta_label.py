"""Meta-label: predict whether a barrier bet is *profitable*, not which class wins.

The primary triple-barrier estimator answers "which outcome?" (stop-first / timeout /
tp-first). With a fixed bracket and a ~0.30-ATR round-trip fee, that question is the wrong
one to gate an order on: a 1.5:1 bet needs ~64% tp-first to break even, and the primary
tops out near ~62% at 1h. Meta-labeling (Lopez de Prado, AFML ch. 3) replaces it with a
binary question the serving path actually needs: "does THIS setup's net return clear the
fee-adjusted break-even?"

Every row of a labelled barrier frame — one row per (candle, barrier pair, direction) —
gets `meta_profitable = net_return_atr > 0`, where `net_return_atr` is the realised ATR
multiple of that bet minus the round-trip cost. The meta-learner then fits on
[primary-confidence, barrier context] -> profitable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

META_PROFITABLE_COLUMN = "meta_profitable"
META_NET_RETURN_ATR_COLUMN = "net_return_atr"

#: Barrier-context rows the meta-learner consumes along with the primary's probability.
#: These are the same context the primary already conditions on (BARRIER_FEATURE_COLUMNS),
#: plus the primary's own win probability — the meta-learner is deliberately small.
META_CONTEXT_COLUMNS: tuple[str, ...] = (
    "take_profit_atr",
    "stop_loss_atr",
    "risk_reward_ratio",
    "direction_sign",
)

#: NaN/None cells produced when a row cannot carry a number (e.g. an unlabelled/warm-up row
#: slipped through). The meta-learner, like the primary, is a HistGradientBoosting that
#: tolerates missing values natively.
_FLOAT = float
_TIME_DELTA = None  # placeholder; keep imports minimal


def realised_return_atr(
    target: pd.Series | np.ndarray,
    take_profit_atr: pd.Series | np.ndarray,
    stop_loss_atr: pd.Series | np.ndarray,
    timeout_return_atr: pd.Series | np.ndarray,
    fee_atr: float,
) -> np.ndarray:
    """Realised net return of a barrier bet in ATR multiples, signed by the bet's own view.

    `target` follows the primary's label: +1 tp-first, -1 stop-first, 0 timeout.
    Shapes match the barrier frame's row order (one row per candle/pair/direction).
    """
    target = np.asarray(target, dtype=float)
    take_profit_atr = np.asarray(take_profit_atr, dtype=float)
    stop_loss_atr = np.asarray(stop_loss_atr, dtype=float)
    timeout_return_atr = np.asarray(timeout_return_atr, dtype=float)
    return np.where(
        target == 1,
        take_profit_atr - fee_atr,
        np.where(target == -1, -stop_loss_atr - fee_atr, timeout_return_atr - fee_atr),
    )


def build_meta_features(frame: pd.DataFrame, p_win: np.ndarray) -> pd.DataFrame:
    """The meta-learner's feature matrix from a barrier frame + primary win probabilities.

    `frame` must carry `take_profit_atr`, `stop_loss_atr`, `risk_reward_ratio`,
    `direction_sign`. `p_win` is the primary model's P(outcome == +1 = tp-first) for the
    row's (pair, direction) — the same number the old serving gate read.
    """
    required = set(META_CONTEXT_COLUMNS)
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Barrier frame missing meta context columns: {sorted(missing)}")
    features = frame[list(META_CONTEXT_COLUMNS)].copy()
    features["p_win"] = np.asarray(p_win, dtype=float)
    return pd.DataFrame(features)


def add_meta_labels(
    frame: pd.DataFrame,
    p_win: np.ndarray,
    fee_atr: float,
) -> pd.DataFrame:
    """Attach `net_return_atr` and `meta_profitable` to a barrier frame in place.

    Returns a new frame (does not mutate the input). Requires the label columns the primary
    training already produced (`target`, `take_profit_atr`, `stop_loss_atr`,
    `timeout_return_atr`). Raises if any are absent so a silently-wrong label set cannot
    be trained on.
    """
    required = {
        "target",
        "take_profit_atr",
        "stop_loss_atr",
        "timeout_return_atr",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Cannot meta-label frame missing: {sorted(missing)}")
    out = frame.copy()
    net = realised_return_atr(
        out["target"].to_numpy(),
        out["take_profit_atr"].to_numpy(),
        out["stop_loss_atr"].to_numpy(),
        out["timeout_return_atr"].to_numpy(),
        fee_atr,
    )
    out[META_NET_RETURN_ATR_COLUMN] = net
    out[META_PROFITABLE_COLUMN] = net > 0
    out["p_win"] = np.asarray(p_win, dtype=float)
    return out