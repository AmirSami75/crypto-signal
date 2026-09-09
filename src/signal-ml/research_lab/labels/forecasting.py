"""Forecasting targets (§7): future return, MFE, MAE over a horizon.

All three are computed from the FORWARD window [t+1, t+horizon] only, so they
are legitimate prediction targets. They are auxiliary heads for the multi-task
TCN; the economic gate still consumes only the direction head.

- future_log_return: log(close[t+h] / close[t])
- mfe_atr: max favourable excursion for the bet's direction, in ATR
- mae_atr: max adverse excursion for the bet's direction, in ATR (positive number)
Rows lacking a full forward window are NaN (caller drops them).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def forecasting_targets(
    frame: pd.DataFrame, direction_sign: int, horizon: int
) -> pd.DataFrame:
    high = frame["high"].to_numpy(dtype=np.float64)
    low = frame["low"].to_numpy(dtype=np.float64)
    close = frame["close"].to_numpy(dtype=np.float64)
    atr = frame["atr"].to_numpy(dtype=np.float64)
    n = len(frame)

    future_close = np.full(n, np.nan)
    if n > horizon:
        future_close[: n - horizon] = close[horizon:]
    with np.errstate(invalid="ignore", divide="ignore"):
        future_log_return = np.log(future_close / close)

    # Running max/min over the forward window via cumulative scan per offset.
    best = np.full(n, -np.inf)
    worst = np.full(n, np.inf)
    for h in range(1, horizon + 1):
        if h >= n:
            break
        fh = np.full(n, np.nan)
        fl = np.full(n, np.nan)
        fh[: n - h] = high[h:]
        fl[: n - h] = low[h:]
        best = np.fmax(best, fh)
        worst = np.fmin(worst, fl)
    best[n - horizon:] = np.nan if n > horizon else best[n - horizon:]
    worst[n - horizon:] = np.nan if n > horizon else worst[n - horizon:]

    with np.errstate(invalid="ignore", divide="ignore"):
        if direction_sign > 0:
            mfe = (best - close) / atr
            mae = (close - worst) / atr
        else:
            mfe = (close - worst) / atr
            mae = (best - close) / atr

    return pd.DataFrame({
        "timestamp": pd.to_datetime(frame["timestamp"].to_numpy(), utc=True),
        "future_log_return": future_log_return * direction_sign,
        "mfe_atr": mfe,
        "mae_atr": mae,
    })
