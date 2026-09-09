"""E7 — volatility-targeting breakout straddle at 15m.

Thesis (E6 consequence): the model can predict RANGE (+9% over mean) but not
direction. A breakout straddle is the bet that pays on range: stop entries both
sides, ride the breach. Direction is decided by the market, not the model; the
model's job is to pick the candles whose forward range will be large enough to
clear trigger + costs.

Design:
- Labels: `label_straddle` (net ATR outcome incl. whipsaw penalty, taker entry,
  limit TP, market SL/timeout). Target for the model: `range_atr` (regression).
- Model: HGB regressor on the same 39 causal features (the E6 forecasting result
  says trees on these features can rank excursion).
- Policy: trade the straddle only when predicted range >= threshold.
- Unconditional straddle (trade every candle) is the sanity baseline: if the
  filtered policy is not better than unconditional, prediction adds nothing.
- Split-half holdout: choose the threshold on half A (best expectancy with
  >=100 trades), report half B. Gate on B: expectancy>0 AND PF>1 AND >=30 trades.
- Grid: trigger {0.5, 0.75, 1.0} × (tp, sl) {(1.5,1.0),(2.0,1.0),(1.0,0.75)} —
  small on purpose (§13 multiple-testing); every cell is reported, PASS or not.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

_LAB = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_LAB / "src"))
sys.path.insert(0, str(_LAB))

from crypto_signal.config import load_config  # noqa: E402
from crypto_signal.data import load_ohlcv  # noqa: E402
from crypto_signal.features import WARMUP_COLUMNS, build_features  # noqa: E402
from research_lab.labels.straddle import StraddleConfig, label_straddle  # noqa: E402
from sklearn.ensemble import HistGradientBoostingRegressor  # noqa: E402

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
HORIZON = 48  # 12h at 15m
NON_FEATURE = {"timestamp", "symbol", "open", "high", "low", "close", "atr",
               "range_atr", "traded", "net_atr", "resolved", "direction"}


def load_features() -> dict[str, pd.DataFrame]:
    out = {}
    for symbol in SYMBOLS:
        raw = load_ohlcv(_LAB / "data" / f"{symbol}_15m.csv", "15m")
        feats = build_features(raw, atr_window=14)
        frame = feats.frame.copy()
        frame["timestamp"] = pd.to_datetime(raw["timestamp"].to_numpy(), utc=True)
        for c in ("open", "high", "low", "close"):
            frame[c] = raw[c].astype(float).to_numpy()
        frame["atr"] = feats.atr.to_numpy(dtype=np.float64)
        warm = feats.frame[list(WARMUP_COLUMNS)].notna().all(axis=1).to_numpy()
        out[symbol] = frame[warm & (frame["atr"] > 0)].reset_index(drop=True)
        print(f"  {symbol}: {len(out[symbol]):,} candles", flush=True)
    return out


def stats(net: np.ndarray) -> dict:
    if len(net) == 0:
        return {"trades": 0, "expectancy_atr": None, "pf": None, "win_rate": None}
    wins, losses = net[net > 0], net[net < 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else None
    return {"trades": int(len(net)), "expectancy_atr": round(float(net.mean()), 4),
            "pf": round(pf, 3) if pf is not None else None,
            "win_rate": round(float((net > 0).mean()), 4)}


def main() -> int:
    started = time.perf_counter()
    config = load_config(_LAB / "config.2y.toml")
    fee, slip = config.backtest.fee_rate, config.backtest.slippage_rate
    features = load_features()
    feature_columns = [c for c in features["BTCUSDT"].columns if c not in NON_FEATURE]

    grid = [(trig, tp, sl) for trig in (0.5, 0.75, 1.0) for tp, sl in ((1.5, 1.0), (2.0, 1.0), (1.0, 0.75))]
    results = []
    range_model_fitted = False
    for trig, tp, sl in grid:
        cfg = StraddleConfig(trigger_atr=trig, take_profit_atr=tp, stop_loss_atr=sl,
                             max_horizon=HORIZON, fee_rate=fee, slippage_rate=slip)
        pieces = []
        for symbol, frame in features.items():
            lab = label_straddle(frame, cfg)
            merged = frame.merge(lab, on="timestamp", how="inner")
            merged["symbol"] = symbol
            pieces.append(merged)
        ds = pd.concat(pieces, ignore_index=True)
        ds = ds.iloc[np.argsort(ds["timestamp"].to_numpy(), kind="stable")].reset_index(drop=True)
        cut = int(len(ds) * (1.0 - config.barrier.holdout_fraction))
        purge = HORIZON * len(SYMBOLS)
        dev, hold = ds.iloc[: cut - purge], ds.iloc[cut + purge:]

        # Range model is geometry-independent (range_atr is the same target for all
        # cells) — fit once on the first cell's dev split and reuse predictions.
        if not range_model_fitted:
            reg = HistGradientBoostingRegressor(max_iter=300, max_leaf_nodes=31, learning_rate=0.05,
                                                min_samples_leaf=200, l2_regularization=1.0,
                                                early_stopping=False, random_state=42)
            reg.fit(dev[feature_columns], dev["range_atr"].to_numpy())
            pred_hold = reg.predict(hold[feature_columns])
            y_hold = hold["range_atr"].to_numpy()
            mae_model = float(np.mean(np.abs(pred_hold - y_hold)))
            mae_mean = float(np.mean(np.abs(y_hold - dev["range_atr"].mean())))
            corr = float(np.corrcoef(pred_hold, y_hold)[0, 1])
            print(f"range model: holdout MAE {mae_model:.4f} vs mean-baseline {mae_mean:.4f} "
                  f"(gain {1 - mae_model / mae_mean:.1%}), corr {corr:.3f}", flush=True)
            range_model_fitted = True
            pred_lookup = pd.Series(
                pred_hold, index=pd.MultiIndex.from_arrays([hold["symbol"], hold["timestamp"]])
            )
        hold = hold.copy()
        keys = pd.MultiIndex.from_arrays([hold["symbol"], hold["timestamp"]])
        hold["pred_range"] = pred_lookup.reindex(keys).to_numpy()
        assert not np.isnan(hold["pred_range"]).any(), "prediction lookup missed rows"

        mid = len(hold) // 2
        A, B = hold.iloc[:mid], hold.iloc[mid:]
        uncond_B = stats(B.loc[B["traded"], "net_atr"].to_numpy())

        # choose threshold on A: quantiles of predicted range
        best_thr, best_exp = None, -np.inf
        for q in (0.5, 0.6, 0.7, 0.8, 0.9, 0.95):
            thr = float(np.quantile(A["pred_range"], q))
            sel = A[(A["pred_range"] >= thr) & A["traded"]]
            if len(sel) >= 100 and sel["net_atr"].mean() > best_exp:
                best_exp, best_thr, best_q = float(sel["net_atr"].mean()), thr, q
        if best_thr is None:
            cell = {"trigger": trig, "tp": tp, "sl": sl, "uncond_B": uncond_B,
                    "filtered_B": None, "note": "no threshold with >=100 trades on A"}
        else:
            selB = B[(B["pred_range"] >= best_thr) & B["traded"]]
            filt_B = stats(selB["net_atr"].to_numpy())
            outcomes = selB["resolved"].value_counts(normalize=True).round(3).to_dict()
            cell = {"trigger": trig, "tp": tp, "sl": sl, "threshold_q": best_q,
                    "A_expectancy": round(best_exp, 4), "uncond_B": uncond_B,
                    "filtered_B": filt_B, "B_outcomes": outcomes}
        results.append(cell)
        fb = cell.get("filtered_B") or {}
        print(f"  trig {trig} tp {tp} sl {sl} | uncond B exp {uncond_B['expectancy_atr']} "
              f"pf {uncond_B['pf']} n {uncond_B['trades']} | filtered B exp {fb.get('expectancy_atr')} "
              f"pf {fb.get('pf')} n {fb.get('trades')}", flush=True)

    passing = [c for c in results if c.get("filtered_B") and c["filtered_B"]["expectancy_atr"] is not None
               and c["filtered_B"]["expectancy_atr"] > 0 and (c["filtered_B"]["pf"] or 0) > 1.0
               and c["filtered_B"]["trades"] >= 30]
    verdict = "PASS" if passing else "REJECT"
    meta = {"grid_cells": len(grid), "results": results, "passing_cells": passing, "verdict": verdict,
            "range_model": {"mae": mae_model, "mae_mean_baseline": mae_mean, "corr": corr},
            "seconds": round(time.perf_counter() - started)}
    (_LAB / "research_lab" / "results" / "e7_meta.json").write_text(json.dumps(meta, indent=2, default=str))
    print(f"E7 VERDICT: {verdict} | passing cells {len(passing)}/{len(grid)} ({meta['seconds']}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
