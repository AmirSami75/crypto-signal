"""E13 — calibrate the incumbent 1h HGB's probabilities on strict holdout.

Question (E11-lite consequence): the flat HGB ranks direction (k10 auc 0.72)
yet its probabilities are worse than base rate — miscalibrated. Does
post-hoc calibration (temperature scaling vs isotonic regression) fix the
incumbent 1h HGB's probabilities without hurting the production floor?

Design (leakage-first):
- Rebuild the incumbent dataset: config.2y.toml universe, identical
  production features (`build_features`), fee-aware binary labels
  (P(net>0), `research_lab/labels/fee_aware.py`), strict 20% chronological
  holdout with the production purge gap (max_horizon candles x both sides
  x symbols).
- Train the SAME-capacity HGB (config.2y.toml hyperparams) on the 80% dev
  block only. The model never sees the holdout.
- Split the strict holdout chronologically into a calibration-dev half
  (fit) and an eval half (report), separated by a purge gap so no
  horizon overlap leaks across the boundary.
- Fit temperature scaling AND isotonic regression on cal-dev; evaluate
  BOTH on the eval half: log-loss, ECE (15 equal-width bins), reliability
  curve points, floor-0.40 precision/recall before vs after.
- SHIP gate (declared BEFORE the run): candidate = better-LL calibrator;
  PASS requires calibrated LL strictly better AND ECE reduced AND floor
  (0.40) precision not worse — else CALIBRATION-REJECT (report only, no
  artifact promotion). On PASS, calibrator params are saved as
  results/e13calibrator.json and NOT wired into serving (separate deploy).
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
from crypto_signal.features import WARMUP_COLUMNS, build_features  # noqa: E402
from crypto_signal.modeling.estimator import aligned_probabilities  # noqa: E402
from research_lab.experiments.run_e1 import (  # noqa: E402
    _label_frame,
    _load_frames,
)
from research_lab.labels.fee_aware import FeeAwareConfig  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.isotonic import IsotonicRegression  # noqa: E402

SEED = 13
FLOOR = 0.40
N_BINS = 15
EPS = 1e-6
log = lambda m: print(m, flush=True)  # noqa: E731


def build_side_dataset(frames, fee_config, atr_window) -> pd.DataFrame:
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
            labelled = _label_frame(side, fee_config, sign)
            merged = side.merge(
                labelled[[c for c in ("timestamp", "label", "net_atr", "resolved", "fee_atr")
                           if c in labelled.columns]],
                on="timestamp", how="inner",
            )
            merged["symbol"] = symbol
            pieces.append(merged)
    return pd.concat(pieces, ignore_index=True)


def log_loss_bin(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, EPS, 1.0 - EPS)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def ece_and_curve(y: np.ndarray, p: np.ndarray, n_bins: int = N_BINS):
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, n_bins - 1)
    ece, points = 0.0, []
    for b in range(n_bins):
        m = idx == b
        n = int(m.sum())
        if n == 0:
            points.append({"bin": b, "lo": round(float(edges[b]), 4),
                           "hi": round(float(edges[b + 1]), 4),
                           "conf": None, "acc": None, "n": 0})
            continue
        conf = float(p[m].mean())
        acc = float(y[m].mean())
        ece += (n / len(y)) * abs(acc - conf)
        points.append({"bin": b, "lo": round(float(edges[b]), 4),
                       "hi": round(float(edges[b + 1]), 4),
                       "conf": round(conf, 4), "acc": round(acc, 4), "n": n})
    return float(ece), points


def floor_metrics(y: np.ndarray, p: np.ndarray, floor: float = FLOOR) -> dict:
    take = p >= floor
    n_take = int(take.sum())
    if n_take == 0:
        return {"floor": floor, "n_take": 0, "precision": None, "recall": None,
                "coverage": 0.0}
    prec = float(y[take].mean())
    rec = float(y[take].sum() / max(y.sum(), 1))
    return {"floor": floor, "n_take": n_take, "precision": round(prec, 4),
            "recall": round(rec, 4), "coverage": round(n_take / len(y), 4)}


def fit_temperature(p_dev: np.ndarray, y_dev: np.ndarray) -> float:
    """Scalar T>0 minimizing NLL of sigmoid(logit(p)/T) on cal-dev."""
    p = np.clip(p_dev, EPS, 1.0 - EPS)
    logits = np.log(p / (1 - p))
    logits = np.clip(logits, -15.0, 15.0)
    y = y_dev.astype(float)

    def nll(logT: float) -> float:
        T = float(np.exp(logT))
        z = logits / T
        q = 1.0 / (1.0 + np.exp(-z))
        q = np.clip(q, EPS, 1.0 - EPS)
        return float(-np.mean(y * np.log(q) + (1 - y) * np.log(1 - q)))

    try:
        from scipy.optimize import minimize_scalar

        res = minimize_scalar(nll, bounds=(-4.0, 4.0), method="bounded",
                              options={"xatol": 1e-5})
        T = float(np.exp(res.x))
    except Exception:
        grid = np.exp(np.linspace(-4.0, 4.0, 321))
        T = float(grid[int(np.argmin([nll(np.log(t)) for t in grid]))])
    return T


def apply_temperature(p: np.ndarray, T: float) -> np.ndarray:
    p = np.clip(p, EPS, 1.0 - EPS)
    logits = np.clip(np.log(p / (1 - p)), -15.0, 15.0)
    z = logits / T
    return 1.0 / (1.0 + np.exp(-z))


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
    log(f"fee_config: {fee_config}")

    frames = _load_frames(config)
    log(f"symbols: {len(frames)}")
    dataset = build_side_dataset(frames, fee_config, barrier.atr_window)
    log(f"rows: {len(dataset):,} | label balance: {dataset['label'].mean():.4f}")

    times = dataset["timestamp"].to_numpy()
    order = np.argsort(times, kind="stable")
    dataset = dataset.iloc[order].reset_index(drop=True)
    cut = int(len(dataset) * (1.0 - barrier.holdout_fraction))
    gap_rows = barrier.max_horizon * 2 * len(frames)
    dev = dataset.iloc[: cut - gap_rows]
    hold = dataset.iloc[cut + gap_rows:]
    log(f"development: {len(dev):,} | strict holdout: {len(hold):,} "
        f"(purge {gap_rows:,} rows)")

    # Chronological split of the strict holdout: cal-dev half (fit) + eval
    # half (report), with a purge gap between them.
    h = len(hold) // 2
    cal_dev = hold.iloc[: h - gap_rows]
    ev = hold.iloc[h + gap_rows:]
    log(f"cal-dev: {len(cal_dev):,} | eval: {len(ev):,} "
        f"(inter-holdout purge {2 * gap_rows:,} rows)")

    feature_columns = [c for c in dev.columns if c not in
                       {"timestamp", "symbol", "label", "net_atr", "resolved"}]
    X_dev, y_dev = dev[feature_columns], dev["label"].to_numpy()
    X_cal, y_cal = cal_dev[feature_columns], cal_dev["label"].to_numpy()
    X_ev, y_ev = ev[feature_columns], ev["label"].to_numpy()

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
    log(f"HGB fit done ({time.perf_counter() - started:.0f}s)")

    p_cal = aligned_probabilities(model, X_cal)[:, 2]
    p_ev = aligned_probabilities(model, X_ev)[:, 2]
    base_ev = float(y_ev.mean())
    ll_base = log_loss_bin(y_ev, np.full_like(p_ev, base_ev))

    # BEFORE
    ll_before = log_loss_bin(y_ev, p_ev)
    ece_before, curve_before = ece_and_curve(y_ev, p_ev)
    floor_before = floor_metrics(y_ev, p_ev)
    log(f"BEFORE cal: LL={ll_before:.4f} (base {ll_base:.4f}) | "
        f"ECE={ece_before:.4f} | floor{FLOOR}: {floor_before}")

    # AFTER: temperature scaling
    T = fit_temperature(p_cal, y_cal)
    p_temp = apply_temperature(p_ev, T)
    ll_temp = log_loss_bin(y_ev, p_temp)
    ece_temp, curve_temp = ece_and_curve(y_ev, p_temp)
    floor_temp = floor_metrics(y_ev, p_temp)
    log(f"TEMP T={T:.4f}: LL={ll_temp:.4f} | ECE={ece_temp:.4f} | "
        f"floor{FLOOR}: {floor_temp}")

    # AFTER: isotonic regression
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(p_cal, y_cal.astype(float))
    p_iso = np.clip(iso.predict(p_ev), EPS, 1.0 - EPS)
    ll_iso = log_loss_bin(y_ev, p_iso)
    ece_iso, curve_iso = ece_and_curve(y_ev, p_iso)
    floor_iso = floor_metrics(y_ev, p_iso)
    log(f"ISO: LL={ll_iso:.4f} | ECE={ece_iso:.4f} | floor{FLOOR}: {floor_iso}")

    # Candidate = better-LL calibrator; SHIP gate declared before the run.
    cands = {
        "temperature": {"ll": ll_temp, "ece": ece_temp, "floor": floor_temp,
                        "curve": curve_temp},
        "isotonic": {"ll": ll_iso, "ece": ece_iso, "floor": floor_iso,
                     "curve": curve_iso},
    }
    method = min(cands, key=lambda k: cands[k]["ll"])
    after = cands[method]
    gate_ll = after["ll"] < ll_before
    gate_ece = after["ece"] < ece_before
    gate_floor = (after["floor"]["precision"] is not None
                  and floor_before["precision"] is not None
                  and after["floor"]["precision"] >= floor_before["precision"])
    passed = bool(gate_ll and gate_ece and gate_floor)
    verdict = "CALIBRATION-PASS" if passed else "CALIBRATION-REJECT"
    log(f"E13 GATE ({method}): LL {ll_before:.4f}->{after['ll']:.4f} "
        f"({'ok' if gate_ll else 'FAIL'}) | ECE {ece_before:.4f}->"
        f"{after['ece']:.4f} ({'ok' if gate_ece else 'FAIL'}) | floor prec "
        f"{floor_before['precision']}->{after['floor']['precision']} "
        f"({'ok' if gate_floor else 'FAIL'}) => {verdict}")

    out = _LAB / "research_lab" / "results"
    out.mkdir(exist_ok=True)
    meta = {
        "experiment": "E13",
        "floor": FLOOR,
        "n_bins": N_BINS,
        "rows": {"dev": len(dev), "cal_dev": len(cal_dev), "eval": len(ev)},
        "label_balance": {"dev": float(y_dev.mean()), "cal_dev": float(y_cal.mean()),
                          "eval": float(y_ev.mean())},
        "base_rate_ll_eval": ll_base,
        "before": {"ll": ll_before, "ece": ece_before, "floor": floor_before,
                   "reliability": curve_before},
        "temperature": {"T": T, "ll": ll_temp, "ece": ece_temp,
                        "floor": floor_temp, "reliability": curve_temp},
        "isotonic": {"ll": ll_iso, "ece": ece_iso, "floor": floor_iso,
                     "reliability": curve_iso},
        "candidate_method": method,
        "after": {"ll": after["ll"], "ece": after["ece"], "floor": after["floor"],
                  "reliability": after["curve"]},
        "gate": {"ll_strictly_better": gate_ll, "ece_reduced": gate_ece,
                 "floor_precision_not_worse": gate_floor},
        "verdict": verdict,
        "fee_config": {k: getattr(fee_config, k) for k in
                       ("take_profit_atr", "stop_loss_atr", "max_horizon",
                        "fee_rate", "slippage_rate")},
        "elapsed_s": round(time.perf_counter() - started, 1),
    }
    (out / "e13cal_meta.json").write_text(json.dumps(meta, indent=2, default=str))

    if passed:
        # Lab artifact only — NOT wired into serving (separate deploy step).
        params: dict = {"method": method, "floor": FLOOR,
                        "fitted_on": "E13 cal-dev half of strict holdout"}
        if method == "temperature":
            params["T"] = T
        else:
            params["X_thresholds"] = [float(v) for v in iso.X_thresholds_]
            params["f"] = [float(v) for v in iso.f_]
        (out / "e13calibrator.json").write_text(json.dumps(params, indent=2))
        log("wrote results/e13calibrator.json (lab-only, not wired to serving)")

    log(f"E13 {verdict} ({time.perf_counter() - started:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
