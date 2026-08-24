"""Chronological folds for a dataset with several rows per candle.

`TimeSeriesSplit` splits on row positions, which is right when one row is one observation. Barrier
augmentation breaks that assumption: a single candle contributes a dozen rows that share its features and
its forward window, so a positional split puts some of a candle's variants in train and the rest in
validation. The validation score that comes back is then partly a memory test, and it is flattering —
the model has seen this exact feature vector, only with a different barrier attached.

Two rules follow, and both are about the *unit* of a split rather than its size:

1. **Split on time, not on rows.** Every row sharing a candle open goes to the same side of the boundary.
2. **Purge in candles.** A barrier label can look `max_horizon` candles into the future, so the last
   `max_horizon` candles before a validation block have labels drawn from inside it and must be dropped
   from training. Measuring that gap in rows instead of candles would under-purge by exactly the
   augmentation factor — a `gap` of 24 rows covers two candles when each candle emits twelve.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Sequence

import numpy as np


@dataclass(frozen=True, slots=True)
class TimeGroupedSplit:
    """Expanding-window chronological folds whose boundaries fall between candles.

    The block layout matches `TimeSeriesSplit`: validation blocks of equal size tile the tail of the
    series, and each fold trains on everything before its block minus the purge gap. The difference is
    that "everything before" is counted in distinct timestamps, so a timestamp is never divided.
    """

    n_splits: int
    gap: int

    def __post_init__(self) -> None:
        if self.n_splits < 2:
            raise ValueError(f"n_splits must be at least 2, got {self.n_splits}")
        if self.gap < 0:
            raise ValueError(f"gap must not be negative, got {self.gap}")

    def get_n_splits(self, *_: object) -> int:
        return self.n_splits

    def split(self, times: np.ndarray) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        """Yield `(train_rows, validation_rows)` as positional indices into `times`."""
        stamps = np.asarray(times)
        if stamps.ndim != 1:
            raise ValueError("times must be one-dimensional: one timestamp per row")

        unique = np.unique(stamps)
        candles = len(unique)
        block = candles // (self.n_splits + 1)
        if block < 1:
            raise ValueError(
                f"{candles} distinct candles cannot fill {self.n_splits} validation blocks; "
                "reduce cv_splits or extend the history"
            )

        # One searchsorted for the whole frame: each row's position in the chronological candle list.
        # Comparing that ordinal against block boundaries is then exact, and cheap on every fold.
        ordinal = np.searchsorted(unique, stamps)

        for fold in range(self.n_splits):
            validation_start = candles - (self.n_splits - fold) * block
            validation_end = validation_start + block
            train_end = validation_start - self.gap
            if train_end < 1:
                raise ValueError(
                    f"A purge gap of {self.gap} candles leaves fold {fold + 1} of {self.n_splits} with "
                    f"no training candles ({candles} distinct candles, {block} per validation block). "
                    "Shorten max_horizon, reduce cv_splits, or extend the history."
                )
            train_rows = np.flatnonzero(ordinal < train_end)
            validation_rows = np.flatnonzero((ordinal >= validation_start) & (ordinal < validation_end))
            if len(train_rows) == 0 or len(validation_rows) == 0:
                raise ValueError(f"Fold {fold + 1} of {self.n_splits} came out empty on one side")
            yield train_rows, validation_rows


def candles_between(times: np.ndarray, train_rows: np.ndarray, validation_rows: np.ndarray) -> int:
    """Distinct candles separating a train block from its validation block.

    A verification helper rather than a production one: it recomputes the realised purge gap from the
    emitted row indices, so a test can assert the gap actually applied instead of trusting the arithmetic
    that produced it.
    """
    stamps = np.asarray(times)
    unique = np.unique(stamps)
    ordinal = np.searchsorted(unique, stamps)
    last_train = int(ordinal[train_rows].max())
    first_validation = int(ordinal[validation_rows].min())
    return first_validation - last_train - 1


def chronological_blocks(
    times: np.ndarray,
    fractions: Sequence[float],
    gap: int,
) -> tuple[np.ndarray, ...]:
    """Cut a dataset into consecutive chronological blocks on candle boundaries, purging between them.

    What `TimeGroupedSplit` does for cross-validation, this does for the one-off split a calibrator
    needs: an estimator is fitted on the first block, the calibrator on the second, and the third is
    held back so the reliability curve is measured on candles neither of them has seen. Three separate
    blocks rather than two, because a calibration curve scored on the slice the calibrator was fitted to
    is a curve of its own residuals and always looks excellent.

    The same two rules as everywhere else in this module apply: boundaries fall between candles, and the
    `gap` is counted in candles because a barrier label reaches `max_horizon` candles forward.
    """
    stamps = np.asarray(times)
    if stamps.ndim != 1:
        raise ValueError("times must be one-dimensional: one timestamp per row")
    if len(fractions) < 2:
        raise ValueError(f"expected at least two blocks, got {len(fractions)}")
    if any(fraction <= 0 for fraction in fractions):
        raise ValueError(f"every block fraction must be > 0, got {tuple(fractions)}")
    total_fraction = float(sum(fractions))
    if abs(total_fraction - 1.0) > 1e-9:
        raise ValueError(f"block fractions must sum to 1, got {total_fraction!r}")
    if gap < 0:
        raise ValueError(f"gap must not be negative, got {gap}")

    unique = np.unique(stamps)
    candles = len(unique)
    ordinal = np.searchsorted(unique, stamps)

    # Cumulative candle boundaries, so rounding never loses or double-counts a candle.
    edges = [0]
    running = 0.0
    for fraction in fractions[:-1]:
        running += fraction
        edges.append(int(round(running * candles)))
    edges.append(candles)

    blocks: list[np.ndarray] = []
    for index in range(len(fractions)):
        start, end = edges[index], edges[index + 1]
        # Purge from the tail of every block but the last: it is the *earlier* block whose labels reach
        # into the later one, so the gap comes off the end that does the reaching.
        if index < len(fractions) - 1:
            end -= gap
        if end - start < 1:
            raise ValueError(
                f"Block {index + 1} of {len(fractions)} came out empty: {candles} distinct candles "
                f"split {tuple(fractions)} with a {gap}-candle purge leaves it nothing. Extend the "
                "history, shorten max_horizon, or use fewer blocks."
            )
        rows = np.flatnonzero((ordinal >= start) & (ordinal < end))
        if len(rows) == 0:
            raise ValueError(f"Block {index + 1} of {len(fractions)} selected no rows")
        blocks.append(rows)
    return tuple(blocks)
