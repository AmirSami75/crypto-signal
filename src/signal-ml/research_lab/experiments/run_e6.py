"""E6 — HGB vs multi-task TCN on the 15m dataset (§27 model comparison).

Question: does a sequence model (TCN, receptive field 31 candles ≈ 7.75h) with
auxiliary forecasting heads (return / MFE / MAE) extract MORE strict-holdout
edge than HGB from the same 15m features, and does that edge clear the
economic gate that E3-E5 failed?

Design (Muse-defensible):
- Identical rows, identical chronological split + purge as E4 (maker labels,
  12h horizon). HGB is the baseline; TCN the challenger.
- TCN sees sequences of the SAME feature vectors (lookback 32) — no extra
  information, so any gain is architecture, not data.
- Features standardised with statistics fitted on the DEVELOPMENT block only
  (no normalisation leakage), NaN -> 0 after standardisation.
- Early stopping on the LAST 15% of the development block (chronological), not
  on the holdout. The holdout is scored exactly once.
- Gate: strict LL vs HGB, AND economic cell (expectancy>0, PF>1, >=30 trades)
  under maker costs. The forecasting heads are reported (MAE/RMSE) as diagnostics.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

_LAB = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_LAB / "src"))
sys.path.insert(0, str(_LAB))

from crypto_signal.config import load_config  # noqa: E402
from crypto_signal.data import load_ohlcv  # noqa: E402
from crypto_signal.domain import percent_from_atr  # noqa: E402
from crypto_signal.evaluation.bracket import BracketCosts, run_bracket_backtest  # noqa: E402
from crypto_signal.features import WARMUP_COLUMNS, build_features  # noqa: E402
from crypto_signal.modeling.estimator import aligned_probabilities  # noqa: E402
from research_lab.experiments.run_e4 import maker_label_symbol  # noqa: E402
from research_lab.labels.fee_aware import FeeAwareConfig  # noqa: E402
from research_lab.labels.forecasting import forecasting_targets  # noqa: E402
from research_lab.models.tcn import MultiTaskTCN, multitask_loss  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
NON_FEATURE = {"timestamp", "symbol", "label", "net_atr", "resolved",
               "open", "high", "low", "close", "atr",
               "future_log_return", "mfe_atr", "mae_atr", "row_id"}
MAKER_FEE = 0.0002
LOOKBACK = 32
EPOCHS = 12
BATCH = 1024
SEED = 42
TRAIN_STRIDE = 3   # every 3rd dev window (adjacent windows are ~identical); holdout scored fully


def build_dataset(fee_config: FeeAwareConfig, atr_window: int) -> pd.DataFrame:
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
            labelled = maker_label_symbol(side, sign, fee_config, MAKER_FEE)
            targets = forecasting_targets(side, sign, fee_config.max_horizon)
            merged = side.merge(labelled[["timestamp", "label", "net_atr", "resolved"]],
                                on="timestamp", how="inner")
            merged = merged.merge(targets, on="timestamp", how="left")
            merged["symbol"] = symbol
            pieces.append(merged)
        print(f"  {symbol}: {len(frame):,} candles", flush=True)
    dataset = pd.concat(pieces, ignore_index=True)
    dataset = dataset.dropna(subset=["future_log_return", "mfe_atr", "mae_atr"]).reset_index(drop=True)
    return dataset


def make_sequences(frame: pd.DataFrame, feature_columns: list[str], mean: np.ndarray, std: np.ndarray,
                   lookback: int, stride: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """Per (symbol, direction) series: sliding windows of standardised features.

    Returns (X [N, lookback, F], keep_index [N]) where keep_index maps each
    window to the row it predicts (the window's last row). Rows without a full
    lookback are dropped — those are the first `lookback-1` rows of each series.
    """
    xs, idx = [], []
    for (_s, _d), group in frame.groupby(["symbol", "direction_sign"], sort=False):
        g = group.sort_values("timestamp")
        values = ((g[feature_columns].to_numpy(dtype=np.float32) - mean) / std)
        values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
        n = len(values)
        if n < lookback:
            continue
        # sliding windows via stride tricks
        windows = np.lib.stride_tricks.sliding_window_view(values, (lookback, values.shape[1]))[:, 0]
        xs.append(np.ascontiguousarray(windows[::stride]).astype(np.float32))
        idx.append(g.index.to_numpy()[lookback - 1:][::stride])
    return np.concatenate(xs), np.concatenate(idx)


def train_tcn(X: np.ndarray, y_dir: np.ndarray, y_ret: np.ndarray, y_mfe: np.ndarray, y_mae: np.ndarray,
              n_features: int, val_fraction: float = 0.15) -> tuple[MultiTaskTCN, dict]:
    torch.manual_seed(SEED)
    n = len(X)
    cut = int(n * (1 - val_fraction))  # chronological: sequences were built in time order per series;
    # to keep it chronological globally we sort by the predicted-row index before calling.
    Xt = torch.from_numpy(X)
    yd = torch.from_numpy(y_dir.astype(np.float32))
    yr = torch.from_numpy(np.clip(y_ret, -0.2, 0.2).astype(np.float32) * 10)   # scale to ~unit
    ym = torch.from_numpy(np.clip(y_mfe, 0, 10).astype(np.float32))
    ya = torch.from_numpy(np.clip(y_mae, 0, 10).astype(np.float32))

    model = MultiTaskTCN(n_features=n_features)
    optim = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(optim, T_max=EPOCHS)
    best_state, best_val, history = None, float("inf"), []
    train_idx = np.arange(cut)
    for epoch in range(EPOCHS):
        model.train()
        rng = np.random.default_rng(SEED + epoch)
        perm = rng.permutation(train_idx)
        total, steps = 0.0, 0
        t0 = time.perf_counter()
        for start in range(0, len(perm), BATCH):
            b = perm[start:start + BATCH]
            out = model(Xt[b])
            loss, _parts = multitask_loss(out, yd[b], yr[b], ym[b], ya[b])
            optim.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optim.step()
            total += float(loss); steps += 1
        sched.step()
        model.eval()
        with torch.no_grad():
            vb = slice(cut, n)
            vout = model(Xt[vb])
            vloss, vparts = multitask_loss(vout, yd[vb], yr[vb], ym[vb], ya[vb])
        history.append({"epoch": epoch + 1, "train": total / max(steps, 1), "val": float(vloss),
                        "val_dir": vparts["dir"], "secs": round(time.perf_counter() - t0, 1)})
        print(f"  epoch {epoch+1}/{EPOCHS} train {total/max(steps,1):.4f} val {float(vloss):.4f} "
              f"(dir {vparts['dir']:.4f}) {history[-1]['secs']}s", flush=True)
        if float(vloss) < best_val:
            best_val = float(vloss)
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)
    model.eval()
    return model, {"history": history, "best_val": best_val}


def economic_gate(hold: pd.DataFrame, p_win: np.ndarray, fee_config: FeeAwareConfig, costs: BracketCosts,
                  floors=(0.45, 0.50, 0.55, 0.60)) -> list[dict]:
    hold = hold.copy()
    hold["p_win"] = p_win
    rows = []
    for floor in floors:
        take = hold[hold["p_win"] >= floor]
        sims = []
        for (_s, sgn), group in take.groupby(["symbol", "direction_sign"]):
            g = group.sort_values("timestamp")
            e = g["close"].to_numpy(dtype=float); a = g["atr"].to_numpy(dtype=float)
            decisions = pd.DataFrame({
                "timestamp": g["timestamp"].to_numpy(),
                "open": g["open"], "high": g["high"], "low": g["low"], "close": g["close"], "atr": g["atr"],
                "direction": np.full(len(g), int(sgn), dtype=int),
                "take_profit_percent": [percent_from_atr(p, fee_config.take_profit_atr, x) for p, x in zip(e, a)],
                "stop_loss_percent": [percent_from_atr(p, fee_config.stop_loss_atr, x) for p, x in zip(e, a)],
            })
            try:
                _t, m = run_bracket_backtest(decisions, "15m", fee_config.max_horizon, costs)
                sims.append(m["trades"])
            except ValueError:
                continue
        if sims:
            trades = sum(s["trades"] for s in sims)
            ev = [s["expectancy_atr"] for s in sims if s["trades"]]
            pf = [s["profit_factor"] for s in sims if s["trades"] and s["profit_factor"]]
            if trades and ev:
                rows.append({"floor": floor, "trades": trades,
                             "expectancy_atr": round(float(np.mean(ev)), 4),
                             "pf_mean": round(float(np.mean(pf)), 3) if pf else None})
    return rows


def passes(gate: list[dict]) -> bool:
    return any(r["expectancy_atr"] > 0 and (r["pf_mean"] or 0) > 1.0 and r["trades"] >= 30 for r in gate)


def main() -> int:
    started = time.perf_counter()
    torch.set_num_threads(max(1, torch.get_num_threads() - 2))
    config = load_config(_LAB / "config.2y.toml")
    barrier = config.barrier
    fee_config = FeeAwareConfig(
        take_profit_atr=barrier.backtest_take_profit_atr, stop_loss_atr=barrier.backtest_stop_loss_atr,
        max_horizon=48, fee_rate=config.backtest.fee_rate, slippage_rate=config.backtest.slippage_rate,
    )
    dataset = build_dataset(fee_config, barrier.atr_window)
    times = pd.to_datetime(dataset["timestamp"], utc=True)
    dataset = dataset.iloc[np.argsort(times.to_numpy(), kind="stable")].reset_index(drop=True)
    dataset["row_id"] = np.arange(len(dataset))
    cut = int(len(dataset) * (1.0 - barrier.holdout_fraction))
    purge = fee_config.max_horizon * 2 * len(SYMBOLS)
    dev = dataset.iloc[: cut - purge]
    hold = dataset.iloc[cut + purge:]
    feature_columns = [c for c in dev.columns if c not in NON_FEATURE]
    print(f"rows {len(dataset):,} | dev {len(dev):,} | hold {len(hold):,} | features {len(feature_columns)}", flush=True)

    # ---- HGB baseline ----
    hgb = HistGradientBoostingClassifier(
        max_iter=config.model.max_iter, max_leaf_nodes=config.model.max_leaf_nodes,
        learning_rate=config.model.learning_rate, min_samples_leaf=config.model.min_samples_leaf,
        l2_regularization=config.model.l2_regularization, early_stopping=False,
        random_state=config.model.random_state,
    )
    hgb.fit(dev[feature_columns], dev["label"].to_numpy())
    p_hgb = aligned_probabilities(hgb, hold[feature_columns])[:, 2]
    y = hold["label"].to_numpy(); eps = 1e-6
    ll_hgb = float(-np.mean(y * np.log(p_hgb + eps) + (1 - y) * np.log(1 - p_hgb + eps)))
    costs = BracketCosts(fee_rate=MAKER_FEE, slippage_rate=config.backtest.slippage_rate)
    gate_hgb = economic_gate(hold, p_hgb, fee_config, costs)
    print(f"HGB strict LL {ll_hgb:.4f} | gate {gate_hgb}", flush=True)

    # ---- TCN challenger ----
    mean = dev[feature_columns].mean().to_numpy(dtype=np.float32)
    std = dev[feature_columns].std().replace(0, 1).to_numpy(dtype=np.float32)
    X_dev, idx_dev = make_sequences(dev, feature_columns, mean, std, LOOKBACK, stride=TRAIN_STRIDE)
    order = np.argsort(idx_dev, kind="stable")           # chronological for the val split
    X_dev, idx_dev = X_dev[order], idx_dev[order]
    d = dataset.loc[idx_dev]
    print(f"TCN sequences: dev {len(X_dev):,} × {LOOKBACK} × {len(feature_columns)} "
          f"({X_dev.nbytes/1e9:.2f} GB)", flush=True)
    tcn, fit = train_tcn(X_dev, d["label"].to_numpy(), d["future_log_return"].to_numpy(),
                         d["mfe_atr"].to_numpy(), d["mae_atr"].to_numpy(), len(feature_columns))

    X_hold, idx_hold = make_sequences(hold, feature_columns, mean, std, LOOKBACK)
    h = dataset.loc[idx_hold]
    with torch.no_grad():
        outs = [tcn(torch.from_numpy(X_hold[i:i + 8192])) for i in range(0, len(X_hold), 8192)]
    p_tcn = torch.cat([torch.sigmoid(o["direction_logit"]) for o in outs]).numpy()
    ret_hat = torch.cat([o["ret"] for o in outs]).numpy() / 10
    mfe_hat = torch.cat([o["mfe"] for o in outs]).numpy()
    mae_hat = torch.cat([o["mae"] for o in outs]).numpy()
    yh = h["label"].to_numpy()
    ll_tcn = float(-np.mean(yh * np.log(p_tcn + eps) + (1 - yh) * np.log(1 - p_tcn + eps)))
    # HGB on the SAME rows the TCN could score (drop first lookback-1 per series) for a fair LL
    p_hgb_same = aligned_probabilities(hgb, h[feature_columns])[:, 2]
    ll_hgb_same = float(-np.mean(yh * np.log(p_hgb_same + eps) + (1 - yh) * np.log(1 - p_hgb_same + eps)))
    gate_tcn = economic_gate(h, p_tcn, fee_config, costs)
    forecast = {
        "ret_mae": float(np.mean(np.abs(ret_hat - h["future_log_return"].to_numpy()))),
        "ret_mae_zero_baseline": float(np.mean(np.abs(h["future_log_return"].to_numpy()))),
        "mfe_mae": float(np.mean(np.abs(mfe_hat - h["mfe_atr"].to_numpy()))),
        "mfe_mae_mean_baseline": float(np.mean(np.abs(h["mfe_atr"].to_numpy() - d["mfe_atr"].mean()))),
        "mae_mae": float(np.mean(np.abs(mae_hat - h["mae_atr"].to_numpy()))),
        "mae_mae_mean_baseline": float(np.mean(np.abs(h["mae_atr"].to_numpy() - d["mae_atr"].mean()))),
    }
    print(f"TCN strict LL {ll_tcn:.4f} vs HGB(same rows) {ll_hgb_same:.4f} | gate {gate_tcn}", flush=True)
    print(f"forecast heads: {json.dumps({k: round(v, 5) for k, v in forecast.items()})}", flush=True)

    verdict = "PASS" if (ll_tcn < ll_hgb_same and passes(gate_tcn)) else "REJECT"
    meta = {
        "hgb": {"log_loss": ll_hgb, "log_loss_same_rows": ll_hgb_same, "gate": gate_hgb},
        "tcn": {"log_loss": ll_tcn, "gate": gate_tcn, "fit": fit, "forecast_heads": forecast,
                "lookback": LOOKBACK, "epochs": EPOCHS, "params": sum(p.numel() for p in tcn.parameters())},
        "delta_log_loss_tcn_minus_hgb": round(ll_tcn - ll_hgb_same, 5),
        "verdict": verdict, "holdout_rows_scored": int(len(h)),
        "seconds": round(time.perf_counter() - started),
    }
    out = _LAB / "research_lab" / "results"
    (out / "e6_meta.json").write_text(json.dumps(meta, indent=2, default=str))
    torch.save(tcn.state_dict(), out / "e6_tcn.pt")
    print(f"E6 VERDICT: {verdict} | ΔLL(TCN−HGB) {ll_tcn - ll_hgb_same:+.5f} ({meta['seconds']}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
