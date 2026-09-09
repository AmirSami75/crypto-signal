"""E3 — 15m resolution experiment.

Question: does the 1h feature set's post-cost emptiness (E0/E1) come from
resolution? Microstructure signals (intrabar flows, short-horizon mean
reversion) live below 1h. The 15m data exists on disk for BTC/ETH/SOL
(234k candles each, 2020→2026) — enough for an A/B without any download.

Design:
- Population: BTC/ETH/SOL (the symbols with 15m history).
- Labels: the SAME fee-aware net-outcome labeller, with horizon and costs
  rescaled to 15m candles: horizon 24×15m = 6h (matches the 1h×24 span),
  tp 1.5 / sl 1.0 ATR(14) unchanged (ATR-normalised, resolution-free).
- A/B on identical rows/split: BASELINE15 (same 42-feature builder at 15m)
  vs the 1h incumbent's strict-holdout economic result as context.
- Gate (pre-declared): strict-holdout log loss must beat the 15m base rate by
  a REAL margin (>0.01) AND open an economic cell (expectancy>0 AND PF>1 AND
  >=30 trades in the SAME cell).
- Failure mode guarded against: 15m rows are 4× 1h rows; the fee per trade is
  IDENTICAL in ATR units, so no cost illusion is possible.
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
from research_lab.labels.fee_aware import FeeAwareConfig  # noqa: E402

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
NON_FEATURE = {"timestamp", "symbol", "label", "net_atr", "resolved",
               "open", "high", "low", "close", "atr"}


def build_dataset(fee_config: FeeAwareConfig, atr_window: int) -> pd.DataFrame:
    from crypto_signal.features import WARMUP_COLUMNS, build_features

    pieces = []
    for symbol in SYMBOLS:
        raw = load_ohlcv(_LAB / "data" / f"{symbol}_15m.csv", "15m")
        feats = build_features(raw, atr_window=atr_window)
        frame = feats.frame.copy()
        frame["timestamp"] = pd.to_datetime(raw["timestamp"].to_numpy(), utc=True)
        for column in ("open", "high", "low", "close"):
            frame[column] = raw[column].astype(float).to_numpy()
        frame["atr"] = feats.atr.to_numpy(dtype=np.float64)
        warm = feats.frame[list(WARMUP_COLUMNS)].notna().all(axis=1).to_numpy()
        frame = frame[warm & (frame["atr"] > 0)].reset_index(drop=True)
        for sign in (+1, -1):
            side = frame.copy()
            side["direction_sign"] = float(sign)
            from research_lab.experiments.run_e1 import _label_frame

            labelled = _label_frame(side, fee_config, sign)
            merged = side.merge(
                labelled[["timestamp", "label", "net_atr", "resolved"]],
                on="timestamp", how="inner",
            )
            merged["symbol"] = symbol
            pieces.append(merged)
        print(f"  {symbol}: {len(frame):,} candles", flush=True)
    return pd.concat(pieces, ignore_index=True)


def main() -> int:
    started = time.perf_counter()
    config = load_config(_LAB / "config.2y.toml")
    barrier = config.barrier

    # Horizon rescale: 24 × 15m = 6h — the same forward span the 1h labels ask
    # about. ATR multiples unchanged: barriers are ATR-normalised.
    fee_config = FeeAwareConfig(
        take_profit_atr=barrier.backtest_take_profit_atr,
        stop_loss_atr=barrier.backtest_stop_loss_atr,
        max_horizon=24,
        fee_rate=config.backtest.fee_rate,
        slippage_rate=config.backtest.slippage_rate,
    )
    print(f"fee_config: tp={fee_config.take_profit_atr} sl={fee_config.stop_loss_atr} "
          f"horizon={fee_config.max_horizon}×15m=6h", flush=True)

    dataset = build_dataset(fee_config, barrier.atr_window)
    print(f"rows: {len(dataset):,} | balance: {dataset['label'].mean():.4f}", flush=True)

    times = pd.to_datetime(dataset["timestamp"], utc=True)
    order = np.argsort(times.to_numpy(), kind="stable")
    dataset = dataset.iloc[order].reset_index(drop=True)
    cut = int(len(dataset) * (1.0 - barrier.holdout_fraction))
    purge = fee_config.max_horizon * 2 * len(SYMBOLS)
    dev = dataset.iloc[: cut - purge]
    hold = dataset.iloc[cut + purge :]
    print(f"development: {len(dev):,} | holdout: {len(hold):,}", flush=True)

    feature_columns = [c for c in dev.columns if c not in NON_FEATURE]
    from sklearn.ensemble import HistGradientBoostingClassifier

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

    from crypto_signal.modeling.estimator import aligned_probabilities

    p_win = aligned_probabilities(model, hold[feature_columns])[:, 2]
    y = hold["label"].to_numpy()
    eps = 1e-6
    ll = float(-np.mean(y * np.log(p_win + eps) + (1 - y) * np.log(1 - p_win + eps)))
    base = float(y.mean())
    print(f"strict LL {ll:.4f} vs base-rate LL {(-np.mean(base*np.log(base+eps)+(1-base)*np.log(1-base+eps))):.4f}", flush=True)

    hold = hold.copy()
    hold["p_win"] = p_win
    costs = BracketCosts(fee_rate=config.backtest.fee_rate, slippage_rate=config.backtest.slippage_rate)
    gate_rows = []
    for floor in (0.40, 0.42, 0.44, 0.46, 0.48, 0.50, 0.52, 0.55, 0.58, 0.60):
        take = hold[hold["p_win"] >= floor]
        sims = []
        for (_s, sgn), group in take.groupby(["symbol", "direction_sign"]):
            g = group.sort_values("timestamp")
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
                _t, metrics = run_bracket_backtest(decisions, "15m", fee_config.max_horizon, costs)
                sims.append(metrics["trades"])
            except ValueError:
                continue
        if sims:
            trades = sum(s["trades"] for s in sims)
            exp_values = [s["expectancy_atr"] for s in sims if s["trades"]]
            pf_values = [s["profit_factor"] for s in sims if s["trades"] and s["profit_factor"]]
            if trades and exp_values:
                cell = {
                    "floor": floor, "trades": trades,
                    "expectancy_atr": round(float(np.mean(exp_values)), 4),
                    "pf_mean": round(float(np.mean(pf_values)), 3) if pf_values else None,
                }
                gate_rows.append(cell)
                print(f"  floor {floor}: {cell}", flush=True)

    gate = pd.DataFrame(gate_rows)
    out = _LAB / "research_lab" / "results"
    gate.to_csv(out / "e3_gate.csv", index=False)

    ll_margin = -np.mean(base * np.log(base + eps) + (1 - base) * np.log(1 - base + eps)) - ll
    econ_ok = bool(
        len(gate)
        and ((gate["expectancy_atr"] > 0) & (gate["pf_mean"] > 1.0) & (gate["trades"] >= 30)).any()
    )
    verdict = "PASS" if (ll_margin > 0.01 and econ_ok) else "REJECT"
    meta = {
        "log_loss": ll, "base_rate": base, "ll_margin_vs_base": round(float(ll_margin), 5),
        "gate": gate_rows, "economic_gate_ok": econ_ok, "verdict": verdict,
        "symbols": SYMBOLS, "rows": int(len(dataset)),
        "fee_config": {k: getattr(fee_config, k) for k in
                       ("take_profit_atr", "stop_loss_atr", "max_horizon", "fee_rate", "slippage_rate")},
    }
    (out / "e3_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"E3 VERDICT: {verdict} | LL margin {ll_margin:+.5f} ({time.perf_counter()-started:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
