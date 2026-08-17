from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from crypto_signal.backtest import run_backtest, signals_to_positions


class BacktestTests(unittest.TestCase):
    def test_long_only_sell_exits_and_hold_keeps_position(self) -> None:
        signals = np.array([0, 1, 0, -1, 0, 1])
        positions = signals_to_positions(signals, allow_short=False)
        np.testing.assert_array_equal(positions, np.array([0, 1, 1, 0, 0, 1]))

    def test_costs_apply_to_position_changes(self) -> None:
        frame = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC"),
                "close": [100.0, 101.0, 102.0, 101.0],
                "signal": [1, 0, -1, 0],
            }
        )
        result, metrics = run_backtest(
            frame,
            interval="1h",
            fee_rate=0.001,
            slippage_rate=0.0005,
            allow_short=False,
        )
        self.assertAlmostEqual(result["trading_cost"].iloc[0], 0.0015)
        self.assertAlmostEqual(result["trading_cost"].iloc[2], 0.0015)
        self.assertEqual(metrics["strategy"]["position_changes"], 2)


if __name__ == "__main__":
    unittest.main()

