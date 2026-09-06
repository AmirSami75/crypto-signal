"""The Strategy League: every zoo strategy backtested and ranked, honestly.

One row per (strategy, symbol, interval). The ranking is decided on **test-split numbers only** —
the training split exists so the walk-forward verdict can compare a strategy's in-sample story
against its out-of-sample behaviour, never to flatter the table. This is the same honesty rule the
bracket sweep applied to the ML model: a strategy that cannot pay on data it was not tuned on is
not a strategy, whatever its training curve says.

**Walk-forward shape.** The candle history is cut into consecutive chronological blocks (purged by
`max_horizon` candles, via `modeling.splitting.chronological_blocks`). The first block trains —
for a rule-based strategy "training" means: this is the era its parameters were *chosen* on, the
fixed constants the zoo ships with — and every later block is a test era the strategy must survive
untouched. A strategy that only earned in its own era is overfitted, and the verdict says so:

* **ROBUST** — test return ≥ half the train return (the edge survived out of sample).
* **MODERATE** — test return positive but less than half (thin, worth watching).
* **WEAK** — test return ≤ 0 (no out-of-sample edge).
* **OVERFITTED** — train return was large (≥ 5× |test|) while test is weak: a strategy that
  memorised its era.

A strategy with nothing in its train block (no trades) cannot claim any verdict better than its
test behaviour supports; with no train trades the verdict degrades to the test-sign rules.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import numpy as np
import pandas as pd

from pathlib import Path

from ..data import interval_periods_per_year
from ..domain import Direction
from ..features.indicators import average_true_range
from ..log_setup import get_logger
from ..modeling.splitting import chronological_blocks
from ..strategies import STRATEGIES, Signal
from .bracket import BracketCosts, run_bracket_backtest

logger = get_logger(__name__)

#: The purge gap: a decision's bracket can look `max_horizon` candles forward, so the tail of one
#: era and the head of the next must not share information. Same rule the labeller obeys.
DEFAULT_MAX_HORIZON = 24
DEFAULT_TRAIN_FRACTION = 0.4
DEFAULT_N_TEST_BLOCKS = 3

#: A train return at least this many times |test| while test is weak means the strategy memorised
#: its era rather than learned a rule.
OVERFIT_RATIO = 5.0


def verdict(train: float, test: float) -> str:
    """The walk-forward overfit verdict from train/test total returns.

    OVERFITTED means the train era earned while the test eras lost — a ratio game the train side
    can only play when it actually traded and won. No train profit means there is nothing to have
    overfitted: positive test is MODERATE (unproven in-sample), anything else WEAK.
    """
    if train > 0:
        if test >= 0.5 * train:
            return "ROBUST"
        if test < 0 and train >= OVERFIT_RATIO * abs(test):
            return "OVERFITTED"
        if test >= 0:
            return "MODERATE"
    if test > 0:
        return "MODERATE"
    return "WEAK"


def _prepare(frame: pd.DataFrame, atr_window: int = 14) -> pd.DataFrame:
    """Attach the ATR column a strategy's bracket needs, if the caller has not."""
    frame = frame.copy()
    if "atr" not in frame.columns:
        frame["atr"] = average_true_range(frame, atr_window)
    return frame


def _signals_to_decisions(frame: pd.DataFrame, strategy: Callable[[pd.DataFrame], Signal | None]) -> pd.DataFrame:
    """Walk the frame once and emit the decision columns the bracket simulator reads.

    Direction is ±1 (a short is a real short: the barrier model's convention, not the legacy
    SELL-means-exit one). Brackets are ATR-native at 1.5 / 1.0 — the middle of the trained grid —
    because fixed-percent brackets extrapolate outside everything the platform's models know.
    """
    direction = np.zeros(len(frame), dtype=int)
    for index in range(len(frame)):
        signal = strategy(frame.iloc[: index + 1])
        if signal is not None:
            side = Direction.LONG if signal.direction == "LONG" else Direction.SHORT
            direction[index] = side.value
    decisions = frame[["timestamp", "open", "high", "low", "close", "atr"]].copy()
    decisions["direction"] = direction
    # ATR multiples: percent = atr_multiple * atr / close * 100. Computed per row so a bracket is
    # always 1.5 ATR away on a quiet market and on a wild one alike.
    atr = decisions["atr"]
    close = decisions["close"]
    decisions["take_profit_percent"] = 1.5 * atr / close * 100.0
    decisions["stop_loss_percent"] = 1.0 * atr / close * 100.0
    return decisions


def _split_eras(frame: pd.DataFrame, n_blocks: int, gap: int) -> tuple[pd.DataFrame, list[pd.DataFrame]]:
    """First `train_fraction` of candles is the train era; the rest is n_test_blocks test eras."""
    times = frame["timestamp"].to_numpy()
    n_train = max(1, int(DEFAULT_TRAIN_FRACTION * len(frame)))
    # chronological_blocks cuts on candle boundaries and purges the gap off each block's tail,
    # so no era's labels reach into the next one.
    fractions = [DEFAULT_TRAIN_FRACTION] + [
        (1.0 - DEFAULT_TRAIN_FRACTION) / n_test for n_test in [n_blocks]
    ] * n_blocks
    blocks = chronological_blocks(times, fractions, gap)
    train = frame.iloc[blocks[0]].reset_index(drop=True)
    tests = [frame.iloc[block].reset_index(drop=True) for block in blocks[1:]]
    del n_train
    return train, tests


def _era_metrics(trades: pd.DataFrame, metrics: dict[str, Any]) -> dict[str, Any]:
    """The compact per-era figure the league table and JSON artifact carry."""
    stats = metrics["trades"]
    equity = metrics["equity"]
    return {
        "trades": int(stats["trades"]),
        "win_rate": float(stats["win_rate"]),
        "total_return": float(equity["cumulative_return"]),
        "profit_factor": stats["profit_factor"],
        "sharpe": float(equity.get("sharpe_zero_rate", 0.0)),
        "max_drawdown": float(equity.get("max_drawdown", 0.0)),
        "expectancy_atr": float(stats["expectancy_atr"]),
        "stale_entries_skipped": int(stats["stale_entries_skipped"]),
    }


def run_league(
    frames: dict[str, pd.DataFrame],
    intervals: list[str],
    strategy_names: list[str],
    costs: BracketCosts | None = None,
    max_horizon: int = DEFAULT_MAX_HORIZON,
    n_blocks: int = DEFAULT_N_TEST_BLOCKS,
    partial_path_override: Path | None = None,
) -> dict[str, Any]:
    """Backtest every strategy on every (symbol, interval) and rank the league.

    `frames` maps a key of `f"{symbol}_{interval}"` (or just the symbol when one interval is in
    play) to its OHLCV frame; every strategy is run against every frame. Returns the ranked rows
    (test-split numbers decide the order: total_return desc, profit_factor tiebreak) plus the
    full train/test detail for the audit artifact.

    When `partial_path_override` is set, every completed (strategy, key) pair is flushed there as a
    partial artifact — a run killed mid-way loses at most the combo in flight, and `--resume`
    picks the rest up from that file.
    """
    costs = costs or BracketCosts(fee_rate=0.0010, slippage_rate=0.0005)
    rows: list[dict[str, Any]] = []
    # T4.2: pooled TEST-split trade frames per (strategy, symbol, interval) for CSV export.
    trade_frames: dict[str, pd.DataFrame] = {}
    partial_path: Path | None = partial_path_override
    for name in strategy_names:
        strategy = STRATEGIES[name]
        for key, frame in frames.items():
            symbol, interval = _parse_key(key, intervals)
            logger.info("League run | strategy=%s | key=%s | candles=%s", name, key, len(frame))
            prepared = _prepare(frame)
            train, tests = _split_eras(prepared, n_blocks, max_horizon)

            def evaluate(frame: pd.DataFrame) -> pd.DataFrame:
                return _signals_to_decisions(frame, strategy)

            train_decisions = evaluate(train)
            _, train_metrics = run_bracket_backtest(train_decisions, interval, max_horizon, costs)
            train_summary = _era_metrics(_era_trades(train_decisions, interval, max_horizon, costs), train_metrics)

            test_rows: list[dict[str, Any]] = []
            pooled_trades: list[pd.DataFrame] = []
            for era_index, era in enumerate(tests):
                era_decisions = evaluate(era)
                era_trades, era_metrics = run_bracket_backtest(
                    era_decisions, interval, max_horizon, costs
                )
                summary = _era_metrics(era_trades, era_metrics)
                summary["era"] = era_index
                test_rows.append(summary)
                if not era_trades.empty:
                    era_trades = era_trades.assign(era=era_index)
                    pooled_trades.append(era_trades)

            # The league number is the *pooled* test split — every test era, not the best one.
            pooled = _pool_test(test_rows)
            rows.append(
                {
                    "strategy": name,
                    "symbol": symbol,
                    "interval": interval,
                    "verdict": verdict(train_summary["total_return"], pooled["total_return"]),
                    "train": train_summary,
                    "test": pooled,
                    "test_eras": test_rows,
                }
            )
            # Keep the pooled TEST-split trades for T4.2 artifacts — the summary rows say how
            # many, these say what actually happened. Train-split trades stay out of the
            # exported set: the league's honesty rule is TEST-only in the summary, and the
            # same rule keeps the audit trail one-sided.
            if pooled_trades:
                trades_frame = pd.concat(pooled_trades, axis=0, ignore_index=True)
                trades_frame.insert(0, "symbol", symbol)
                trades_frame.insert(0, "strategy", name)
                trade_frames[f"{name}|{symbol}|{interval}"] = trades_frame
            if partial_path is not None:
                _flush_partial(partial_path, rows)

    rows.sort(
        key=lambda row: (
            -row["test"]["total_return"],
            -(row["test"]["profit_factor"] if row["test"]["profit_factor"] is not None else 0.0),
        )
    )
    return {
        "rows": rows,
        "trade_frames": trade_frames,
        "max_horizon": max_horizon,
        "fee_rate": costs.fee_rate,
        "slippage_rate": costs.slippage_rate,
        "n_test_blocks": n_blocks,
    }


def _era_trades(
    decisions: pd.DataFrame, interval: str, max_horizon: int, costs: BracketCosts
) -> pd.DataFrame:
    trades, _ = run_bracket_backtest(decisions, interval, max_horizon, costs)
    return trades


def _flush_partial(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write the rows computed so far so a kill costs at most the combo in flight."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"partial": True, "rows": rows}, indent=2, default=str), encoding="utf-8"
        )
    except OSError as error:
        logger.warning("Partial flush failed | path=%s | error=%s", path, error)


def _pool_test(era_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Combine the test eras into one honest split: trades summed, returns averaged by era length.

    Compounding eras would let one lucky era dominate; averaging trades-weighted keeps each era's
    weight proportional to the activity it actually saw, which is what the rank order needs.
    """
    if not era_rows:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "total_return": 0.0,
            "profit_factor": None,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "expectancy_atr": 0.0,
            "stale_entries_skipped": 0,
        }
    trades = sum(row["trades"] for row in era_rows)
    wins = sum(row["trades"] * row["win_rate"] for row in era_rows)
    total_return = float(np.average(
        [row["total_return"] for row in era_rows],
        weights=[max(row["trades"], 1) for row in era_rows],
    ))
    profit_factors = [row["profit_factor"] for row in era_rows if row["profit_factor"] is not None]
    return {
        "trades": trades,
        "win_rate": float(wins / trades) if trades else 0.0,
        "total_return": total_return,
        "profit_factor": float(np.mean(profit_factors)) if profit_factors else None,
        "sharpe": float(np.mean([row["sharpe"] for row in era_rows])),
        "max_drawdown": float(min(row["max_drawdown"] for row in era_rows)),
        "expectancy_atr": float(
            np.average(
                [row["expectancy_atr"] for row in era_rows],
                weights=[max(row["trades"], 1) for row in era_rows],
            )
        ),
        "stale_entries_skipped": sum(row["stale_entries_skipped"] for row in era_rows),
    }


def _parse_key(key: str, intervals: list[str]) -> tuple[str, str]:
    """Split a frame key into (symbol, interval). `{SYMBOL}_{INTERVAL}` or a bare symbol."""
    if len(intervals) == 1:
        return key.upper(), intervals[0]
    for interval in sorted(intervals, key=len, reverse=True):
        suffix = f"_{interval}"
        if key.lower().endswith(suffix):
            return key[: -len(suffix)].upper(), interval
    raise ValueError(f"Frame key {key!r} does not end with a known interval from {intervals}")
