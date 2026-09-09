"""Fee-aware barrier labels (E1).

The production labeller values a timeout at zero EV ("the same default the serving
evaluator uses"). A real timeout trade does not exit at zero — it exits at market
after `max_horizon` candles, paying a market-fill slippage plus round-trip fees,
and keeps whatever the price moved. E0 showed the honest simulator punishes that
gap: every geometry is negative when the model is trained on zero-timeout labels.

This module relabels every (candle, direction) bet by its NET outcome in ATR:

- take-profit first  -> net = +tp_atr - fee_atr          (limit exit, no slippage)
- stop-loss first    -> net = -sl_atr - fee_atr          (limit exit, no slippage)
- timeout            -> net = signed_move_atr - fee_atr  (MARKET exit, slippage)

with fee_atr = (2*fee_rate + 2*slippage_rate) * entry / atr — both-side fees plus
conservative slippage on both market fills (entry is always a market fill).

Label is binary: 1 = the bet nets money, 0 = it does not. That is exactly the
event a trader is paid on, so `P(label=1)` calibrated against these labels is the
quantity the backtest gate consumes. Tie rule matches production: a candle that
touches both barriers resolves ADVERSE (stop first).

Vectorised over one symbol at a time; memory O(candles) per direction.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class FeeAwareConfig:
    take_profit_atr: float
    stop_loss_atr: float
    max_horizon: int
    fee_rate: float
    slippage_rate: float


def fee_atr_series(entry: np.ndarray, atr: np.ndarray, config: FeeAwareConfig) -> np.ndarray:
    """Round-trip cost in ATR units: both-side fees + both market-fill slippages.

    Non-positive ATR yields +inf cost, which the valid mask drops downstream —
    a candle with no range has no defined ATR-normalised P&L.
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(
            atr > 0,
            (2.0 * config.fee_rate + 2.0 * config.slippage_rate) * entry / np.where(atr > 0, atr, 1.0),
            np.inf,
        )


def label_symbol(
    frame: pd.DataFrame, direction_sign: int, config: FeeAwareConfig
) -> pd.DataFrame:
    """One direction's net-outcome labels for one symbol.

    `frame` needs columns timestamp, open, high, low, close, atr — the same raw
    candle frame `build_barrier_dataset` consumes. Returns one row per candle
    with `label` in {0,1}, `fee_atr`, and the realised `net_atr` (diagnostics).
    Candles without a complete forward window (last `max_horizon` rows) and any
    non-positive ATR are dropped, mirroring the production warm-up rules.
    """
    high = frame["high"].to_numpy(dtype=np.float64)
    low = frame["low"].to_numpy(dtype=np.float64)
    close = frame["close"].to_numpy(dtype=np.float64)
    atr = frame["atr"].to_numpy(dtype=np.float64)
    n = len(frame)
    horizon = config.max_horizon
    tp = config.take_profit_atr
    sl = config.stop_loss_atr

    entry = close
    fee = fee_atr_series(entry, atr, config)

    tp_price = entry + direction_sign * tp * atr
    sl_price = entry - direction_sign * sl * atr

    # First-touch scan, vectorised over candles for each forward offset h.
    tp_first = np.full(n, horizon + 1, dtype=np.int32)
    sl_first = np.full(n, horizon + 1, dtype=np.int32)
    for h in range(1, horizon + 1):
        if h >= n:
            break
        # Aligned forward candle: index t+h. Touch tests use that candle's range.
        future_high = np.empty(n, dtype=np.float64)
        future_low = np.empty(n, dtype=np.float64)
        future_high[: n - h] = high[h:]
        future_low[: n - h] = low[h:]
        future_high[n - h :] = np.nan
        future_low[n - h :] = np.nan

        # Direction-aware touch tests. LONG: TP above entry is 'reached' when the
        # future HIGH rises to it; SL below is reached when the future LOW falls
        # to it. SHORT mirrors: TP below is reached when future LOW <= tp_price,
        # SL above when future HIGH >= sl_price. Both the source array AND the
        # comparison flip with direction.
        if direction_sign > 0:
            hits_tp = future_high >= tp_price
            hits_sl = future_low <= sl_price
        else:
            hits_tp = future_low <= tp_price
            hits_sl = future_high >= sl_price
        unassigned = tp_first == horizon + 1
        unassigned_sl = sl_first == horizon + 1
        tp_first = np.where(hits_tp & unassigned, h, tp_first).astype(np.int32)
        sl_first = np.where(hits_sl & unassigned_sl, h, sl_first).astype(np.int32)

    touched = (tp_first <= horizon) | (sl_first <= horizon)
    # Adverse-wins tie: one candle touching both barriers resolves stop-first for
    # BOTH sides (production rule: 'adverse barrier wins an ambiguous candle').
    tp_wins = (tp_first < sl_first) & touched
    sl_wins = touched & ~tp_wins

    # Timeout exit: market fill at close[t+horizon], signed move, net of costs.
    signed_move = np.zeros(n, dtype=np.float64)
    future_close = np.full(n, np.nan)
    if n > horizon:
        future_close[: n - horizon] = close[horizon:]
    with np.errstate(invalid="ignore"):
        signed_move = (future_close - entry) * direction_sign / atr

    net = np.where(
        tp_wins,
        tp - fee,
        np.where(sl_wins, -sl - fee, signed_move - fee),
    )

    label = (net > 0).astype(np.int8)
    # Rows without a full forward window have NaN forward candles (their scan
    # truncated early, and the timeout move is NaN) — drop them rather than
    # trust a partial horizon. ATR>0 is required for ATR-normalised P&L.
    valid = np.isfinite(net) & (atr > 0)

    out = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(frame["timestamp"].to_numpy(), utc=True),
            "label": label,
            "net_atr": net,
            "fee_atr": fee,
            "resolved": np.where(tp_wins, "tp", np.where(sl_wins, "sl", "timeout")),
        }
    )
    return out[valid].reset_index(drop=True)
