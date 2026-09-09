"""E0 — bracket-geometry × confidence sweep on the incumbent pooled model's strict holdout.

Question (research-loop §19): does ANY (tp_atr, sl_atr, conf_floor) cell turn the
incumbent model's holdout probabilities into positive NET expectancy under the
production simulator? The served geometry is negative by construction; this runs
BEFORE any deep-learning investment.

Method — zero drift from production:
- Same data, features, warm-up, holdout carve, and per-variant barrier scoring as
  `barrier_pipeline` (functions imported, not copied).
- `_score_side` + `_expected_values` reproduce the engine's pricing (asserted
  against `domain.expected_value` on every call by `_expected_values` itself).
- `run_bracket_backtest` = the production simulator with config costs.

Per symbol we build features ONCE, then sweep the (geometry × floor) grid on the
cached probability matrix — 35 symbols × 42 cells in one pass.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

_LAB = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_LAB / "src"))
sys.path.insert(0, str(_LAB))

from crypto_signal.config import load_config  # noqa: E402
from crypto_signal.data import load_ohlcv  # noqa: E402
from crypto_signal.evaluation.bracket import BracketCosts, run_bracket_backtest  # noqa: E402
from crypto_signal.features import WARMUP_COLUMNS, build_features  # noqa: E402
from crypto_signal.training import barrier_pipeline as bp  # noqa: E402


def sweep_cell(
    long_probabilities: np.ndarray,
    short_probabilities: np.ndarray,
    pair: bp.BarrierPair,
    floor: float,
    allow_short: bool,
) -> np.ndarray:
    """Same selection rule as `_decide_window` (EV decides, tie → confidence, both floors)."""
    long_value = bp._expected_values(long_probabilities, pair)
    short_value = bp._expected_values(short_probabilities, pair)
    long_confidence = long_probabilities[:, bp.WIN_CLASS_INDEX]
    short_confidence = short_probabilities[:, bp.WIN_CLASS_INDEX]

    long_ok = (long_confidence >= floor) & (long_value >= bp.MINIMUM_EXPECTED_VALUE_ATR)
    short_ok = (
        (short_confidence >= floor)
        & (short_value >= bp.MINIMUM_EXPECTED_VALUE_ATR)
        & allow_short
    )
    take_long = long_ok & (
        ~short_ok
        | (long_value > short_value)
        | ((long_value == short_value) & (long_confidence >= short_confidence))
    )
    take_short = short_ok & ~take_long
    return np.where(
        take_long, int(bp.Direction.LONG), np.where(take_short, int(bp.Direction.SHORT), 0)
    )


def main() -> int:
    started = time.perf_counter()
    config = load_config(_LAB / "config.2y.toml")
    barrier = config.barrier

    frames = bp.download_barrier_data(config, refresh=False)
    symbols = sorted(frames)
    print(f"symbols: {len(symbols)}", flush=True)

    dataset = bp.build_barrier_dataset(
        frames,
        config.market.interval,
        max_horizon=barrier.max_horizon,
        pairs_per_candle=barrier.pairs_per_candle,
        grid=bp.barrier_grid(barrier.grid_atr, barrier.min_risk_reward, barrier.max_risk_reward),
        atr_window=barrier.atr_window,
        mtf_context=config.features.mtf_context,
        mtf_higher_interval=config.features.mtf_higher_interval,
        mtf_frames=None,
    )
    _development, holdout = bp._carve_holdout(dataset, barrier)
    holdout_times = pd.unique(dataset.times[holdout])
    selected = pd.to_datetime(pd.Series(holdout_times), utc=True)
    print(f"holdout candles: {len(holdout_times):,}", flush=True)

    bundle_path = config.output.model_dir / f"{bp.POOLED_STEM}_{config.market.interval}.joblib"
    bundle: dict[str, Any] = joblib.load(bundle_path)
    model = bundle["model"]
    model_columns = bp._model_feature_columns(dataset, tuple(bundle["feature_columns"]))

    costs = BracketCosts(fee_rate=config.backtest.fee_rate, slippage_rate=config.backtest.slippage_rate)
    geometries = [(1.5, 1.0), (2.0, 1.0), (2.0, 1.5), (2.5, 1.0), (3.0, 1.0), (3.0, 1.5), (4.0, 1.5)]
    floors = [0.36, 0.40, 0.44, 0.48, 0.52, 0.56]

    results: list[dict[str, Any]] = []
    for symbol in symbols:
        raw = frames[symbol]
        features = build_features(raw, atr_window=barrier.atr_window)
        frame = features.frame.copy()
        frame["timestamp"] = pd.to_datetime(raw["timestamp"].to_numpy(), utc=True)
        for column in ("open", "high", "low", "close"):
            frame[column] = raw[column].astype(float).to_numpy()
        frame["atr"] = features.atr.to_numpy(dtype=np.float64)
        warm = features.frame[list(WARMUP_COLUMNS)].notna().all(axis=1).to_numpy()
        frame = frame.loc[
            warm & frame["timestamp"].isin(selected).to_numpy() & (frame["atr"].to_numpy() > 0)
        ].reset_index(drop=True)
        if frame.empty:
            continue

        for tp, sl in geometries:
            pair = bp.BarrierPair(take_profit_atr=tp, stop_loss_atr=sl)
            long_p = bp._score_side(model, frame, model_columns, pair, bp.Direction.LONG, dataset)
            short_p = bp._score_side(model, frame, model_columns, pair, bp.Direction.SHORT, dataset)
            for floor in floors:
                direction = sweep_cell(long_p, short_p, pair, floor, barrier.allow_short)
                take = direction != 0
                if not take.any():
                    continue
                entry = frame["close"].to_numpy(dtype=np.float64)
                atr = frame["atr"].to_numpy(dtype=np.float64)
                decisions = pd.DataFrame({
                    "timestamp": frame["timestamp"],
                    "open": frame["open"], "high": frame["high"],
                    "low": frame["low"], "close": frame["close"], "atr": atr,
                    "direction": direction,
                    "take_profit_percent": [
                        bp.percent_from_atr(p, tp, a) if p > 0 else 0.0 for p, a in zip(entry, atr)
                    ],
                    "stop_loss_percent": [
                        bp.percent_from_atr(p, sl, a) if p > 0 else 0.0  # noqa: AttributeError guard
                        for p, a in zip(entry, atr)
                    ],
                })
                decisions = decisions[decisions["direction"] != 0].reset_index(drop=True)
                try:
                    _trades, metrics = run_bracket_backtest(
                        decisions, config.market.interval, barrier.max_horizon, costs
                    )
                except ValueError as exc:
                    # Ruin-level equity (return <= -100%) — the simulator refuses to quote
                    # metrics off an undefined equity curve. Record the cell as blown.
                    results.append({
                        "symbol": symbol, "tp_atr": tp, "sl_atr": sl, "conf_floor": floor,
                        "trades": int(take.sum()), "win_rate": np.nan,
                        "profit_factor": np.nan, "expectancy_atr": np.nan,
                        "total_return_percent": np.nan,
                    })
                    continue
                stats = metrics["trades"]
                results.append({
                    "symbol": symbol, "tp_atr": tp, "sl_atr": sl, "conf_floor": floor,
                    "trades": stats["trades"],
                    "win_rate": round(stats["win_rate"], 4),
                    "profit_factor": stats["profit_factor"],
                    "expectancy_atr": round(stats["expectancy_atr"], 4),
                    "total_return_percent": round(stats["total_return_percent"], 2),
                })
        print(f"  {symbol}: done @{time.perf_counter()-started:.0f}s", flush=True)

    out = _LAB / "research_lab" / "results"
    out.mkdir(exist_ok=True)
    frame_out = pd.DataFrame(results)
    frame_out.to_csv(out / "e0_geometry_sweep.csv", index=False)

    pooled = (
        frame_out.groupby(["tp_atr", "sl_atr", "conf_floor"])
        .agg(trades=("trades", "sum"), exp_weighted=("expectancy_atr", "mean"),
             pf_mean=("profit_factor", "mean"))
        .reset_index()
        .sort_values("exp_weighted", ascending=False)
    )
    pooled.to_csv(out / "e0_pooled_summary.csv", index=False)
    with pd.option_context("display.width", 200):
        print(pooled.head(15).to_string(index=False))
    (out / "e0_meta.json").write_text(json.dumps({
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "symbols": symbols, "geometries": geometries, "floors": floors,
        "costs": {"fee_rate": costs.fee_rate, "slippage_rate": costs.slippage_rate},
        "holdout_candles": int(len(holdout_times)),
    }, indent=2))
    print(f"E0 complete in {time.perf_counter()-started:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
