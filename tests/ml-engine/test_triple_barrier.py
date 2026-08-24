"""Barrier labelling, barrier augmentation, and the fold isolation the augmentation demands.

The rules under test here are the ones that decide whether a reported win rate is real:

* an ambiguous candle is a loss for whichever side is holding it, so it cannot be mirrored;
* a row whose forward window runs off the end of the data is dropped, not called a timeout;
* barriers are measured with the ATR the decision could actually have known;
* every variant of one candle stays on one side of every fold boundary, and the purge gap between
  train and validation is counted in candles rather than rows.

The last one is the reason this file exists at all. `TimeSeriesSplit` on an augmented frame produces a
validation score that is partly a memory test, and it fails in the flattering direction.
"""

from __future__ import annotations

import subprocess
import sys
import unittest

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

from crypto_signal.config import ModelConfig
from crypto_signal.domain import BarrierPair, Direction
from crypto_signal.labeling import (
    BARRIER_FEATURE_COLUMNS,
    CONTEXT_COLUMNS,
    DEFAULT_MAX_HORIZON,
    LABEL_COLUMN,
    TIME_COLUMN,
    barrier_grid,
    build_barrier_dataset,
    label_triple_barrier,
    sample_barrier_pairs,
)
from crypto_signal.modeling import (
    TimeGroupedSplit,
    candles_between,
    walk_forward_validation_by_time,
)


def candles(rows: list[tuple[float, float, float, float]], start: str = "2024-01-01") -> pd.DataFrame:
    """An OHLCV frame from explicit `(open, high, low, close)` tuples."""
    frame = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    frame.insert(0, "timestamp", pd.date_range(start, periods=len(rows), freq="1h", tz="UTC"))
    frame["volume"] = 1_000.0
    return frame


def synthetic_market(
    periods: int = 900,
    seed: int = 3,
    drift: float = 0.0,
    volatility: float = 0.004,
    start_price: float = 100.0,
    start: str = "2024-01-01",
) -> pd.DataFrame:
    """A random walk long enough to clear the 168-candle feature warm-up plus a barrier horizon."""
    generator = np.random.default_rng(seed)
    close = start_price * np.exp(np.cumsum(generator.normal(drift, volatility, periods)))
    wiggle = np.abs(generator.normal(0.0, volatility / 2, periods)) * close
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(start, periods=periods, freq="1h", tz="UTC"),
            "open": np.r_[close[0], close[:-1]],
            "high": close + wiggle,
            "low": close - wiggle,
            "close": close,
            "volume": generator.lognormal(3.0, 0.4, periods),
        }
    )


class BarrierGridTests(unittest.TestCase):
    def test_every_pair_respects_the_risk_reward_bounds(self) -> None:
        pairs = barrier_grid((0.5, 1.0, 2.0, 4.0), minimum_risk_reward=0.5, maximum_risk_reward=2.0)
        self.assertTrue(pairs)
        for pair in pairs:
            self.assertGreaterEqual(pair.risk_reward_ratio, 0.5)
            self.assertLessEqual(pair.risk_reward_ratio, 2.0)

    def test_the_grid_includes_both_sides_of_even_money(self) -> None:
        ratios = {pair.risk_reward_ratio for pair in barrier_grid()}
        self.assertTrue(any(ratio < 1.0 for ratio in ratios), "no pair risks more than it targets")
        self.assertTrue(any(ratio > 1.0 for ratio in ratios), "no pair targets more than it risks")
        self.assertIn(1.0, ratios)

    def test_impossible_bounds_are_refused_rather_than_returning_nothing(self) -> None:
        with self.assertRaisesRegex(ValueError, "grid is empty"):
            barrier_grid((1.0, 2.0), minimum_risk_reward=10.0, maximum_risk_reward=20.0)


class LabelTests(unittest.TestCase):
    """Hand-computed outcomes. Entry is 100, ATR is 1, so an ATR multiple is a whole currency unit."""

    def label(
        self,
        rows: list[tuple[float, float, float, float]],
        direction: Direction = Direction.LONG,
        take_profit_atr: float = 2.0,
        stop_loss_atr: float = 1.0,
        max_horizon: int = 3,
    ):
        frame = candles(rows)
        return label_triple_barrier(
            high=frame["high"].to_numpy(),
            low=frame["low"].to_numpy(),
            entry_price=frame["close"].to_numpy(),
            atr=np.ones(len(frame)),
            direction=direction,
            barriers=BarrierPair(take_profit_atr=take_profit_atr, stop_loss_atr=stop_loss_atr),
            max_horizon=max_horizon,
        )

    def test_reaching_the_take_profit_first_is_a_win(self) -> None:
        # Entry 100 on row 0; take-profit 102, stop-loss 99. Row 2 trades up to 102.5.
        labels = self.label(
            [
                (100, 100, 100, 100),
                (100, 101, 99.5, 100),
                (100, 102.5, 99.5, 102),
                (102, 102, 102, 102),
            ]
        )
        self.assertEqual(labels.outcome[0], 1)
        self.assertTrue(labels.resolved[0])
        self.assertEqual(labels.bars_held[0], 2)
        self.assertFalse(labels.ambiguous[0])

    def test_reaching_the_stop_loss_first_is_a_loss(self) -> None:
        labels = self.label(
            [
                (100, 100, 100, 100),
                (100, 101, 98.5, 99),
                (99, 103, 99, 103),
                (103, 103, 103, 103),
            ]
        )
        self.assertEqual(labels.outcome[0], -1)
        self.assertEqual(labels.bars_held[0], 1)

    def test_touching_neither_barrier_inside_the_horizon_is_a_timeout(self) -> None:
        labels = self.label([(100, 100.5, 99.5, 100)] * 5)
        self.assertEqual(labels.outcome[0], 0)
        self.assertTrue(labels.resolved[0])
        self.assertEqual(labels.bars_held[0], 3, "a timeout is held for the whole horizon")

    def test_a_candle_touching_both_barriers_is_a_loss_for_the_long(self) -> None:
        labels = self.label(
            [
                (100, 100, 100, 100),
                (100, 103, 98, 100),  # straddles take-profit 102 and stop-loss 99
                (100, 100, 100, 100),
                (100, 100, 100, 100),
            ]
        )
        self.assertEqual(labels.outcome[0], -1)
        self.assertTrue(labels.ambiguous[0])

    def test_a_candle_touching_both_barriers_is_a_loss_for_the_short_too(self) -> None:
        # The same prices, read as a short: take-profit 98, stop-loss 101. Row 1 straddles both.
        labels = self.label(
            [
                (100, 100, 100, 100),
                (100, 103, 98, 100),
                (100, 100, 100, 100),
                (100, 100, 100, 100),
            ],
            direction=Direction.SHORT,
        )
        self.assertEqual(
            labels.outcome[0],
            -1,
            "a straddling candle must be a loss for both sides; scoring it as a short win is how "
            "mirroring one label set manufactures profit",
        )
        self.assertTrue(labels.ambiguous[0])

    def test_the_decision_candle_cannot_resolve_its_own_label(self) -> None:
        # Row 0 itself trades through the take-profit, but the decision is taken at its close.
        labels = self.label(
            [
                (100, 105, 100, 100),
                (100, 100.5, 99.5, 100),
                (100, 100.5, 99.5, 100),
                (100, 100.5, 99.5, 100),
            ]
        )
        self.assertEqual(labels.outcome[0], 0)

    def test_rows_without_a_full_forward_window_are_unresolved_not_timeouts(self) -> None:
        labels = self.label([(100, 100.5, 99.5, 100)] * 6, max_horizon=3)
        self.assertTrue(labels.resolved[:3].all())
        self.assertFalse(
            labels.resolved[3:].any(),
            "the last max_horizon rows have no evidence either barrier went untouched",
        )

    def test_barriers_use_the_atr_of_the_decision_candle(self) -> None:
        # Row 0 has ATR 1 (stop at 99); row 1 has ATR 10 (stop at 90). The same subsequent low of 98.5
        # must stop row 0 out and leave row 1 open. Reading a later ATR would widen row 0's barrier
        # exactly when the market was about to move.
        frame = candles([(100, 100, 100, 100)] * 2 + [(100, 100.5, 98.5, 100)] * 4)
        labels = label_triple_barrier(
            high=frame["high"].to_numpy(),
            low=frame["low"].to_numpy(),
            entry_price=frame["close"].to_numpy(),
            atr=np.array([1.0, 10.0, 1.0, 1.0, 1.0, 1.0]),
            direction=Direction.LONG,
            barriers=BarrierPair(take_profit_atr=2.0, stop_loss_atr=1.0),
            max_horizon=3,
        )
        self.assertEqual(labels.outcome[0], -1)
        self.assertEqual(labels.outcome[1], 0)
        self.assertAlmostEqual(labels.stop_loss_price[0], 99.0)
        self.assertAlmostEqual(labels.stop_loss_price[1], 90.0)

    def test_an_unusable_atr_leaves_the_row_unresolved(self) -> None:
        frame = candles([(100, 101, 99, 100)] * 6)
        labels = label_triple_barrier(
            high=frame["high"].to_numpy(),
            low=frame["low"].to_numpy(),
            entry_price=frame["close"].to_numpy(),
            atr=np.array([1.0, 0.0, np.nan, 1.0, 1.0, 1.0]),
            direction=Direction.LONG,
            barriers=BarrierPair(take_profit_atr=1.0, stop_loss_atr=1.0),
            max_horizon=2,
        )
        self.assertTrue(labels.resolved[0])
        self.assertFalse(labels.resolved[1], "a zero ATR cannot place a barrier")
        self.assertFalse(labels.resolved[2], "a missing ATR cannot place a barrier")

    def test_a_barrier_below_zero_is_not_a_timeout(self) -> None:
        # A stop 4 ATR below a price of 3 ATR is a negative price, which no candle can reach. Calling
        # that a timeout would teach the model a bet nobody can place.
        frame = candles([(100, 101, 99, 100)] * 6)
        labels = label_triple_barrier(
            high=frame["high"].to_numpy(),
            low=frame["low"].to_numpy(),
            entry_price=frame["close"].to_numpy(),
            atr=np.full(6, 40.0),
            direction=Direction.LONG,
            barriers=BarrierPair(take_profit_atr=1.0, stop_loss_atr=4.0),
            max_horizon=2,
        )
        self.assertFalse(labels.resolved.any())

    def test_flat_has_nothing_to_label(self) -> None:
        with self.assertRaisesRegex(ValueError, "FLAT"):
            self.label([(100, 101, 99, 100)] * 4, direction=Direction.FLAT)

    def test_a_horizon_must_reach_at_least_one_candle_forward(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_horizon"):
            self.label([(100, 101, 99, 100)] * 4, max_horizon=0)


class SamplingTests(unittest.TestCase):
    def test_every_candle_draws_the_requested_number_of_pairs(self) -> None:
        grid = barrier_grid()
        mask = sample_barrier_pairs(500, grid, pairs_per_candle=6, random_state=1)
        self.assertEqual(mask.shape, (500, len(grid)))
        self.assertTrue((mask.sum(axis=1) == 6).all())

    def test_asking_for_more_pairs_than_exist_yields_the_whole_grid(self) -> None:
        grid = barrier_grid()
        mask = sample_barrier_pairs(50, grid, pairs_per_candle=len(grid) + 5, random_state=1)
        self.assertTrue(mask.all())

    def test_no_pair_is_starved_across_the_history(self) -> None:
        grid = barrier_grid()
        share = sample_barrier_pairs(20_000, grid, pairs_per_candle=6, random_state=1).mean(axis=0)
        expected = 6 / len(grid)
        self.assertTrue(
            np.allclose(share, expected, atol=0.02),
            f"pair coverage {share.min():.3f}..{share.max():.3f} strays from {expected:.3f}",
        )

    def test_the_same_seed_draws_the_same_variants(self) -> None:
        grid = barrier_grid()
        first = sample_barrier_pairs(300, grid, pairs_per_candle=4, random_state=7)
        second = sample_barrier_pairs(300, grid, pairs_per_candle=4, random_state=7)
        third = sample_barrier_pairs(300, grid, pairs_per_candle=4, random_state=8)
        np.testing.assert_array_equal(first, second)
        self.assertFalse(np.array_equal(first, third), "a different seed must draw differently")

    def test_a_fresh_interpreter_builds_the_same_dataset(self) -> None:
        """Guards the per-symbol seed against Python's salted string hashing.

        Seeding a symbol's variants from `hash(symbol)` looks fine in one process and silently reshuffles
        the dataset in the next, which makes two training runs incomparable without anything appearing to
        have changed. PYTHONHASHSEED is varied here precisely to catch that.
        """
        program = """
import hashlib
import numpy as np
import pandas as pd
from crypto_signal.labeling import build_barrier_dataset

generator = np.random.default_rng(3)
close = 100 * np.exp(np.cumsum(generator.normal(0.0, 0.004, 900)))
wiggle = np.abs(generator.normal(0.0, 0.002, 900)) * close
frame = pd.DataFrame({
    "timestamp": pd.date_range("2024-01-01", periods=900, freq="1h", tz="UTC"),
    "open": np.r_[close[0], close[:-1]],
    "high": close + wiggle,
    "low": close - wiggle,
    "close": close,
    "volume": generator.lognormal(3.0, 0.4, 900),
})
dataset = build_barrier_dataset({"AAAUSDT": frame, "BBBUSDT": frame}, interval="1h", random_state=42)
payload = dataset.frame[["take_profit_atr", "stop_loss_atr", "direction_sign", "target"]]
print(hashlib.sha256(pd.util.hash_pandas_object(payload, index=False).values.tobytes()).hexdigest())
"""
        digests = set()
        for hash_seed in ("0", "12345"):
            completed = subprocess.run(
                [sys.executable, "-c", program],
                capture_output=True,
                text=True,
                check=True,
                env={"PYTHONHASHSEED": hash_seed, "PATH": "/usr/bin:/bin"},
            )
            digests.add(completed.stdout.strip())
        self.assertEqual(len(digests), 1, f"the dataset changed between interpreters: {digests}")


class DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frame = synthetic_market()
        cls.dataset = build_barrier_dataset({"AAAUSDT": cls.frame}, interval="1h", random_state=42)

    def test_each_candle_is_emitted_once_per_pair_and_direction(self) -> None:
        self.assertAlmostEqual(self.dataset.rows_per_candle, 12.0, places=6)

    def test_the_feature_list_carries_the_barrier_bet_and_nothing_it_should_not(self) -> None:
        features = set(self.dataset.feature_columns)
        for column in BARRIER_FEATURE_COLUMNS:
            self.assertIn(column, features)
        for column in (*CONTEXT_COLUMNS, LABEL_COLUMN):
            self.assertNotIn(column, features, f"{column} is context, not a feature")

    def test_the_label_only_ever_takes_the_three_outcome_values(self) -> None:
        self.assertEqual(set(self.dataset.y.unique()) - {-1, 0, 1}, set())

    def test_the_barrier_features_are_never_missing(self) -> None:
        barriers = self.dataset.frame[list(BARRIER_FEATURE_COLUMNS)]
        self.assertFalse(barriers.isna().to_numpy().any())
        self.assertEqual(set(self.dataset.frame["direction_sign"].unique()), {-1.0, 1.0})

    def test_the_recorded_barrier_prices_match_the_requested_distances(self) -> None:
        frame = self.dataset.frame
        longs = frame[frame.direction_sign > 0]
        expected = longs.entry_price + longs.take_profit_atr * longs.atr
        np.testing.assert_allclose(longs.take_profit_price, expected, rtol=1e-12)
        shorts = frame[frame.direction_sign < 0]
        expected = shorts.entry_price - shorts.take_profit_atr * shorts.atr
        np.testing.assert_allclose(shorts.take_profit_price, expected, rtol=1e-12)

    def test_warm_up_candles_are_never_decision_candles(self) -> None:
        earliest = self.dataset.frame["timestamp"].min()
        self.assertGreaterEqual(
            self.frame.index[self.frame["timestamp"] == earliest][0],
            168,
            "a decision candle must have its longest-window features",
        )

    def test_the_last_candles_are_dropped_rather_than_called_timeouts(self) -> None:
        latest = self.dataset.frame["timestamp"].max()
        cutoff = self.frame["timestamp"].iloc[-DEFAULT_MAX_HORIZON]
        self.assertLess(latest, cutoff)

    def test_timeouts_are_identical_for_long_and_short_at_symmetric_barriers(self) -> None:
        """An internal consistency check the labeller cannot fake.

        "Neither barrier was touched" is a statement about two price levels, not about who is holding
        the position, so at equal distances the timeout counts for long and short must agree exactly.
        """
        frame = self.dataset.frame
        symmetric = frame[np.isclose(frame.take_profit_atr, frame.stop_loss_atr)]
        by_direction = symmetric.groupby(["take_profit_atr", "direction_sign"])[LABEL_COLUMN].apply(
            lambda column: int((column == 0).sum())
        )
        for distance in symmetric["take_profit_atr"].unique():
            self.assertEqual(
                by_direction[(distance, 1.0)],
                by_direction[(distance, -1.0)],
                f"timeout counts diverge at {distance} ATR",
            )

    def test_a_driftless_market_gives_the_labels_no_edge(self) -> None:
        """Optional stopping: a bracket on a martingale has expectancy zero, whatever the ratio.

        Look-ahead in a labeller shows up here as systematic profit, so this is the cheapest broad test
        that no future information has leaked into a label. Timeouts are marked to market, because
        dropping them is itself a bias — see the module docstring.
        """
        frame = synthetic_market(periods=1_400, seed=19, drift=0.0)
        dataset = build_barrier_dataset({"FLATUSDT": frame}, interval="1h", random_state=5)
        rows = dataset.frame

        position = pd.Series(np.arange(len(frame)), index=frame["timestamp"].to_numpy())
        entered = position.reindex(rows["timestamp"].to_numpy()).to_numpy()
        exited = np.minimum(entered + dataset.max_horizon, len(frame) - 1)
        closes = frame["close"].to_numpy()
        marked = (closes[exited] - rows.entry_price) * rows.direction_sign / rows.atr

        profit = np.where(
            rows[LABEL_COLUMN] == 1,
            rows.take_profit_atr,
            np.where(rows[LABEL_COLUMN] == -1, -rows.stop_loss_atr, marked),
        )
        expectancy = float(np.mean(profit))
        self.assertLess(
            abs(expectancy),
            0.05,
            f"a driftless market yielded {expectancy:+.4f} ATR per trade; the labels see the future",
        )

    def test_pooling_two_symbols_keeps_both_and_stays_chronological(self) -> None:
        other = synthetic_market(seed=11, start_price=3.5)
        dataset = build_barrier_dataset(
            {"AAAUSDT": self.frame, "BBBUSDT": other}, interval="1h", random_state=42
        )
        self.assertEqual(set(dataset.frame["symbol"]), {"AAAUSDT", "BBBUSDT"})
        self.assertTrue(dataset.frame["timestamp"].is_monotonic_increasing)
        self.assertEqual(dataset.feature_columns, self.dataset.feature_columns)

    def test_a_symbol_does_not_change_the_others_variants_when_pooled(self) -> None:
        """Adding a symbol to the pool must not reshuffle the ones already in it.

        Otherwise every extension of the training set silently rebuilds the whole dataset, and a model
        trained on four symbols cannot be compared with one trained on three.
        """
        pooled = build_barrier_dataset(
            {"AAAUSDT": self.frame, "BBBUSDT": synthetic_market(seed=11)},
            interval="1h",
            random_state=42,
        )
        alone = self.dataset.frame
        together = pooled.frame[pooled.frame.symbol == "AAAUSDT"]
        pd.testing.assert_frame_equal(
            alone.reset_index(drop=True),
            together.reset_index(drop=True),
            check_like=True,
        )

    def test_a_single_frame_is_accepted_without_a_symbol_map(self) -> None:
        dataset = build_barrier_dataset(self.frame, interval="1h", random_state=42)
        self.assertEqual(set(dataset.frame["symbol"]), {"POOLED"})

    def test_a_history_shorter_than_the_horizon_is_refused_clearly(self) -> None:
        # 190 candles is 168 of feature warm-up plus 22 — fewer than the 24-candle horizon, so no
        # candle can see far enough forward to earn a label.
        with self.assertRaisesRegex(ValueError, "No symbol produced a labelled row"):
            build_barrier_dataset({"TINY": synthetic_market(periods=190)}, interval="1h")

    def test_no_frames_at_all_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "No candle frames"):
            build_barrier_dataset({}, interval="1h")

    def test_flat_cannot_be_asked_for(self) -> None:
        with self.assertRaisesRegex(ValueError, "not a tradeable direction"):
            build_barrier_dataset(
                {"AAAUSDT": self.frame}, interval="1h", directions=(Direction.FLAT,)
            )


class FoldIsolationTests(unittest.TestCase):
    """The leakage barrier augmentation creates, and the split that closes it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = build_barrier_dataset(
            {"AAAUSDT": synthetic_market(periods=1_600, seed=23)}, interval="1h", random_state=42
        )
        cls.times = cls.dataset.times
        cls.gap = cls.dataset.max_horizon

    def folds(self, n_splits: int = 4, gap: int | None = None):
        splitter = TimeGroupedSplit(n_splits=n_splits, gap=self.gap if gap is None else gap)
        return list(splitter.split(self.times))

    def test_no_candle_appears_on_both_sides_of_a_boundary(self) -> None:
        for index, (train, validation) in enumerate(self.folds(), start=1):
            shared = set(self.times[train]) & set(self.times[validation])
            self.assertEqual(shared, set(), f"fold {index} splits {len(shared)} candles")

    def test_every_variant_of_a_candle_lands_together(self) -> None:
        for index, (train, validation) in enumerate(self.folds(), start=1):
            for name, rows in (("train", train), ("validation", validation)):
                held = self.dataset.frame.iloc[rows]
                counts = held.groupby(TIME_COLUMN).size()
                whole = self.dataset.frame.groupby(TIME_COLUMN).size().reindex(counts.index)
                self.assertTrue(
                    (counts == whole).all(),
                    f"fold {index} {name} holds a partial candle",
                )

    def test_the_purge_gap_is_counted_in_candles(self) -> None:
        for index, (train, validation) in enumerate(self.folds(), start=1):
            purged = candles_between(self.times, train, validation)
            self.assertGreaterEqual(
                purged, self.gap, f"fold {index} purged {purged} candles, not {self.gap}"
            )

    def test_training_never_reaches_into_the_future(self) -> None:
        for index, (train, validation) in enumerate(self.folds(), start=1):
            self.assertLess(
                self.times[train].max(), self.times[validation].min(), f"fold {index} trains ahead"
            )

    def test_validation_blocks_move_forward_and_never_repeat(self) -> None:
        seen: set = set()
        previous_end = None
        for train, validation in self.folds():
            block = set(self.times[validation])
            self.assertEqual(block & seen, set(), "a candle is validated twice")
            seen |= block
            start = self.times[validation].min()
            if previous_end is not None:
                self.assertGreater(start, previous_end)
            previous_end = self.times[validation].max()
            self.assertLessEqual(len(train), len(self.dataset.frame))

    def test_the_training_window_expands_fold_over_fold(self) -> None:
        sizes = [len(train) for train, _ in self.folds()]
        self.assertEqual(sizes, sorted(sizes))
        self.assertLess(sizes[0], sizes[-1])

    def test_a_row_positional_split_would_have_leaked(self) -> None:
        """The measurement that justifies this whole module.

        `TimeSeriesSplit` is the obvious choice and the wrong one here, in two separate ways, and they
        show up at different settings — which is why this asserts twice rather than once.

        Ungapped, it cuts straight through a candle: some of that candle's barrier variants train the
        model and the rest score it, on identical features. Gapped, the boundary candle lands inside
        the discarded rows and the split looks clean, but the purge is still counted in rows — 24 rows
        is two candles here, and the realised separation comes to a single candle against the 24 the
        caller asked for. Labels drawn from 23 candles the model trained on then sit in validation.
        """
        train, validation = next(iter(TimeSeriesSplit(n_splits=4, gap=0).split(self.dataset.frame)))
        shared = set(self.times[train]) & set(self.times[validation])
        self.assertEqual(
            len(shared), 1, "expected the naive splitter to divide one candle across the boundary"
        )
        self.assertLess(
            candles_between(self.times, train, validation),
            0,
            "a divided candle means the two sides overlap in time, not merely touch",
        )

        train, validation = next(
            iter(TimeSeriesSplit(n_splits=4, gap=self.gap).split(self.dataset.frame))
        )
        self.assertFalse(set(self.times[train]) & set(self.times[validation]))
        purged = candles_between(self.times, train, validation)
        self.assertLess(
            purged,
            self.gap,
            "expected a row-counted gap to under-purge on an augmented frame",
        )
        rows_between = int(validation.min() - train.max() - 1)
        self.assertEqual(
            rows_between,
            self.gap,
            "TimeSeriesSplit honours the gap it was given, to the row",
        )
        self.assertEqual(
            purged,
            1,
            f"{rows_between} rows of separation is {purged} candle here, not the {self.gap} candles a "
            "barrier label can reach across",
        )

    def test_a_gap_that_would_erase_the_training_set_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "no training candles"):
            list(TimeGroupedSplit(n_splits=4, gap=10_000).split(self.times))

    def test_too_few_candles_for_the_requested_folds_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "validation blocks"):
            list(TimeGroupedSplit(n_splits=5, gap=0).split(np.arange(4)))

    def test_the_splitter_rejects_nonsense_settings(self) -> None:
        with self.assertRaisesRegex(ValueError, "n_splits"):
            TimeGroupedSplit(n_splits=1, gap=0)
        with self.assertRaisesRegex(ValueError, "gap"):
            TimeGroupedSplit(n_splits=3, gap=-1)
        with self.assertRaisesRegex(ValueError, "one-dimensional"):
            list(TimeGroupedSplit(n_splits=2, gap=0).split(np.zeros((4, 2))))


class GroupedValidationTests(unittest.TestCase):
    def test_validation_reports_the_gap_it_actually_purged(self) -> None:
        dataset = build_barrier_dataset(
            {"AAAUSDT": synthetic_market(periods=1_200, seed=31)}, interval="1h", random_state=42
        )
        config = ModelConfig(
            test_fraction=0.2,
            cv_splits=3,
            probability_threshold=0.4,
            random_state=42,
            max_iter=12,
            learning_rate=0.2,
            max_leaf_nodes=8,
            min_samples_leaf=40,
            l2_regularization=0.0,
        )
        report = walk_forward_validation_by_time(
            dataset.X, dataset.y, dataset.times, config, gap=dataset.max_horizon
        )
        self.assertEqual(report["gap_unit"], "candles")
        self.assertEqual(len(report["folds"]), 3)
        for fold in report["folds"]:
            self.assertGreaterEqual(fold["purged_candles"], dataset.max_horizon)
            self.assertGreater(fold["validation_rows"], 0)
        self.assertIn("balanced_accuracy", report["combined"])

    def test_times_must_line_up_with_the_rows(self) -> None:
        frame = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0]})
        target = pd.Series([1, -1, 1, -1])
        config = ModelConfig(
            test_fraction=0.2,
            cv_splits=2,
            probability_threshold=0.4,
            random_state=1,
            max_iter=5,
            learning_rate=0.1,
            max_leaf_nodes=4,
            min_samples_leaf=1,
            l2_regularization=0.0,
        )
        with self.assertRaisesRegex(ValueError, "must line up"):
            walk_forward_validation_by_time(frame, target, np.arange(3), config, gap=0)


if __name__ == "__main__":
    unittest.main()
