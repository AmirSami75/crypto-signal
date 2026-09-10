"""E12 — vol-proportional position sizing on the incumbent (lab simulation only).

E10 showed binary skip-gates on predicted range buy only +0.011 ATR. E12 asks the
softer question: instead of blocking trades, scale them by predicted range.

- Data: the production universe (config.2y.toml, 35 symbols, 1h spot klines), the
  incumbent's own fee-aware labels, 0.40 floor (plus 0.50 as secondary).
- Range model: HGB regressor, same feature pipeline as production, target =
  forward range/ATR over 24 candles. Median fitted on dev, evaluated on the last
  20% (strict holdout, purged).
- Policy: size = clip(pred_range / median_range, 0.5, 2.0) x base notional;
  compare vs flat sizing (size = 1) on the same strict holdout by
  expectancy-per-unit-risk, risk-adjusted expectancy (expectancy / stdev), and
  max drawdown of the exposure-normalized equity curve.
- Deploy gate: sizing must improve risk-adjusted expectancy vs flat with >= 200
  trades and no worse max drawdown. Else dashboard-only verdict (range-based
  size signal to dashboard, flat sizing unchanged).

No serving-path changes: lab simulation only.
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
SIZE_LO, SIZE_HI = 0.5, 2.0


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


def max_drawdown(equity: np.ndarray) -> float:
    if len(equity) == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    return float(np.max(peak - equity))


def policy_stats(net: np.ndarray, size: np.ndarray) -> dict:
    """Stats for one sizing policy. net = per-trade net ATR at unit notional."""
    n = len(net)
    if n == 0:
        return {"trades": 0, "expectancy": None, "pf": None,
                "expectancy_per_unit_risk": None, "risk_adj": None,
                "maxdd": None, "total": None, "mean_size": None}
    scaled = net * size
    w, l = scaled[scaled > 0], scaled[scaled < 0]
    pf = float(w.sum() / -l.sum()) if l.sum() < 0 else None
    exp_unit = float(scaled.sum() / size.sum())  # size-weighted mean net: per-unit-risk
    mu, sd = float(scaled.mean()), float(scaled.std(ddof=1)) if n > 1 else 0.0
    risk_adj = round(mu / sd, 5) if sd > 0 else None
    # exposure-normalized equity: same average notional as flat -> fair DD comparison
    avg_size = float(size.mean())
    eq = np.cumsum(scaled) / avg_size if avg_size > 0 else np.cumsum(scaled)
    return {"trades": int(n), "expectancy": round(mu, 4),
            "pf": round(pf, 3) if pf is not None else None,
            "expectancy_per_unit_risk": round(exp_unit, 4),
            "risk_adj": risk_adj,
            "maxdd": round(max_drawdown(eq), 3),
            "total": round(float(scaled.sum()), 2),
            "mean_size": round(avg_size, 4)}


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
    parts = []
    for symbol in config.market.symbols:
        df = build(symbol, fee_cfg, barrier.atr_window)
        parts.append(df)
        print(f"  {symbol}: {len(df):,}", flush=True)
    ds = pd.concat(parts, ignore_index=True)
    ds = ds.iloc[np.argsort(ds["timestamp"].to_numpy(), kind="stable")].reset_index(drop=True)
    cols = [c for c in ds.columns if c not in non_feature]

    cut = int(len(ds) * (1.0 - barrier.holdout_fraction))
    purge = H * len(config.market.symbols)
    dev, hold = ds.iloc[: cut - purge], ds.iloc[cut + purge:].copy()

    # range model (same construction as E10)
    reg = HistGradientBoostingRegressor(max_iter=300, max_leaf_nodes=31, learning_rate=0.05,
                                        min_samples_leaf=200, l2_regularization=1.0,
                                        early_stopping=False, random_state=42)
    valid = dev[np.isfinite(dev["fwd_range_atr"])]
    reg.fit(valid[cols], valid["fwd_range_atr"].to_numpy())
    dev_pred = reg.predict(dev[cols])
    hold["pred_range"] = reg.predict(hold[cols])
    median_range = float(np.median(dev_pred[np.isfinite(dev_pred)]))
    y = valid["fwd_range_atr"].to_numpy()
    p = hold["pred_range"].to_numpy()
    yh = hold["fwd_range_atr"].to_numpy()
    ok = np.isfinite(yh)
    mae_model = float(np.mean(np.abs(p[ok] - yh[ok])))
    mae_base = float(np.mean(np.abs(yh[ok] - valid["fwd_range_atr"].mean())))
    print(f"range model: holdout MAE {mae_model:.3f} vs mean {mae_base:.3f} "
          f"(gain {1 - mae_model / mae_base:.1%}), dev median {median_range:.3f} ATR", flush=True)

    # incumbent direction model (for the confidence floor only)
    clf = HistGradientBoostingClassifier(max_iter=300, max_leaf_nodes=31, learning_rate=0.05,
                                         min_samples_leaf=200, l2_regularization=1.0,
                                         early_stopping=False, random_state=42)
    clf.fit(dev[cols], dev["label"].to_numpy())
    hold["p"] = clf.predict_proba(hold[cols])[:, 1]
    yy = hold["label"].to_numpy()
    base = float(dev["label"].mean())
    ll, llb = float(log_loss(yy, hold["p"])), float(log_loss(yy, np.full(len(hold), base)))
    print(f"incumbent check: LL {ll:.4f} vs base {llb:.4f} AUC {roc_auc_score(yy, hold['p']):.4f}", flush=True)

    rows = []
    for floor in (0.40, 0.50):
        sel = hold[hold["p"] >= floor].copy()
        net = sel["net_atr"].to_numpy()
        flat = np.ones_like(net)
        sized = np.clip(sel["pred_range"].to_numpy() / median_range, SIZE_LO, SIZE_HI)
        sized = np.where(np.isfinite(sized), sized, 1.0)
        f, s = policy_stats(net, flat), policy_stats(net, sized)
        rows.append({"floor": floor, "policy": "flat", **f})
        rows.append({"floor": floor, "policy": "vol-sized", **s})
        print(f"floor {floor} flat     : n {f['trades']:6d} exp {f['expectancy']} "
              f"exp/risk {f['expectancy_per_unit_risk']} risk_adj {f['risk_adj']} "
              f"maxdd {f['maxdd']} total {f['total']}", flush=True)
        print(f"floor {floor} vol-sized: n {s['trades']:6d} exp {s['expectancy']} "
              f"exp/risk {s['expectancy_per_unit_risk']} risk_adj {s['risk_adj']} "
              f"maxdd {s['maxdd']} total {s['total']} mean_size {s['mean_size']}", flush=True)

    deployable = []
    for floor in (0.40, 0.50):
        f = next(r for r in rows if r["floor"] == floor and r["policy"] == "flat")
        s = next(r for r in rows if r["floor"] == floor and r["policy"] == "vol-sized")
        better = (s["risk_adj"] is not None and f["risk_adj"] is not None
                  and s["risk_adj"] > f["risk_adj"]
                  and s["trades"] >= 200 and s["maxdd"] <= f["maxdd"])
        if better:
            deployable.append({"floor": floor, "flat": f, "vol-sized": s})
    report = {"median_range_atr": round(median_range, 4),
              "range_mae_gain": round(1 - mae_model / mae_base, 4),
              "ll": ll, "ll_base": llb, "policies": rows,
              "deployable": deployable,
              "verdict": "PASS" if deployable else "REJECT",
              "note": ("vol sizing improves risk-adjusted expectancy without worse drawdown"
                       if deployable else
                       "sizing does not clear the gate; range signal stays dashboard-only, flat sizing unchanged"),
              "seconds": round(time.perf_counter() - started)}
    out = _LAB / "research_lab" / "results" / "e12_meta.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"E12 VERDICT: {report['verdict']} ({report['seconds']}s) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
