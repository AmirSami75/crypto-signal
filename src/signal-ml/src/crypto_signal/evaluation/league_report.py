"""The `run-league` command: load frames, run the league, write the artifact, print the table.

Kept apart from `league.py` (the pure ranking engine) so the CLI concerns — data loading, artifact
paths, human formatting — never leak into the part tests exercise without a config file.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from ..config import AppConfig
from ..data import fetch_historical_ohlcv, load_ohlcv
from ..log_setup import get_logger
from .league import run_league
from ..strategies import STRATEGIES

logger = get_logger(__name__)

_VERDICT_PAD = "OVERFITTED"  # the widest verdict, for column alignment


def run_league_command(
    config: AppConfig,
    symbols: list[str],
    intervals: list[str],
    refresh: bool = False,
    offline: bool = False,
) -> dict[str, Any]:
    """Entry point behind `python -m crypto_signal run-league`."""
    frames: dict[str, Any] = {}
    for interval in intervals:
        for symbol in symbols:
            key = f"{symbol}_{interval}"
            frame = _load_frame(config, symbol, interval, refresh=refresh, offline=offline)
            if frame is None:
                logger.warning("League skip | no data for %s", key)
                continue
            frames[key] = frame

    if not frames:
        raise RuntimeError("run-league has no frames to rank: every requested frame failed to load")

    league = run_league(frames, intervals=intervals, strategy_names=sorted(STRATEGIES))

    artifact_dir = config.output.artifact_dir / "league"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_path = artifact_dir / f"{stamp}.json"
    artifact = {
        "generated_at": stamp,
        "symbols": symbols,
        "intervals": intervals,
        "max_horizon": league["max_horizon"],
        "fee_rate": league["fee_rate"],
        "slippage_rate": league["slippage_rate"],
        "n_test_blocks": league["n_test_blocks"],
        "rows": league["rows"],
    }
    artifact_path.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")
    logger.info("League artifact written | path=%s | rows=%s", artifact_path, len(league["rows"]))

    return {
        "artifact_path": artifact_path,
        "rows": league["rows"],
        "table": format_league_table(league["rows"], artifact_path),
    }


def _load_frame(
    config: AppConfig, symbol: str, interval: str, refresh: bool, offline: bool
) -> Any | None:
    """Load a symbol's candles: local CSV when present, else a download (unless offline)."""
    csv_path = config.market.data_dir / f"{symbol}_{interval}.csv"
    if csv_path.exists() and not refresh:
        return load_ohlcv(csv_path, interval)
    if offline:
        if csv_path.exists():
            return load_ohlcv(csv_path, interval)
        logger.warning("League offline skip | missing CSV | path=%s", csv_path)
        return None
    try:
        frame = fetch_historical_ohlcv(
            symbol,
            interval,
            config.market.start,
            config.market.end,
            proxy_url=config.network.proxy_url,
            timeout=config.network.timeout_seconds,
        )
        frame.to_csv(csv_path, index=False)
        return frame
    except Exception as error:
        logger.warning("League download failed | symbol=%s | interval=%s | error=%s", symbol, interval, error)
        return None


def format_league_table(rows: list[dict[str, Any]], artifact_path: Path) -> str:
    """The ranked league table. TEST-split numbers only — train figures stay in the JSON artifact."""
    lines = [
        f"Strategy League — ranked by TEST-split total return (profit_factor tiebreak)",
        f"artifact: {artifact_path}",
        "",
        f"{'rank':>4}  {'strategy':<16} {'symbol':<10} {'tf':<4} {'verdict':<{len(_VERDICT_PAD)}} "
        f"{'trades':>6} {'win%':>6} {'ret%':>8} {'PF':>6} {'sharpe':>7} {'maxDD%':>7}",
    ]
    for rank, row in enumerate(rows, start=1):
        test = row["test"]
        pf = "n/a" if test["profit_factor"] is None else f"{test['profit_factor']:.2f}"
        lines.append(
            f"{rank:>4}  {row['strategy']:<16} {row['symbol']:<10} {row['interval']:<4} {row['verdict']:<{len(_VERDICT_PAD)}} "
            f"{test['trades']:>6} {test['win_rate'] * 100:>6.1f} {test['total_return'] * 100:>8.2f} {pf:>6} "
            f"{test['sharpe']:>7.2f} {test['max_drawdown'] * 100:>7.2f}"
        )
    return "\n".join(lines)
