"""LeagueRunner tests: ranking shape, determinism, and walk-forward verdicts on synthetic data."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from crypto_signal.evaluation.league import run_league, verdict
from crypto_signal.features.indicators import average_true_range


def make_frame(seed: int, n: int = 220, drift: float = 0.05) -> pd.DataFrame:
    """A trending-then-reverting synthetic market: enough structure for strategies to fire."""
    rng = np.random.default_rng(seed)
    steps = rng.normal(drift, 1.0, n)
    close = 100 + np.cumsum(steps)
    spread = np.abs(rng.normal(0.4, 0.15, n))
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2023-01-01", periods=n, freq="h", tz="UTC"),
            "open": np.concatenate([[close[0]], close[:-1]]),
            "high": close + spread,
            "low": close - spread,
            "close": close,
            "volume": rng.uniform(500, 2000, n),
        }
    )
    frame["atr"] = average_true_range(frame, 14)
    return frame


class VerdictTests(unittest.TestCase):
    def test_verdict_ladder(self) -> None:
        self.assertEqual(verdict(train=1.0, test=0.6), "ROBUST")
        self.assertEqual(verdict(train=1.0, test=0.1), "MODERATE")
        # Train earned, test lost, but the train edge is only 2x the loss — not a memorisation
        # signature, just no out-of-sample edge.
        self.assertEqual(verdict(train=1.0, test=-0.5), "WEAK")
        # Train earned 10x what test lost: the era was memorised.
        self.assertEqual(verdict(train=1.0, test=-0.1), "OVERFITTED")
        self.assertEqual(verdict(train=8.0, test=0.5), "MODERATE")

    def test_verdict_no_train_is_weak(self) -> None:
        self.assertEqual(verdict(train=-1.0, test=0.5), "MODERATE")
        self.assertEqual(verdict(train=0.0, test=0.5), "MODERATE")
        self.assertEqual(verdict(train=0.0, test=-0.5), "WEAK")


class LeagueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frames = {"ALPHAUSDT": make_frame(1), "BETAUSDT": make_frame(2, drift=-0.03)}
        self.result = run_league(
            self.frames,
            intervals=["1h"],
            strategy_names=["rsi", "donchian", "ema_cross"],
            n_blocks=3,
        )

    def test_one_row_per_strategy_symbol_interval(self) -> None:
        rows = self.result["rows"]
        self.assertEqual(len(rows), 3 * 2 * 1)

    def test_ranking_is_total_return_desc_with_profit_factor_tiebreak(self) -> None:
        rows = self.result["rows"]
        keys = [(-r["test"]["total_return"], -(r["test"]["profit_factor"] or 0.0)) for r in rows]
        self.assertEqual(keys, sorted(keys))

    def test_rows_carry_required_fields(self) -> None:
        row = self.result["rows"][0]
        for field in ("strategy", "symbol", "interval", "verdict", "train", "test"):
            self.assertIn(field, row)
        for metric in ("trades", "win_rate", "total_return", "profit_factor", "sharpe", "max_drawdown"):
            self.assertIn(metric, row["test"])

    def test_verdict_consistent_with_returns(self) -> None:
        for row in self.result["rows"]:
            self.assertEqual(
                row["verdict"],
                verdict(row["train"]["total_return"], row["test"]["total_return"]),
            )

    def test_run_is_deterministic(self) -> None:
        again = run_league(
            self.frames,
            intervals=["1h"],
            strategy_names=["rsi", "donchian", "ema_cross"],
            n_blocks=3,
        )
        self.assertEqual(self.result["rows"], again["rows"])


if __name__ == "__main__":
    unittest.main()
