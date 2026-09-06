#!/usr/bin/env python3
"""Render the weekly strategy-league digest for Telegram (T4.3).

Reads the newest `artifacts/league/<stamp>.json` and prints a compact top-10
table (strategy, symbol, interval, TEST trades, net return, verdict). Pure and
network-free: the cron wrapper (hermes cron / monitor.sh digest) captures stdout
and relays it. Exit 0 always — a missing artifact prints a note, not a failure,
because a scheduled digest that crashes produces silence, which is worse.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEAGUE_DIR = REPO_ROOT / "src" / "signal-ml" / "artifacts" / "league"

TOP_N = 10
VERDICT_MARK = {"ROBUST": "✅", "MODERATE": "⚠️", "WEAK": "❌", "OVERFITTED": "❌"}


def newest_artifact() -> Path | None:
    if not LEAGUE_DIR.exists():
        return None
    artifacts = sorted(LEAGUE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    return artifacts[-1] if artifacts else None


def render(artifact_path: Path) -> str:
    data = json.loads(artifact_path.read_text())
    rows = data.get("rows", [])
    if not rows:
        return f"League artifact {artifact_path.name} has no rows."

    ranked = sorted(
        rows,
        key=lambda r: (
            -r["test"]["total_return"],
            -(r["test"]["profit_factor"] or 0.0),
        ),
    )[:TOP_N]

    stamp = data.get("generated_at", artifact_path.stem)
    lines = [
        f"📊 Strategy league — top {len(ranked)} (TEST split, net of costs)",
        f"run {stamp} · {data.get('symbols', '?')} · {data.get('intervals', '?')}",
        "",
    ]
    for row in ranked:
        test = row["test"]
        mark = VERDICT_MARK.get(row["verdict"], "·")
        net = test["total_return"] * 100
        pf = test["profit_factor"]
        pf_text = f"{pf:.2f}" if pf is not None else "—"
        lines.append(
            f"{mark} {row['strategy']} {row['symbol']} {row['interval']}: "
            f"{test['trades']} trades, net {net:+.2f}%, PF {pf_text} — {row['verdict']}"
        )

    adoptable = [r for r in rows if r["test"]["trades"] >= 30 and r["verdict"] == "ROBUST"]
    lines.append("")
    if adoptable:
        lines.append(f"✅ Adoptable (≥30 test trades AND ROBUST): {len(adoptable)}")
    else:
        lines.append("⚠️ Nothing adoptable (gate: ≥30 test trades AND ROBUST verdict).")
    return "\n".join(lines)


def main() -> int:
    artifact = newest_artifact()
    if artifact is None:
        print(f"No league artifacts found under {LEAGUE_DIR}")
        return 0
    print(render(artifact))
    return 0


if __name__ == "__main__":
    sys.exit(main())
