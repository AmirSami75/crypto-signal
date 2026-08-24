from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd

from ..data import interval_periods_per_year
from ..log_setup import get_logger


logger = get_logger(__name__)


def signals_to_positions(signals: np.ndarray, allow_short: bool) -> np.ndarray:
    positions = np.zeros(len(signals), dtype=float)
    current = 0.0
    for index, signal in enumerate(signals):
        if signal == 1:
            current = 1.0
        elif signal == -1:
            current = -1.0 if allow_short else 0.0
        positions[index] = current
    return positions


def performance_metrics(
    returns: pd.Series,
    positions: pd.Series,
    interval: str,
    turnover: pd.Series | None = None,
) -> dict[str, float | int]:
    clean_returns = returns.fillna(0.0).astype(float)
    if (clean_returns <= -1).any():
        raise ValueError("A backtest return is <= -100%, so equity is undefined")
    equity = (1 + clean_returns).cumprod()
    periods_per_year = interval_periods_per_year(interval)
    years = len(clean_returns) / periods_per_year
    cumulative_return = float(equity.iloc[-1] - 1) if len(equity) else 0.0
    cagr = float(equity.iloc[-1] ** (1 / years) - 1) if years > 0 and len(equity) else 0.0
    volatility = float(clean_returns.std(ddof=0) * np.sqrt(periods_per_year))
    mean_return = float(clean_returns.mean() * periods_per_year)
    sharpe = mean_return / volatility if volatility > 0 else 0.0
    drawdown = equity / equity.cummax() - 1
    active = positions.abs() > 0
    active_returns = clean_returns.loc[active]
    hit_rate = float((active_returns > 0).mean()) if len(active_returns) else 0.0
    realized_turnover = (
        turnover
        if turnover is not None
        else positions.diff().abs().fillna(positions.abs())
    )

    return {
        "cumulative_return": cumulative_return,
        "cagr": cagr,
        "annualized_volatility": volatility,
        "sharpe_zero_rate": float(sharpe),
        "max_drawdown": float(drawdown.min()) if len(drawdown) else 0.0,
        "hit_rate_active_bars": hit_rate,
        "exposure": float(active.mean()) if len(active) else 0.0,
        "position_changes": int((realized_turnover > 0).sum()),
        "total_turnover": float(realized_turnover.sum()),
    }


def run_backtest(
    predictions: pd.DataFrame,
    interval: str,
    fee_rate: float,
    slippage_rate: float,
    allow_short: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    started = time.perf_counter()
    logger.info(
        "Backtest started | rows=%s | interval=%s | fee=%.3f%% | slippage=%.3f%% | short=%s",
        f"{len(predictions):,}",
        interval,
        fee_rate * 100,
        slippage_rate * 100,
        allow_short,
    )
    required = {"timestamp", "close", "signal"}
    missing = required.difference(predictions.columns)
    if missing:
        raise ValueError(f"Backtest is missing columns: {sorted(missing)}")

    result = predictions.copy().sort_values("timestamp").reset_index(drop=True)
    result["position"] = signals_to_positions(
        result["signal"].to_numpy(dtype=int), allow_short=allow_short
    )
    result["next_bar_return"] = result["close"].shift(-1) / result["close"] - 1
    prior_position = result["position"].shift(1).fillna(0.0)
    result["turnover"] = (result["position"] - prior_position).abs()
    result["trading_cost"] = result["turnover"] * (fee_rate + slippage_rate)
    result["strategy_return"] = (
        result["position"] * result["next_bar_return"] - result["trading_cost"]
    )
    result = result.iloc[:-1].copy()

    # Realize the strategy at the end of the test instead of granting a free
    # unclosed position. Charge buy-and-hold the same one-way entry/exit costs.
    one_way_cost = fee_rate + slippage_rate
    result["terminal_liquidation_cost"] = 0.0
    if len(result) and result["position"].iloc[-1] != 0:
        terminal_turnover = abs(float(result["position"].iloc[-1]))
        terminal_cost = terminal_turnover * one_way_cost
        last_index = result.index[-1]
        result.loc[last_index, "terminal_liquidation_cost"] = terminal_cost
        result.loc[last_index, "trading_cost"] += terminal_cost
        result.loc[last_index, "turnover"] += terminal_turnover
        result.loc[last_index, "strategy_return"] -= terminal_cost

    result["benchmark_trading_cost"] = 0.0
    if len(result):
        result.loc[result.index[0], "benchmark_trading_cost"] += one_way_cost
        result.loc[result.index[-1], "benchmark_trading_cost"] += one_way_cost
    result["benchmark_return"] = (
        result["next_bar_return"] - result["benchmark_trading_cost"]
    )
    result["strategy_equity"] = (1 + result["strategy_return"]).cumprod()
    result["benchmark_equity"] = (1 + result["benchmark_return"]).cumprod()

    strategy_metrics = performance_metrics(
        result["strategy_return"], result["position"], interval, result["turnover"]
    )
    benchmark_positions = pd.Series(1.0, index=result.index)
    benchmark_turnover = result["benchmark_trading_cost"] / max(one_way_cost, 1e-15)
    benchmark_metrics = performance_metrics(
        result["benchmark_return"], benchmark_positions, interval, benchmark_turnover
    )
    logger.info(
        "Backtest finished | strategy_return=%+.2f%% | benchmark_return=%+.2f%% | "
        "max_drawdown=%.2f%% | position_changes=%s | elapsed=%.3fs",
        strategy_metrics["cumulative_return"] * 100,
        benchmark_metrics["cumulative_return"] * 100,
        strategy_metrics["max_drawdown"] * 100,
        f"{strategy_metrics['position_changes']:,}",
        time.perf_counter() - started,
    )
    return result, {"strategy": strategy_metrics, "buy_and_hold": benchmark_metrics}
