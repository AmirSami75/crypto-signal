"""E11-lite — HGB baseline vs DeepLOB on the S-razmi BTC LOB file.

Question: does second-level LOB microstructure (DeepLOB or a flat HGB on the
same snapshots) carry fee-beating directional sign at futures costs?

Data (read-only, gitignored): research_lab/data/micro/BTCUSDT/lob/
    BTCUSDT-lob-sraz-2023-01.csv — 3.73M rows, 2023-01-09..2023-01-20 (~11d).
    cols: index, epoch_ms, datetime, then 40 floats = 10 bid levels
    (price-desc, px/qty alternating) then 10 ask levels (price-asc).

Pipeline:
 (1) chunked CSV stream -> mid series; rolling-DAY trailing z-score per LOB
     column (fixed window W = rows/24h from median cadence); (100,40)
     non-overlapping snapshot windows of z-scored features.
 (2) 3-class mid-price labels (down/flat/up = 0/1/2) at k=10 and k=50 rows
     ahead; dead zone theta_k = median |move| on DEV rows only.
 (3) HGB on flattened windows FIRST (same rows both models). DeepLOB trains
     ONLY if HGB dev log-loss margin vs base rate > 0 (primary horizon k=50).
 (4) Economics: per-window P(up)-P(down) averaged into 15m bins -> bin bet
     direction; fee-aware net outcome (TP1.5/SL1.0 ATR, H=48 = 12h, futures
     costs 0.05% taker + 0.02% slip) via research_lab/labels/fee_aware.py;
     sequential non-overlapping book on strict-holdout TEST bins only.
Gate (E8-upgrade): strict holdout last 3 days (purge label-horizon rows at
 boundaries); sequential book; bootstrap (2000x) CI lower > 0; LL margin > 0;
 20x shuffled-direction null with pass <= 1/20.
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

from research_lab.labels.fee_aware import FeeAwareConfig, label_symbol  # noqa: E402
from research_lab.models.deeplob import DeepLOB  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.metrics import log_loss, roc_auc_score  # noqa: E402

DATA = _LAB / "data/micro/BTCUSDT/lob/BTCUSDT-lob-sraz-2023-01.csv"
RESULTS = _LAB / "results"
SEED = 11
T, STRIDE = 100, 100
K10, K50 = 10, 50
FEE_CFG = FeeAwareConfig(take_profit_atr=1.5, stop_loss_atr=1.0,
                         max_horizon=48, fee_rate=0.0005, slippage_rate=0.0002)
DAY_MS = 86_400_000
log = lambda m: (print(m, flush=True))  # noqa: E731


def load_streaming(path: Path):
    """Chunked read; returns epoch_ms (int64) + raw 40-col float32 + med_dt."""
    names = ["idx", "epoch_ms", "dt"] + [f"c{i}" for i in range(40)]
    use = ["epoch_ms"] + [f"c{i}" for i in range(40)]
    dts = {f"c{i}": np.float32 for i in range(40)}
    ep_parts, raw_parts, dtsamp = [], [], []
    for ch in pd.read_csv(path, names=names, header=0, usecols=[1] + list(range(3, 43)),
                          dtype={**{"epoch_ms": np.int64}, **dts},
                          chunksize=500_000):
        ep_parts.append(ch["epoch_ms"].to_numpy())
        raw_parts.append(ch[[f"c{i}" for i in range(40)]].to_numpy(dtype=np.float32))
        if len(dtsamp) < 20_000:
            dtsamp.append(ch["epoch_ms"].to_numpy()[:20_000])
    ep = np.concatenate(ep_parts)
    raw = np.concatenate(raw_parts)
    med_dt = float(np.median(np.diff(np.concatenate(dtsamp))))
    return ep, raw, med_dt


def rolling_z(raw: np.ndarray, w: int) -> np.ndarray:
    """Trailing-w rolling z-score per column, pandas (Cython) in 10-col blocks."""
    n, f = raw.shape
    z = np.empty((n, f), dtype=np.float32)
    df = pd.DataFrame(raw)
    for a in range(0, f, 10):
        blk = df.iloc[:, a:a + 10]
        mu = blk.rolling(w, min_periods=w).mean()
        sd = blk.rolling(w, min_periods=w).std(ddof=0)
        z[:, a:a + 10] = ((blk - mu) / sd.where(sd > 1e-9, np.nan)).to_numpy(dtype=np.float32)
    return z


def dir_auc(y: np.ndarray, p: np.ndarray) -> float:
    m = y != 1
    if m.sum() < 20 or len(np.unique(y[m])) < 2:
        return float("nan")
    s = p[m, 2] / np.clip(p[m, 0] + p[m, 2], 1e-12, None)
    return float(roc_auc_score((y[m] == 2).astype(int), s))


def fit_hgb(Xtr, ytr, seed=SEED):
    clf = HistGradientBoostingClassifier(max_iter=150, learning_rate=0.1,
                                         early_stopping=False, random_state=seed)
    clf.fit(Xtr, ytr)
    return clf


def eval_3class(y, p) -> dict:
    base = np.tile(np.bincount(y, minlength=3) / len(y), (len(y), 1))
    ll, llb = float(log_loss(y, p)), float(log_loss(y, base))
    try:
        macro = float(roc_auc_score(y, p, multi_class="ovr"))
    except Exception:
        macro = float("nan")
    return {"ll": ll, "ll_base": llb, "ll_margin": ll - llb,
            "auc_dir": dir_auc(y, p), "auc_macro": macro}


def train_deeplob(Xtr, ytr, Xdev, ydev):
    import torch
    from torch.utils.data import DataLoader, TensorDataset
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    dev = torch.device("cpu")
    net = DeepLOB().to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=1e-3)
    crit = torch.nn.CrossEntropyLoss()
    tl = DataLoader(TensorDataset(torch.from_numpy(Xtr), torch.from_numpy(ytr)),
                    batch_size=256, shuffle=True)
    net.train()
    for _ in range(8):
        for xb, yb in tl:
            xb, yb = xb.to(dev), yb.to(dev)
            opt.zero_grad()
            loss = crit(net.forward_logits(xb), yb)
            loss.backward()
            opt.step()
    net.eval()
    out = {}
    with torch.no_grad():
        for tag, Xx in (("tr", Xtr), ("dev", Xdev)):
            probs = []
            for i in range(0, len(Xx), 1024):
                probs.append(net(torch.from_numpy(Xx[i:i + 1024]).to(dev)).cpu().numpy())
            out[tag] = np.concatenate(probs)
    return net, out["dev"]


def wilder_atr(h, l, c, n=14):
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    tr[0] = h[0] - l[0]
    atr = np.empty_like(tr)
    atr[n - 1] = tr[:n].mean()
    for i in range(n, len(tr)):
        atr[i] = (atr[i - 1] * (n - 1) + tr[i]) / n
    atr[:n - 1] = np.nan
    return atr


def economics(mid: np.ndarray, ep: np.ndarray, sig: np.ndarray, sig_t: np.ndarray,
              test_start_ms: int):
    """15m mid candles + ATR14; bin signals; sequential non-overlapping book."""
    ts = pd.to_datetime(ep, unit="ms", utc=True)
    df = pd.DataFrame({"ts": ts, "mid": mid}).set_index("ts")
    o = df["mid"].resample("15min").agg(["first", "max", "min", "last"]).dropna()
    o.columns = ["open", "high", "low", "close"]
    o["atr"] = wilder_atr(o.high.to_numpy(), o.low.to_numpy(), o.close.to_numpy())
    o = o.dropna().reset_index(names="timestamp")
    L = {s: label_symbol(o[["timestamp", "open", "high", "low", "close", "atr"]], s, FEE_CFG)
             for s in (1, -1)}
    netmap = {s: dict(zip(L[s]["timestamp"].astype("int64"), L[s]["net_atr"])) for s in (1, -1)}
    bins = o["timestamp"].to_numpy()
    bidx = np.searchsorted(bins, pd.to_datetime(sig_t, unit="ms", utc=True).to_numpy())
    agg = np.zeros(len(o))
    cnt = np.zeros(len(o))
    m = bidx < len(o)
    np.add.at(agg, bidx[m], sig[m])
    np.add.at(cnt, bidx[m], 1)
    with np.errstate(invalid="ignore"):
        mean_sig = np.where(cnt > 0, agg / cnt, np.nan)
    t0 = int(np.searchsorted(bins, pd.Timestamp(test_start_ms, unit="ms", tz="UTC")))
    H = FEE_CFG.max_horizon
    spots, seq = [], []
    i = t0
    while i < len(o) - H:
        d = 0 if np.isnan(mean_sig[i]) else int(np.sign(mean_sig[i]))
        spots.append((i, d))
        if d != 0:
            k = int(bins[i].value) if hasattr(bins[i], "value") else int(bins[i].astype("int64"))
            seq.append(netmap[d].get(k, np.nan))
            i += H
        else:
            i += 1
    seq = np.array(seq, dtype=float)
    seq = seq[np.isfinite(seq)]
    exp = float(seq.mean()) if len(seq) else float("nan")
    pf = float(seq[seq > 0].sum() / abs(seq[seq < 0].sum())) if (seq < 0).any() and (seq > 0).any() else float("nan")
    rng = np.random.default_rng(SEED)
    boots = rng.choice(seq, size=(2000, len(seq)), replace=True).mean(axis=1) if len(seq) else np.array([np.nan])
    ci = float(np.nanquantile(boots, 0.025))
    # 20x shuffled-direction null
    dirs = np.array([d for _, d in spots])
    passes = 0
    for r in range(20):
        sh = rng.permutation(dirs)
        sq, j = [], 0
        for k2, d2 in zip([i for i, _ in spots], sh):
            if j > 0:
                j -= 1
                continue
            if d2 != 0 and k2 < len(o) - H:
                kk = int(bins[k2].value) if hasattr(bins[k2], "value") else int(bins[k2].astype("int64"))
                v = netmap[int(d2)].get(kk, np.nan)
                if np.isfinite(v):
                    sq.append(v)
                j = H - 1
        sq = np.array(sq)
        if len(sq):
            b = rng.choice(sq, size=(500, len(sq)), replace=True).mean(axis=1)
            if sq.mean() > 0 and float(np.quantile(b, 0.025)) > 0:
                passes += 1
    return {"n_bins": len(o), "n_test_bins": len(o) - t0, "n_trades": int(len(seq)),
            "expectancy": exp, "pf": pf, "ci_lower": ci, "null_passes": passes,
            "fees": {"fee_rate": FEE_CFG.fee_rate, "slippage_rate": FEE_CFG.slippage_rate}}


def main():
    t_start = time.time()
    RESULTS.mkdir(exist_ok=True)
    log(f"DATA={DATA} bytes={DATA.stat().st_size}")
    ep, raw, med_dt = load_streaming(DATA)
    n = len(ep)
    log(f"rows={n} span_ms={ep[-1]-ep[0]} med_dt_ms={med_dt:.1f}")
    W = int(round(DAY_MS / med_dt))
    log(f"roll_window_W={W} (~24h)")
    bid0, ask0 = raw[:, 0], raw[:, 20]
    mid = ((bid0.astype(np.float64) + ask0.astype(np.float64)) / 2)
    spread_bps = (ask0 - bid0) / mid * 1e4
    log(f"mid[0]={mid[0]:.2f} mid[-1]={mid[-1]:.2f} med_spread_bps={float(np.median(spread_bps)):.2f}")
    z = rolling_z(raw, W)
    del raw
    test0 = int(ep[-1] - 3 * DAY_MS)
    dev0 = int(test0 - 2 * DAY_MS)
    log(f"dev_start_ms={dev0} test_start_ms={test0}")
    starts = np.arange(W, n - K50 - T, STRIDE)
    t_end = starts + T
    split = np.where(ep[t_end] < dev0, 0, np.where(ep[t_end] < test0, 1, 2))
    # purge: label horizon (t_end-1+k) must not cross a boundary
    cross = ((ep[t_end] < dev0) != (ep[t_end - 1 + K50] < dev0)) | \
            ((ep[t_end] < test0) != (ep[t_end - 1 + K50] < test0))
    keep = ~cross
    starts, split = starts[keep], split[keep]
    log(f"windows={len(starts)} train/dev/test={[(split==s).sum() for s in (0,1,2)]} purged={int(cross.sum())}")
    X = z[starts[:, None] + np.arange(T)].reshape(len(starts), T, 40).astype(np.float32)
    del z
    y, thetas, bals = {}, {}, {}
    for tag, k in (("k10", K10), ("k50", K50)):
        mv = mid[starts + T - 1 + k] - mid[starts + T - 1]
        theta = float(np.quantile(np.abs(mv[split == 1]), 0.5))
        thetas[tag], bals[tag] = theta, [int(((np.sign(mv) * (np.abs(mv) >= theta)) == v).sum()) for v in (-1, 0, 1)]
        y[tag] = (np.sign(mv) * (np.abs(mv) >= theta)).astype(int)
        y[tag] = np.where(y[tag] == -1, 0, np.where(y[tag] == 0, 1, 2)).astype(np.int64)
        log(f"{tag}: theta_dev_med={theta:.4f} USD balance(d/f/u)={bals[tag]}")
    out = {"experiment_id": "E11-lite", "seed": SEED, "rows": n,
           "roll_window_W": W, "theta": thetas, "balance": bals,
           "splits": {s: int((split == i).sum()) for i, s in enumerate(("train", "dev", "test"))}}
    trained, probs = {}, {}
    for tag in ("k10", "k50"):
        yy = y[tag]
        tr, dv, te = split == 0, split == 1, split == 2
        clf = fit_hgb(X[tr].reshape(tr.sum(), -1), yy[tr])
        p = {s: clf.predict_proba(X[m].reshape(m.sum(), -1)) for s, m in
             (("dev", dv), ("test", te))}
        m_dev, m_test = eval_3class(yy[dv], p["dev"]), eval_3class(yy[te], p["test"])
        log(f"HGB-{tag} dev LL={m_dev['ll']:.4f} base={m_dev['ll_base']:.4f} "
            f"margin={m_dev['ll_margin']:+.4f} auc_dir={m_dev['auc_dir']:.4f} | "
            f"test LL={m_test['ll']:.4f} margin={m_test['ll_margin']:+.4f}")
        out[tag] = {"hgb": {"dev": m_dev, "test": m_test}}
        trained[tag], probs[tag] = clf, p
    gate = bool(out["k50"]["hgb"]["dev"]["ll_margin"] > 0)
    log(f"DeepLOB-gate (HGB k50 dev LL margin>0): {'TRAIN' if gate else 'SKIP'}")
    out["deeplob_trained"] = gate
    model_tag, model_probs = "hgb", None
    if gate:
        tr, dv, te = split == 0, split == 1, split == 2
        Xc = X.reshape(len(X), 1, T, 40)
        net_trained, pdev = train_deeplob(Xc[tr], y["k50"][tr], Xc[dv], y["k50"][dv])
        import torch as _t
        net_trained.eval()
        m_dev = eval_3class(y["k50"][dv], pdev)
        log(f"DeepLOB-k50 dev LL={m_dev['ll']:.4f} base={m_dev['ll_base']:.4f} "
            f"margin={m_dev['ll_margin']:+.4f} auc_dir={m_dev['auc_dir']:.4f}")
        out["k50"]["deeplob"] = {"dev": m_dev}
        model_tag = "deeplob"
    # economics on primary (k50) test predictions
    yy = y["k50"]
    te = split == 2
    if model_tag == "deeplob":
        import torch
        with torch.no_grad():
            chunks = [net_trained(torch.from_numpy(Xc[te][i:i + 1024])).numpy()
                      for i in range(0, te.sum(), 1024)]
        pte = np.concatenate(chunks)
    else:
        pte = trained["k50"].predict_proba(X[te].reshape(te.sum(), -1))
    sig = pte[:, 2] - pte[:, 0]
    sig_t = ep[starts[te] + T - 1]
    eco = economics(mid, ep, sig, sig_t, test0)
    log(f"ECON n_trades={eco['n_trades']} exp={eco['expectancy']:.4f} pf={eco['pf']:.3f} "
        f"ci_low={eco['ci_lower']:.4f} null={eco['null_passes']}/20")
    out["economics"] = eco
    m = out["k50"]["deeplob" if gate else "hgb"]["dev" if gate else "test"]
    cells = {"ll_margin_gt0": bool(out[("k50")]["deeplob" if gate else "hgb"]
                                   [("dev" if gate else "test")]["ll_margin"] > 0),
             "expectancy_gt0": bool(eco["expectancy"] > 0),
             "ci_lower_gt0": bool(eco["ci_lower"] > 0),
             "null_le1": bool(eco["null_passes"] <= 1),
             "trades_ge5": bool(eco["n_trades"] >= 5)}
    verdict = "PASS" if all(cells.values()) else "REJECT"
    out.update({"cells": cells, "verdict": verdict,
                "elapsed_min": round((time.time() - t_start) / 60, 1)})
    (RESULTS / "e11lite_meta.json").write_text(json.dumps(out, indent=2))
    log(f"VERDICT={verdict} cells={json.dumps(cells)} elapsed_min={out['elapsed_min']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
