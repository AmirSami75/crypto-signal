"""Higher-timeframe context features: scale-free ratios, joined without lookahead.

Three properties carry the whole design, and each has a test that fails on its own:

**Scale-free.** Every MTF column is a ratio of higher-timeframe prices, so a pooled model can read
BTC's 1h context and DOGE's 1h context through the same columns. A raw price here would pass every
local test and quietly break every market the model was not fitted on — the same trap
`test_every_feature_is_scale_free` guards for the base features.

**No lookahead.** A higher-timeframe candle that opens at 10:00 is not *known* at 10:00 — it closes
at 11:00. A lower-timeframe candle may only see context candles that have already CLOSED, so the join
key on the right side is the close time, not the open time. Matching on open time would hand a 15m
candle the high, low and close of an hour that had not finished happening.

**NaN-preserving.** Rows before the higher frame's coverage or within the joined frame's EMA warm-up
have no honest value. Dropping them would silently shorten the dataset the labeller emits; filling
them would fabricate context. NaN travels to the estimator, which handles it the same way it handles
base warm-up NaNs.
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from crypto_signal.features.mtf import attach_higher_tf_features


def higher_frame(rows: int = 80, start: str = "2024-01-01", close: float = 100.0) -> pd.DataFrame:
    """Constant-price hourly candles: every ratio resolves to a hand-checkable constant.

    With close pinned at 100 and a fixed 2.0 true range, Wilder's ATR converges
    to exactly 2.0 and the EMAs converge to the close itself — so
    `trend_ema_ratio` is 1.0, `close_vs_ema20` is 0.0 and `atr_pct` is 0.02
    once the warm-up has filled.
    """
    timestamp = pd.date_range(start, periods=rows, freq="h", tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": timestamp,
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000.0,
        }
    )


def lower_frame(rows: int = 240, start: str = "2024-01-01") -> pd.DataFrame:
    """15-minute candles covering the same span as `higher_frame`."""
    timestamp = pd.date_range(start, periods=rows, freq="15min", tz="UTC")
    close = pd.Series(100 + np.arange(rows) * 0.05)
    return pd.DataFrame(
        {
            "timestamp": timestamp,
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 500.0,
        }
    )


WARMUP = 50  # the lower-frame gate passed through `ema_warmup`


class ScaleFreeAndAlignmentTests(unittest.TestCase):
    """The plan's named test: known ratio values, NaN before warm-up preserved."""

    def test_known_ratio_values_after_the_higher_frame_warms_up(self) -> None:
        frame = attach_higher_tf_features(
            lower_frame(), higher_frame(rows=200), ema_warmup=WARMUP
        )

        for column in (
            "h4_trend_ema_ratio",
            "h4_atr_pct",
            "h4_close_vs_ema20",
        ):
            self.assertIn(column, frame.columns)

        tail = frame.iloc[-40:]
        # Constant higher-TF prices: ema20 == ema50 == close, ATR == 2.0 on a close of 100.
        np.testing.assert_allclose(tail["h4_trend_ema_ratio"].to_numpy(), 1.0, atol=1e-9)
        np.testing.assert_allclose(tail["h4_atr_pct"].to_numpy(), 0.02, atol=1e-9)
        np.testing.assert_allclose(tail["h4_close_vs_ema20"].to_numpy(), 0.0, atol=1e-9)

    def test_nan_is_preserved_before_the_higher_ema_warmup(self) -> None:
        frame = attach_higher_tf_features(
            lower_frame(), higher_frame(rows=200), ema_warmup=WARMUP
        )

        head = frame.iloc[: WARMUP - 1]
        self.assertTrue(head["h4_trend_ema_ratio"].isna().all())
        self.assertTrue(head["h4_close_vs_ema20"].isna().all())
        # The warm-up NaNs do not leak into the rows that have a filled window behind them.
        self.assertTrue(frame.iloc[WARMUP:]["h4_trend_ema_ratio"].notna().all())

    def test_nan_is_preserved_where_the_higher_frame_has_no_coverage(self) -> None:
        # The 1h context starts a day after the 15m frame: those first lower rows have no closed
        # higher candle to read, and the honest value is NaN rather than zero or a backfill.
        frame = attach_higher_tf_features(
            lower_frame(), higher_frame(rows=60, start="2024-01-02"), ema_warmup=0
        )

        early = frame[frame["timestamp"] < pd.Timestamp("2024-01-02", tz="UTC")]
        late = frame[frame["timestamp"] >= pd.Timestamp("2024-01-02", tz="UTC")]
        self.assertFalse(early.empty)
        for column in ("h4_trend_ema_ratio", "h4_atr_pct", "h4_close_vs_ema20"):
            self.assertTrue(early[column].isna().all(), column)
            self.assertTrue(late[column].notna().any(), column)

    def test_scaling_higher_prices_leaves_every_column_unchanged(self) -> None:
        base = higher_frame(rows=200)
        scaled = base.copy()
        scaled[["open", "high", "low", "close"]] *= 7.0

        original = attach_higher_tf_features(lower_frame(), base, ema_warmup=WARMUP)
        rescaled = attach_higher_tf_features(lower_frame(), scaled, ema_warmup=WARMUP)

        for column in ("h4_trend_ema_ratio", "h4_atr_pct", "h4_close_vs_ema20"):
            left = original[column].to_numpy()
            right = rescaled[column].to_numpy()
            np.testing.assert_allclose(
                np.nan_to_num(left, nan=0.0), np.nan_to_num(right, nan=0.0), atol=1e-9
            )

    def test_custom_prefix_names_the_columns(self) -> None:
        frame = attach_higher_tf_features(
            lower_frame(), higher_frame(rows=200), ema_warmup=WARMUP, prefix="h1_"
        )
        self.assertIn("h1_trend_ema_ratio", frame.columns)
        self.assertIn("h1_atr_pct", frame.columns)
        self.assertIn("h1_close_vs_ema20", frame.columns)


class LookaheadTests(unittest.TestCase):
    """The join is on the higher candle's CLOSE time; an opening candle is not evidence yet."""

    def test_a_lower_candle_never_sees_a_higher_candle_still_open(self) -> None:
        # Two 1h candles with deliberately different ratio fingerprints: the 09:00 candle sits in a
        # flat market, the 10:00 candle in one that stepped up. A 15m candle inside 10:00-10:45 must
        # read the 09:00 fingerprint until the 10:00 candle has actually closed at 11:00.
        base = higher_frame(rows=200)
        base.loc[base["timestamp"] == pd.Timestamp("2024-01-01 10:00", tz="UTC"), "close"] = 200.0
        base.loc[base["timestamp"] == pd.Timestamp("2024-01-01 10:00", tz="UTC"), "open"] = 200.0

        frame = attach_higher_tf_features(lower_frame(), base, ema_warmup=0)
        inside = frame[
            (frame["timestamp"] >= pd.Timestamp("2024-01-01 10:00", tz="UTC"))
            & (frame["timestamp"] < pd.Timestamp("2024-01-01 11:00", tz="UTC"))
        ]
        self.assertEqual(int(inside["h4_close_vs_ema20"].notna().sum()), len(inside))
        # The 10:00 1h candle's own close_vs_ema20 would be strongly positive; the 09:00 candle's is 0.
        self.assertAlmostEqual(float(inside["h4_close_vs_ema20"].iloc[0]), 0.0, places=9)

    def test_the_higher_candle_becomes_visible_once_it_has_closed(self) -> None:
        base = higher_frame(rows=200)
        base.loc[base["timestamp"] == pd.Timestamp("2024-01-01 10:00", tz="UTC"), "close"] = 200.0
        base.loc[base["timestamp"] == pd.Timestamp("2024-01-01 10:00", tz="UTC"), "open"] = 200.0

        frame = attach_higher_tf_features(lower_frame(), base, ema_warmup=0)
        after = frame[frame["timestamp"] == pd.Timestamp("2024-01-01 11:00", tz="UTC")]
        self.assertEqual(len(after), 1)
        # The 10:00 candle closed at 11:00; the 11:00 15m candle is the first that may read it.
        self.assertGreater(float(after["h4_close_vs_ema20"].iloc[0]), 0.5)

    def test_mutating_future_higher_candles_leaves_past_rows_unchanged(self) -> None:
        base = higher_frame(rows=200)
        changed = base.copy()
        cutoff = pd.Timestamp("2024-01-04", tz="UTC")
        changed.loc[changed["timestamp"] >= cutoff, ["open", "high", "low", "close"]] *= 3.0

        before = attach_higher_tf_features(lower_frame(), base, ema_warmup=WARMUP)
        after = attach_higher_tf_features(lower_frame(), changed, ema_warmup=WARMUP)
        past = before["timestamp"] < cutoff

        for column in ("h4_trend_ema_ratio", "h4_atr_pct", "h4_close_vs_ema20"):
            np.testing.assert_allclose(
                np.nan_to_num(before.loc[past, column].to_numpy(), nan=0.0),
                np.nan_to_num(after.loc[past, column].to_numpy(), nan=0.0),
                atol=1e-12,
            )


class InputContractTests(unittest.TestCase):
    """Refuse inputs whose arithmetic would succeed and whose meaning would be wrong."""

    def test_an_empty_higher_frame_is_an_error_not_a_silent_nan_column(self) -> None:
        with self.assertRaisesRegex(ValueError, "empty"):
            attach_higher_tf_features(lower_frame(), higher_frame().iloc[0:0])

    def test_an_unsorted_higher_frame_is_rejected(self) -> None:
        base = higher_frame(rows=50)
        shuffled = base.iloc[::-1].reset_index(drop=True)
        with self.assertRaisesRegex(ValueError, "sorted"):
            attach_higher_tf_features(lower_frame(), shuffled)

    def test_a_single_row_higher_frame_cannot_infer_its_step(self) -> None:
        with self.assertRaisesRegex(ValueError, "interval"):
            attach_higher_tf_features(lower_frame(), higher_frame(rows=1))

    def test_missing_price_columns_are_named(self) -> None:
        base = higher_frame(rows=50).drop(columns=["high"])
        with self.assertRaisesRegex(ValueError, "high"):
            attach_higher_tf_features(lower_frame(), base)

    def test_the_returned_frame_keeps_its_index_and_original_columns(self) -> None:
        frame = lower_frame()
        result = attach_higher_tf_features(frame, higher_frame(rows=200), ema_warmup=WARMUP)
        self.assertEqual(list(result.index), list(frame.index))
        self.assertEqual(list(result.columns[: len(frame.columns)]), list(frame.columns))


if __name__ == "__main__":
    unittest.main()
