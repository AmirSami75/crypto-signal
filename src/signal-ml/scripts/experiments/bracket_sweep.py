"""Bracket sweep (roadmap 1.1): backtest every TP/SL pair in the barrier grid against the strict holdout.

Scores the incumbent per-symbol trees bundle (`BTCUSDT_1h.joblib`) on every (take_profit_atr,
stop_loss_atr) pair the labelling grid defines, using the *same* decision rule the serving path uses
(`_decide_window`: confidence floor + expected-value floor + direction choice), and reports per pair:
trade count, win rate vs the break-even ladder, expectancy in % and ATR, cumulative return and max
drawdown. The deliverable is the answer to "does ANY bracket clear costs".

Run from `src/signal-ml`:
    .venv/bin/python scripts/experiments/bracket_sweep.py [--config config.toml]

Writes `artifacts/bracket_sweep/{report.md, results.json}`.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import sys
import time

import joblib
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crypto_signal.config import AppConfig, load_config
from crypto_signal.evaluation.bracket import BracketCosts, run_bracket_backtest
from crypto_signal.labeling.triple_barrier import barrier_grid, build_barrier_dataset
from crypto_signal.log_setup import configure_logging, get_logger
from crypto_signal.training.barrier_pipeline import (
    _carve_holdout,
    _decide_window,
    download_barrier_data,
)

logger = get_logger(__name__)

#: The incumbent that must be beaten: the per-symbol trees override, not the pooled artifact —
#: `_pooled_1h.joblib` currently holds the (rejected) LSTM challenger.
INCUMBENT_PATH = Path("artifacts/models/BTCUSDT_1h.joblib")
OUTPUT_DIR = Path("artifacts/bracket_sweep")


def sweep(config: AppConfig) -> list[dict]:
    started = time.perf_counter()
    bundle = joblib.load(INCUMBENT_PATH)
    model = bundle["model"]
    logger.info("Loaded incumbent | %s | features=%s", INCUMBENT_PATH, len(bundle["feature_columns"]))

    symbol = "BTCUSDT"
    frames = {symbol: download_barrier_data(config, refresh=False)[symbol]}
    dataset = build_barrier_dataset(
        frames,
        config.market.interval,
        max_horizon=config.barrier.max_horizon,
        pairs_per_candle=config.barrier.pairs_per_candle,
        grid=barrier_grid(config.barrier.grid_atr, config.barrier.min_risk_reward, config.barrier.max_risk_reward),
        atr_window=config.barrier.atr_window,
    )
    if tuple(dataset.feature_columns) != tuple(bundle["feature_columns"]):
        logger.warning(
            "Feature columns differ from the trained bundle (%s vs %s); using the bundle's order",
            len(dataset.feature_columns),
            len(bundle["feature_columns"]),
        )
        # The scorer addresses the fitted tree's inputs positionally, so the bundle's own column
        # order wins. `BarrierDataset` is a plain dataclass — rebind rather than rebuild.
        dataset = replace(dataset, feature_columns=tuple(bundle["feature_columns"]))

    _development, holdout = _carve_holdout(dataset, config.barrier)
    window = pd.DataFrame({"timestamp": pd.unique(dataset.times[holdout])})
    logger.info("Holdout window | candles=%s", len(window))

    rows: list[dict] = []
    pairs = barrier_grid(config.barrier.grid_atr, config.barrier.min_risk_reward, config.barrier.max_risk_reward)
    logger.info("Sweeping %s bracket pairs", len(pairs))


    for index, pair in enumerate(pairs, start=1):
        decisions = _decide_window(
            model=model,
            raw=frames[symbol],
            window=window,
            pair=pair,
            dataset=dataset,
            config=config,
        )
        if decisions.empty:
            logger.warning("Pair %s/%s | no decisions", pair.take_profit_atr, pair.stop_loss_atr)
            continue
        _trades, metrics = run_bracket_backtest(
            decisions,
            config.market.interval,
            config.barrier.max_horizon,
            BracketCosts(fee_rate=config.backtest.fee_rate, slippage_rate=config.backtest.slippage_rate),
        )
        stats = metrics["trades"]
        rows.append(
            {
                "take_profit_atr": pair.take_profit_atr,
                "stop_loss_atr": pair.stop_loss_atr,
                "risk_reward": pair.risk_reward_ratio,
                "trades": stats["trades"],
                "win_rate_resolved": stats["win_rate_resolved"],
                "break_even_win_rate": stats.get("break_even_win_rate"),
                "expectancy_percent": stats["expectancy_percent"],
                "expectancy_atr": stats["expectancy_atr"],
                "cumulative_return": metrics.get("cumulative_return"),
                "max_drawdown": metrics.get("max_drawdown"),
                "signals": int((decisions["direction"] != 0).sum()),
                "candles": len(decisions),
            }
        )
        logger.info(
            "Pair %s/%s (R:R %.2f) | trades=%s | win=%.3f vs BE=%s | exp_atr=%+.4f | ret=%s",
            pair.take_profit_atr,
            pair.stop_loss_atr,
            pair.risk_reward_ratio,
            stats["trades"],
            stats["win_rate_resolved"],
            stats.get("break_even_win_rate"),
            stats["expectancy_atr"],
            metrics.get("cumulative_return"),
        )
        if index % 10 == 0:
            logger.info("Progress | %s/%s pairs | elapsed=%.0fs", index, len(pairs), time.perf_counter() - started)

    rows.sort(key=lambda row: row["expectancy_atr"], reverse=True)
    logger.info("Sweep finished | pairs=%s | elapsed=%.0fs", len(rows), time.perf_counter() - started)
    return rows



def write_report(rows: list[dict], config: AppConfig) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    import json

    (OUTPUT_DIR / "results.json").write_text(json.dumps(rows, indent=2, default=str))

    positive = [row for row in rows if (row["expectancy_atr"] or 0) > 0]
    lines = [
        "# Bracket sweep — does any bracket clear costs?",
        "",
        f"*{len(rows)} pairs from the barrier grid · incumbent trees model (`BTCUSDT_1h.joblib`) · "
        f"strict purged holdout · confidence floor {config.barrier.backtest_minimum_confidence} · "
        f"fee {config.backtest.fee_rate:.3%} + slippage {config.backtest.slippage_rate:.3%}*",
        "",
        f"**Verdict: {len(positive)} of {len(rows)} pairs have positive expectancy (ATR).**",
        "",
        "| TP ATR | SL ATR | R:R | trades | win rate | break-even | expectancy % | expectancy ATR | cum return | max DD |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['take_profit_atr']} | {row['stop_loss_atr']} | {row['risk_reward']:.2f} "
            f"| {row['trades']} | {row['win_rate_resolved']:.3f} "
            f"| {row['break_even_win_rate'] if row['break_even_win_rate'] is not None else '—'} "
            f"| {row['expectancy_percent']:+.3f} | {row['expectancy_atr']:+.4f} "
            f"| {row['cumulative_return'] if row['cumulative_return'] is not None else '—'} "
            f"| {row['max_drawdown'] if row['max_drawdown'] is not None else '—'} |"
        )
    if positive:
        lines += ["", "## Cells worth a closer look", ""]
        for row in positive[:10]:
            lines.append(
                f"- TP {row['take_profit_atr']}/SL {row['stop_loss_atr']} ATR — expectancy "
                f"{row['expectancy_atr']:+.4f} ATR over {row['trades']} trades"
            )
    else:
        lines += [
            "",
            "No cell clears costs. Per the roadmap decision point: proceed to the feature review (1.2), "
            "and treat model-class swaps as closed until the features change.",
        ]
    (OUTPUT_DIR / "report.md").write_text("\n".join(lines) + "\n")
    logger.info("Report written | %s", OUTPUT_DIR / "report.md")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bracket sweep over the barrier grid (roadmap 1.1)")
    parser.add_argument("--config", default="config.toml", help="Path to TOML config")
    args = parser.parse_args()

    config = load_config(args.config)
    configure_logging(config.logging)
    rows = sweep(config)
    write_report(rows, config)

    positive = [row for row in rows if (row["expectancy_atr"] or 0) > 0]
    print(f"\nSwept {len(rows)} brackets — positive expectancy: {len(positive)}")
    for row in rows[:5]:
        print(
            f"  TP {row['take_profit_atr']}/SL {row['stop_loss_atr']} ATR "
            f"| trades={row['trades']} | exp_atr={row['expectancy_atr']:+.4f}"
        )
    print(f"Full table: {OUTPUT_DIR / 'report.md'}")


if __name__ == "__main__":
    main()
