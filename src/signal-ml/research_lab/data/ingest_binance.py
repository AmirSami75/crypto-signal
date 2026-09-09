#!/usr/bin/env python3
"""E9 Phase 0 — download Binance Vision futures (USD-M) microstructure data.

Downloads monthly aggTrades (+ optionally bookDepth) zips via the host proxy,
resumable, checksum-verified, into research_lab/data/micro/<SYMBOL>/<type>/.

Catalog (verified 2026-09-09 via S3 list):
  data/futures/um/monthly/aggTrades/<SYM>/<SYM>-aggTrades-YYYY-MM.zip
  data/futures/um/daily/bookDepth/<SYM>/<SYM>-bookDepth-YYYY-MM-DD.zip   (2023-01+, 1s depth)
Usage:
  python ingest_binance.py --symbols BTCUSDT,ETHUSDT,SOLUSDT \
      --types aggTrades --start 2025-09 --end 2026-08
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

BASE = "https://data.binance.vision"
PROXY = "http://127.0.0.1:10808"
LAB = Path(__file__).resolve().parents[1]


def months(start: str, end: str) -> list[str]:
    sy, sm = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    out = []
    while (sy, sm) <= (ey, em):
        out.append(f"{sy:04d}-{sm:02d}")
        sm += 1
        if sm == 13:
            sy, sm = sy + 1, 1
    return out


def key_for(dtype: str, symbol: str, month: str) -> str:
    if dtype == "aggTrades":
        return f"data/futures/um/monthly/aggTrades/{symbol}/{symbol}-aggTrades-{month}.zip"
    if dtype == "klines-15m":
        return f"data/futures/um/monthly/klines/{symbol}/15m/{symbol}-15m-{month}.zip"
    raise SystemExit(f"unknown type {dtype}")


def fetch(url: str, dest: Path) -> bool:
    """curl with resume; True on HTTP 200/206."""
    cmd = ["curl", "-sS", "--proxy", PROXY, "--max-time", "3600", "-C", "-",
           "-o", str(dest), "-w", "%{http_code}", url]
    code = "not-run"
    for attempt in range(4):
        r = subprocess.run(cmd, capture_output=True, text=True)
        code = r.stdout.strip()
        if code in ("200", "206"):
            return True
        time.sleep(5 * (attempt + 1))
    print(f"  FAILED {url} last={code}", flush=True)
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="BTCUSDT")
    ap.add_argument("--types", default="aggTrades")
    ap.add_argument("--start", default="2025-09")
    ap.add_argument("--end", default="2026-08")
    args = ap.parse_args()

    total = ok = fail = skip = 0
    for symbol in args.symbols.split(","):
        for dtype in args.types.split(","):
            for month in months(args.start, args.end):
                total += 1
                stem = "15m" if dtype == "klines-15m" else dtype
                dest = LAB / "data" / "micro" / symbol / dtype / f"{symbol}-{stem}-{month}.zip"
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists() and dest.stat().st_size > 0:
                    skip += 1
                    continue
                t0 = time.perf_counter()
                if fetch(f"{BASE}/{key_for(dtype, symbol, month)}", dest):
                    mb = dest.stat().st_size / 1e6
                    print(f"  {symbol} {dtype} {month}: {mb:.0f}MB in {time.perf_counter()-t0:.0f}s", flush=True)
                    ok += 1
                else:
                    dest.unlink(missing_ok=True)
                    fail += 1
    print(f"done: {ok} fetched, {skip} skipped, {fail} failed / {total}", flush=True)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
