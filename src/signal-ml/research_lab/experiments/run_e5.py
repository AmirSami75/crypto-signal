"""E5 — regime-conditional calibration at 15m.

Hypothesis (E3/E4 consequence): the 15m signal (LL margin +0.064) is real but
averaged across regimes it dilutes below the cost wall. If the edge concentrates
in identifiable regimes (trend vs chop, high vs low vol), a regime-gated policy
trades less often with more edge per trade.

Design (all causal, no new data):
- Two regime indicators per candle, built from CLOSED candles only:
    vol_regime: 1 if realized vol (72-bar) above its 720-bar rolling median, else 0
    trend_regime: 1 if |ema_ratio_26| above its 720-bar rolling median, else 0
  → 4 regime buckets. Rolling medians are shifted by 1 bar (causal).
- Step 1 (diagnosis): per-regime strict-holdout expectancy of the E4 maker model's
  bets. If no regime shows expectancy>0 with enough volume, hypothesis dies here.
- Step 2 (gate): regime-gated policy = trade only in buckets that were POSITIVE on
  the development half of the holdout, evaluate on the second half (split-half
  design prevents selecting regimes on the data we report).
- Gate (pre-declared): OOS half must show expectancy>0 AND PF>1 AND >=30 trades,
  summed across selected buckets, maker cost model.

Fill/label machinery identical to E4 (maker entry at decision close).
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
from crypto_signal.evaluation.bracket import BracketCosts, run_bracket_backtest  # noqa: E402
from crypto_signal.domain import percent_from_atr  # noqa: E402
from crypto_signal.features import WARMUP_COLUMNS, build_features  # noqa: E402
from crypto_signal.modeling.estimator import aligned_probabilities  # noqa: E402
from research_lab.experiments.run_e4 import maker_label_symbol  # noqa: E402
from research_lab.labels.fee_aware import FeeAwareConfig  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
NON_FEATURE = {"timestamp", "symbol", "label", "net_atr", "resolved",
               "open", "high", "low", "close", "atr",
               "vol_regime", "trend_regime", "regime_bucket"}
MAKER_FEE = 0.0002


def add_regimes(frame: pd.DataFrame) -> pd.DataFrame:
    """Causal regime flags from closed candles only."""
    out = frame.copy()
    one_bar = out["close"].astype(float).diff()
    vol72 = one_bar.rolling(72).std()
    vol_median = vol72.rolling(720).median().shift(1)
    out["vol_regime"] = (vol72 > vol_median).astype(float)

    ema26 = out["close"].astype(float).ewm(span=26, adjust=False).mean()
    trend = (out["close"].astype(float) / ema26 - 1).abs()
    trend_median = trend.rolling(720).median().shift(1)
    out["trend_regime"] = (trend > trend_median).astype(float)

    out["regime_bucket"] = (
        out["vol_regime"].astype(int).astype(str)
        + out["trend_regime"].astype(int).astype(str)
    )
    return out


def main() -> int:
    started = time.perf_counter()
    config = load_config(_LAB / "config.2y.toml")
    barrier = config.barrier

    fee_config = FeeAwareConfig(
        take_profit_atr=barrier.backtest_take_profit_atr,
        stop_loss_atr=barrier.backtest_stop_loss_atr,
        max_horizon=48,
        fee_rate=config.backtest.fee_rate,
        slippage_rate=config.backtest.slippage_rate,
    )

    pieces = []
    for symbol in SYMBOLS:
        raw = load_ohlcv(_LAB / "data" / f"{symbol}_15m.csv", "15m")
        raw = add_regimes(raw)
        feats = build_features(raw, atr_window=barrier.atr_window)
        frame = feats.frame.copy()
        frame["timestamp"] = pd.to_datetime(raw["timestamp"].to_numpy(), utc=True)
        for column in ("open", "high", "low", "close"):
            frame[column] = raw[column].astype(float).to_numpy()
        frame["atr"] = feats.atr.to_numpy(dtype=np.float64)
        for column in ("vol_regime", "trend_regime", "regime_bucket"):
            frame[column] = raw[column].to_numpy()
        warm = feats.frame[list(WARMUP_COLUMNS)].notna().all(axis=1).to_numpy()
        frame = frame[warm & (frame["atr"] > 0)].reset_index(drop=True)
        for sign in (+1, -1):
            side = frame.copy()
            side["direction_sign"] = float(sign)
            labelled = maker_label_symbol(side, sign, fee_config, MAKER_FEE)
            merged = side.merge(
                labelled[["timestamp", "label", "net_atr", "resolved"]],
                on="timestamp", how="inner",
            )
            merged["symbol"] = symbol
            pieces.append(merged)
        print(f"  {symbol}: {len(frame):,} candles", flush=True)
    dataset = pd.concat(pieces, ignore_index=True)
    print(f"rows: {len(dataset):,} | balance: {dataset['label'].mean():.4f}", flush=True)

    times = pd.to_datetime(dataset["timestamp"], utc=True)
    order = np.argsort(times.to_numpy(), kind="stable")
    dataset = dataset.iloc[order].reset_index(drop=True)
    cut = int(len(dataset) * (1.0 - barrier.holdout_fraction))
    purge = fee_config.max_horizon * 2 * len(SYMBOLS)
    dev = dataset.iloc[: cut - purge]
    hold = dataset.iloc[cut + purge:]

    feature_columns = [c for c in dev.columns if c not in NON_FEATURE]
    model = HistGradientBoostingClassifier(
        max_iter=config.model.max_iter,
        max_leaf_nodes=config.model.max_leaf_nodes,
        learning_rate=config.model.learning_rate,
        min_samples_leaf=config.model.min_samples_leaf,
        l2_regularization=config.model.l2_regularization,
        early_stopping=False,
        random_state=config.model.random_state,
    )
    model.fit(dev[feature_columns], dev["label"].to_numpy())
    hold = hold.copy()
    hold["p_win"] = aligned_probabilities(model, hold[feature_columns])[:, 2]
    print(f"holdout: {len(hold):,} rows | base {hold['label'].mean():.4f}", flush=True)

    # Split the holdout: first half selects regimes, second half evaluates.
    mid = len(hold) // 2
    hold_a, hold_b = hold.iloc[:mid], hold.iloc[mid:]

    maker_costs = BracketCosts(fee_rate=MAKER_FEE, slippage_rate=config.backtest.slippage_rate)
    CONF_FLOOR = 0.45  # E4's best-volume floor

    def bucket_results(frame: pd.DataFrame) -> dict[str, dict]:
        results = {}
        take = frame[frame["p_win"] >= CONF_FLOOR]
        for bucket, group in take.groupby("regime_bucket"):
            sims = []
            for (_s, sgn), g2 in group.groupby(["symbol", "direction_sign"]):
                g = g2.sort_values("timestamp")
                g_entry = g["close"].to_numpy(dtype=float)
                g_atr = g["atr"].to_numpy(dtype=float)
                decisions = pd.DataFrame({
                    "timestamp": g["timestamp"].to_numpy(),
                    "open": g["open"], "high": g["high"], "low": g["low"], "close": g["close"],
                    "atr": g["atr"],
                    "direction": np.full(len(g), int(sgn), dtype=int),
                    "take_profit_percent": [percent_from_atr(p, fee_config.take_profit_atr, a) for p, a in zip(g_entry, g_atr)],
                    "stop_loss_percent": [percent_from_atr(p, fee_config.stop_loss_atr, a) for p, a in zip(g_entry, g_atr)],
                })
                try:
                    _t, metrics = run_bracket_backtest(decisions, "15m", fee_config.max_horizon, maker_costs)
                    sims.append(metrics["trades"])
                except ValueError:
                    continue
            trades = sum(s["trades"] for s in sims) if sims else 0
            exp_values = [s["expectancy_atr"] for s in sims if s["trades"]] if sims else []
            pf_values = [s["profit_factor"] for s in sims if s["trades"] and s["profit_factor"]] if sims else []
            results[bucket] = {
                "trades": trades,
                "expectancy_atr": round(float(np.mean(exp_values)), 4) if exp_values else None,
                "pf_mean": round(float(np.mean(pf_values)), 3) if pf_values else None,
            }
        return results

    sel = bucket_results(hold_a)
    print(f"selection half (first 50% of holdout): {json.dumps(sel)}", flush=True)
    positive = [b for b, r in sel.items()
                if r["expectancy_atr"] is not None and r["expectancy_atr"] > 0
                and (r["pf_mean"] or 0) > 1.0 and r["trades"] >= 20]
    print(f"buckets selected on dev half: {positive}", flush=True)

    if not positive:
        print("E5 VERDICT: REJECT — no regime bucket positive on the selection half", flush=True)
        ( _LAB / "research_lab" / "results" / "e5_meta.json").write_text(json.dumps({
            "selection": sel, "selected": [], "verdict": "REJECT_NO_POSITIVE_BUCKET",
        }, indent=2))
        return 0

    oos = bucket_results(hold_b[hold_b["regime_bucket"].isin(positive)])
    total_trades = sum(r["trades"] for r in oos.values())
    exp_all = [r["expectancy_atr"] for r in oos.values() if r["expectancy_atr"] is not None]
    pf_all = [r["pf_mean"] for r in oos.values() if r["pf_mean"] is not None]
    econ_ok = bool(
        total_trades >= 30 and exp_all and np.mean(exp_all) > 0
        and pf_all and np.mean(pf_all) > 1.0
    )
    verdict = "PASS" if econ_ok else "REJECT"
    print(f"OOS half (selected buckets {positive}): {json.dumps(oos)}", flush=True)
    print(f"E5 VERDICT: {verdict} | OOS trades {total_trades} "
          f"exp {np.mean(exp_all) if exp_all else float('nan'):.4f} "
          f"pf {np.mean(pf_all) if pf_all else float('nan'):.3f} "
          f"({time.perf_counter()-started:.0f}s)", flush=True)

    (_LAB / "research_lab" / "results" / "e5_meta.json").write_text(json.dumps({
        "selection_half": sel, "selected_buckets": positive,
        "oos_half": oos, "verdict": verdict,
        "conf_floor": CONF_FLOOR, "maker_fee": MAKER_FEE,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
