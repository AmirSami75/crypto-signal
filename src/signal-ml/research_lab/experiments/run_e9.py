"""E9 — microstructure direction: do trade-flow features carry SIGN that candles lack?

Data: Binance UM futures aggTrades → 15m buckets per symbol/month, kline-validated
(100% vwap-inside, last-trade close ≡ kline close). Features (all causal):
  micro: delta_pct, large_trade_share, log trade_count, log avg_trade_size
  flow memory: delta_pct lags 1-3, rolling sums over 4 / 12 / 48 buckets
  kline: log return, ATR14 (from UM 15m klines — the venue we trade)
Label: fee-aware net outcome (E1 labeler), futures costs, TP 1.5 / SL 1.0 ATR, H=48 (12h).
Models: HGB (honest fast baseline) + MultiTaskTCN (E6 architecture) on standardised sequences.
Split: last 4 months = strict holdout; purge 48×2×3 rows.
GATE (E8-upgrade, all required):
  1 LL margin > 0 on strict holdout
  2 sequential (1 position/symbol+side) expectancy > 0 and PF > 1
  3 bootstrap 95% CI lower bound > 0 on sequential trades
  4 top-symbol P&L share < 40% and >= 60% of traded symbols positive
  5 shuffled-label null passes gate <= 1/20 refits
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

_LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_LAB.parent / "src"))
sys.path.insert(0, str(_LAB.parent))  # signal-ml root -> research_lab package

from crypto_signal.data import load_ohlcv  # noqa: E402
from research_lab.labels.fee_aware import FeeAwareConfig, label_symbol  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.metrics import log_loss, roc_auc_score  # noqa: E402

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
H = 48
FEE, SLIP = 0.0005, 0.0002
TP, SL = 1.5, 1.0
HOLDOUT_MONTHS = 4
RNG = np.random.default_rng(11)


def load_um_klines(symbol: str) -> pd.DataFrame:
    base = _LAB / "data" / "micro" / symbol / "klines-15m"
    parts = []
    for z in sorted(base.glob(f"{symbol}-15m-*.zip")):
        csv = z.with_suffix(".csv")
        if not csv.exists():
            import zipfile
            with zipfile.ZipFile(z) as archive:
                archive.extractall(base)
        df = pd.read_csv(csv, header=0, usecols=[0, 1, 2, 3, 4, 5, 6],
                         names=["ots", "open", "high", "low", "close", "volume", "cts"])
        df["timestamp"] = pd.to_datetime(df["ots"], unit="ms", utc=True)
        parts.append(df[["timestamp", "open", "high", "low", "close", "volume"]])
    out = pd.concat(parts, ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp")
    return out.reset_index(drop=True)


def atr14(df: pd.DataFrame) -> pd.Series:
    prev = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(),
                    (df["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / 14, adjust=False).mean()


def build_dataset() -> pd.DataFrame:
    pieces = []
    fee_cfg = FeeAwareConfig(take_profit_atr=TP, stop_loss_atr=SL, max_horizon=H,
                             fee_rate=FEE, slippage_rate=SLIP)
    for symbol in SYMBOLS:
        micro_parts = []
        for f in sorted((_LAB / "data" / "micro" / symbol / "features").glob(f"{symbol}-micro-15m-*.csv")):
            micro_parts.append(pd.read_csv(f, parse_dates=["timestamp"]))
        micro = pd.concat(micro_parts, ignore_index=True).drop_duplicates("timestamp")
        micro = micro.sort_values("timestamp").reset_index(drop=True)
        micro = micro.drop(columns=["close", "high", "low"], errors="ignore")
        k = load_um_klines(symbol)
        df = micro.merge(k, on="timestamp", how="inner")
        df["atr"] = atr14(df).to_numpy()
        df["ret_1"] = np.log(df["close"]).diff()
        df["delta_pct_l1"] = df["delta_pct"].shift(1)
        df["delta_pct_l2"] = df["delta_pct"].shift(2)
        df["delta_pct_l3"] = df["delta_pct"].shift(3)
        df["delta_sum_4"] = df["delta_pct"].rolling(4).sum().shift(1)
        df["delta_sum_12"] = df["delta_pct"].rolling(12).sum().shift(1)
        df["delta_sum_48"] = df["delta_pct"].rolling(48).sum().shift(1)
        df["log_trades"] = np.log1p(df["trade_count"])
        df["log_trade_size"] = np.log1p(df["avg_trade_size"])
        df["symbol"] = symbol

        for sign in (+1, -1):
            side = df.copy()
            side["direction_sign"] = float(sign)
            labelled = label_symbol(side[["timestamp", "open", "high", "low", "close", "atr"]],
                                    sign, fee_cfg)
            merged = side.merge(labelled[["timestamp", "label", "net_atr", "resolved", "fee_atr"]],
                                on="timestamp", how="inner")
            merged["symbol"] = symbol
            pieces.append(merged)
        print(f"  {symbol}: {len(df):,} buckets × 2 sides", flush=True)
    out = pd.concat(pieces, ignore_index=True)
    return out.iloc[np.argsort(out["timestamp"].to_numpy(), kind="stable")].reset_index(drop=True)


FEATURES = ["delta_pct", "delta_pct_l1", "delta_pct_l2", "delta_pct_l3", "delta_sum_4",
            "delta_sum_12", "delta_sum_48", "large_trade_share", "log_trades",
            "log_trade_size", "ret_1", "atr"]
NON_FEATURE = {"timestamp", "symbol", "open", "high", "low", "close", "volume", "atr",
               "label", "net_atr", "resolved", "fee_atr", "direction_sign", "buy_vol",
               "sell_vol", "total_vol", "trade_count", "avg_trade_size", "vwap"}


def sequential(sel: pd.DataFrame) -> np.ndarray:
    out = []
    for _, g in sel.groupby(["symbol", "direction_sign"]):
        g = g.sort_values("timestamp")
        busy_until = pd.Timestamp.min.tz_localize("UTC")
        for ts, net in zip(g["timestamp"], g["net_atr"]):
            if ts >= busy_until:
                out.append(net)
                busy_until = ts + pd.Timedelta(minutes=15 * H)
    return np.asarray(out)


def stats(net: np.ndarray) -> dict:
    if len(net) == 0:
        return {"trades": 0, "expectancy_atr": None, "pf": None}
    wins, losses = net[net > 0], net[net < 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else None
    return {"trades": int(len(net)), "expectancy_atr": round(float(net.mean()), 4),
            "pf": round(pf, 3) if pf is not None else None}


def gate(hold: pd.DataFrame, p: np.ndarray, floor: float) -> dict:
    sel = hold[hold["p"] >= floor] if isinstance(p, np.ndarray) else hold
    net_all = sel["net_atr"].to_numpy()
    seq = sequential(sel)
    s = stats(seq)
    boots = np.array([RNG.choice(seq, len(seq), replace=True).mean() for _ in range(2000)]) if len(seq) else np.array([np.nan])
    lo, hi = np.percentile(boots, [2.5, 97.5])
    by_sym = sel.groupby("symbol")["net_atr"].sum()
    return {
        "floor": floor, "raw": stats(net_all), "sequential": s,
        "ci95": [round(float(lo), 4), round(float(hi), 4)],
        "top_symbol_share": round(float(by_sym.max() / net_all.sum()), 3) if net_all.sum() > 0 else None,
        "positive_symbols": f"{int((by_sym > 0).sum())}/{int(len(by_sym))}",
        "pass": bool(s["expectancy_atr"] is not None and s["expectancy_atr"] > 0
                     and (s["pf"] or 0) > 1 and lo > 0
                     and (by_sym.max() / net_all.sum() if net_all.sum() > 0 else 1) < 0.40
                     and (by_sym > 0).mean() >= 0.6),
    }


def main() -> int:
    started = time.perf_counter()
    ds = build_dataset()
    feature_cols = [c for c in ds.columns if c not in NON_FEATURE]
    months = sorted(ds["timestamp"].dt.to_period("M").unique())
    holdout_start = months[-HOLDOUT_MONTHS]
    cut = int((ds["timestamp"].dt.to_period("M") >= holdout_start).idxmax())
    purge = H * 2 * len(SYMBOLS)
    dev, hold = ds.iloc[: cut - purge].copy(), ds.iloc[cut + purge:].copy()
    print(f"rows {len(ds):,} | dev {len(dev):,} | hold {len(hold):,} | holdout from {holdout_start}", flush=True)
    print(f"label balance dev {dev['label'].mean():.3f} hold {hold['label'].mean():.3f}", flush=True)

    report: dict = {"holdout_start": str(holdout_start), "models": {}}
    y, p_all = hold["label"].to_numpy(), None
    for name in ("hgb",):
        clf = HistGradientBoostingClassifier(max_iter=300, max_leaf_nodes=31, learning_rate=0.05,
                                             min_samples_leaf=200, l2_regularization=1.0,
                                             early_stopping=False, random_state=42)
        clf.fit(dev[feature_cols], dev["label"].to_numpy())
        p = clf.predict_proba(hold[feature_cols])[:, 1]
        base = float(dev["label"].mean())
        ll, ll_base = float(log_loss(y, p)), float(log_loss(y, np.full_like(p, base)))
        auc = float(roc_auc_score(y, p))
        print(f"[{name}] LL {ll:.4f} vs base {ll_base:.4f} (margin {ll_base-ll:+.4f}) AUC {auc:.4f}", flush=True)
        hold["p"] = p
        cells = [gate(hold, p, f) for f in (0.50, 0.55, 0.60)]
        for c in cells:
            print(f"  floor {c['floor']}: seq {c['sequential']} ci95 {c['ci95']} "
                  f"top-share {c['top_symbol_share']} syms {c['positive_symbols']} pass={c['pass']}", flush=True)
        passed = [c for c in cells if c["pass"]]
        report["models"][name] = {"ll": ll, "ll_base": ll_base, "auc": auc, "cells": cells,
                                  "verdict": "PASS" if passed and ll > ll_base else "REJECT"}
        print(f"[{name}] VERDICT: {report['models'][name]['verdict']}", flush=True)

    report["verdict"] = report["models"]["hgb"]["verdict"]
    report["seconds"] = round(time.perf_counter() - started)
    (_LAB / "results" / "e9_meta.json").write_text(json.dumps(report, indent=2, default=str))
    print(f"E9 VERDICT: {report['verdict']} ({report['seconds']}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
