"""E8 adversarial audit (§10 significance, §13 multiple testing, Muse Quant role).

Attacks the futures-tier PASS cells:
 1. Bootstrap 95% CI on expectancy (trade-level resample).
 2. Concentration: per-symbol and per-quarter share of P&L; a cell driven by one
    symbol or one quarter is not a strategy.
 3. Overlap deflation: rows are per-candle bets; a real book holds ONE position per
    symbol+direction for up to 24 bars. Re-simulate sequentially and report the
    non-overlapping trade count and expectancy.
 4. Null distribution: refit the model on dev with labels circularly shifted by a
    large random offset (destroys feature→label link, keeps autocorrelation), score
    holdout, apply the same floors. Repeat 20× → how often does a 'PASS' appear by
    chance under the declared gate?
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_LAB = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_LAB / "src"))
sys.path.insert(0, str(_LAB))

from crypto_signal.config import load_config  # noqa: E402
from crypto_signal.data import load_ohlcv  # noqa: E402
from research_lab.experiments.run_e1 import build_side_dataset  # noqa: E402
from research_lab.experiments.run_e8 import FLOORS, HORIZON, NON_FEATURE, TIERS, resample_4h, stats  # noqa: E402
from research_lab.labels.fee_aware import FeeAwareConfig  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402

RNG = np.random.default_rng(7)


def fit(dev, cols):
    clf = HistGradientBoostingClassifier(max_iter=300, max_leaf_nodes=31, learning_rate=0.05,
                                         min_samples_leaf=200, l2_regularization=1.0,
                                         early_stopping=False, random_state=42)
    return clf.fit(dev[cols], dev["label"].to_numpy())


def sequential(sel: pd.DataFrame) -> np.ndarray:
    """One open position per (symbol, direction); skip signals while a trade is live."""
    out = []
    for _, g in sel.groupby(["symbol", "direction_sign"]):
        g = g.sort_values("timestamp")
        busy_until = pd.Timestamp.min.tz_localize("UTC")
        for ts, net in zip(g["timestamp"], g["net_atr"]):
            if ts >= busy_until:
                out.append(net)
                busy_until = ts + pd.Timedelta(hours=4 * HORIZON)
    return np.asarray(out)


def main() -> int:
    config = load_config(_LAB / "config.2y.toml")
    barrier = config.barrier
    frames = {s: resample_4h(load_ohlcv(_LAB / "data" / f"{s}_1h.csv", "1h"))
              for s in config.market.symbols if (_LAB / "data" / f"{s}_1h.csv").exists()}
    fee_config = FeeAwareConfig(take_profit_atr=barrier.backtest_take_profit_atr,
                                stop_loss_atr=barrier.backtest_stop_loss_atr,
                                max_horizon=HORIZON, **TIERS["futures"])
    ds = build_side_dataset(frames, fee_config, barrier.atr_window)
    ds = ds.iloc[np.argsort(ds["timestamp"].to_numpy(), kind="stable")].reset_index(drop=True)
    cols = [c for c in ds.columns if c not in NON_FEATURE]
    cut = int(len(ds) * (1.0 - barrier.holdout_fraction)); purge = HORIZON * 2 * len(frames)
    dev, hold = ds.iloc[: cut - purge], ds.iloc[cut + purge:].copy()
    hold["p"] = fit(dev, cols).predict_proba(hold[cols])[:, 1]
    print(f"holdout span {hold['timestamp'].min().date()} → {hold['timestamp'].max().date()}, {len(hold):,} rows")

    audit = {}
    for floor in (0.50, 0.55, 0.60):
        sel = hold[hold["p"] >= floor]
        net = sel["net_atr"].to_numpy()
        boots = np.array([RNG.choice(net, len(net), replace=True).mean() for _ in range(2000)])
        lo, hi = np.percentile(boots, [2.5, 97.5])
        se = net.std(ddof=1) / np.sqrt(len(net))
        by_sym = sel.groupby("symbol")["net_atr"].sum().sort_values(ascending=False)
        by_q = sel.groupby(sel["timestamp"].dt.to_period("Q"))["net_atr"].agg(["sum", "count"])
        top_sym_share = float(by_sym.iloc[0] / net.sum()) if net.sum() > 0 else None
        seq = sequential(sel)
        seq_stats = stats(seq)
        both_sides = sel.groupby(["symbol", "timestamp"]).size()
        both = int((both_sides > 1).sum())
        cell = {
            "n": int(len(net)), "expectancy": round(float(net.mean()), 4),
            "boot_ci95": [round(float(lo), 4), round(float(hi), 4)], "t_stat": round(float(net.mean() / se), 2),
            "positive_symbols": int((by_sym > 0).sum()), "symbols_traded": int(len(by_sym)),
            "top_symbol": by_sym.index[0], "top_symbol_share_of_pnl": top_sym_share,
            "quarters": {str(k): {"sum": round(float(v["sum"]), 2), "n": int(v["count"])} for k, v in by_q.iterrows()},
            "sequential_non_overlapping": seq_stats,
            "candles_with_both_long_and_short": both,
        }
        audit[str(floor)] = cell
        print(f"\nfloor {floor}: n {cell['n']} exp {cell['expectancy']} CI95 {cell['boot_ci95']} t {cell['t_stat']}")
        print(f"  symbols +/total {cell['positive_symbols']}/{cell['symbols_traded']} | top {cell['top_symbol']} "
              f"share {top_sym_share and round(top_sym_share, 2)} | both-sides candles {both}")
        print(f"  quarters: {cell['quarters']}")
        print(f"  sequential: {seq_stats}")

    # ---- null: shifted labels ----
    print("\nnull (label circular shift, 20 refits) — does the declared gate PASS by chance?")
    null_pass, null_best = 0, []
    dev_n = dev.copy()
    for i in range(20):
        shift = int(RNG.integers(5000, len(dev_n) - 5000))
        dev_n["label"] = np.roll(dev["label"].to_numpy(), shift)
        p = fit(dev_n, cols).predict_proba(hold[cols])[:, 1]
        cells = []
        for floor in FLOORS:
            s = stats(hold["net_atr"].to_numpy()[p >= floor]); s["floor"] = floor; cells.append(s)
        ok = [c for c in cells if c["expectancy_atr"] is not None and c["expectancy_atr"] > 0
              and (c["pf"] or 0) > 1 and c["trades"] >= 30]
        best = max((c["expectancy_atr"] for c in cells if c["trades"] >= 30), default=None)
        null_pass += bool(ok); null_best.append(best)
        print(f"  null {i:2d}: PASS={bool(ok)} best exp(n>=30)={best} cells={[(c['floor'], c['trades'], c['expectancy_atr']) for c in cells]}")
    audit["null"] = {"refits": 20, "gate_pass_count": null_pass, "best_expectancy_per_refit": null_best}
    print(f"\nNULL: declared gate PASSED in {null_pass}/20 shuffled refits")
    (_LAB / "research_lab" / "results" / "e8_audit.json").write_text(json.dumps(audit, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
