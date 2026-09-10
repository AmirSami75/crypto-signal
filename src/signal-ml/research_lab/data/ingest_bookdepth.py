#!/usr/bin/env python3
"""E11 Lane A — download Binance Vision futures (USD-M) daily bookDepth zips.

Daily bookDepth bulk files (percentage-band depth snapshots, 2023-01+):
  data/futures/um/daily/bookDepth/<SYM>/<SYM>-bookDepth-YYYY-MM-DD.zip
Optionally daily bookTicker (BBO stream, only served 2023-05-16 → ~2024-04):
  data/futures/um/daily/bookTicker/<SYM>/<SYM>-bookTicker-YYYY-MM-DD.zip

Reuses fetch() + checksum logic pattern from ingest_binance.py
(resumable curl via host proxy, .CHECKSUM verify, skip-existing).

Usage:
  python ingest_bookdepth.py --symbols BTCUSDT,ETHUSDT,SOLUSDT \
      --start 2026-03-01 --end 2026-08-31 [--types bookDepth,bookTicker]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_binance import fetch  # noqa: E402  (reuse proxy+resume logic)

BASE = "https://data.binance.vision"
PROXY = "http://127.0.0.1:10808"
LAB = Path(__file__).resolve().parents[1]

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")


def days(start: str, end: str) -> list[str]:
    s = dt.date.fromisoformat(start)
    e = dt.date.fromisoformat(end)
    out: list[str] = []
    d = s
    while d <= e:
        out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def key_for(dtype: str, symbol: str, day: str) -> str:
    if dtype == "bookDepth":
        return f"data/futures/um/daily/bookDepth/{symbol}/{symbol}-bookDepth-{day}.zip"
    if dtype == "bookTicker":
        return f"data/futures/um/daily/bookTicker/{symbol}/{symbol}-bookTicker-{day}.zip"
    raise SystemExit(f"unknown type {dtype}")


def verify(dest: Path, checksum_url: str) -> bool:
    """Compare sha256 of dest against Vision .CHECKSUM file. Warn-only on miss."""
    cmd = ["curl", "-sS", "--proxy", PROXY, "--max-time", "120", checksum_url]
    r = subprocess.run(cmd, capture_output=True, text=True)
    want = (r.stdout.strip().split() or [""])[0]
    if len(want) != 64:
        print(f"  no CHECKSUM for {dest.name} (HTTP body={r.stdout.strip()[:60]!r}); skipping verify")
        return True
    h = hashlib.sha256()
    with open(dest, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    ok = h.hexdigest() == want
    if not ok:
        print(f"  CHECKSUM MISMATCH {dest.name}: got {h.hexdigest()} want {want}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(SYMBOLS))
    ap.add_argument("--types", default="bookDepth")
    ap.add_argument("--start", default="2026-03-01")
    ap.add_argument("--end", default="2026-08-31")
    args = ap.parse_args()

    total = ok = fail = skip = missing = 0
    for symbol in args.symbols.split(","):
        for dtype in args.types.split(","):
            for day in days(args.start, args.end):
                total += 1
                dest = LAB / "data" / "micro" / symbol / dtype / f"{symbol}-{dtype}-{day}.zip"
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists() and dest.stat().st_size > 0:
                    skip += 1
                    continue
                url = f"{BASE}/{key_for(dtype, symbol, day)}"
                t0 = time.perf_counter()
                if fetch(url, dest):
                    if dest.stat().st_size < 1000 and dest.suffix == ".zip":
                        # Vision returns small XML NoSuchKey bodies with HTTP 200 edge cases
                        head = dest.read_bytes()[:5]
                        if head != b"PK\x03\x04":
                            print(f"  MISSING (NoSuchKey) {dtype} {symbol} {day}")
                            dest.unlink(missing_ok=True)
                            missing += 1
                            continue
                    if not verify(dest, url + ".CHECKSUM"):
                        dest.unlink(missing_ok=True)
                        fail += 1
                        continue
                    kb = dest.stat().st_size / 1e3
                    print(f"  {symbol} {dtype} {day}: {kb:.0f}KB in {time.perf_counter()-t0:.0f}s", flush=True)
                    ok += 1
                else:
                    dest.unlink(missing_ok=True)
                    fail += 1
    print(f"done: {ok} fetched, {skip} skipped, {missing} missing-on-server, {fail} failed / {total}", flush=True)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
