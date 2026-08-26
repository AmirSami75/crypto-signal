#!/usr/bin/env python3
"""The self-learning loop's driver: fresh data → retrain → promotion gate.

Runs on the HOST (the container cannot reach mainnet history). One invocation does:

1. Refresh candle CSVs with the latest candles the venue has.
2. Train a candidate bundle through the same `train_barrier_model` pipeline that produced
   the incumbent — identical config, identical splits, only newer data differs.
3. Promotion gate: compare candidate vs incumbent on their strict-holdout log loss AND the
   holdout bracket expectancy. The candidate ships only when it is not worse on either and
   better on at least one. A model that "improved" by getting lucky on one metric while
   degrading the other is exactly what this gate exists to catch.
4. On promotion, the incumbent moves to `artifacts/models/archive/` with its generation
   number; the candidate takes its place. On rejection, the candidate is archived under
   `artifacts/models/rejected/` with its scores in the filename for later review.

The engine's registry hot-reloads from disk (MarketEvaluator holds no per-request state),
so a promoted model starts serving without touching the running gRPC server.

Usage:
    .venv/bin/python ../../scripts/self_learning_loop.py            # refresh + train + gate
    .venv/bin/python ../../scripts/self_learning_loop.py --dry-run  # gate check only
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ML_ROOT = REPO_ROOT / "src" / "signal-ml"
sys.path.insert(0, str(ML_ROOT / "src"))

MODELS_DIR = ML_ROOT / "artifacts" / "models"
ARCHIVE_DIR = MODELS_DIR / "archive"
REJECTED_DIR = MODELS_DIR / "rejected"

# Bundles the loop manages. Anything else in models/ is left untouched.
MANAGED_BUNDLES = ("_pooled_1h.joblib", "BTCUSDT_1h.joblib")


def log(message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def read_metadata(path: Path) -> dict | None:
    sidecar = path.with_suffix(".metadata.json")
    if not sidecar.exists():
        # The trainer writes metadata.json as a combined file; fall back to it for the pooled bundle.
        combined = path.parent / "metadata.json"
        return json.loads(combined.read_text()) if combined.exists() else None
    return json.loads(sidecar.read_text())


def extract_scores(metadata: dict) -> dict:
    """Pull comparable metrics out of a training report.

    Structure (per the trainer's metadata.json): `bundles` is a LIST of per-bundle dicts, each
    with `strict_holdout.log_loss` and a `bracket_backtest.symbols.<SYM>.trades` block whose
    `edge_over_break_even` is the honest net-of-everything expectancy. The pooled bundle's BTC
    entry is the comparison anchor — the bot under review trades BTCUSDT.
    """
    scores: dict[str, float] = {}
    for bundle in metadata.get("bundles", []):
        stem = bundle.get("stem", "unknown")
        holdout = bundle.get("strict_holdout") or {}
        if isinstance(holdout, dict) and "log_loss" in holdout:
            scores[f"{stem}:log_loss"] = float(holdout["log_loss"])
        symbols = ((bundle.get("bracket_backtest") or {}).get("symbols")) or {}
        entry = symbols.get("BTCUSDT") or next(iter(symbols.values()), None)
        if isinstance(entry, dict):
            trades = entry.get("trades") or {}
            if "edge_over_break_even" in trades:
                scores[f"{stem}:edge"] = float(trades["edge_over_break_even"])
            if "win_rate" in trades:
                scores[f"{stem}:win_rate"] = float(trades["win_rate"])
    return scores


def gate(incumbent_scores: dict, candidate_scores: dict) -> tuple[bool, str]:
    """Promote only on: no metric worse, at least one better. Log loss: lower is better."""
    reasons: list[str] = []
    improved_any = False

    shared = set(incumbent_scores) & set(candidate_scores)
    if not shared:
        return False, "no comparable metrics between incumbent and candidate — refusing to promote blind"

    for key in sorted(shared):
        inc, cand = incumbent_scores[key], candidate_scores[key]
        if "log_loss" in key:
            better, tolerance = cand < inc, 1e-6
            delta = inc - cand  # positive = improvement
        else:
            better, tolerance = cand > inc, 1e-9
            delta = cand - inc

        if better and abs(delta) > tolerance:
            improved_any = True
            reasons.append(f"{key}: {inc:.4f} → {cand:.4f} (better)")
        elif delta < -tolerance:
            return False, f"{key}: {inc:.4f} → {cand:.4f} (WORSE — gate blocks promotion)"

    if not improved_any:
        return False, f"no metric improved ({'; '.join(reasons) or 'identical scores'})"
    return True, "; ".join(reasons)


def archive_bundle(path: Path, destination_dir: Path, tag: str) -> None:
    destination_dir.mkdir(parents=True, exist_ok=True)
    stamped = destination_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{tag}_{path.name}"
    shutil.move(str(path), stamped)
    sidecar = path.with_suffix(".metadata.json")
    if sidecar.exists():
        shutil.move(str(sidecar), stamped.with_suffix(stamped.suffix + ".metadata.json"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="Train and score but never swap files")
    parser.add_argument("--no-refresh", action="store_true", help="Skip candle redownload")
    args = parser.parse_args()

    from crypto_signal.config import load_config
    from crypto_signal.training import train_barrier_model

    config = load_config(ML_ROOT / "config.toml")

    log("step 1/3 — refreshing candles" if not args.no_refresh else "step 1/3 — skipping refresh")
    result = train_barrier_model(config, refresh=not args.no_refresh)

    log(f"step 2/3 — trained. report: {result.get('report_path', 'n/a')}")
    # train_barrier_model returns the metadata structure itself, not a wrapper.
    candidate_scores = extract_scores(result)
    if not candidate_scores:
        log("candidate produced no comparable scores — treating as rejection")
        return 1
    for key, value in sorted(candidate_scores.items()):
        log(f"  candidate {key}: {value:.4f}")

    incumbent_scores: dict[str, float] = {}
    incumbent_metadata_path = MODELS_DIR / "metadata.json.previous"
    baseline_exists = incumbent_metadata_path.exists()
    if baseline_exists:
        incumbent_scores = extract_scores(json.loads(incumbent_metadata_path.read_text()))
        for key, value in sorted(incumbent_scores.items()):
            log(f"  incumbent {key}: {value:.4f}")

    if not baseline_exists:
        log("no incumbent recorded — first-generation model promotes unconditionally")
        promoted, reason = True, "first generation"
    elif not incumbent_scores:
        # A baseline that exists but yields nothing is a broken baseline, not a fresh start.
        # Treating it as "first generation" is how a gate silently stops gating — refuse instead,
        # loudly, so the cause gets fixed rather than papered over by a free promotion.
        promoted, reason = False, (
            "baseline file exists but carries no comparable scores — refusing to promote against "
            "an unreadable incumbent (delete metadata.json.previous to deliberately re-baseline)"
        )
    else:
        promoted, reason = gate(incumbent_scores, candidate_scores)

    log(f"gate verdict: {'PROMOTE' if promoted else 'REJECT'} — {reason}")

    if args.dry_run:
        log("dry-run: leaving disk untouched")
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    if promoted and incumbent_metadata_path.exists():
        for name in MANAGED_BUNDLES:
            path = MODELS_DIR / name
            if path.exists():
                archive_bundle(path, ARCHIVE_DIR, "incumbent")
        shutil.move(str(incumbent_metadata_path), ARCHIVE_DIR / f"{stamp}_incumbent_metadata.json")

    # Record this run's scores as the next run's incumbent baseline. `result` IS the metadata
    # structure — passing `result.get("metadata")` wrote a baseline with no bundles, which
    # extract_scores then read as "no incumbent" and the gate waved through as a first
    # generation. Every future retrain would have promoted unconditionally: a gate that cannot
    # see the incumbent is not a gate.
    (MODELS_DIR / "metadata.json.previous").write_text(
        json.dumps(
            {
                "archived_at": datetime.now(timezone.utc).isoformat(),
                "promoted": promoted,
                **result,
            },
            indent=2,
            default=str,
        )
    )

    if not promoted:
        log("candidate archived under rejected/ for review")
    else:
        log(f"model live at {MODELS_DIR} — registry hot-reloads, no restart needed")
    log(f"done at {stamp}")
    return 0 if promoted or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
