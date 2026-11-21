"""Run the league until a wall-clock deadline, one model at a time, resumable by construction.

Each candidate runs in its own forked process so a model that hangs or eats the machine can be killed
without taking the campaign with it; its result — or its TIMEOUT — is appended to the same JSONL the
report is rendered from. Restarting the script skips whatever already has a row, which is what lets the
campaign survive a reboot, a container restart, or a curious operator pressing Ctrl-C.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

ML_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ML_ROOT / "src"))

from crypto_signal.data import load_ohlcv  # noqa: E402
from crypto_signal.domain import BarrierPair  # noqa: E402
from crypto_signal.labeling import build_barrier_dataset  # noqa: E402

from . import core  # noqa: E402
from .candidates import CLASSES, Candidate, candidates, expected_r_from_proba  # noqa: E402

DATA_DIR = ML_ROOT / "data"
CACHE_ROOT = core.ARTIFACT_ROOT / "datasets"


# ── dataset construction ────────────────────────────────────────────────────────


def dataset_plan(interval: str, symbols: tuple[str, ...]) -> dict:
    """What one interval's sample is. Kept explicit so two splits differ only by sampling seed."""
    return {
        "1h": {"pairs_per_candle": 2, "max_horizon": 24, "start": "2022-01-01"},
        "5m": {"pairs_per_candle": 2, "max_horizon": 72, "start": "2024-01-01"},
    }[interval] | {"symbols": symbols}


def build_dataset_payload(interval: str, seed: int, symbols: tuple[str, ...]) -> dict:
    plan = dataset_plan(interval, symbols)
    frames = {}
    for symbol in plan["symbols"]:
        path = DATA_DIR / f"{symbol}_{interval}.csv"
        if not path.exists():
            raise FileNotFoundError(f"missing candle file: {path}")
        # `load_ohlcv` validates the frame; anything it rejects is not data this league can score.
        frame = load_ohlcv(path, interval)
        frame = frame[frame["timestamp"] >= f"{plan['start']}T00:00:00Z"].reset_index(drop=True)
        if len(frame) > plan["max_horizon"] + 500:
            frames[symbol] = frame

    if not frames:
        raise RuntimeError(f"no usable candles for {interval} {symbols}")

    # Wider stops than the production grid on purpose: at a 1-ATR stop the round-trip fee is ~0.6R on 1h
    # candles, so every model loses by construction and the league ranks fee efficiency instead of skill.
    # The league scores at 4.5/3.0 ATR (~0.2R of fee) and reports the tight 1.5/1.0 bracket alongside.
    grid = [
        BarrierPair(1.0, 1.0),
        BarrierPair(1.5, 1.0),
        BarrierPair(2.0, 1.0),
        BarrierPair(1.5, 2.0),
        BarrierPair(3.0, 3.0),
        BarrierPair(4.5, 3.0),
    ]
    dataset = build_barrier_dataset(
        frames,
        interval,
        max_horizon=plan["max_horizon"],
        pairs_per_candle=plan["pairs_per_candle"],
        grid=grid,
        atr_window=14,
        random_state=seed,
    )
    frame = dataset.frame
    arrays = {
        "X": dataset.X.to_numpy(dtype=np.float32),
        "y": frame[dataset.label_column].to_numpy(dtype=np.int8),
        "r": frame["r_multiple"].to_numpy(dtype=np.float32),
        "times": frame[dataset.time_column].to_numpy(dtype="datetime64[ns]").astype("int64"),
        "entry": frame["entry_price"].to_numpy(dtype=np.float32),
        "atr": frame["atr"].to_numpy(dtype=np.float32),
        "stop_atr": frame["stop_loss_atr"].to_numpy(dtype=np.float32),
    }
    meta = {
        "interval": interval,
        "seed": seed,
        "symbols": list(frames),
        "rows": int(len(frame)),
        "candles": int(dataset.candle_count),
        "feature_names": list(dataset.feature_columns),
        "gap_rows": plan["max_horizon"],
        "built_at": datetime.now().isoformat(timespec="seconds"),
    }
    return {"arrays": arrays, "meta": meta}


def ensure_dataset(interval: str, seed: int, symbols: tuple[str, ...]) -> Path:
    cache_dir = CACHE_ROOT / f"{interval}_seed{seed}_{len(symbols)}sym"
    core.Dataset.load(cache_dir, lambda: build_dataset_payload(interval, seed, symbols))
    return cache_dir


# ── one candidate, in a child process ───────────────────────────────────────────


def _evaluate(cache_dir: Path, candidate: Candidate, seed: int) -> dict:
    started = time.perf_counter()
    ds = core.Dataset.load(cache_dir, lambda: (_ for _ in ()).throw(RuntimeError("cache missing")))
    train, calibration, holdout = ds.split.train, ds.split.calibration, ds.split.holdout

    if candidate.max_train_rows is not None and len(train) > candidate.max_train_rows:
        rng = np.random.default_rng(seed)
        train = rng.choice(train, size=candidate.max_train_rows, replace=False)

    X_train = ds.X[train]
    y_train = ds.y[train]
    r_train = ds.r[train]
    X_hold = ds.X[holdout]

    model = candidate.estimator(seed)
    fit_started = time.perf_counter()
    if candidate.kind == "classifier":
        model.fit(X_train, y_train)
    else:
        model.fit(X_train, r_train)
    fit_seconds = time.perf_counter() - fit_started

    metrics: dict = {}
    if candidate.kind == "classifier":
        probabilities = model.predict_proba(X_hold)
        # Some estimators (binary collapses, missing classes) return fewer columns; align to ALL_CLASSES.
        if probabilities.shape[1] != len(CLASSES):
            aligned = np.zeros((len(X_hold), len(CLASSES)))
            for index, label in enumerate(getattr(model, "classes_", CLASSES)):
                aligned[:, int(np.flatnonzero(CLASSES == label)[0])] = probabilities[:, index]
            probabilities = aligned
        metrics["classification"] = core.classification_metrics(ds.y[holdout], probabilities)
        predicted_r = expected_r_from_proba(probabilities, ds.X[holdout][:, list(ds.feature_names).index("take_profit_atr")],
                                            ds.X[holdout][:, list(ds.feature_names).index("stop_loss_atr")])
    else:
        predicted_r = np.asarray(model.predict(X_hold), dtype=float)
        metrics["regression"] = core.regression_metrics(ds.r[holdout].astype(float), predicted_r)

    fee = core.fee_in_r(ds.entry[holdout].astype(float), ds.atr[holdout].astype(float), ds.stop_atr[holdout].astype(float))
    tp_column = ds.X[holdout][:, list(ds.feature_names).index("take_profit_atr")]
    sl_column = ds.X[holdout][:, list(ds.feature_names).index("stop_loss_atr")]
    league = np.isclose(tp_column, core.LEAGUE_TAKE_PROFIT_ATR) & np.isclose(sl_column, core.LEAGUE_STOP_LOSS_ATR)
    tight = np.isclose(tp_column, core.TIGHT_TAKE_PROFIT_ATR) & np.isclose(sl_column, core.TIGHT_STOP_LOSS_ATR)

    metrics["trading"] = core.trading_metrics(
        ds.r[holdout][league].astype(float), predicted_r[league], fee[league], ds.times[holdout][league]
    )
    metrics["trading_tight"] = core.trading_metrics(
        ds.r[holdout][tight].astype(float), predicted_r[tight], fee[tight], ds.times[holdout][tight]
    )
    return {
        "model": candidate.name,
        "kind": candidate.kind,
        "status": "ok",
        "fit_seconds": fit_seconds,
        "eval_seconds": time.perf_counter() - started,
        "train_rows": int(len(train)),
        "holdout_rows": int(len(holdout)),
        "note": candidate.note,
        "metrics": metrics,
    }


def _child(cache_dir: str, candidate: Candidate, seed: int, queue) -> None:
    try:
        queue.put(_evaluate(Path(cache_dir), candidate, seed))
    except Exception as error:  # noqa: BLE001 — the parent records any failure as a row, never drops it
        queue.put({"model": candidate.name, "status": "error", "detail": f"{type(error).__name__}: {error}"})


def run_candidate(cache_dir: Path, interval: str, seed: int, candidate: Candidate) -> dict:
    context = mp.get_context("fork")
    queue = context.Queue()
    process = context.Process(target=_child, args=(str(cache_dir), candidate, seed, queue))
    started = time.perf_counter()
    process.start()
    process.join(candidate.timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(15)
        if process.is_alive():
            process.kill()
        return {
            "model": candidate.name,
            "interval": interval,
            "seed": seed,
            "status": "timeout",
            "detail": f"exceeded {candidate.timeout_seconds}s",
            "elapsed_seconds": time.perf_counter() - started,
        }

    try:
        result = queue.get_nowait()
    except Exception:  # noqa: BLE001 — a child that died without a payload is still a recorded outcome
        result = {"model": candidate.name, "status": "error", "detail": f"exitcode {process.exitcode}"}
    result.update({"interval": interval, "seed": seed})
    return result


# ── campaign loop ──────────────────────────────────────────────────────────────


def _done(rows: list[dict], interval: str, seed: int, model: str) -> bool:
    return any(
        row.get("interval") == interval
        and int(row.get("seed", -1)) == seed
        and row.get("model") == model
        for row in rows
    )


TG_REPORT = Path.home() / ".hermes" / "bin" / "tg-report"


def _digest(deadline_label: str, limit: int = 5) -> None:
    """Send the current top of the leaderboard to Telegram, if the project helper exists.

    Best-effort by design: a missing helper or a Telegram outage must never stop the campaign, and the
    report file on disk is always the source of truth.
    """
    if not TG_REPORT.exists():
        return
    rows = [row for row in core.load_results() if row.get("status") == "ok"]
    if not rows:
        return
    ranked = sorted(rows, key=lambda r: r["metrics"]["trading"]["expectancy_r_net"], reverse=True)[:limit]
    lines = [f"Model league — {deadline_label}", ""]
    for index, row in enumerate(ranked, 1):
        trading = row["metrics"]["trading"]
        lines.append(
            f"{index}. {row['model']} ({row['interval']}, seed {row['seed']}): "
            f"{trading['expectancy_r_net']:+.3f}R/trade · {trading['trades']} trades"
        )
    try:
        subprocess.run(
            [str(TG_REPORT), "model league digest", "\n".join(lines)],
            check=False,
            timeout=30,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:  # noqa: BLE001 — a digest failure is not a campaign failure
        pass


def _parse_deadline(value: str) -> float:
    """`--until 23:55` is today's clock time; a value already past means tomorrow."""
    hour, minute = (int(part) for part in value.split(":"))
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target.timestamp()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--until", default="23:55", help="wall-clock deadline, HH:MM (local)")
    parser.add_argument("--intervals", default="1h,5m")
    parser.add_argument("--symbols-1h", default="BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT")
    parser.add_argument("--symbols-5m", default="BTCUSDT")
    parser.add_argument("--seeds", default="42,7,2026")
    parser.add_argument("--only", default="", help="comma-separated model names, for a quick check")
    parser.add_argument("--digest-minutes", type=int, default=90, help="Telegram digest cadence (0 = off)")
    args = parser.parse_args()

    deadline = _parse_deadline(args.until)
    intervals = [item.strip() for item in args.intervals.split(",") if item.strip()]
    seeds = [int(item) for item in args.seeds.split(",") if item.strip()]
    symbol_map = {
        "1h": tuple(s.strip() for s in args.symbols_1h.split(",") if s.strip()),
        "5m": tuple(s.strip() for s in args.symbols_5m.split(",") if s.strip()),
    }
    wanted = {item.strip() for item in args.only.split(",") if item.strip()}
    queue_candidates = [c for c in candidates() if not wanted or c.name in wanted]

    print(f"[league] deadline {datetime.fromtimestamp(deadline):%Y-%m-%d %H:%M} · intervals={intervals} · seeds={seeds}", flush=True)
    core.ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)

    last_digest = 0.0
    round_index = 0
    while time.time() < deadline:
        for interval in intervals:
            symbols = symbol_map[interval]
            for seed in seeds:
                if time.time() >= deadline:
                    break
                print(f"[league] dataset {interval} seed={seed} symbols={len(symbols)}", flush=True)
                cache_dir = ensure_dataset(interval, seed + round_index, symbols)
                rows = core.load_results()
                for candidate in queue_candidates:
                    if time.time() >= deadline:
                        break
                    if _done(rows, interval, seed + round_index, candidate.name):
                        continue
                    print(f"[league] {interval}/seed{seed + round_index} · {candidate.name} …", flush=True)
                    result = run_candidate(cache_dir, interval, seed + round_index, candidate)
                    core.append_result(result)
                    status = result.get("status")
                    if status == "ok":
                        trading = result["metrics"]["trading"]
                        print(
                            f"[league]   ok · net {trading['expectancy_r_net']:+.4f}R/trade · "
                            f"{trading['trades']} trades · fit {result.get('fit_seconds', 0):.1f}s",
                            flush=True,
                        )
                    else:
                        print(f"[league]   {status}: {result.get('detail')}", flush=True)
                    core.write_report(datetime.fromtimestamp(deadline).strftime("%Y-%m-%d %H:%M"))
                    rows = core.load_results()
                    if args.digest_minutes and time.time() - last_digest >= args.digest_minutes * 60:
                        _digest(datetime.fromtimestamp(deadline).strftime("%Y-%m-%d %H:%M"))
                        last_digest = time.time()
        round_index += 1
        print(f"[league] round {round_index} complete — advancing sampling seed", flush=True)

    label = datetime.fromtimestamp(deadline).strftime("%Y-%m-%d %H:%M")
    core.write_report(label)
    final = core.write_final_report(label)
    _digest(label, limit=10)
    print(f"[league] deadline reached · final report {final}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
