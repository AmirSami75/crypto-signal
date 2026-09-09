"""Unit tests for fee-aware labels — synthetic candles, hand-computed verdicts.

Every test constructs a tiny OHLC frame whose first-touch outcome is knowable by
inspection, then pins the net_outcome label against the hand-computed value.
Run: .venv/bin/python -m pytest research_lab/labels/test_fee_aware.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_LAB = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_LAB / "src"))
sys.path.insert(0, str(_LAB))

from research_lab.labels.fee_aware import FeeAwareConfig, label_symbol  # noqa: E402


def make_frame(closes: list[float], highs: list[float], lows: list[float]) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC"),
        "open": closes, "high": highs, "low": lows, "close": closes,
        "volume": [1.0] * n,
        "atr": [1.0] * n,  # unit ATR: ATR multiples == price distances
    })


CFG = FeeAwareConfig(take_profit_atr=2.0, stop_loss_atr=1.0, max_horizon=4,
                     fee_rate=0.0004, slippage_rate=0.0002)
# fee_atr with entry=100, atr=1.0 → (2*0.0004+2*0.0002)*100 = 0.12 ATR per round trip.


def test_long_take_profit_first_nets_tp_minus_fee():
    # Entry 100, TP at 102, SL at 99. Candle 1 spikes to 103 → TP first.
    frame = make_frame(
        closes=[100, 100.5, 103.0, 101, 100, 99.5],
        highs=[100.5, 101.0, 103.0, 103.0, 101, 100],
        lows=[99.5, 100.0, 100.5, 100.5, 99, 99],
    )
    frame["atr"] = 1.0  # 2 ATR == 2.0 price units; fee_atr = 0.0012*100/1 = 0.12
    out = label_symbol(frame, +1, CFG)
    row = out.iloc[0]
    assert row["resolved"] == "tp"
    assert row["label"] == 1
    assert row["net_atr"] == pytest.approx(2.0 - 0.12)


def test_long_stop_loss_first():
    # Candle 1 dumps to 98.5 → SL at 99 hit before TP.
    frame = make_frame(
        closes=[100, 99.2, 98.5, 99, 100, 101],
        highs=[100.5, 99.8, 99.0, 100, 100.5, 101],
        lows=[99.5, 99.0, 98.5, 98.5, 99.5, 100],
    )
    frame["atr"] = 1.0
    out = label_symbol(frame, +1, CFG)
    row = out.iloc[0]
    assert row["resolved"] == "sl"
    assert row["label"] == 0
    assert row["net_atr"] == pytest.approx(-1.0 - 0.12)


def test_timeout_exits_at_market_net_of_costs():
    # Price drifts nowhere: closes flat at 100. Timeout after 4 candles.
    frame = make_frame(
        closes=[100, 100, 100, 100, 100, 100],
        highs=[100.2, 100.2, 100.2, 100.2, 100.2, 100.2],
        lows=[99.8, 99.8, 99.8, 99.8, 99.8, 99.8],
    )
    frame["atr"] = 1.0
    out = label_symbol(frame, +1, CFG)
    row = out.iloc[0]
    assert row["resolved"] == "timeout"
    # move = (close[t+4] - entry)/atr = 0 → net = 0 - 0.0012
    assert row["net_atr"] == pytest.approx(-0.12)
    assert row["label"] == 0


def test_timeout_positive_move_can_still_win():
    # No barrier touch, but price drifts +0.5 ATR by horizon → market exit wins net.
    frame = make_frame(
        closes=[100, 100.1, 100.2, 100.3, 100.5, 100.5],
        highs=[100.4, 100.5, 100.6, 100.7, 100.9, 100.9],
        lows=[99.9, 99.9, 99.9, 99.9, 99.9, 99.9],
    )
    frame["atr"] = 1.0
    out = label_symbol(frame, +1, CFG)
    row = out.iloc[0]
    assert row["resolved"] == "timeout"
    assert row["net_atr"] == pytest.approx(0.5 - 0.12)
    assert row["label"] == 1


def test_short_mirror_and_adverse_tie():
    # SHORT: TP at 98 (below), SL at 101 (above). Forward candle 1 spans both
    # (high 101.5 ≥ SL, low 97.5 ≤ TP) → tie → adverse (SL) wins for a short.
    frame = make_frame(
        closes=[100, 100, 100, 100, 100, 100],
        highs=[100.2, 101.5, 100.2, 100.2, 100.2, 100.2],
        lows=[99.8, 97.5, 99.8, 99.8, 99.8, 99.8],
    )
    frame["atr"] = 1.0
    out = label_symbol(frame, -1, CFG)
    row = out.iloc[0]
    assert row["resolved"] == "sl"
    assert row["label"] == 0
    assert row["net_atr"] == pytest.approx(-1.0 - 0.12)


def test_short_take_profit():
    frame = make_frame(
        closes=[100, 99.0, 97.5, 98, 99, 100],
        highs=[100.5, 99.5, 98.0, 98.5, 99.5, 100.5],
        lows=[99.5, 98.5, 97.5, 97.5, 98.5, 99.5],
    )
    frame["atr"] = 1.0
    out = label_symbol(frame, -1, CFG)
    row = out.iloc[0]
    assert row["resolved"] == "tp"
    assert row["label"] == 1
    assert row["net_atr"] == pytest.approx(2.0 - 0.12)


def test_tail_rows_without_full_horizon_dropped():
    frame = make_frame(
        closes=[100] * 6,
        highs=[100.2] * 6,
        lows=[99.8] * 6,
    )
    frame["atr"] = 1.0
    out = label_symbol(frame, +1, CFG)
    # max_horizon=4 → last 4 candles lack a full forward window; only rows 0..n-5
    # survive plus any candle whose scan still resolved — here expect n-horizon rows.
    assert len(out) == len(frame) - CFG.max_horizon


def test_nonpositive_atr_dropped():
    frame = make_frame(closes=[100, 100, 100, 100, 100, 100],
                       highs=[100.2] * 6, lows=[99.8] * 6)
    frame["atr"] = [100.0, 0.0, 100.0, 100.0, 100.0, 100.0]
    out = label_symbol(frame, +1, CFG)
    assert (out["timestamp"].isin([frame["timestamp"].iloc[1]])).sum() == 0
