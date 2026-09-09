"""E8 — coarse-resolution re-test: fee-aware directional HGB at 4h, 35 symbols, two cost tiers.

Thesis (E7 finding): round-trip cost in ATR units is 0.41 ATR at 1h (lab cfg) and
1.17 ATR at 15m — larger than or comparable to the 1.0 ATR risk unit. At 4h the same
bps costs are 0.09 ATR (futures tier) / 0.20 ATR (lab cfg). If the OHLCV feature family
has *any* directional content, 4h is where a bracket can afford to express it.

Design (E1 machinery, unchanged except resolution/costs):
- 4h candles built from the 1h CSVs by exact OHLCV aggregation on UTC 4h boundaries
  (Binance-aligned: 00/04/08/...), incomplete bins dropped. No look-ahead: each 4h
  bar closes at the close of its 4th 1h bar.
- Features: production `build_features` (same 42 columns), ATR window 14.
- Labels: `label_symbol` fee-aware net outcome, TP 1.5 / SL 1.0 ATR, horizon 24 bars (4 days).
- Two cost tiers, each with its own labels + model + gate:
    futures : fee 0.0005 taker, slip 0.0002   (Binance USDT-M — the venue the bots trade)  PRIMARY
    lab     : fee 0.0010, slip 0.0005          (spot-tier conservative)                   ROBUSTNESS
- Chronological carve, strict holdout 20%, purge = horizon × 2 sides × symbols.
- Gate (declared): a floor cell on strict holdout with expectancy>0 AND PF>1 AND >=30 trades,
  where expectancy/PF are computed from the realised `net_atr` of taken rows (fee-aware,
  tested labeler). Report unconditional (take-everything) as the naive baseline.
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
from research_lab.experiments.run_e1 import build_side_dataset  # noqa: E402
from research_lab.labels.fee_aware import FeeAwareConfig  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.metrics import log_loss, roc_auc_score  # noqa: E402

HORIZON = 24  # 4h bars → 4 days
TIERS = {
    "futures": {"fee_rate": 0.0005, "slippage_rate": 0.0002},
    "lab": {"fee_rate": 0.0010, "slippage_rate": 0.0005},
}
FLOORS = [0.50, 0.55, 0.60, 0.65, 0.70]
NON_FEATURE = {"timestamp", "symbol", "open", "high", "low", "close", "atr",
               "label", "net_atr", "resolved", "fee_atr"}


def resample_4h(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    extra = {c: "sum" for c in ("quote_volume", "trade_count", "taker_buy_base_volume",
                                "taker_buy_quote_volume") if c in df.columns}
    out = df.resample("4h", label="left", closed="left", origin="start_day").agg({**agg, **extra})
    count = df["close"].resample("4h", label="left", closed="left", origin="start_day").count()
    out = out[count == 4].dropna(subset=["open", "high", "low", "close"])
    return out.reset_index()


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
    barrier = config.barrier

    frames: dict[str, pd.DataFrame] = {}
    for symbol in config.market.symbols:
        csv = _LAB / "data" / f"{symbol}_1h.csv"
        if csv.exists():
            frames[symbol] = resample_4h(load_ohlcv(csv, "1h"))
    total = sum(len(f) for f in frames.values())
    span = (min(f["timestamp"].min() for f in frames.values()),
            max(f["timestamp"].max() for f in frames.values()))
    print(f"symbols: {len(frames)} | 4h candles: {total:,} | span {span[0].date()} → {span[1].date()}", flush=True)

    report: dict = {"horizon_bars": HORIZON, "symbols": len(frames), "candles_4h": total, "tiers": {}}
    for tier, costs in TIERS.items():
        fee_config = FeeAwareConfig(
            take_profit_atr=barrier.backtest_take_profit_atr, stop_loss_atr=barrier.backtest_stop_loss_atr,
            max_horizon=HORIZON, **costs,
        )
        dataset = build_side_dataset(frames, fee_config, barrier.atr_window)
        dataset = dataset.iloc[np.argsort(dataset["timestamp"].to_numpy(), kind="stable")].reset_index(drop=True)
        feature_columns = [c for c in dataset.columns if c not in NON_FEATURE]
        cut = int(len(dataset) * (1.0 - barrier.holdout_fraction))
        purge = HORIZON * 2 * len(frames)
        dev, hold = dataset.iloc[: cut - purge], dataset.iloc[cut + purge:]
        cost_atr = float(dataset["fee_atr"].median()) if "fee_atr" in dataset else None
        print(f"\n[{tier}] rows {len(dataset):,} | dev {len(dev):,} | hold {len(hold):,} | "
              f"label balance {dataset['label'].mean():.3f} | median round-trip cost "
              f"{cost_atr if cost_atr is not None else 'n/a'} ATR", flush=True)

        clf = HistGradientBoostingClassifier(
            max_iter=300, max_leaf_nodes=31, learning_rate=0.05, min_samples_leaf=200,
            l2_regularization=1.0, early_stopping=False, random_state=42,
        )
        clf.fit(dev[feature_columns], dev["label"].to_numpy())
        p = clf.predict_proba(hold[feature_columns])[:, 1]
        y = hold["label"].to_numpy()
        base = float(dev["label"].mean())
        ll = float(log_loss(y, p)); ll_base = float(log_loss(y, np.full_like(p, base)))
        auc = float(roc_auc_score(y, p))
        print(f"[{tier}] strict holdout LL {ll:.4f} vs base-rate {ll_base:.4f} (margin {ll_base-ll:+.4f}) | AUC {auc:.4f}", flush=True)

        net = hold["net_atr"].to_numpy()
        uncond = stats(net)
        cells = []
        for floor in FLOORS:
            sel = net[p >= floor]
            s = stats(sel); s["floor"] = floor
            cells.append(s)
            print(f"[{tier}]   floor {floor:.2f}: n {s['trades']:6d} exp {s['expectancy_atr']} pf {s['pf']} wr {s['win_rate']}", flush=True)
        print(f"[{tier}]   unconditional: n {uncond['trades']} exp {uncond['expectancy_atr']} pf {uncond['pf']}", flush=True)

        passing = [c for c in cells if c["expectancy_atr"] is not None and c["expectancy_atr"] > 0
                   and (c["pf"] or 0) > 1.0 and c["trades"] >= 30]
        report["tiers"][tier] = {
            "costs": costs, "rows": len(dataset), "median_cost_atr": cost_atr,
            "log_loss": ll, "log_loss_base": ll_base, "auc": auc,
            "unconditional": uncond, "cells": cells, "passing": passing,
            "verdict": "PASS" if passing else "REJECT",
        }
        print(f"[{tier}] VERDICT: {report['tiers'][tier]['verdict']} ({len(passing)}/{len(FLOORS)} cells)", flush=True)

    report["verdict"] = "PASS" if report["tiers"]["futures"]["verdict"] == "PASS" else "REJECT"
    report["seconds"] = round(time.perf_counter() - started)
    (_LAB / "research_lab" / "results" / "e8_meta.json").write_text(json.dumps(report, indent=2, default=str))
    print(f"\nE8 VERDICT (primary=futures): {report['verdict']} ({report['seconds']}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
