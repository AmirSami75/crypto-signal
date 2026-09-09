"""Tests for the TCN (shape/causality) and forecasting targets (hand-computed)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch

_LAB = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_LAB / "src"))
sys.path.insert(0, str(_LAB))

from research_lab.labels.forecasting import forecasting_targets  # noqa: E402
from research_lab.models.tcn import MultiTaskTCN, focal_bce, multitask_loss  # noqa: E402


def test_tcn_output_shapes():
    model = MultiTaskTCN(n_features=7, channels=8)
    x = torch.randn(5, 32, 7)
    out = model(x)
    for key in ("direction_logit", "ret", "mfe", "mae"):
        assert out[key].shape == (5,), key


def test_tcn_is_causal_last_step_ignores_future_perturbation():
    """Perturbing timesteps AFTER the last one must not exist (we read the last
    step). Perturbing EARLIER steps may change the output; perturbing the LAST
    step's own input must. This pins that no future leakage path exists in the
    padding scheme: left-pad only."""
    torch.manual_seed(0)
    model = MultiTaskTCN(n_features=4, channels=8).eval()
    x = torch.randn(1, 40, 4)
    base = model(x)["direction_logit"].item()
    # Left-padding means output[t] depends on x[<=t]; to prove NO right-padding
    # leak, compare output at the last step for x vs x with an EXTRA appended
    # step — the appended step must not alter the prediction for the old last step.
    x_ext = torch.cat([x, torch.randn(1, 1, 4) * 100], dim=1)
    h_ext = model.trunk(x_ext.transpose(1, 2))[:, :, -2]  # old last step
    h_ext = model.norm(h_ext)
    ext_logit = model.head_direction(h_ext).squeeze(-1).item()
    assert abs(base - ext_logit) < 1e-4


def test_focal_loss_downweights_confident_correct():
    logits = torch.tensor([4.0, -4.0])   # very confident
    targets = torch.tensor([1.0, 0.0])   # and correct
    easy = focal_bce(logits, targets)
    hard = focal_bce(torch.tensor([0.0, 0.0]), targets)
    assert easy < hard


def test_multitask_loss_returns_components():
    out = {k: torch.zeros(3) for k in ("direction_logit", "ret", "mfe", "mae")}
    total, parts = multitask_loss(out, torch.ones(3), torch.zeros(3), torch.zeros(3), torch.zeros(3))
    assert set(parts) == {"dir", "ret", "mfe", "mae"}
    assert total.item() > 0


def _frame(closes, highs, lows):
    n = len(closes)
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
        "open": closes, "high": highs, "low": lows, "close": closes, "atr": [1.0] * n,
    })


def test_forecasting_targets_long_hand_computed():
    # entry close 100; forward window h=1..3: highs 101,103,102 lows 99,98,99.5; close[t+3]=102
    f = _frame(closes=[100, 100.5, 102.5, 102, 101], highs=[100.2, 101, 103, 102, 101.5],
               lows=[99.8, 99, 98, 99.5, 100.5])
    t = forecasting_targets(f, +1, horizon=3)
    row = t.iloc[0]
    assert row["mfe_atr"] == pytest.approx(3.0)      # max high 103 - 100
    assert row["mae_atr"] == pytest.approx(2.0)      # 100 - min low 98
    assert row["future_log_return"] == pytest.approx(np.log(102 / 100))


def test_forecasting_targets_short_mirror():
    f = _frame(closes=[100, 100.5, 102.5, 102, 101], highs=[100.2, 101, 103, 102, 101.5],
               lows=[99.8, 99, 98, 99.5, 100.5])
    t = forecasting_targets(f, -1, horizon=3)
    row = t.iloc[0]
    assert row["mfe_atr"] == pytest.approx(2.0)      # short: 100 - min low 98
    assert row["mae_atr"] == pytest.approx(3.0)      # short: max high 103 - 100
    assert row["future_log_return"] == pytest.approx(-np.log(102 / 100))


def test_forecasting_targets_tail_is_nan():
    f = _frame(closes=[100] * 5, highs=[100.5] * 5, lows=[99.5] * 5)
    t = forecasting_targets(f, +1, horizon=3)
    assert t["mfe_atr"].iloc[-3:].isna().all()
    assert t["future_log_return"].iloc[-3:].isna().all()
