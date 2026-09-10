"""Tests for the DeepLOB reimplementation: shape, simplex, causality, training."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import torch
import torch.nn as nn

_LAB = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_LAB / "src"))
sys.path.insert(0, str(_LAB))

from research_lab.models.deeplob import DeepLOB, count_params  # noqa: E402


def test_output_shape():
    model = DeepLOB().eval()
    with torch.no_grad():
        out = model(torch.randn(4, 1, 100, 40))
    assert out.shape == (4, 3)


def test_probability_simplex():
    model = DeepLOB().eval()
    with torch.no_grad():
        out = model(torch.randn(8, 1, 100, 40))
    assert torch.all(out >= 0)
    assert torch.allclose(out.sum(-1), torch.ones(8), atol=1e-5)


def test_param_count_near_150k():
    n = count_params(DeepLOB())
    assert 100_000 <= n <= 250_000, n


def test_causality_future_snapshot_leaves_prefix_bit_identical():
    """Appending a future snapshot must leave the first-99 per-step outputs
    bit-identical: every conv is left-padded (causal) and the LSTM is
    sequential, so prefix outputs cannot see the future."""
    torch.manual_seed(0)
    model = DeepLOB().eval()
    x = torch.randn(2, 1, 100, 40)
    with torch.no_grad():
        base = model.forward_seq(x[:, :, :99, :])
        ext = model.forward_seq(x)
    assert base.shape == (2, 99, 3)
    assert torch.equal(base, ext[:, :99, :])


def test_one_optimizer_step_reduces_loss():
    torch.manual_seed(1)
    model = DeepLOB()
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.CrossEntropyLoss()
    x = torch.randn(64, 1, 100, 40)
    y = torch.randint(0, 3, (64,))
    model.train()
    l0 = loss_fn(model.forward_logits(x), y)
    opt.zero_grad()
    l0.backward()
    opt.step()
    l1 = loss_fn(model.forward_logits(x), y)
    assert l1.item() < l0.item(), (l0.item(), l1.item())
