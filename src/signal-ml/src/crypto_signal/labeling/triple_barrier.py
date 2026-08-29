"""The label the barrier-conditional model is trained on: which barrier a bracket order hits first.

The legacy labeller in `horizon_return` answers "did the close move more than 0.35% over six candles",
which is one specific bet. A caller asking for 2% profit against a 1% stop is not asking that question,
so thresholding that model's probability tells them about a trade they are not placing.

This module answers the question a bracket order actually asks. For a candle *t*, a direction, and a
pair of barrier distances, it walks the following candles and reports whether the take-profit or the
stop-loss came first. The barrier distances then travel into the feature row, which is the whole point:
because the model is *told* how far the barriers are, one estimator answers any requested pair instead
of one hard-coded band.

Three rules here are load-bearing, and each is enforced in `domain.barriers` so that the backtester
cannot disagree with the labeller about them:

1. **The adverse barrier wins an ambiguous candle.** Intrabar order is unknowable from OHLC, so a
   candle that touches both barriers is scored as the loss.
2. **Barriers come from the ATR at *t*.** Sizing a barrier with volatility the trade could not have
   known is look-ahead, and it is the flattering kind: it widens barriers exactly when the market is
   about to move.
3. **A row whose forward window runs off the end of the data is dropped, not called a timeout.** A
   timeout is a claim that neither barrier was touched in `max_horizon` candles, and the last rows of
   the file have no such evidence.

## Why rows carry a direction instead of being mirrored

An obvious economy: label everything long, then read the labels backwards for shorts, since a long's
win at the upper barrier is a short's loss there. It is wrong, and quietly so. Every *unambiguous*
outcome does mirror, but a tie does not — under rule 1 a candle that straddles both barriers is a loss
for the long **and** a loss for the short, because whoever is in the trade eats the adverse touch.
Reading one label set backwards turns each of those into a short win. At tight barriers ties are over
5% of resolved rows (`tests/ml-engine/test_barriers.py` asserts it), so this is not a rounding error;
it is a systematic gift to the short side, concentrated in exactly the violent candles a risk model
most needs to have learned from.

The other tempting economy — flip the sign of every directional feature and train one "canonical long"
model — fails for a different reason. Half the features have no meaningful mirror (RSI, stochastic
position, volatility, volume ratios), and crypto is genuinely asymmetric: drawdowns are faster and
deeper than the rallies that precede them. Forcing exact symmetry would erase real signal to save
rows we can afford.

So each candle is emitted once per (barrier pair, direction), with the direction among the features.

## The timeout class is load-bearing

It is tempting to treat class 0 as "nothing happened" and evaluate only the resolved rows. Measured on
BTCUSDT 1h, that single shortcut invents profit. On the widest-stop pairs 26.6% of trades time out, and
dropping them lifts apparent expectancy to +0.081 ATR for longs *and* +0.067 ATR for shorts — both
directions profitable on one price series, which is impossible. Valuing each timeout at the horizon
close instead gives +0.038 long against -0.044 short, mirrored around the market's real drift.

The mechanism is censoring: an unresolved path is disproportionately one drifting slowly toward the far
barrier, so discarding it flatters whichever barrier is nearer. Two consequences for downstream code —
the expected value a signal reports must include the timeout branch, and the bracket backtester must
exit a timed-out trade at the horizon close rather than skipping the trade.
"""

from __future__ import annotations

from dataclasses import dataclass
import time
import zlib
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from ..domain import (
    ADVERSE_WINS_TIE_BREAK,
    BarrierPair,
    Direction,
    Outcome,
    barrier_prices_from_atr,
    resolve_first_touch,
)
from ..features import WARMUP_COLUMNS, build_features
from ..log_setup import get_logger

logger = get_logger(__name__)

#: Barrier distances offered to the model, in ATR units. Coarse on purpose — neighbouring distances
#: carry nearly the same information, and every extra rung multiplies the row count.
BARRIER_GRID_ATR: tuple[float, ...] = (0.5, 1.0, 1.5, 2.0, 3.0)

#: Reward-to-risk bounds on the grid. A 10:1 target is not a trade anybody holds to the end and a 1:10
#: is not one anybody survives; both would spend rows teaching the model about bets nobody places.
MIN_RISK_REWARD = 0.4
MAX_RISK_REWARD = 4.0

#: One day of hourly candles. Long enough for a 3-ATR barrier to resolve, short enough that the purge
#: gap it forces between CV folds does not eat the training set.
DEFAULT_MAX_HORIZON = 24

#: How many of the grid's pairs each candle is emitted with. Every candle gets exactly this many, drawn
#: without replacement, so each pair still appears on a uniform ~`pairs/len(grid)` share of the history.
DEFAULT_PAIRS_PER_CANDLE = 6

#: The columns the barrier bet contributes to the feature row. `risk_reward_ratio` is redundant with the
#: two distances for a human, but an axis-aligned tree cannot divide one feature by another, so handing
#: it the ratio directly saves it from approximating one with a staircase of splits.
BARRIER_FEATURE_COLUMNS: tuple[str, ...] = (
    "take_profit_atr",
    "stop_loss_atr",
    "risk_reward_ratio",
    "direction_sign",
)

#: Columns kept beside the label for auditing, grouping and reporting. None of these are features; the
#: dataset builder returns the feature list explicitly so nothing here can leak into the model.
CONTEXT_COLUMNS: tuple[str, ...] = (
    "timestamp",
    "symbol",
    "interval",
    "entry_price",
    "atr",
    "take_profit_price",
    "stop_loss_price",
    "bars_held",
    "ambiguous",
    "timeout_return_atr",
)

LABEL_COLUMN = "target"

#: What CV folds must be split on. It is the raw candle open, not a `symbol|timestamp` key, because the
#: purge gap between folds is counted in *candles*: pooling three symbols under a composite key would make
#: a gap of 24 groups mean 8 candles, under-purging by exactly the number of symbols. Splitting on the bare
#: timestamp also keeps two symbols' rows at one candle open on the same side of a boundary, which is what
#: a chronological split means anyway.
TIME_COLUMN = "timestamp"

#: Column carrying the per-row uniqueness weight used by AFML sample weighting. Each candle in a group
#: shares the weight equally: the inverse of how many rows reference the same (symbol, candle-open).
UNIQUENESS_COLUMN = "uniqueness"


def compute_uniqueness_weights(frame: pd.DataFrame) -> pd.Series:
    """Compute the AFML "uniqueness weight" for every row of a barrier-variant frame.

    "Uniqueness (overlap)" in Lopez de Prado counts, for each observation, how many concurrent
    overlapping observations share the same unit of information — here a (symbol, candle-open) key.
    A candle emitted three times (for example, three barrier variants) gives each row 1/3; a candle
    emitted once gets 1.0. The weight therefore measures how much of the sample is "unique" versus
    duplicated, and feeds the AFML `sample_weight = uniqueness` so correlated duplicates do not
    dominate training.

    Returns a float Series aligned to the input frame's index, carrying only the weights so the
    caller can multiply it directly into an estimator's `sample_weight` without aligning columns.
    """
    if "symbol" not in frame.columns or "timestamp" not in frame.columns:
        raise ValueError("compute_uniqueness_weights requires 'symbol' and 'timestamp' columns")

    keys = frame[["symbol", "timestamp"]]
    # Normalise so NaT/NaN in either column is treated as one comparable bucket, and so that two rows
    # describing the same candle really are the same group.
    normalised = keys.assign(
        symbol=keys["symbol"].astype(object),
        timestamp=pd.to_datetime(keys["timestamp"], utc=True, format="ISO8601"),
    )
    group_sizes = normalised.groupby(["symbol", "timestamp"], dropna=False)["symbol"].transform("size")
    weights = 1.0 / group_sizes.astype(float)
    return pd.Series(weights.to_numpy(), index=frame.index, name="uniqueness")


def barrier_grid(
    multiples: Sequence[float] = BARRIER_GRID_ATR,
    minimum_risk_reward: float = MIN_RISK_REWARD,
    maximum_risk_reward: float = MAX_RISK_REWARD,
) -> tuple[BarrierPair, ...]:
    """Every take-profit/stop-loss pair from the grid whose reward-to-risk is worth training on."""
    pairs = [
        BarrierPair(take_profit_atr=float(take_profit), stop_loss_atr=float(stop_loss))
        for take_profit in multiples
        for stop_loss in multiples
        if minimum_risk_reward <= take_profit / stop_loss <= maximum_risk_reward
    ]
    if not pairs:
        raise ValueError(
            "The barrier grid is empty; widen the risk-reward bounds or the multiples "
            f"(multiples={tuple(multiples)}, bounds=[{minimum_risk_reward}, {maximum_risk_reward}])"
        )
    return tuple(pairs)


@dataclass(frozen=True, slots=True)
class BarrierLabels:
    """One direction's verdict on one barrier pair, for every candle in a frame.

    `resolved` is the honest part: it is False both for rows whose forward window runs past the end of
    the data and for rows the caller must therefore drop. Everything else is only meaningful where it
    is True.
    """

    outcome: np.ndarray
    resolved: np.ndarray
    bars_held: np.ndarray
    ambiguous: np.ndarray
    take_profit_price: np.ndarray
    stop_loss_price: np.ndarray
    timeout_return_atr: np.ndarray

    def __len__(self) -> int:
        return int(self.outcome.shape[0])

    @property
    def resolved_count(self) -> int:
        return int(np.count_nonzero(self.resolved))

    @property
    def ambiguous_share(self) -> float:
        """Share of *resolved* rows where one candle touched both barriers."""
        resolved = self.resolved_count
        if resolved == 0:
            return 0.0
        return float(np.count_nonzero(self.ambiguous & self.resolved) / resolved)

    @property
    def mean_timeout_return_atr(self) -> float:
        """Average mark-to-market of the rows that timed out, in ATR units.

        The diagnostic behind `domain.expectancy`'s decision to value a timeout at zero. It is
        accumulated drift and nothing else, so a figure far from zero says the sample had a trend, not
        that the strategy has an edge.
        """
        timed_out = self.resolved & (self.outcome == Outcome.TIMEOUT)
        if not np.any(timed_out):
            return 0.0
        return float(np.mean(self.timeout_return_atr[timed_out]))


def label_triple_barrier(
    high: np.ndarray | pd.Series,
    low: np.ndarray | pd.Series,
    entry_price: np.ndarray | pd.Series,
    atr: np.ndarray | pd.Series,
    direction: Direction,
    barriers: BarrierPair,
    max_horizon: int = DEFAULT_MAX_HORIZON,
) -> BarrierLabels:
    """Label every candle in a frame for one direction and one barrier pair.

    The entry price is the decision candle's close; the barriers sit `barriers.take_profit_atr` and
    `barriers.stop_loss_atr` ATRs from it, measured with that same candle's ATR. Scanning starts at the
    *next* candle, because a decision taken on candle *t* cannot be filled or resolved by *t* itself.
    """
    if max_horizon < 1:
        raise ValueError(f"max_horizon must be at least 1 candle, got {max_horizon}")
    if not direction.is_open:
        raise ValueError("FLAT has no barriers to resolve; label the direction you are considering")

    highs = np.asarray(high, dtype=np.float64)
    lows = np.asarray(low, dtype=np.float64)
    entries = np.asarray(entry_price, dtype=np.float64)
    atrs = np.asarray(atr, dtype=np.float64)

    take_profit_price, stop_loss_price = barrier_prices_from_atr(
        direction, entries, barriers.take_profit_atr, barriers.stop_loss_atr, atrs
    )

    outcome, resolved, bars_held, ambiguous = resolve_first_touch(
        high=highs,
        low=lows,
        take_profit_price=take_profit_price,
        stop_loss_price=stop_loss_price,
        direction=direction,
        max_horizon=max_horizon,
    )

    # What a timed-out trade is actually worth: it exits at the close of the last candle in its window,
    # so the mark is that close against the entry, signed by direction and divided by the ATR the
    # barriers were measured in. `entries` *is* the close series — the entry price of candle t is its
    # close — so the horizon close is the same array shifted by the horizon. Rows whose window runs off
    # the end get NaN, and they are exactly the rows `resolved` already excludes.
    horizon_close = np.full_like(entries, np.nan)
    if len(entries) > max_horizon:
        horizon_close[:-max_horizon] = entries[max_horizon:]
    with np.errstate(divide="ignore", invalid="ignore"):
        timeout_return_atr = (horizon_close - entries) / atrs * float(direction.sign)

    # An unusable ATR cannot produce a barrier, and a barrier at or below zero can never be touched, so
    # every such row would resolve as a timeout the market never actually delivered.
    usable = np.isfinite(atrs) & (atrs > 0) & np.isfinite(entries) & (entries > 0)
    usable &= np.isfinite(take_profit_price) & (take_profit_price > 0)
    usable &= np.isfinite(stop_loss_price) & (stop_loss_price > 0)

    return BarrierLabels(
        outcome=outcome,
        resolved=resolved & usable,
        bars_held=bars_held,
        ambiguous=ambiguous,
        take_profit_price=take_profit_price,
        stop_loss_price=stop_loss_price,
        timeout_return_atr=timeout_return_atr,
    )


def sample_barrier_pairs(
    candle_count: int,
    grid: Sequence[BarrierPair],
    pairs_per_candle: int,
    random_state: int,
) -> np.ndarray:
    """A `(candle_count, len(grid))` boolean mask: which pairs each candle is emitted with.

    Every candle draws exactly `pairs_per_candle` pairs without replacement, which keeps each pair on a
    uniform share of the history while cutting the row count by `len(grid) / pairs_per_candle`. Emitting
    the whole grid on every candle would cover the barrier response surface more densely per candle, but
    the coverage that matters is coverage *in aggregate* — with tens of thousands of candles each pair
    still lands on thousands of them.

    Seeded, because a dataset that differs between two runs makes every comparison of two models a
    comparison of two datasets as well.
    """
    if pairs_per_candle < 1:
        raise ValueError(f"pairs_per_candle must be at least 1, got {pairs_per_candle}")
    wanted = min(pairs_per_candle, len(grid))

    generator = np.random.default_rng(random_state)
    # argsort of uniform noise per row is a per-row permutation; the first `wanted` columns of it are a
    # draw without replacement, and every row gets the same count.
    order = np.argsort(generator.random((candle_count, len(grid))), axis=1)
    mask = np.zeros((candle_count, len(grid)), dtype=bool)
    np.put_along_axis(mask, order[:, :wanted], True, axis=1)
    return mask


@dataclass(frozen=True, slots=True)
class BarrierDataset:
    """The augmented training frame, plus the names the trainer must not confuse for each other.

    `feature_columns` is the only thing that goes into the model — the frame also carries the label and a
    dozen audit columns, and handing the whole frame to an estimator would train it on its own answer.
    `time_column` is what folds must be split on; see `modeling.splitting` for why row-positional
    splitting leaks here.
    """

    frame: pd.DataFrame
    feature_columns: tuple[str, ...]
    label_column: str = LABEL_COLUMN
    time_column: str = TIME_COLUMN
    tie_break: str = ADVERSE_WINS_TIE_BREAK
    max_horizon: int = DEFAULT_MAX_HORIZON

    def __len__(self) -> int:
        return len(self.frame)

    @property
    def X(self) -> pd.DataFrame:
        return self.frame[list(self.feature_columns)]

    @property
    def y(self) -> pd.Series:
        return self.frame[self.label_column]

    @property
    def times(self) -> np.ndarray:
        """The fold-splitting key: one candle open per row."""
        return self.frame[self.time_column].to_numpy()

    @property
    def class_counts(self) -> dict[int, int]:
        return {int(k): int(v) for k, v in self.frame[self.label_column].value_counts().sort_index().items()}

    @property
    def candle_count(self) -> int:
        """Distinct decision candles behind the rows — the real sample size, not `len(self)`.

        Counted per (symbol, candle), because one candle open shared by three symbols is three genuinely
        independent observations, while one candle emitted with twelve barrier pairs is one.
        """
        return int(len(self.frame[["symbol", self.time_column]].drop_duplicates()))

    @property
    def rows_per_candle(self) -> float:
        candles = self.candle_count
        return float(len(self.frame) / candles) if candles else 0.0


def build_barrier_dataset(
    frames: Mapping[str, pd.DataFrame] | pd.DataFrame,
    interval: str,
    max_horizon: int = DEFAULT_MAX_HORIZON,
    pairs_per_candle: int = DEFAULT_PAIRS_PER_CANDLE,
    grid: Sequence[BarrierPair] | None = None,
    directions: Iterable[Direction] = (Direction.LONG, Direction.SHORT),
    random_state: int = 42,
    atr_window: int = 14,
) -> BarrierDataset:
    """Build the pooled, barrier-augmented dataset from one or many symbols' candles.

    Pass a single frame for one symbol, or a mapping of symbol to frame to pool several. Pooling is what
    makes one model answer for a symbol it never saw: every feature is scale-free (asserted by
    `test_every_feature_is_scale_free`), so a row from a $3 altcoin and a row from BTC are directly
    comparable.

    The returned frame carries one row per (candle, barrier pair, direction) that resolved. Its
    `timestamp` column is the unit CV folds must be split on: every variant of one candle shares that
    candle's features and its forward window, so a row-positional split would put some variants in
    training and the rest in validation and score the model on a feature vector it had already seen.
    """
    started = time.perf_counter()
    if isinstance(frames, pd.DataFrame):
        frames = {"POOLED": frames}
    if not frames:
        raise ValueError("No candle frames were given to label")

    pairs = tuple(grid) if grid is not None else barrier_grid()
    open_directions = tuple(directions)
    for direction in open_directions:
        if not direction.is_open:
            raise ValueError(f"{direction.name} is not a tradeable direction to label")

    logger.info(
        "Barrier labelling started | symbols=%s | pairs_in_grid=%s | pairs_per_candle=%s "
        "| directions=%s | max_horizon=%s | tie_break=%s",
        len(frames),
        len(pairs),
        min(pairs_per_candle, len(pairs)),
        ",".join(d.name for d in open_directions),
        max_horizon,
        ADVERSE_WINS_TIE_BREAK,
    )

    blocks: list[pd.DataFrame] = []
    feature_columns: tuple[str, ...] | None = None
    ambiguous_shares: list[float] = []

    for symbol, raw in sorted(frames.items()):
        block, columns, shares = _label_one_symbol(
            symbol=symbol,
            interval=interval,
            raw=raw,
            pairs=pairs,
            open_directions=open_directions,
            max_horizon=max_horizon,
            pairs_per_candle=pairs_per_candle,
            random_state=random_state,
            atr_window=atr_window,
        )
        if block is None:
            continue
        if feature_columns is None:
            feature_columns = columns
        elif feature_columns != columns:
            # Pooling frames whose feature columns differ would silently align on the union and fill the
            # difference with NaN, which trains a model on the absence of a column.
            raise ValueError(
                f"{symbol} produced a different feature set than the earlier symbols; "
                "all pooled frames must yield identical feature columns"
            )
        blocks.append(block)
        ambiguous_shares.extend(shares)

    if feature_columns is None or not blocks:
        raise ValueError(
            "No symbol produced a labelled row. Each frame needs more than "
            f"{max_horizon} candles beyond the feature warm-up period."
        )

    dataset = pd.concat(blocks, axis=0, ignore_index=True)
    # Chronological, then stable within a timestamp, so a fold boundary is a point in time even when
    # several symbols share a candle open.
    dataset = dataset.sort_values(["timestamp", "symbol"], kind="stable").reset_index(drop=True)

    all_features = tuple(feature_columns) + BARRIER_FEATURE_COLUMNS
    result = BarrierDataset(
        frame=dataset,
        feature_columns=all_features,
        max_horizon=max_horizon,
    )

    logger.info(
        "Barrier labelling finished | rows=%s | candles=%s | features=%s | classes=%s "
        "| ambiguous_share=%.2f%% | elapsed=%.2fs",
        f"{len(result):,}",
        f"{result.candle_count:,}",
        len(all_features),
        result.class_counts,
        float(np.mean(ambiguous_shares)) * 100 if ambiguous_shares else 0.0,
        time.perf_counter() - started,
    )
    return result


def _symbol_seed(random_state: int, symbol: str) -> int:
    """A per-symbol seed that is stable across processes.

    `hash("BTCUSDT")` is not: Python salts string hashing per interpreter unless PYTHONHASHSEED is set,
    so seeding from it would reshuffle every symbol's barrier variants on every run and make two training
    runs incomparable. CRC32 is a fixed function of the bytes.
    """
    return (int(random_state) ^ zlib.crc32(symbol.encode("utf-8"))) % (2**32)


def _label_one_symbol(
    symbol: str,
    interval: str,
    raw: pd.DataFrame,
    pairs: Sequence[BarrierPair],
    open_directions: Sequence[Direction],
    max_horizon: int,
    pairs_per_candle: int,
    random_state: int,
    atr_window: int,
) -> tuple[pd.DataFrame | None, tuple[str, ...], list[float]]:
    """Features, labels and barrier variants for one symbol. Returns `(block, columns, shares)`."""
    features = build_features(raw, atr_window=atr_window)

    # The warm-up rows have no long-window features, so they cannot be decision candles. They are still
    # needed *as future candles* for the rows before them, which is why the barrier scan runs on the
    # full arrays and the warm-up rows are excluded only from the emitted set.
    warm = features.frame[list(WARMUP_COLUMNS)].notna().all(axis=1).to_numpy()

    high = raw["high"].astype(float).to_numpy()
    low = raw["low"].astype(float).to_numpy()
    close = raw["close"].astype(float).to_numpy()
    atr = features.atr.to_numpy(dtype=np.float64)

    candle_count = len(raw)
    if candle_count <= max_horizon:
        logger.warning(
            "%s has %s candles, which is not more than max_horizon=%s; nothing can resolve",
            symbol,
            f"{candle_count:,}",
            max_horizon,
        )
        return None, tuple(features.columns), []

    # Seed per symbol so that adding a symbol to the pool does not reshuffle the others' variants.
    mask = sample_barrier_pairs(
        candle_count=candle_count,
        grid=pairs,
        pairs_per_candle=pairs_per_candle,
        random_state=_symbol_seed(random_state, symbol),
    )

    base = features.frame[list(features.columns)]
    timestamps = raw["timestamp"].to_numpy()
    variants: list[pd.DataFrame] = []
    shares: list[float] = []

    for pair_index, pair in enumerate(pairs):
        for direction in open_directions:
            labels = label_triple_barrier(
                high=high,
                low=low,
                entry_price=close,
                atr=atr,
                direction=direction,
                barriers=pair,
                max_horizon=max_horizon,
            )
            shares.append(labels.ambiguous_share)
            keep = labels.resolved & warm & mask[:, pair_index]
            if not keep.any():
                continue
            rows = np.flatnonzero(keep)
            variant = base.iloc[rows].reset_index(drop=True)
            variant["take_profit_atr"] = pair.take_profit_atr
            variant["stop_loss_atr"] = pair.stop_loss_atr
            variant["risk_reward_ratio"] = pair.risk_reward_ratio
            variant["direction_sign"] = float(direction.sign)
            variant[LABEL_COLUMN] = labels.outcome[rows].astype(np.int8)
            variant["timestamp"] = timestamps[rows]
            variant["symbol"] = symbol
            variant["interval"] = interval
            variant["entry_price"] = close[rows]
            variant["atr"] = atr[rows]
            variant["take_profit_price"] = labels.take_profit_price[rows]
            variant["stop_loss_price"] = labels.stop_loss_price[rows]
            variant["bars_held"] = labels.bars_held[rows].astype(np.int16)
            variant["ambiguous"] = labels.ambiguous[rows]
            # Only meaningful where the label is a timeout; kept for every row so a report can compare
            # the mark against what the barriers actually paid.
            variant["timeout_return_atr"] = labels.timeout_return_atr[rows]
            variants.append(variant)

    if not variants:
        return None, tuple(features.columns), shares

    block = pd.concat(variants, axis=0, ignore_index=True)
    return block, tuple(features.columns), shares
