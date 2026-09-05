"""Resume support for the league: skip (strategy, key) pairs already committed to a partial artifact.

A league run is hours of deterministic arithmetic; a crash or a kill at combo 43 of 54 must not cost
the other 43. `--resume` points at the newest partial artifact, loads its rows, and the runner emits
only the missing pairs. Completed rows are copied through unchanged — the backtests are
deterministic, so recomputing them would buy nothing and cost the same hours again.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..log_setup import get_logger
from .league import run_league

logger = get_logger(__name__)


def load_partial(path: Path) -> dict[str, Any] | None:
    """Read a partial league artifact. None if missing, unreadable, or missing its header."""
    if not path.exists():
        return None
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        logger.warning("Resume artifact unreadable | path=%s | error=%s", path, error)
        return None
    for field in ("symbols", "intervals", "rows", "max_horizon", "fee_rate", "slippage_rate", "n_test_blocks"):
        if field not in artifact:
            logger.warning("Resume artifact missing field %r | path=%s", field, path)
            return None
    return artifact


def run_league_resumable(
    frames: dict[str, Any],
    intervals: list[str],
    strategy_names: list[str],
    partial: dict[str, Any] | None,
    n_blocks: int = 3,
    partial_path: Any = None,
) -> dict[str, Any]:
    """`run_league` with resume: pairs present in `partial` are skipped, new ones computed.

    The returned dict has the same shape `run_league` returns, so callers downstream cannot tell
    whether a resume happened — the artifact is identical to one uninterrupted run. `partial_path`
    is passed through so the fresh computation keeps flushing completed pairs for the next crash.
    """
    done: set[tuple[str, str, str]] = set()
    carried: list[dict[str, Any]] = []
    if partial:
        for row in partial["rows"]:
            key = (row["strategy"], row["symbol"], row["interval"])
            done.add(key)
            carried.append(row)
        logger.info("Resume loaded | completed_pairs=%s", len(done))

    todo_strategies = [name for name in strategy_names if any(
        (name, _symbol_of(key, intervals), _interval_of(key, intervals)) not in done for key in frames
    )]
    if not todo_strategies:
        logger.info("Resume: nothing to compute, every pair already present")
    fresh = run_league(
        {key: frame for key, frame in frames.items() if any(
            (name, _symbol_of(key, intervals), _interval_of(key, intervals)) not in done
            for name in strategy_names
        )},
        intervals=intervals,
        strategy_names=[name for name in strategy_names if name in todo_strategies],
        n_blocks=n_blocks,
        partial_path_override=partial_path,
    )
    fresh["rows"] = carried + fresh["rows"]
    return fresh


def _symbol_of(key: str, intervals: list[str]) -> str:
    for interval in sorted(intervals, key=len, reverse=True):
        suffix = f"_{interval}"
        if key.lower().endswith(suffix):
            return key[: -len(suffix)].upper()
    return key.upper()


def _interval_of(key: str, intervals: list[str]) -> str:
    for interval in sorted(intervals, key=len, reverse=True):
        if key.lower().endswith(f"_{interval}"):
            return interval
    if len(intervals) == 1:
        return intervals[0]
    raise ValueError(f"Frame key {key!r} does not end with a known interval from {intervals}")
