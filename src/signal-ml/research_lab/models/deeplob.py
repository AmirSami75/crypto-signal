"""DeepLOB reimplementation (lane B, E11) — from the architecture description in
Zhang et al., "DeepLOB: Deep Convolutional Neural Networks for Limit Order
Books" (arXiv 1808.03668). Written from the description, not copied.

Input:  standardised LOB snapshot tensors [B, 1, T, 40]  (T=100 timesteps,
         40 = 10 levels x (bid price, bid vol, ask price, ask vol)).
Output: [B, 3] class probabilities (down / flat / up).

Structure:
  3 x conv block:  Conv(1x2, stride 1x2) halves the feature axis
                   + 2 x Conv(4x1) on the time axis, each followed by
                   LeakyReLU(0.01) + BatchNorm. Time convs are LEFT-padded
                   (causal): output[t] sees inputs[<=t] only.
  collapse Conv(1xF) -> inception branches 1x1 / 3x1 / 5x1 / maxpool(3x1),
                   all causal, concat over channels.
  LSTM(64) over time (inherently causal) -> FC(64->3) + softmax on LAST step.

Causality contract: appending a future snapshot leaves all earlier per-step
outputs bit-identical (in eval mode, where BatchNorm uses fixed running
stats — same convention as the TCN causality test).
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class CausalConv2d(nn.Module):
    """Conv2d causal in time: left-pad (k_t - 1) on the past side only.

    Kernel (k_t, k_f), stride (1, s_f): time length preserved, feature axis
    downsampled by s_f. No right/bottom padding -> no future leakage.
    """

    def __init__(
        self,
        in_ch: int,
        out_ch: int,
        kernel: tuple[int, int],
        stride: tuple[int, int] = (1, 1),
        leak: float = 0.01,
    ) -> None:
        super().__init__()
        k_t, _ = kernel
        self.pad_top = k_t - 1
        self.conv = nn.Conv2d(in_ch, out_ch, kernel, stride=stride)
        self.norm = nn.BatchNorm2d(out_ch)
        self.act = nn.LeakyReLU(leak)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self.pad_top:
            x = F.pad(x, (0, 0, self.pad_top, 0))  # (left, right, top, bottom)
        return self.act(self.norm(self.conv(x)))


class ConvBlock(nn.Module):
    """One DeepLOB conv block: Conv(1x2, stride 1x2) + 2 x Conv(4x1)."""

    def __init__(self, in_ch: int, out_ch: int = 32) -> None:
        super().__init__()
        self.shrink = CausalConv2d(in_ch, out_ch, (1, 2), stride=(1, 2))
        self.tconv1 = CausalConv2d(out_ch, out_ch, (4, 1))
        self.tconv2 = CausalConv2d(out_ch, out_ch, (4, 1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.tconv2(self.tconv1(self.shrink(x)))


class CausalMaxPool(nn.Module):
    """MaxPool(3x1) causal in time via left-pad then unpadded pool."""

    def __init__(self, kernel: int = 3) -> None:
        super().__init__()
        self.k = kernel

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = F.pad(x, (0, 0, self.k - 1, 0))
        return F.max_pool2d(x, (self.k, 1), stride=(1, 1))


class InceptionModule(nn.Module):
    """4 causal branches over time: 1x1 / 3x1 / 5x1 convs + 3x1 maxpool path."""

    def __init__(self, in_ch: int = 32, branch_ch: int = 32) -> None:
        super().__init__()
        self.b1 = CausalConv2d(in_ch, branch_ch, (1, 1))
        self.b3 = CausalConv2d(in_ch, branch_ch, (3, 1))
        self.b5 = CausalConv2d(in_ch, branch_ch, (5, 1))
        self.pool = CausalMaxPool(3)
        self.pool_proj = CausalConv2d(in_ch, branch_ch, (1, 1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.cat(
            [self.b1(x), self.b3(x), self.b5(x), self.pool_proj(self.pool(x))],
            dim=1,
        )


class DeepLOB(nn.Module):
    """DeepLOB: conv blocks -> inception -> LSTM(64) -> FC(3) softmax.

    forward(x [B,1,T,40]) -> probs [B,3] (last step).
    forward_seq(x)        -> probs [B,T,3] (every prefix step, causal).
    forward_logits(x)     -> logits [B,3] (for CrossEntropyLoss training).
    """

    N_LEVELS = 40

    def __init__(
        self,
        n_features: int = 40,
        conv_ch: int = 32,
        branch_ch: int = 64,
        lstm_hidden: int = 64,
        n_classes: int = 3,
    ) -> None:
        super().__init__()
        self.block1 = ConvBlock(1, conv_ch)
        self.block2 = ConvBlock(conv_ch, conv_ch)
        self.block3 = ConvBlock(conv_ch, conv_ch)
        # After 3 x stride-(1,2): 40 -> 20 -> 10 -> 5 features.
        self.collapse = CausalConv2d(conv_ch, conv_ch, (1, 5))
        self.inception = InceptionModule(conv_ch, branch_ch)
        self.lstm = nn.LSTM(4 * branch_ch, lstm_hidden, batch_first=True)
        self.fc = nn.Linear(lstm_hidden, n_classes)

    def _encode(self, x: torch.Tensor) -> torch.Tensor:
        h = self.block3(self.block2(self.block1(x)))
        h = self.collapse(h)          # [B, C, T, 1]
        h = self.inception(h)         # [B, 4*Cb, T, 1]
        return h.squeeze(-1).transpose(1, 2)  # [B, T, 4*Cb]

    def _logits_seq(self, x: torch.Tensor) -> torch.Tensor:
        seq, _ = self.lstm(self._encode(x))  # [B, T, H], causal over time
        return self.fc(seq)                  # [B, T, 3]

    def forward_seq(self, x: torch.Tensor) -> torch.Tensor:
        return self._logits_seq(x).softmax(-1)

    def forward_logits(self, x: torch.Tensor) -> torch.Tensor:
        return self._logits_seq(x)[:, -1, :]

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.forward_logits(x).softmax(-1)


def count_params(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)
