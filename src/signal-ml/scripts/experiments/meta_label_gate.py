"""Meta-label go/no-go: does a binary meta-learner pick a holdout subset whose NET
expectancy clears the fee break-even on at least 3 of 7 symbols?

Method:
  1. Build the pooled holdout the production split uses (cut at 80% of timestamp with a
     one-max_horizon purge).
  2. Score every row with the shipped primary model -> p_win = P(class == +1).
  3. Compute net_return_atr per row using realised_return_atr (gross - fee_atr).
  4. Label profitable = net > 0.
  5. Chronological train/eval split (first 60% of holdout -> meta-fit, last 40% -> meta-eval).
     This is in-sample for selection purposes; the plan flags it as such and a positive
     result becomes a forward-paper hypothesis, not a promise.
  6. Sweep meta-floors; report per-symbol n-trades, TP-first rate, and net E[ATR].

Pass criterion (from the plan): at least one floor yields net E[ATR] > +0.05 on >= 3 of
7 symbols with >= 50 trades.
"""

from __future__ import annotations

import json
import os
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import HistGradientBoostingClassifier

warnings.filterwarnings("ignore")

from crypto_signal.config import load_config
from crypto_signal.data import load_ohlcv
from crypto_signal.features import build_features
from crypto_signal.labeling.meta_label import (
    add_meta_labels,
    build_meta_features,
)
from crypto_signal.labeling.triple_barrier import build_barrier_dataset

t0 = time.time()
config = load_config("config.toml")
BUNDLE = joblib.load("artifacts/models/_pooled_1h.joblib")
PRIMARY = BUNDLE["model"]
PRIMARY_FEATURES = list(BUNDLE["feature_columns"])

# Round-trip fee in ATR — match the production backtest so this test and the shipped
# bracket backtest agree. Empirically ~0.30 on the 1.5/1.0 ATR pair (BTC 0.298 from the
# last train report); we use 0.30 to match.
FEE_ATR = 0.30

# Rebuild the pooled frame the production trainer uses.
frames = {}
for s in config.market.symbols:
    raw = load_ohlcv(f"data/{s}_1h.csv", "1h")
    ff = build_features(raw)
    frames[s] = raw.assign(**{c: ff.frame[c] for c in ff.frame.columns})

ds = build_barrier_dataset(frames, interval="1h")
df = ds.frame
features = list(ds.feature_columns)
ts = pd.to_datetime(df["timestamp"], utc=True)
cut = ts.quantile(0.8)
ho = df[ts >= cut].copy()
print(f"holdout rows: {len(ho):,}", flush=True)

# Score with the primary; the argmax class is irrelevant — only P(win) matters for the
# meta-learner.
proba = PRIMARY.predict_proba(ho[features])
p_win = proba[:, 2]  # class +1 = tp-first
ho = add_meta_labels(ho, p_win, fee_atr=FEE_ATR)
print(f"primary scored | profitable rate = {ho['meta_profitable'].mean():.4f}", flush=True)

# Chronological split of the holdout: 60% meta-fit, 40% meta-eval.
ho_ts = pd.to_datetime(ho["timestamp"], utc=True)
meta_cut = ho_ts.quantile(0.6)
meta_tr = ho[ho_ts < meta_cut]
meta_ho = ho[ho_ts >= meta_cut]
print(f"meta-fit rows: {len(meta_tr):,}  meta-eval rows: {len(meta_ho):,}", flush=True)

X_tr = build_meta_features(meta_tr, meta_tr["p_win"].to_numpy()).to_numpy()
y_tr = meta_tr["meta_profitable"].astype(int).to_numpy()
X_ho = build_meta_features(meta_ho, meta_ho["p_win"].to_numpy()).to_numpy()
y_ho = meta_ho["meta_profitable"].astype(int).to_numpy()
sym_ho = meta_ho["symbol"].to_numpy()
net_ho = meta_ho["net_return_atr"].to_numpy()
tp_ho = (meta_ho["target"].to_numpy() == 1).astype(int)

# Tiny meta-learner. Deliberately low capacity: the meta feature set is 5 columns and we
# only need monotone in p_win, so overfitting the gate is the bigger risk.
meta = HistGradientBoostingClassifier(
    learning_rate=0.05,
    max_iter=120,
    max_leaf_nodes=8,
    min_samples_leaf=200,
    l2_regularization=2.0,
    early_stopping=False,
    random_state=42,
)
meta.fit(X_tr, y_tr)
p_meta = meta.predict_proba(X_ho)[:, 1]
print(f"meta fitted | meta-eval profitable rate = {y_ho.mean():.4f}", flush=True)

# Sweep floors.
SYM = config.market.symbols
report: dict = {"meta_floors": [0.50, 0.55, 0.60, 0.65, 0.70], "results": []}
for floor in report["meta_floors"]:
    take = p_meta >= floor
    summary = {"floor": floor, "n_total": int(take.sum()),
                "mean_net_atr": float(net_ho[take].mean()) if take.any() else None,
                "tp_first_rate": float(tp_ho[take].mean()) if take.any() else None}
    per_symbol = {}
    positive_symbols = 0
    for s in SYM:
        m = take & (sym_ho == s)
        if m.sum() < 5:
            per_symbol[s] = {"n": int(m.sum()), "net": None}
            continue
        net = float(net_ho[m].mean())
        if net > 0.05:
            positive_symbols += 1
        per_symbol[s] = {"n": int(m.sum()), "net": round(net, 4),
                          "tp": round(float(tp_ho[m].mean()), 4)}
    summary["per_symbol"] = per_symbol
    summary["positive_symbols"] = positive_symbols
    report["results"].append(summary)
    print(f"floor {floor}: n={summary['n_total']:,}  net={summary['mean_net_atr']}  "
          f"positive_symbols={positive_symbols}/7", flush=True)

# Pass / no-pass verdict.
best = max((r for r in report["results"] if r["n_total"] >= 200),
           key=lambda r: r["positive_symbols"], default=None)
verdict = {
    "passes_plan_criterion": False,
    "best_floor": None,
    "best_positive_symbols": 0,
    "explanation": "",
}
if best is not None:
    verdict["best_floor"] = best["floor"]
    verdict["best_positive_symbols"] = best["positive_symbols"]
    # Re-check the stricter gate: at least 3 symbols, each with n>=50 and net > 0.05.
    n_per = {s: best["per_symbol"][s]["n"] for s in SYM if best["per_symbol"][s].get("net") is not None}
    ok = [s for s in SYM
          if best["per_symbol"][s].get("net") is not None
          and best["per_symbol"][s]["net"] > 0.05
          and best["per_symbol"][s]["n"] >= 50]
    verdict["qualifying_symbols"] = ok
    verdict["passes_plan_criterion"] = len(ok) >= 3
    verdict["explanation"] = (
        f"Best floor = {best['floor']}; qualifying symbols (net>+0.05, n>=50) = {ok}. "
        f"{'PASS' if verdict['passes_plan_criterion'] else 'FAIL'}: "
        + ("proceed to wire meta-label as the serving gate"
           if verdict["passes_plan_criterion"] else
           "model-side fix not available at 1h; record and surface the operational levers (fees, bracket, venue).")
    )
else:
    verdict["explanation"] = (
        "No floor fired >=200 trades on the holdout; the meta-learner did not "
        "concentrate confidence in a way that leaves a gateable subset. FAIL."
    )
report["verdict"] = verdict
print(json.dumps(verdict, indent=1), flush=True)

# Persist the result for the plan + manual review.
out_path = Path("artifacts/meta_label_sweep.json")
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(report, indent=1, default=str))
print(f"wrote {out_path} | total {time.time()-t0:.1f}s", flush=True)