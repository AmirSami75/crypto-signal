"""Temporal Convolutional Network with multi-task forecasting heads.

Architecture (§8 TCN, §7 multi-task):
  input [B, lookback, F]
    -> causal dilated Conv1D blocks (kernel 3, dilations 1,2,4,8 -> receptive
       field 31 candles) with residual connections, weight norm, dropout
    -> take the LAST timestep's representation (causal; nothing from the future)
    -> heads:
         direction: P(net > 0)             (classification, focal loss)
         ret:       future log-return over horizon (regression, Huber)
         mfe:       max favourable excursion in ATR (regression, Huber)
         mae:       max adverse excursion in ATR  (regression, Huber)

CPU-only by design: channels 32, ~50k params, batch 512 — trains on a 15Gi box.
The classification head is what the economic gate consumes; the forecasting
heads are auxiliary targets that regularise the shared trunk (multi-task) and
are reported for diagnostics.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class CausalConv1d(nn.Module):
    """Conv1d that never sees the future: left-pad by (kernel-1)*dilation."""

    def __init__(self, channels_in: int, channels_out: int, kernel: int, dilation: int) -> None:
        super().__init__()
        self.pad = (kernel - 1) * dilation
        self.conv = nn.utils.parametrizations.weight_norm(
            nn.Conv1d(channels_in, channels_out, kernel, dilation=dilation)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.conv(F.pad(x, (self.pad, 0)))


class TemporalBlock(nn.Module):
    def __init__(self, channels_in: int, channels_out: int, kernel: int, dilation: int, dropout: float) -> None:
        super().__init__()
        self.conv1 = CausalConv1d(channels_in, channels_out, kernel, dilation)
        self.conv2 = CausalConv1d(channels_out, channels_out, kernel, dilation)
        self.dropout = nn.Dropout(dropout)
        self.downsample = nn.Conv1d(channels_in, channels_out, 1) if channels_in != channels_out else None

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.dropout(F.gelu(self.conv1(x)))
        out = self.dropout(F.gelu(self.conv2(out)))
        residual = x if self.downsample is None else self.downsample(x)
        return F.gelu(out + residual)


class MultiTaskTCN(nn.Module):
    def __init__(
        self,
        n_features: int,
        channels: int = 32,
        kernel: int = 3,
        dilations: tuple[int, ...] = (1, 2, 4, 8),
        dropout: float = 0.15,
    ) -> None:
        super().__init__()
        blocks = []
        channels_in = n_features
        for dilation in dilations:
            blocks.append(TemporalBlock(channels_in, channels, kernel, dilation, dropout))
            channels_in = channels
        self.trunk = nn.Sequential(*blocks)
        self.norm = nn.LayerNorm(channels)
        self.head_direction = nn.Linear(channels, 1)
        self.head_ret = nn.Linear(channels, 1)
        self.head_mfe = nn.Linear(channels, 1)
        self.head_mae = nn.Linear(channels, 1)
        self.receptive_field = 1 + sum((kernel - 1) * d * 2 for d in dilations)

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        # x: [B, lookback, F] -> conv expects [B, F, lookback]
        h = self.trunk(x.transpose(1, 2))[:, :, -1]  # last timestep only (causal)
        h = self.norm(h)
        return {
            "direction_logit": self.head_direction(h).squeeze(-1),
            "ret": self.head_ret(h).squeeze(-1),
            "mfe": self.head_mfe(h).squeeze(-1),
            "mae": self.head_mae(h).squeeze(-1),
        }


def focal_bce(logits: torch.Tensor, targets: torch.Tensor, gamma: float = 2.0, alpha: float = 0.5) -> torch.Tensor:
    """Focal loss on a binary logit: down-weights easy examples so the minority
    'net-positive' class is not swamped. alpha=0.5 = balanced."""
    bce = F.binary_cross_entropy_with_logits(logits, targets, reduction="none")
    p = torch.sigmoid(logits)
    p_t = p * targets + (1 - p) * (1 - targets)
    alpha_t = alpha * targets + (1 - alpha) * (1 - targets)
    return (alpha_t * (1 - p_t) ** gamma * bce).mean()


def multitask_loss(
    out: dict[str, torch.Tensor],
    y_dir: torch.Tensor,
    y_ret: torch.Tensor,
    y_mfe: torch.Tensor,
    y_mae: torch.Tensor,
    aux_weight: float = 0.3,
) -> tuple[torch.Tensor, dict[str, float]]:
    l_dir = focal_bce(out["direction_logit"], y_dir)
    l_ret = F.huber_loss(out["ret"], y_ret, delta=1.0)
    l_mfe = F.huber_loss(out["mfe"], y_mfe, delta=1.0)
    l_mae = F.huber_loss(out["mae"], y_mae, delta=1.0)
    total = l_dir + aux_weight * (l_ret + l_mfe + l_mae)
    return total, {
        "dir": float(l_dir), "ret": float(l_ret), "mfe": float(l_mfe), "mae": float(l_mae),
    }
