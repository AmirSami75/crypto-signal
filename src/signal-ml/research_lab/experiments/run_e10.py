"""E10 — vol-targeted entry gate on the incumbent (the deployable version of E7's finding).

E6/E7 proved the lab's one real skill: predicting forward RANGE (+9-12% MAE vs mean).
E7 also showed high-range candles whipsaw. Question for deployment: does gating the
INCUMBENT 1h policy (confidence >= 0.40) to skip high-predicted-range candles improve
its net expectancy on a strict holdout? This is the incumbent's own data, its own
labels, its own floor — only the vol gate is new.

- Data: the production universe (config.2y.toml, 35 symbols, 1h spot klines — the same
  data the incumbent trained on).
- Range model: HGB regressor, same feature pipeline as production, target =
  forward range/ATR over 24 candles. Split-half: fit thresholds on dev, evaluate on
  the last 20% (strict holdout, purged).
- Gate cells (declared): skip candles with predicted range above dev quantile
  q in {0.90, 0.95, 1.00(=no gate)} x confidence floor {0.40, 0.50}.
- Deploy gate: a gated cell must beat the same floor ungated on expectancy AND PF,
  with >= 200 trades on holdout. If no cell qualifies, ship the range model as a
  monitoring signal only (dashboard), keep incumbent policy untouched.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

_LAB = Path(__file__).resolve().parents[2]  # signal-ml root
sys.path.insert(0, str(_LAB / "src"))
sys.path.insert(0, str(_LAB))

from crypto_signal.config import load_config  # noqa: E402
from crypto_signal.data import load_ohlcv  # noqa: E402
from crypto_signal.features import WARMUP_COLUMNS, build_features  # noqa: E402
from research_lab.labels.fee_aware import FeeAwareConfig, label_symbol  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor  # noqa: E402
from sklearn.metrics import log_loss, roc_auc_score  # noqa: E402

H = 24  # 24h horizon at 1h
RNG = np.random.default_rng(5)


def build(symbol: str, fee_cfg: FeeAwareConfig, atr_window: int) -> pd.DataFrame:
    raw = load_ohlcv(_LAB / "data" / f"{symbol}_1h.csv", "1h")
    feats = build_features(raw, atr_window=atr_window)
    df = feats.frame.copy()
    df["timestamp"] = pd.to_datetime(raw["timestamp"].to_numpy(), utc=True)
    for c in ("open", "high", "low", "close"):
        df[c] = raw[c].astype(float).to_numpy()
    df["atr"] = feats.atr.to_numpy(dtype=np.float64)
    warm = feats.frame[list(WARMUP_COLUMNS)].notna().all(axis=1).to_numpy()
    df = df[warm & (df["atr"] > 0)].reset_index(drop=True)
    # forward range target (causal: uses only [t+1, t+H])
    hi, lo = df["high"].to_numpy(), df["low"].to_numpy()
    best, worst = np.full(len(df), -np.inf), np.full(len(df), np.inf)
    for h in range(1, H + 1):
        if h >= len(df):
            break
        best[: len(df) - h] = np.fmax(best[: len(df) - h], hi[h:])
        worst[: len(df) - h] = np.fmin(worst[: len(df) - h], lo[h:])
    with np.errstate(invalid="ignore", divide="ignore"):
        df["fwd_range_atr"] = (best - worst) / df["atr"].to_numpy()
    sign = +1  # incumbent scores the long side; net label from fee_aware
    labelled = label_symbol(df[["timestamp", "open", "high", "low", "close", "atr"]], sign, fee_cfg)
    df = df.merge(labelled[["timestamp", "label", "net_atr", "resolved", "fee_atr"]], on="timestamp", how="inner")
    df["symbol"] = symbol
    return df


def stats(net: np.ndarray) -> dict:
    if len(net) == 0:
        return {"trades": 0, "expectancy": None, "pf": None}
    w, l = net[net > 0], net[net < 0]
    pf = float(w.sum() / -l.sum()) if l.sum() < 0 else None
    return {"trades": int(len(net)), "expectancy": round(float(net.mean()), 4),
            "pf": round(pf, 3) if pf is not None else None}


def main() -> int:
    started = time.perf_counter()
    config = load_config(_LAB / "config.2y.toml")
    barrier = config.barrier
    fee_cfg = FeeAwareConfig(take_profit_atr=barrier.backtest_take_profit_atr,
                             stop_loss_atr=barrier.backtest_stop_loss_atr,
                             max_horizon=H, fee_rate=config.backtest.fee_rate,
                             slippage_rate=config.backtest.slippage_rate)
    non_feature = {"timestamp", "symbol", "open", "high", "low", "close", "atr",
                   "label", "net_atr", "resolved", "fee_atr", "fwd_range_atr"}
    parts, rng_parts = [], []
    for symbol in config.market.symbols:
        df = build(symbol, fee_cfg, barrier.atr_window)
        parts.append(df)
        rng_parts.append(df[["timestamp", "fwd_range_atr"]].assign(symbol=symbol))
        print(f"  {symbol}: {len(df):,}", flush=True)
    ds = pd.concat(parts, ignore_index=True)
    ds = ds.iloc[np.argsort(ds["timestamp"].to_numpy(), kind="stable")].reset_index(drop=True)
    cols = [c for c in ds.columns if c not in non_feature]

    cut = int(len(ds) * (1.0 - barrier.holdout_fraction))
    purge = H * len(config.market.symbols)
    dev, hold = ds.iloc[: cut - purge], ds.iloc[cut + purge:].copy()

    # range model on dev (dev-split-half for thresholds), scored on hold
    reg = HistGradientBoostingRegressor(max_iter=300, max_leaf_nodes=31, learning_rate=0.05,
                                        min_samples_leaf=200, l2_regularization=1.0,
                                        early_stopping=False, random_state=42)
    valid = dev[np.isfinite(dev["fwd_range_atr"])]
    reg.fit(valid[cols], valid["fwd_range_atr"].to_numpy())
    hold["pred_range"] = reg.predict(hold[cols])
    y = valid["fwd_range_atr"].to_numpy()
    p = hold["pred_range"].to_numpy()
    yh = hold["fwd_range_atr"].to_numpy()
    ok = np.isfinite(yh)
    mae_model = float(np.mean(np.abs(p[ok] - yh[ok])))
    mae_base = float(np.mean(np.abs(yh[ok] - valid["fwd_range_atr"].mean())))
    print(f"range model: holdout MAE {mae_model:.3f} vs mean {mae_base:.3f} "
          f"(gain {1 - mae_model / mae_base:.1%})", flush=True)

    clf = HistGradientBoostingClassifier(max_iter=300, max_leaf_nodes=31, learning_rate=0.05,
                                         min_samples_leaf=200, l2_regularization=1.0,
                                         early_stopping=False, random_state=42)
    clf.fit(dev[cols], dev["label"].to_numpy())
    hold["p"] = clf.predict_proba(hold[cols])[:, 1]
    y = hold["label"].to_numpy()
    base = float(dev["label"].mean())
    ll, llb = float(log_loss(y, hold["p"])), float(log_loss(y, np.full(len(hold), base)))
    print(f"incumbent check: LL {ll:.4f} vs base {llb:.4f} AUC {roc_auc_score(y, hold['p']):.4f}", flush=True)

    # thresholds from dev half, evaluated on hold
    dv = np.isfinite(dev["fwd_range_atr"])
    q90 = float(np.quantile(dev.loc[dv, "fwd_range_atr"], 0.90))
    q95 = float(np.quantile(dev.loc[dv, "fwd_range_atr"], 0.95))

    rows = []
    for floor in (0.40, 0.50):
        for name, thr in (("no-gate", np.inf), ("skip>=q90", q90), ("skip>=q95", q95)):
            sel = hold[(hold["p"] >= floor) & (hold["pred_range"] < thr)]
            s = stats(sel["net_atr"].to_numpy())
            whips = sel["resolved"].value_counts(normalize=True).get("sl", 0.0)
            rows.append({"floor": floor, "gate": name, **s, "sl_share": round(float(whips), 3)})
            print(f"floor {floor} {name:9s}: n {s['trades']:6d} exp {s['expectancy']} pf {s['pf']} sl% {whips:.3f}", flush=True)

    verdict_cells = []
    for floor in (0.40, 0.50):
        base_cell = next(r for r in rows if r["floor"] == floor and r["gate"] == "no-gate")
        for r in rows:
            if r["floor"] == floor and r["gate"] != "no-gate":
                better = (r["expectancy"] or -9) > (base_cell["expectancy"] or 9) and \
                         (r["pf"] or 0) > (base_cell["pf"] or 9) and r["trades"] >= 200
                if better:
                    verdict_cells.append(r)
    report = {"range_mae_gain": round(1 - mae_model / mae_base, 4), "q90": round(q90, 3),
              "q95": round(q95, 3), "ll": ll, "ll_base": llb, "cells": rows,
              "deployable_cells": verdict_cells,
              "verdict": "PASS" if verdict_cells else "REJECT",
              "seconds": round(time.perf_counter() - started)}
    (_LAB / "research_lab" / "results" / "e10_meta.json").write_text(json.dumps(report, indent=2, default=str))
    print(f"E10 VERDICT: {report['verdict']} ({report['seconds']}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
