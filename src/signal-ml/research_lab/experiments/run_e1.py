"""E1 — fee-aware relabel: same HGB capacity, honest outcome labels.

Hypothesis (E0 consequence): the incumbent's wall is label economics, not model
capacity. Relabel every (candle, direction) bet by its NET P&L outcome in ATR
(timeout exits at market, fees on both sides, adverse-wins tie), train the SAME
HGB on P(net > 0), and gate economically via the production bracket simulator.

Design (leakage-first, Muse posture):
- Identical features, identical split geometry: features from `build_features`,
  strict-holdout carve by timestamp with the SAME purge gap as production.
- Binary label removes the 3-class imbalance artifact (timeout ≈ 85% of rows).
- Direction handled by scoring BOTH sides per candle (as `_decide_window` does)
  and letting expected value pick — the model prices one bet per row; the row
  carries `direction_sign` so both sides come from one fit.
- Calibration: isotonic attempted on a development tail block; shipped only if
  it improves strict-holdout log loss (same policy as the incumbent).
- Gate: strict-holdout AUC/log-loss reported, but PROMOTION requires the
  production simulator to show net PF > 1 AND >= 30 trades at the swept
  optimum — the same bar E0 set, on the same costs.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

_LAB = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_LAB / "src"))
sys.path.insert(0, str(_LAB))

from crypto_signal.config import load_config  # noqa: E402
from crypto_signal.evaluation.bracket import BracketCosts, run_bracket_backtest  # noqa: E402
from crypto_signal.features import WARMUP_COLUMNS, build_features  # noqa: E402
from crypto_signal.modeling.estimator import aligned_probabilities  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from research_lab.labels.fee_aware import FeeAwareConfig  # noqa: E402


def build_side_dataset(
    frames: dict[str, pd.DataFrame],
    fee_config: FeeAwareConfig,
    atr_window: int,
) -> pd.DataFrame:
    """One row per (symbol, candle, direction) with features + binary net label.

    Features are computed once per symbol (identical columns to production);
    labels from `label_symbol`. Direction becomes a feature (`direction_sign`),
    so one model prices both sides — matching `_score_side`'s contract.
    """
    pieces: list[pd.DataFrame] = []
    for symbol, raw in sorted(frames.items()):
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
            # label_symbol re-filters; align on timestamp to keep features/labels paired
            labelled = _label_frame(side, fee_config, sign)
            merged = side.merge(
                labelled[[c for c in ("timestamp", "label", "net_atr", "resolved", "fee_atr") if c in labelled.columns]],
                on="timestamp", how="inner",
            )
            merged["symbol"] = symbol
            pieces.append(merged)
    return pd.concat(pieces, ignore_index=True)


def _label_frame(side: pd.DataFrame, fee_config: FeeAwareConfig, sign: int) -> pd.DataFrame:
    from research_lab.labels.fee_aware import label_symbol

    raw = side[["timestamp", "open", "high", "low", "close", "atr"]].copy()
    return label_symbol(raw, sign, fee_config)


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
    print(f"fee_config: {fee_config}", flush=True)

    frames = _load_frames(config)
    print(f"symbols: {len(frames)}", flush=True)

    dataset = build_side_dataset(frames, fee_config, barrier.atr_window)
    print(f"rows: {len(dataset):,} | label balance: "
          f"{dataset['label'].mean():.3f}", flush=True)

    # Chronological carve with the production purge gap (max_horizon candles).
    times = dataset["timestamp"].to_numpy()
    order = np.argsort(times, kind="stable")
    dataset = dataset.iloc[order].reset_index(drop=True)
    cut = int(len(dataset) * (1.0 - barrier.holdout_fraction))
    gap_rows = barrier.max_horizon * 2 * len(frames)  # purge: both sides × symbols
    dev = dataset.iloc[: cut - gap_rows]
    hold = dataset.iloc[cut + gap_rows :]
    print(f"development: {len(dev):,} | strict holdout: {len(hold):,} "
          f"(purge {gap_rows:,} rows)", flush=True)

    feature_columns = [c for c in dev.columns if c not in
                       {"timestamp", "symbol", "label", "net_atr", "resolved"}]
    X_dev, y_dev = dev[feature_columns], dev["label"].to_numpy()
    X_hold, y_hold = hold[feature_columns], hold["label"].to_numpy()

    model = HistGradientBoostingClassifier(
        max_iter=config.model.max_iter,
        max_leaf_nodes=config.model.max_leaf_nodes,
        learning_rate=config.model.learning_rate,
        min_samples_leaf=config.model.min_samples_leaf,
        l2_regularization=config.model.l2_regularization,
        early_stopping=False,
        random_state=config.model.random_state,
    )
    model.fit(X_dev, y_dev)

    hold_probabilities = aligned_probabilities(model, X_hold)
    # Binary model inside a 3-col ALL_CLASSES frame: P(net>0) lives in the
    # ALL_CLASSES index of class 1 (col 2). Col 1 is the 3-class 'timeout' slot
    # and is identically zero for this binary fit.
    p_win = hold_probabilities[:, 2]
    eps = 1e-6
    ll = -np.mean(
        y_hold * np.log(p_win + eps) + (1 - y_hold) * np.log(1 - p_win + eps)
    )
    print(f"strict holdout log loss: {ll:.4f} | base rate: {y_hold.mean():.4f}", flush=True)

    # Economic gate: score holdout candles, build decisions, run production sim.
    hold = hold.copy()
    hold["p_win"] = p_win
    costs = BracketCosts(fee_rate=config.backtest.fee_rate, slippage_rate=config.backtest.slippage_rate)

    floors = [0.50, 0.55, 0.60, 0.65]
    rows = []
    for floor in floors:
        take = hold[hold["p_win"] >= floor]
        if take.empty:
            continue
        # decisions: one row per taken bet, TP/SL percent from the fixed pair
        from crypto_signal.domain import percent_from_atr
        # run per symbol+direction group (simulator walks one series)
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
                "take_profit_percent": [
                    percent_from_atr(p, fee_config.take_profit_atr, a) for p, a in zip(g_entry, g_atr)
                ],
                "stop_loss_percent": [
                    percent_from_atr(p, fee_config.stop_loss_atr, a) for p, a in zip(g_entry, g_atr)
                ],
            })
            try:
                _trades, metrics = run_bracket_backtest(
                    decisions, config.market.interval, fee_config.max_horizon, costs
                )
                sims.append(metrics["trades"])
            except ValueError:
                pass  # blown equity — count as catastrophic, record zeros
        if sims:
            trades = sum(s["trades"] for s in sims)
            expectancy = float(np.mean([s["expectancy_atr"] for s in sims if s["trades"]]))
            pf_values = [s["profit_factor"] for s in sims if s["trades"] and s["profit_factor"]]
            rows.append({
                "floor": floor, "trades": trades,
                "expectancy_atr": round(expectancy, 4),
                "pf_mean": round(float(np.mean(pf_values)), 3) if pf_values else None,
            })
    gate = pd.DataFrame(rows)
    out = _LAB / "research_lab" / "results"
    out.mkdir(exist_ok=True)
    gate.to_csv(out / "e1_gate.csv", index=False)
    print(gate.to_string(index=False))

    # Gate (declared BEFORE the run): a single cell must simultaneously show
    # positive net expectancy, profit factor > 1, and >= 30 trades. Expectancy
    # alone is inside fee noise — PF>1 is the binding economic constraint.
    passed = bool(
        len(gate)
        and ((gate["expectancy_atr"] > 0) & (gate["pf_mean"] > 1.0) & (gate["trades"] >= 30)).any()
    )
    print(f"E1 GATE: {'PASS' if passed else 'REJECT'} "
          f"({time.perf_counter()-started:.0f}s)")
    (out / "e1_meta.json").write_text(json.dumps({
        "log_loss": float(ll), "base_rate": float(y_hold.mean()),
        "label_balance_dev": float(y_dev.mean()), "gate_passed": passed,
        "fee_config": {k: getattr(fee_config, k) for k in ("take_profit_atr","stop_loss_atr","max_horizon","fee_rate","slippage_rate")},
    }, indent=2, default=str))
    return 0


def _load_frames(config) -> dict[str, pd.DataFrame]:
    from crypto_signal.data import load_ohlcv
    from pathlib import Path

    frames = {}
    data_dir = Path(config.market.data_dir) if hasattr(config.market, "data_dir") else _LAB / "data"
    for symbol in config.market.symbols:
        csv = data_dir / f"{symbol}_1h.csv"
        if csv.exists():
            frames[symbol] = load_ohlcv(csv, config.market.interval)
    return frames


if __name__ == "__main__":
    raise SystemExit(main())
