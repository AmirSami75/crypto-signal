"""E2 — funding ablation on fee-aware labels (7 funded symbols).

Question: do causal funding features (funding_rate_last, funding_rate_chg_3)
add predictive value BEYOND the OHLCV feature set on the E1 net-outcome labels?

Design:
- Population: only the 7 symbols with funding history (BTC/ETH/SOL/XRP/ADA/BNB/DOGE).
- A/B on identical rows and split: BASELINE (E1 features) vs +FUNDING (adds the two
  causal funding columns). Same HGB capacity, same strict-holdout carve.
- Gate (pre-declared): +FUNDING must improve strict-holdout log loss AND the economic
  gate cell (expectancy>0 AND PF>1 AND >=30 trades) must appear where BASELINE had none.
- Ablation logic: if funding helps, delta > 0; if not, record honest REJECT — the
  feature group is dropped from the roadmap rather than shipped on hope.
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
from crypto_signal.data import join_derivatives_features, load_ohlcv  # noqa: E402
from crypto_signal.evaluation.bracket import BracketCosts, run_bracket_backtest  # noqa: E402
from crypto_signal.domain import percent_from_atr  # noqa: E402
from crypto_signal.modeling.estimator import aligned_probabilities  # noqa: E402
from research_lab.experiments.run_e1 import _label_frame  # noqa: E402
from research_lab.labels.fee_aware import FeeAwareConfig  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402

FUNDED = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "BNBUSDT", "DOGEUSDT"]
FUNDING_COLS = ["funding_rate_last", "funding_rate_chg_3"]
NON_FEATURE = {"timestamp", "symbol", "label", "net_atr", "resolved", "open", "high", "low", "close", "atr"}


def load_funding(symbol: str) -> pd.DataFrame | None:
    path = _LAB / "data" / f"{symbol}_funding.csv"
    if not path.exists():
        return None
    frame = pd.read_csv(path)
    frame["funding_time"] = pd.to_datetime(frame["funding_time"], utc=True, format="mixed")
    return frame


def build_dataset(frames: dict[str, pd.DataFrame], fee_config: FeeAwareConfig, atr_window: int, with_funding: bool) -> pd.DataFrame:
    pieces = []
    for symbol, raw in sorted(frames.items()):
        from crypto_signal.features import WARMUP_COLUMNS, build_features

        work = raw
        if with_funding:
            work = join_derivatives_features(raw.copy(), load_funding(symbol), None)
        feats = build_features(work, atr_window=atr_window)
        frame = feats.frame.copy()
        # funding columns bypass build_features; pull them from the joined work frame
        if with_funding:
            for column in FUNDING_COLS:
                if column in work.columns:
                    frame[column] = work[column].to_numpy()
        frame["timestamp"] = pd.to_datetime(raw["timestamp"].to_numpy(), utc=True)
        for column in ("open", "high", "low", "close"):
            frame[column] = raw[column].astype(float).to_numpy()
        frame["atr"] = feats.atr.to_numpy(dtype=np.float64)
        warm = feats.frame[list(WARMUP_COLUMNS)].notna().all(axis=1).to_numpy()
        frame = frame[warm & (frame["atr"] > 0)].reset_index(drop=True)
        for sign in (+1, -1):
            side = frame.copy()
            side["direction_sign"] = float(sign)
            labelled = _label_frame(side, fee_config, sign)
            merged = side.merge(
                labelled[["timestamp", "label", "net_atr", "resolved"]],
                on="timestamp", how="inner",
            )
            merged["symbol"] = symbol
            pieces.append(merged)
    return pd.concat(pieces, ignore_index=True)


def train_and_gate(dataset: pd.DataFrame, holdout_fraction: float, purge_rows: int, config, costs: BracketCosts, fee_config: FeeAwareConfig) -> dict:
    times = pd.to_datetime(dataset["timestamp"], utc=True)
    order = np.argsort(times.to_numpy(), kind="stable")
    dataset = dataset.iloc[order].reset_index(drop=True)
    cut = int(len(dataset) * (1.0 - holdout_fraction))
    dev = dataset.iloc[: cut - purge_rows]
    hold = dataset.iloc[cut + purge_rows :]

    feature_columns = [c for c in dev.columns if c not in NON_FEATURE and c != "direction_sign"]
    feature_columns += ["direction_sign"]
    from crypto_signal.modeling.estimator import build_model  # capacity parity with incumbent

    model_config = config.model
    model = HistGradientBoostingClassifier(
        max_iter=model_config.max_iter,
        max_leaf_nodes=model_config.max_leaf_nodes,
        learning_rate=model_config.learning_rate,
        min_samples_leaf=model_config.min_samples_leaf,
        l2_regularization=model_config.l2_regularization,
        early_stopping=False,
        random_state=model_config.random_state,
    )
    model.fit(dev[feature_columns], dev["label"].to_numpy())

    probabilities = aligned_probabilities(model, hold[feature_columns])
    p_win = probabilities[:, 2]
    y = hold["label"].to_numpy()
    eps = 1e-6
    ll = float(-np.mean(y * np.log(p_win + eps) + (1 - y) * np.log(1 - p_win + eps)))

    hold = hold.copy()
    hold["p_win"] = p_win
    best = {"floor": None, "trades": 0, "expectancy_atr": None, "pf_mean": None}
    for floor in (0.50, 0.55, 0.60):
        take = hold[hold["p_win"] >= floor]
        sims = []
        for (_symbol, sgn), group in take.groupby(["symbol", "direction_sign"]):
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
                _t, metrics = run_bracket_backtest(decisions, config.market.interval, fee_config.max_horizon, costs)
                sims.append(metrics["trades"])
            except ValueError:
                continue
        if sims:
            trades = sum(s["trades"] for s in sims)
            exp_values = [s["expectancy_atr"] for s in sims if s["trades"]]
            pf_values = [s["profit_factor"] for s in sims if s["trades"] and s["profit_factor"]]
            if trades and exp_values:
                best = {
                    "floor": floor, "trades": trades,
                    "expectancy_atr": round(float(np.mean(exp_values)), 4),
                    "pf_mean": round(float(np.mean(pf_values)), 3) if pf_values else None,
                }
                if best["expectancy_atr"] and best["expectancy_atr"] > 0 and (best["pf_mean"] or 0) > 1.0 and trades >= 30:
                    break  # strongest cell found
    return {"log_loss": ll, "gate": best, "n_holdout": int(len(hold))}


def main() -> int:
    started = time.perf_counter()
    config = load_config(_LAB / "config.2y.toml")
    barrier = config.barrier
    fee_config = FeeAwareConfig(
        take_profit_atr=barrier.backtest_take_profit_atr,
        stop_loss_atr=barrier.backtest_stop_loss_atr,
        max_horizon=barrier.max_horizon,
        fee_rate=config.backtest.fee_rate,
        slippage_rate=config.backtest.slippage_rate,
    )
    frames = {s: load_ohlcv(_LAB / "data" / f"{s}_1h.csv", config.market.interval) for s in FUNDED}
    costs = BracketCosts(fee_rate=config.backtest.fee_rate, slippage_rate=config.backtest.slippage_rate)
    purge = barrier.max_horizon * 2 * len(FUNDED)

    results = {}
    for with_funding in (False, True):
        tag = "+funding" if with_funding else "baseline"
        print(f"=== {tag} ===", flush=True)
        dataset = build_dataset(frames, fee_config, barrier.atr_window, with_funding)
        print(f"rows {len(dataset):,} | balance {dataset['label'].mean():.4f}", flush=True)
        results[tag] = train_and_gate(dataset, barrier.holdout_fraction, purge, config, costs, fee_config)
        print(results[tag], flush=True)

    delta_ll = results["baseline"]["log_loss"] - results["+funding"]["log_loss"]
    results["delta_log_loss"] = round(delta_ll, 5)
    gate_ok = (
        results["+funding"]["gate"]["expectancy_atr"] is not None
        and results["+funding"]["gate"]["expectancy_atr"] > 0
        and (results["+funding"]["gate"]["pf_mean"] or 0) > 1.0
        and results["+funding"]["gate"]["trades"] >= 30
    )
    baseline_had_none = (
        results["baseline"]["gate"]["expectancy_atr"] is None
        or results["baseline"]["gate"]["expectancy_atr"] <= 0
        or (results["baseline"]["gate"]["pf_mean"] or 0) <= 1.0
    )
    verdict = "PASS" if (gate_ok and delta_ll > 0 and baseline_had_none) else "REJECT"
    results["verdict"] = verdict
    print(f"E2 VERDICT: {verdict} | delta LL {delta_ll:+.5f} ({time.perf_counter()-started:.0f}s)")

    out = _LAB / "research_lab" / "results"
    (out / "e2_meta.json").write_text(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
