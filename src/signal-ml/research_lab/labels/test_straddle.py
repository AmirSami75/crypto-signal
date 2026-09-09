"""Hand-computed straddle label tests. entry=100, atr=1 → ATR units == price units."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

_LAB = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_LAB / "src"))
sys.path.insert(0, str(_LAB))

from research_lab.labels.straddle import StraddleConfig, label_straddle  # noqa: E402

# trigger ±1, TP +2 from fill, SL −1 from fill, horizon 5, fee 0.1%, slip 0.05%
CFG = StraddleConfig(trigger_atr=1.0, take_profit_atr=2.0, stop_loss_atr=1.0, max_horizon=5,
                     fee_rate=0.001, slippage_rate=0.0005)
FEE = 0.001 * 100      # 0.1 ATR per fee leg at price≈100, atr=1
SLIP = 0.0005 * 100    # 0.05 ATR


def _frame(closes, highs, lows):
    n = len(closes)
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
        "open": closes, "high": highs, "low": lows, "close": closes, "atr": [1.0] * n,
    })


def test_upside_breakout_then_take_profit():
    # t0 close 100. h1 high 101 → long fills at 101. h2 high 103.2 → TP at 103 hit.
    f = _frame(closes=[100, 100.8, 103.0, 102, 102, 102, 102],
               highs=[100.5, 101.0, 103.2, 102.5, 102.5, 102.5, 102.5],
               lows=[99.5, 100.2, 100.9, 101.5, 101.5, 101.5, 101.5])
    r = label_straddle(f, CFG).iloc[0]
    assert r["resolved"] == "tp" and r["direction"] == 1.0
    # entry cost (fee+slip at entry 101) + TP exit (fee at 101)
    expected = 2.0 - (0.001 + 0.0005) * 101 - 0.001 * 101
    assert r["net_atr"] == pytest.approx(expected)


def test_downside_breakout_then_stop():
    # h1 low 99 → short fills at 99. SL at 100. h2 high 100.3 → stopped.
    f = _frame(closes=[100, 99.2, 100.2, 100, 100, 100, 100],
               highs=[100.5, 99.8, 100.3, 100.2, 100.2, 100.2, 100.2],
               lows=[99.5, 99.0, 99.5, 99.8, 99.8, 99.8, 99.8])
    r = label_straddle(f, CFG).iloc[0]
    assert r["resolved"] == "sl" and r["direction"] == -1.0
    expected = -1.0 - (0.001 + 0.0005) * 99 - (0.001 + 0.0005) * 99
    assert r["net_atr"] == pytest.approx(expected)


def test_whipsaw_same_candle_charged_as_stop():
    # h1 spans 98.5..101.5 → both triggers same candle.
    f = _frame(closes=[100] * 7, highs=[100.2, 101.5, 100.2, 100.2, 100.2, 100.2, 100.2],
               lows=[99.8, 98.5, 99.8, 99.8, 99.8, 99.8, 99.8])
    r = label_straddle(f, CFG).iloc[0]
    assert r["resolved"] == "whipsaw"
    assert r["net_atr"] == pytest.approx(-1.0 - (2 * 0.001 + 2 * 0.0005) * 100)


def test_no_trigger_is_not_a_trade():
    f = _frame(closes=[100] * 7, highs=[100.5] * 7, lows=[99.5] * 7)
    r = label_straddle(f, CFG).iloc[0]
    assert r["resolved"] == "no_trigger" and not r["traded"] and r["net_atr"] == 0.0
    assert r["range_atr"] == pytest.approx(1.0)   # 100.5 - 99.5


def test_timeout_exits_at_market():
    # long fills at 101 on h1, then drifts to 101.5 by h5 with no TP/SL touch.
    f = _frame(closes=[100, 100.9, 101.2, 101.3, 101.4, 101.5, 101.5],
               highs=[100.5, 101.0, 101.4, 101.5, 101.6, 101.7, 101.7],
               lows=[99.5, 100.3, 100.8, 100.9, 101.0, 101.1, 101.1])
    r = label_straddle(f, CFG).iloc[0]
    assert r["resolved"] == "timeout" and r["direction"] == 1.0
    move = (101.5 - 101.0)
    expected = move - (0.001 + 0.0005) * 101 - (0.001 + 0.0005) * 101
    assert r["net_atr"] == pytest.approx(expected)


def test_tail_rows_dropped():
    f = _frame(closes=[100] * 8, highs=[100.5] * 8, lows=[99.5] * 8)
    out = label_straddle(f, CFG)
    assert len(out) == 8 - CFG.max_horizon
