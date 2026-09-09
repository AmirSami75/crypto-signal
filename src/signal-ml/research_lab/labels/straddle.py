"""Breakout-straddle labels (E7): the bet structure that monetises RANGE, not direction.

Structure per candle t (all distances in ATR(t)):
  - two resting STOP entries at close ± trigger_atr
  - first breach fills that side (taker: stop orders execute as market → slippage)
  - from the fill: TP at +tp_atr, SL at -sl_atr (adverse-wins tie), timeout at
    close[t+H] (market)
  - both triggers on the SAME candle = whipsaw; charged as a full stop-loss on one
    leg (conservative — real outcome is path-dependent and unknowable from OHLC)
  - neither trigger within H → no trade (row dropped: nothing was risked)

Net outcome in ATR minus costs: taker fee + slippage on entry, TP as resting limit
(fee only), SL/timeout as market (fee + slippage). Also returns `range_atr`, the
realised (MFE+MAE) path range that a vol predictor will target.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class StraddleConfig:
    trigger_atr: float
    take_profit_atr: float
    stop_loss_atr: float
    max_horizon: int
    fee_rate: float
    slippage_rate: float


def label_straddle(frame: pd.DataFrame, cfg: StraddleConfig) -> pd.DataFrame:
    high = frame["high"].to_numpy(dtype=np.float64)
    low = frame["low"].to_numpy(dtype=np.float64)
    close = frame["close"].to_numpy(dtype=np.float64)
    atr = frame["atr"].to_numpy(dtype=np.float64)
    n = len(frame)
    H = cfg.max_horizon
    NOT = H + 1

    up_trig = close + cfg.trigger_atr * atr
    dn_trig = close - cfg.trigger_atr * atr

    def fwd(arr: np.ndarray, h: int) -> np.ndarray:
        out = np.full(n, np.nan)
        if h < n:
            out[: n - h] = arr[h:]
        return out

    # ---- phase 1: which trigger fires first ----
    up_first = np.full(n, NOT, dtype=np.int32)
    dn_first = np.full(n, NOT, dtype=np.int32)
    with np.errstate(invalid="ignore"):
        for h in range(1, H + 1):
            fh, fl = fwd(high, h), fwd(low, h)
            up_first = np.where((fh >= up_trig) & (up_first == NOT), h, up_first).astype(np.int32)
            dn_first = np.where((fl <= dn_trig) & (dn_first == NOT), h, dn_first).astype(np.int32)

    triggered = (up_first <= H) | (dn_first <= H)
    whipsaw = triggered & (up_first == dn_first)
    go_long = triggered & ~whipsaw & (up_first < dn_first)
    go_short = triggered & ~whipsaw & (dn_first < up_first)
    sign = np.where(go_long, 1.0, np.where(go_short, -1.0, 0.0))
    h0 = np.where(go_long, up_first, np.where(go_short, dn_first, NOT)).astype(np.int32)
    entry = np.where(go_long, up_trig, np.where(go_short, dn_trig, np.nan))

    tp_price = entry + sign * cfg.take_profit_atr * atr
    sl_price = entry - sign * cfg.stop_loss_atr * atr

    # ---- phase 2: bracket from the fill candle onward (h > h0) ----
    tp_first = np.full(n, NOT, dtype=np.int32)
    sl_first = np.full(n, NOT, dtype=np.int32)
    with np.errstate(invalid="ignore"):
        for h in range(1, H + 1):
            fh, fl = fwd(high, h), fwd(low, h)
            active = (sign != 0) & (h > h0)
            hit_tp = np.where(sign > 0, fh >= tp_price, fl <= tp_price) & active
            hit_sl = np.where(sign > 0, fl <= sl_price, fh >= sl_price) & active
            tp_first = np.where(hit_tp & (tp_first == NOT), h, tp_first).astype(np.int32)
            sl_first = np.where(hit_sl & (sl_first == NOT), h, sl_first).astype(np.int32)

    touched = (tp_first <= H) | (sl_first <= H)
    tp_wins = (tp_first < sl_first) & touched           # adverse-wins tie
    sl_wins = touched & ~tp_wins

    future_close = fwd(close, H)
    with np.errstate(invalid="ignore", divide="ignore"):
        timeout_move = (future_close - entry) * sign / atr
        # costs in ATR: entry taker (fee+slip); exit: TP limit (fee), SL/timeout market (fee+slip)
        entry_cost = (cfg.fee_rate + cfg.slippage_rate) * np.abs(entry) / atr
        exit_cost_limit = cfg.fee_rate * np.abs(entry) / atr
        exit_cost_market = (cfg.fee_rate + cfg.slippage_rate) * np.abs(entry) / atr
        whipsaw_cost = (2 * cfg.fee_rate + 2 * cfg.slippage_rate) * close / atr

        net = np.where(
            whipsaw, -cfg.stop_loss_atr - whipsaw_cost,
            np.where(
                tp_wins, cfg.take_profit_atr - entry_cost - exit_cost_limit,
                np.where(
                    sl_wins, -cfg.stop_loss_atr - entry_cost - exit_cost_market,
                    timeout_move - entry_cost - exit_cost_market,
                ),
            ),
        )

        # realised path range over the full horizon (for the vol target)
        best = np.full(n, -np.inf)
        worst = np.full(n, np.inf)
        for h in range(1, H + 1):
            best = np.fmax(best, fwd(high, h))
            worst = np.fmin(worst, fwd(low, h))
        range_atr = (best - worst) / atr

    valid = np.isfinite(range_atr) & (atr > 0)
    valid[n - H:] = False
    traded = valid & (triggered)
    resolved = np.where(whipsaw, "whipsaw", np.where(tp_wins, "tp", np.where(sl_wins, "sl",
                        np.where(triggered, "timeout", "no_trigger"))))

    out = pd.DataFrame({
        "timestamp": pd.to_datetime(frame["timestamp"].to_numpy(), utc=True),
        "range_atr": range_atr,
        "traded": traded,
        "net_atr": np.where(traded, net, 0.0),
        "resolved": resolved,
        "direction": sign,
    })
    return out[valid].reset_index(drop=True)
