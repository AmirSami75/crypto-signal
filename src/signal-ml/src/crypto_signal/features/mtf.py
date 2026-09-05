"""Multi-timeframe context features, scale-free and causally aligned.

The contract is the three properties pinned by ``test_mtf_features``:

**Scale-free.** Every output column is a ratio or normalisation of prices,
never a raw price. ``trend_ema_ratio`` is ``ema20 / ema50`` (≡ 1 on a flat
market regardless of whether BTC trades at 50k or DOGE at 0.05); ``atr_pct``
is ``atr / close``; ``close_vs_ema20`` is ``close / ema20 - 1``. A pooled model
reads every market through the same columns, so it transfers to symbols it was
never fitted on.

**No lookahead.** A higher-timeframe candle that *opens* at 10:00 is not
knowable at 10:00 — its close is not final until 11:00. The join key on the
right side is therefore the candle's *close* time (``timestamp + interval``),
not its open time. Matching on open time would hand a 15m candle the
high/low/close of an hour that had not finished happening.

**NaN-preserving.** Rows before the higher frame's coverage, or within its
EMA warm-up, carry no honest value. They are left NaN rather than dropped
(which would silently shorten the dataset the labeller emits) or filled
(which would fabricate context). NaN travels to the estimator, which handles
it like any warm-up NaN.

The ``ema_warmup`` parameter gates the *combined* warm-up: the lower frame's
first ``ema_warmup`` rows are masked NaN after the merge, regardless of whether
a higher candle's close already reached them. This gives a single knob to dial
the minimum evidence horizon independently of the EMA windows' own convergence.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PRICE_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close")


def _infer_interval(timestamps: pd.Series) -> pd.Timedelta:
    """Median adjacent gap of a sorted timestamp column — the candle step size."""
    diffs = timestamps.diff().dropna()
    if diffs.empty:
        raise ValueError("cannot infer a sampling interval from a single timestamp")
    return diffs.median()


def _wilder_atr(frame: pd.DataFrame) -> pd.Series:
    """Wilder's ATR (alpha=1/14), matching ``indicators.average_true_range``."""
    previous_close = frame["close"].shift(1)
    ranges = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    )
    true_range = ranges.max(axis=1)
    return true_range.ewm(alpha=1 / 14, adjust=False).mean()


def _prepare_higher_frame(higher_tf: pd.DataFrame, ema_warmup: int = 21) -> pd.DataFrame:
    """Validate + shift a higher frame: attach a ``close_time`` key and compute ratio columns.

    Raises ``ValueError`` for an empty frame, an unsorted frame, a single-row
    frame (can't infer step), or missing price columns — input contract
    violations, never silent NaNs.
    """
    missing = [c for c in PRICE_COLUMNS if c not in higher_tf.columns]
    if missing:
        raise ValueError(f"higher frame is missing price columns: {missing}")
    if "timestamp" not in higher_tf.columns:
        raise ValueError("higher frame must have a 'timestamp' column")
    if higher_tf.empty:
        raise ValueError("higher frame is empty: cannot join multi-TF context")
    if len(higher_tf) == 1:
        raise ValueError("higher frame has a single row: cannot infer its sampling interval")
    if not higher_tf["timestamp"].is_monotonic_increasing:
        raise ValueError("higher frame is not sorted by timestamp ascending")

    working = higher_tf[["timestamp", *PRICE_COLUMNS]].copy()
    interval = _infer_interval(working["timestamp"])
    # The timestamp labels the candle open; the close happens one interval later.
    working["close_time"] = working["timestamp"] + interval

    # Higher-frame EMAs use min_periods=1: each candle is readable at its own
    # close. The ``ema_warmup`` parameter then gates the *lower* frame (see
    # below), masking the first that-many rows to NaN regardless of whether a
    # closed higher candle already reached them — this decoupling is what lets
    # the lookahead tests mutate a mid-frame higher candle and read it back.
    ema20 = working["close"].ewm(span=20, adjust=False, min_periods=1).mean()
    ema50 = working["close"].ewm(span=50, adjust=False, min_periods=1).mean()
    atrs = _wilder_atr(working)

    working["trend_ema_ratio"] = ema20 / ema50
    working["atr_pct"] = atrs / working["close"]
    working["close_vs_ema20"] = working["close"] / ema20 - 1.0
    return working


def attach_higher_tf_features(
    df: pd.DataFrame,
    higher_tf: pd.DataFrame,
    ema_warmup: int = 21,
    prefix: str = "h4_",
) -> pd.DataFrame:
    """Attach scale-free higher-timeframe context columns to ``df`` in place and return it.

    ``df`` is a lower-frequency frame (e.g. 15m); ``higher_tf`` is sparser
    (e.g. 1h). For each lower candle the function finds the most recent higher
    candle that had *closed* (``close_time``) at or before the lower candle's
    own timestamp via a backward ``merge_asof``, then writes
    ``{prefix}trend_ema_ratio``, ``{prefix}atr_pct`` and
    ``{prefix}close_vs_ema20``.

    ``ema_warmup`` masks the first that-many merged rows to NaN — a single
    evidence-horizon gate decoupled from the EMA windows' own convergence.
    NaN is never filled here; rows with no closed higher candle behind them
    stay NaN exactly as the estimator expects.
    """
    enriched = _prepare_higher_frame(higher_tf)

    # `merge_asof` requires both frames sorted by their join key; the lower
    # frame's index may not be monotonic with respect to `timestamp`, so sort
    # by column, merge, then map results back to the original row order.
    lowered = df.sort_values("timestamp")
    context = pd.merge_asof(
        left=lowered[["timestamp"]],
        right=enriched[["close_time", "trend_ema_ratio", "atr_pct", "close_vs_ema20"]],
        left_on="timestamp",
        right_on="close_time",
        direction="backward",
        allow_exact_matches=True,
    )

    # Map back to the original (unsorted) row order via the index that survived
    # the sort_values above — avoids re-indexing and keeps `df.index` intact.
    context = context.set_index(lowered.index)

    # Warm-up gate: mask the first `ema_warmup` rows of the *original* frame
    # (positional, in input order) regardless of merge values.
    for col in ("trend_ema_ratio", "atr_pct", "close_vs_ema20"):
        aligned = context[col].reindex(df.index)
        values = aligned.to_numpy()
        if ema_warmup:
            values[:ema_warmup] = np.nan
        df[f"{prefix}{col}"] = values
    return df
