"""E0 — bracket-geometry × confidence sweep on the incumbent's holdout.

Question (§19): does ANY (tp, sl) bracket geometry + confidence floor turn the
incumbent HGB pooled model's holdout probabilities into positive net expectancy
after realistic costs? The trained geometry (1.5/1.0 ATR, fee≈0.4 ATR) is
negative by construction; this experiment answers whether a different geometry
rescues it, BEFORE any deep-learning investment.

Method: replay `run_bracket_backtest` over a grid of (tp, sl, conf_floor) with
direction/confidence taken from the pooled model's holdout predictions, entry at
the candle close, ATR from the fitted pipeline. Uses the production simulator
for realistic fills — no invented metrics.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from crypto_signal.evaluation.bracket import BracketCosts, run_bracket_backtest


def load_predictions(path: Path) -> pd.DataFrame:
    """Holdout predictions with model probabilities; one row per (candle, pair)."""
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df["conf"] = df[["probability_sell", "probability_hold", "probability_buy"]].max(axis=1)
    # direction from model probabilities: buy vs sell only (hold rows excluded downstream)
    df["direction"] = np.where(df["probability_buy"] >= df["probability_sell"], 1, -1)
    return df


def build_decisions(
    candles: pd.DataFrame, preds: pd.DataFrame, tp: float, sl: float, conf_floor: float
) -> pd.DataFrame:
    """One row per candle: engine decision for a given geometry + floor.

    Entry price = candle close (proxy for next-candle open in the simulator's
    market-fill model). TP/SL as percent of entry.
    """
    p = preds.drop_duplicates("timestamp", keep="last").set_index("timestamp")
    joined = candles.join(p[["conf", "direction"]], how="left")
    take = joined["conf"].notna() & (joined["conf"] >= conf_floor)
    joined["direction"] = np.where(take, joined["direction"], 0)
    entry = joined["close"]
    joined["take_profit_percent"] = np.where(take, tp * joined["atr"] / entry, 0.0)
    joined["stop_loss_percent"] = np.where(take, sl * joined["atr"] / entry, 0.0)
    take_rows = joined[joined["direction"] != 0]
    return take_rows[
        ["timestamp", "open", "high", "low", "close", "atr", "direction",
         "take_profit_percent", "stop_loss_percent"]
    ].reset_index(drop=True)


def sweep(
    candles: pd.DataFrame,
    preds: pd.DataFrame,
    geometries: list[tuple[float, float]],
    floors: list[float],
    costs: BracketCosts,
    max_horizon: int = 24,
) -> pd.DataFrame:
    """Run the full (geometry × floor) grid through the production simulator."""
    rows: list[dict] = []
    started = time.perf_counter()
    for (tp, sl), floor in itertools_product(geometries, floors):
        decisions = build_decisions(candles, preds, tp, sl, floor)
        if decisions.empty:
            continue
        _trades, metrics = run_bracket_backtest(decisions, "1h", max_horizon, costs)
        stats = metrics["trades"]
        rows.append({
            "tp_atr": tp,
            "sl_atr": sl,
            "conf_floor": floor,
            "trades": stats["trades"],
            "win_rate": stats["win_rate"],
            "profit_factor": stats["profit_factor"],
            "expectancy_atr": stats["expectancy_atr"],
            "total_return": stats["total_return_percent"],
        })
    print(f"sweep done in {time.perf_counter() - started:.1f}s — {len(rows)} cells")
    return pd.DataFrame(rows)


def itertools_product(a: list, b: list):
    for x in a:
        for y in b:
            yield x, y


if __name__ == "__main__":
    raise SystemExit("import from e0 runner script; this module holds the sweep logic only")
