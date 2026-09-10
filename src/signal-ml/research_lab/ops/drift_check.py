"""Feature-drift monitor: live vs training-reference distributions via PSI.

Compares the distribution of each training feature over a recent ("live")
window against a training ("reference") window and reports the Population
Stability Index (PSI) per feature plus an overall PASS / WARN / FAIL verdict.

Data source: local OHLCV CSVs (``data/<SYMBOL>_<interval>.csv``) — the same
candles the training pipeline consumes. Features are rebuilt with the shared
``crypto_signal.features.build_features`` so training/serving skew cannot hide
inside a duplicated feature definition. (The .NET side's StrategyDecision-linked
candles are the same Binance klines; when a decisions export exists it can be
passed via --live-csv to score exactly the traded population instead of the
trailing window.)

Exit codes: 0 = PASS, 1 = WARN, 2 = FAIL, 3 = operational error.
Read-only: never writes, never trains, never touches bots/risk/serving.

Usage:
    .venv/bin/python research_lab/ops/drift_check.py --symbol BTCUSDT --interval 1h
    .venv/bin/python research_lab/ops/drift_check.py --symbol BTCUSDT --interval 1h --live-window 720 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_LAB = Path(__file__).resolve().parents[1]          # research_lab/
REPO = _LAB.parent                                   # signal-ml/
sys.path.insert(0, str(REPO / "src"))

from crypto_signal.data import load_ohlcv  # noqa: E402
from crypto_signal.features import build_features  # noqa: E402

# PSI bands (industry-standard cut points).
WARN_PSI = 0.10   # single feature above this -> at least WARN
FAIL_PSI = 0.25   # single feature above this -> FAIL
FAIL_FEATURE_COUNT = 3  # >= this many features above WARN -> FAIL
N_BINS = 10
EPS = 1e-6


def psi(expected, actual, bins: int = N_BINS) -> float:
    """Population Stability Index of `actual` vs `expected` (reference)."""
    ref = pd.Series(expected).dropna().to_numpy(dtype=float)
    live = pd.Series(actual).dropna().to_numpy(dtype=float)
    if ref.size == 0 or live.size == 0:
        return float("nan")
    if np.all(ref == ref[0]) and np.all(live == live[0]):
        return 0.0 if ref[0] == live[0] else 1.0
    edges = np.quantile(ref, np.linspace(0, 1, bins + 1))
    edges = np.unique(edges)
    if len(edges) < 3:  # near-constant reference; fall back to mean-shift scale
        spread = ref.std() or abs(ref.mean()) or 1.0
        return float(min(1.0, abs(live.mean() - ref.mean()) / spread))
    edges[0], edges[-1] = -np.inf, np.inf
    ref_counts, _ = np.histogram(ref, bins=edges)
    live_counts, _ = np.histogram(live, bins=edges)
    ref_pct = np.clip(ref_counts / ref_counts.sum(), EPS, None)
    live_pct = np.clip(live_counts / live_counts.sum(), EPS, None)
    ref_pct /= ref_pct.sum()
    live_pct /= live_pct.sum()
    return float(np.sum((live_pct - ref_pct) * np.log(live_pct / ref_pct)))


def verdict_for(psi_by_feature: dict[str, float],
                warn: float = WARN_PSI,
                fail: float = FAIL_PSI) -> str:
    vals = [v for v in psi_by_feature.values() if not np.isnan(v)]
    if not vals:
        return "FAIL"
    n_warn = sum(v >= warn for v in vals)
    if any(v >= fail for v in vals) or n_warn >= FAIL_FEATURE_COUNT:
        return "FAIL"
    if n_warn:
        return "WARN"
    return "PASS"


EXIT_CODE = {"PASS": 0, "WARN": 1, "FAIL": 2}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Feature-drift check (PSI) vs training reference.")
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--interval", default="1h")
    p.add_argument("--data-dir", default=str(REPO / "data"),
                   help="Directory holding <SYMBOL>_<interval>.csv")
    p.add_argument("--live-csv", default=None,
                   help="Optional CSV of exactly the traded/live population "
                        "(e.g. StrategyDecisions-linked candles export). "
                        "Same OHLCV schema. Overrides --live-window.")
    p.add_argument("--live-window", type=int, default=720,
                   help="Trailing candles forming the live window (default 720 ≈ 30d @1h).")
    p.add_argument("--warn", type=float, default=WARN_PSI)
    p.add_argument("--fail", type=float, default=FAIL_PSI)
    p.add_argument("--json", action="store_true", help="Emit machine-readable JSON only.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        ref_path = Path(args.data_dir) / f"{args.symbol}_{args.interval}.csv"
        ref_frame = load_ohlcv(ref_path, args.interval)
    except Exception as exc:
        print(f"drift_check ERROR: cannot load reference candles: {exc}", file=sys.stderr)
        return 3

    if args.live_csv:
        try:
            live_frame = load_ohlcv(Path(args.live_csv), args.interval)
        except Exception as exc:
            print(f"drift_check ERROR: cannot load --live-csv: {exc}", file=sys.stderr)
            return 3
        live_source = args.live_csv
    else:
        if len(ref_frame) <= args.live_window:
            print(f"drift_check ERROR: only {len(ref_frame)} candles, "
                  f"live-window needs {args.live_window}", file=sys.stderr)
            return 3
        live_frame = ref_frame.tail(args.live_window).reset_index(drop=True)
        ref_frame = ref_frame.iloc[:-args.live_window].reset_index(drop=True)
        live_source = f"trailing {args.live_window} candles"

    try:
        ref_feat = build_features(ref_frame).frame.dropna().reset_index(drop=True)
        live_feat = build_features(live_frame).frame.dropna().reset_index(drop=True)
    except Exception as exc:
        print(f"drift_check ERROR: feature build failed: {exc}", file=sys.stderr)
        return 3

    shared = [c for c in ref_feat.columns if c in live_feat.columns]
    psi_by_feature = {c: psi(ref_feat[c], live_feat[c]) for c in shared}
    verdict = verdict_for(psi_by_feature, warn=args.warn, fail=args.fail)

    payload = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": args.symbol,
        "interval": args.interval,
        "reference_rows": int(len(ref_feat)),
        "live_rows": int(len(live_feat)),
        "live_source": live_source,
        "thresholds": {"warn_psi": args.warn, "fail_psi": args.fail,
                       "fail_feature_count": FAIL_FEATURE_COUNT, "bins": N_BINS},
        "psi_by_feature": {k: round(v, 4) for k, v in sorted(
            psi_by_feature.items(), key=lambda kv: kv[1], reverse=True)},
        "features_warn_or_worse": sum(v >= args.warn for v in psi_by_feature.values()),
        "max_psi": round(float(max(psi_by_feature.values())), 4),
        "verdict": verdict,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"drift_check {args.symbol} {args.interval} | "
              f"ref={len(ref_feat)} rows live={len(live_feat)} rows ({live_source})")
        print(f"{'feature':<24}{'PSI':>8}  flag")
        for name, v in sorted(psi_by_feature.items(), key=lambda kv: kv[1], reverse=True):
            flag = "FAIL" if v >= args.fail else ("warn" if v >= args.warn else "ok")
            print(f"{name:<24}{v:>8.4f}  {flag}")
        print(f"verdict: {verdict} "
              f"(max PSI {payload['max_psi']}, "
              f"{payload['features_warn_or_worse']} features >= warn {args.warn})")
    return EXIT_CODE[verdict]


if __name__ == "__main__":
    sys.exit(main())
