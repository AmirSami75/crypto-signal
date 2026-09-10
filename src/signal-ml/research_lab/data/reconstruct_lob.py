#!/usr/bin/env python3
"""E11 Lane A — 10-level LOB snapshot reconstruction from depth deltas.

Delta contract (Binance futures diff-depth event shape, JSON per line):
  {"U": first_update_id, "u": last_update_id, "b": [[price, qty], ...],
   "a": [[price, qty], ...], "T": event_ms}
Qty "0" (or 0) removes the level. Levels are kept sorted
(bids desc, asks asc); a crossed book (bid1 >= ask1) raises CrossedBookError.

Output contract (Lane B/C consume this — fixed):
  research_lab/data/micro/<SYM>/lob/<SYM>-lob-1s-YYYY-MM.csv
  columns: timestamp,bid_p1..10,bid_q1..10,ask_p1..10,ask_q1..10
  one row per second (last snapshot within the second, UTC ISO8601).

SOURCE-FORMAT NOTE (verified 2026-09-10): Binance Vision daily bookDepth
bulk zips do NOT contain deltas. They hold percentage-band aggregates:
  timestamp,percentage,depth,notional   e.g. 2026-03-01 00:00:08,-5.00,...
No per-level prices exist in that file, so 10-level LOB reconstruction
from the bulk file alone is impossible. `reconstruct_day()` detects this
schema and raises UnsupportedSourceFormat instead of fabricating levels.
True delta input comes from a diff-depth stream archive (e.g. Tardis.dev)
or the futures websocket; feed such JSONL via --deltas.

Validation: reconstructed BBO vs bookTicker BBO per second; tolerance
default 1 tick (relative 1e-6); match% must be >= 99.9. Update-ID gaps
are counted; days with gap-seconds > 1% are flagged EXCLUDE.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import sys
import zipfile
from bisect import bisect_left
from dataclasses import dataclass, field
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
LEVELS = 10
CSV_COLS = (
    ["timestamp"]
    + [f"bid_p{i}" for i in range(1, LEVELS + 1)]
    + [f"bid_q{i}" for i in range(1, LEVELS + 1)]
    + [f"ask_p{i}" for i in range(1, LEVELS + 1)]
    + [f"ask_q{i}" for i in range(1, LEVELS + 1)]
)
BULK_HDR = ("timestamp", "percentage", "depth", "notional")


class CrossedBookError(ValueError):
    """Raised when best bid >= best ask after applying a delta."""


class UnsupportedSourceFormat(ValueError):
    """Raised when the input file is Vision band-aggregate, not deltas."""


@dataclass
class LobBook:
    bids: dict[float, float] = field(default_factory=dict)  # price -> qty, desc
    asks: dict[float, float] = field(default_factory=dict)  # price -> qty, asc
    last_u: int | None = None
    gaps: int = 0  # count of sequencing gaps (u+1 != U)
    n_updates: int = 0

    def apply(self, upd: dict) -> None:
        U, u = int(upd["U"]), int(upd["u"])
        if self.last_u is not None and U != self.last_u + 1:
            self.gaps += 1
        self.last_u = u
        for side, book in (("b", self.bids), ("a", self.asks)):
            for p, q in upd.get(side, []):
                pf, qf = float(p), float(q)
                if qf == 0.0:
                    book.pop(pf, None)
                else:
                    book[pf] = qf
        self.n_updates += 1
        if self.bids and self.asks and max(self.bids) >= min(self.asks):
            raise CrossedBookError(
                f"crossed book after u={u}: bid1={max(self.bids)} ask1={min(self.asks)}"
            )

    def top(self, n: int = LEVELS) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
        bids = sorted(self.bids.items(), reverse=True)[:n]
        asks = sorted(self.asks.items())[:n]
        return bids, asks

    def bbo(self) -> tuple[float | None, float | None]:
        return (max(self.bids) if self.bids else None, min(self.asks) if self.asks else None)


def second_key(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def deltas_to_1s_rows(deltas: list[dict], day: str | None = None) -> tuple[list[dict], dict]:
    """Apply deltas in order; keep last snapshot per second. Returns (rows, stats)."""
    book = LobBook()
    per_sec: dict = {}
    for upd in deltas:
        book.apply(upd)
        if day is None or second_key(int(upd.get("T", 0))).startswith(day):
            bids, asks = book.top()
            if len(bids) < LEVELS or len(asks) < LEVELS:
                continue  # thin book: skip incomplete seconds
            row: dict = {"timestamp": second_key(int(upd.get("T", 0)))}
            for i in range(LEVELS):
                row[f"bid_p{i+1}"] = bids[i][0]
                row[f"bid_q{i+1}"] = bids[i][1]
                row[f"ask_p{i+1}"] = asks[i][0]
                row[f"ask_q{i+1}"] = asks[i][1]
            per_sec[row["timestamp"]] = row
    stats = {"n_updates": book.n_updates, "gaps": book.gaps,
             "n_seconds": len(per_sec)}
    return [per_sec[k] for k in sorted(per_sec)], stats


def write_lob_csv(rows: list[dict], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS)
        w.writeheader()
        w.writerows(rows)


def is_vision_bulk_csv(header: list[str]) -> bool:
    return tuple(h.strip() for h in header) == BULK_HDR


def reconstruct_day(zip_path: Path, symbol: str, day: str, out_dir: Path) -> dict:
    """Reconstruct one day. Raises UnsupportedSourceFormat for band-aggregate zips."""
    with zipfile.ZipFile(zip_path) as z:
        name = z.namelist()[0]
        with z.open(name) as f:
            head = f.read(4096).decode("utf-8", "replace")
    first_line = head.splitlines()[0]
    if "percentage" in first_line and "notional" in first_line:
        raise UnsupportedSourceFormat(
            f"{zip_path.name}: Vision bookDepth bulk holds (timestamp,percentage,"
            "depth,notional) band aggregates — no per-level prices, L1–L10 "
            "reconstruction impossible from this source (need diff-depth deltas)."
        )
    raise UnsupportedSourceFormat(f"{zip_path.name}: unrecognized schema: {first_line[:120]!r}")


def validate_bbo(lob_csv: Path, ticker_csv: Path, rel_tol: float = 1e-6) -> dict:
    """Compare reconstructed L1 vs bookTicker BBO per second.

    ticker_csv: bookTicker bulk CSV with best bid/ask per row; rows are
    (transaction_time, symbol, best_bid_price, best_bid_qty,
     best_ask_price, best_ask_qty, transaction_id, event_time).
    Returns {n_seconds, n_match, match_pct, verdict}.
    """
    import csv as _csv

    lob: dict[str, tuple[float, float]] = {}
    with open(lob_csv) as f:
        for r in _csv.DictReader(f):
            lob[r["timestamp"]] = (float(r["bid_p1"]), float(r["ask_p1"]))
    tick: dict[str, tuple[float, float]] = {}
    with open(ticker_csv) as f:
        rdr = _csv.reader(f)
        hdr = next(rdr)
        bi = hdr.index("best_bid_price") if "best_bid_price" in hdr else 2
        ai = hdr.index("best_ask_price") if "best_ask_price" in hdr else 4
        ti = hdr.index("transaction_time") if "transaction_time" in hdr else 0
        for r in rdr:
            try:
                ts = dt.datetime.fromtimestamp(int(r[ti]) / 1000, tz=dt.timezone.utc)
            except ValueError:
                ts = dt.datetime.fromisoformat(r[ti].replace("Z", "+00:00"))
            tick[ts.strftime("%Y-%m-%dT%H:%M:%SZ")] = (float(r[bi]), float(r[ai]))
    n = m = 0
    for sec, (bp, ap) in lob.items():
        if sec not in tick:
            continue
        tb, ta = tick[sec]
        if abs(bp - tb) <= rel_tol * max(tb, 1e-12) and abs(ap - ta) <= rel_tol * max(ta, 1e-12):
            m += 1
        n += 1
    pct = 100.0 * m / n if n else 0.0
    return {"n_seconds": n, "n_match": m, "match_pct": pct,
            "verdict": "PASS" if pct >= 99.9 else "FAIL"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--day", required=True, help="YYYY-MM-DD")
    ap.add_argument("--deltas", default=None, help="JSONL diff-depth deltas (U,u,b,a,T)")
    ap.add_argument("--zip", default=None, help="Vision daily bookDepth zip to diagnose")
    args = ap.parse_args()

    out_dir = LAB / "data" / "micro" / args.symbol / "lob"
    if args.deltas:
        import json

        upd = [json.loads(l) for l in open(args.deltas) if l.strip()]
        rows, stats = deltas_to_1s_rows(upd, args.day)
        month = args.day[:7]
        dest = out_dir / f"{args.symbol}-lob-1s-{month}.csv"
        write_lob_csv(rows, dest)
        print(f"{args.symbol} {args.day}: {stats['n_updates']} updates, "
              f"{stats['n_seconds']} seconds, {stats['gaps']} gaps -> {dest}")
        if stats["gaps"] / max(stats["n_updates"], 1) > 0.01:
            print("FLAGGED EXCLUDE: update-ID gaps >1%")
            return 2
        return 0
    if args.zip:
        rep = reconstruct_day(Path(args.zip), args.symbol, args.day, out_dir)
        print(rep)
        return 0
    ap.error("need --deltas or --zip")
    return 1


if __name__ == "__main__":
    sys.exit(main())
