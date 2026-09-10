#!/usr/bin/env python3
"""Live L2 order-book recorder — Binance USDT-M futures diff-depth @500ms.

Accumulates the delta dataset Lane A could not download (Vision bookDepth
bulk zips hold band aggregates, not per-level deltas).

Delta contract (identical to reconstruct_lob.py --deltas input):
  {"U": first_update_id, "u": last_update_id,
   "b": [[price, qty], ...], "a": [[price, qty], ...], "T": event_ms}
Qty "0" removes the level. A crossed book raises CrossedBookError.

Snapshots (REST fapi/v1/depth) go to a separate file so the deltas file
stays directly consumable by reconstruct_lob.deltas_to_1s_rows:
  deltas:    <outdir>/<SYM>/<SYM>-deltas-YYYY-MM-DD.jsonl
  snapshots: <outdir>/<SYM>/<SYM>-snapshots-YYYY-MM-DD.jsonl
  snapshot line: {"snapshot": true, "lastUpdateId": int,
                  "bids": [[p,q]..], "asks": [[p,q]..], "T": ms}

Sync protocol (Binance USDT-M futures diff-depth):
  - fetch REST snapshot (lastUpdateId=S); buffer stream events meanwhile
  - drop buffered events with u < S; first kept event must satisfy
    U <= S+1 <= u, else refetch snapshot
  - steady state: futures update IDs are GLOBAL (shared across symbols),
    so consecutive batches never satisfy U == last_u + 1. Chain on the
    event's `pu` (previous final update ID): require pu == last_u.
    Events without `pu` (spot-style / synthetic) fall back to U == last_u+1.
    Any break -> gap -> resync.
  - any disconnect -> resync; crossed book -> resync (raise first)

Usage:
  .venv/bin/python research_lab/data/record_lob.py --symbols BTCUSDT \\
      --duration 600 --outdir research_lab/data/deltas
  daemon (3 symbols, infinite): nohup ... --symbols BTCUSDT,ETHUSDT,SOLUSDT \\
      >> research_lab/results/lob_recorder.log 2>&1 &
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import logging
import sys
from pathlib import Path
from typing import IO

import aiohttp

from reconstruct_lob import CrossedBookError, LobBook

LAB = Path(__file__).resolve().parents[1]
FAPI = "https://fapi.binance.com"
FSTREAM = "wss://fstream.binance.com/stream"

log = logging.getLogger("record_lob")


# ---------------------------------------------------------------- snapshot
async def fetch_snapshot(session: aiohttp.ClientSession, symbol: str,
                         proxy: str | None, limit: int = 1000) -> dict:
    async with session.get(
        f"{FAPI}/fapi/v1/depth",
        params={"symbol": symbol, "limit": limit},
        proxy=proxy,
        timeout=aiohttp.ClientTimeout(total=20),
    ) as r:
        r.raise_for_status()
        return await r.json()


def book_from_snapshot(snap: dict) -> LobBook:
    return LobBook(
        bids={float(p): float(q) for p, q in snap.get("bids", []) if float(q) != 0.0},
        asks={float(p): float(q) for p, q in snap.get("asks", []) if float(q) != 0.0},
    )


# ---------------------------------------------------------------- writers
class DayWriter:
    """Append-only JSONL writer rotating on UTC day boundary."""

    def __init__(self, outdir: Path, symbol: str, kind: str):
        self.outdir = outdir
        self.symbol = symbol
        self.kind = kind  # "deltas" | "snapshots"
        self.day: str | None = None
        self.fh: IO[str] | None = None
        self.bytes = 0
        self.lines = 0

    def _path(self, day: str) -> Path:
        d = self.outdir / self.symbol
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{self.symbol}-{self.kind}-{day}.jsonl"

    def emit(self, obj: dict, day: str) -> None:
        if day != self.day:
            if self.fh:
                self.fh.close()
            self.day = day
            self.fh = open(self._path(day), "a")
        line = json.dumps(obj)
        assert self.fh is not None
        self.fh.write(line + "\n")
        self.fh.flush()
        self.bytes += len(line) + 1
        self.lines += 1

    def close(self) -> None:
        if self.fh:
            self.fh.close()
            self.fh = None


def utc_day(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- feed logic (pure; network injected -> unit-testable)
class GapError(ValueError):
    """Raised internally when an event breaks the update-ID chain."""


class SymbolFeed:
    """Per-symbol sync state machine. Only async boundary is fetch_snapshot."""

    NEED_SNAPSHOT, SYNCING, SYNCED = "need_snapshot", "syncing", "synced"

    def __init__(self, symbol: str, fetch, emit_delta, emit_snapshot):
        self.symbol = symbol
        self._fetch = fetch  # async () -> snapshot dict
        self._emit_delta = emit_delta  # (delta: dict) -> None
        self._emit_snapshot = emit_snapshot
        self.state = self.NEED_SNAPSHOT
        self.snap_id: int | None = None
        self.last_u: int | None = None
        self.book = LobBook()
        self.n_deltas = 0
        self.n_resyncs = 0
        self.n_gaps = 0

    async def resync(self) -> None:
        snap = await self._fetch()
        self.snap_id = int(snap["lastUpdateId"])
        self.book = book_from_snapshot(snap)
        self._emit_snapshot({
            "snapshot": True, "symbol": self.symbol,
            "lastUpdateId": self.snap_id,
            "bids": snap.get("bids", []), "asks": snap.get("asks", []),
            "T": int(snap.get("T", 0)),
        })
        self.state = self.SYNCING
        self.n_resyncs += 1
        log.info("%s resync #%d snap=%d", self.symbol, self.n_resyncs, self.snap_id)

    def _apply_event(self, evt: dict) -> None:
        upd = {"U": int(evt["U"]), "u": int(evt["u"]),
               "b": evt.get("b", []), "a": evt.get("a", []),
               "T": int(evt.get("T", evt.get("E", 0)))}
        self.book.apply(upd)  # raises CrossedBookError on crossed book
        self.last_u = upd["u"]
        self._emit_delta(upd)
        self.n_deltas += 1

    async def on_event(self, evt: dict) -> None:
        U, u = int(evt["U"]), int(evt["u"])
        if self.state == self.NEED_SNAPSHOT:
            await self.resync()
        if self.state == self.SYNCING:
            assert self.snap_id is not None
            if u < self.snap_id:
                return  # stale buffered event
            if U <= self.snap_id + 1 <= u:
                self._apply_event(evt)
                self.state = self.SYNCED
            else:
                self.n_gaps += 1  # snapshot too old for stream; refetch
                await self.resync()
            return
        # SYNCED: chain on futures `pu` (global update IDs); fall back to
        # U == last_u + 1 for pu-less (spot-style / synthetic) events.
        assert self.last_u is not None
        chained = (int(evt["pu"]) == self.last_u) if "pu" in evt else (U == self.last_u + 1)
        if not chained:
            self.n_gaps += 1
            log.warning("%s gap: want U=%d got U=%d (last_u=%d)",
                        self.symbol, self.last_u + 1, U, self.last_u)
            await self.resync()
            await self.on_event(evt)  # re-evaluate against fresh snapshot
            return
        self._apply_event(evt)  # CrossedBookError propagates to caller


# ---------------------------------------------------------------- live loop
def stream_url(symbols: list[str]) -> str:
    streams = "/".join(f"{s.lower()}@depth@500ms" for s in symbols)
    return f"{FSTREAM}?streams={streams}"


async def run(symbols: list[str], outdir: Path, proxy: str | None,
              duration: float, snap_limit: int) -> dict:
    writers_d = {s: DayWriter(outdir, s, "deltas") for s in symbols}
    writers_s = {s: DayWriter(outdir, s, "snapshots") for s in symbols}
    stats: dict = {}
    try:
        async with aiohttp.ClientSession() as session:
            feeds = {}
            for s in symbols:
                wd, ws = writers_d[s], writers_s[s]

                def _ed(o, _wd=wd):
                    _wd.emit(o, utc_day(int(o["T"])))

                async def _fetch(_s=s):
                    return await fetch_snapshot(session, _s, proxy, snap_limit)

                def _es(o, _ws=ws):
                    _ws.emit(o, utc_day(int(o.get("T") or 0)) or
                             dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"))

                feeds[s] = SymbolFeed(s, _fetch, _ed, _es)
                try:
                    await feeds[s].resync()
                except Exception as e:
                    log.error("%s initial snapshot failed: %r", s, e)
            url = stream_url(symbols)
            log.info("connect %s", url)
            t_end = asyncio.get_event_loop().time() + duration if duration > 0 else None
            backoff = 1.0
            while True:
                try:
                    async with session.ws_connect(
                            url, proxy=proxy, heartbeat=15.0) as ws:
                        backoff = 1.0
                        log.info("ws connected")
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    env = json.loads(msg.data)
                                except json.JSONDecodeError:
                                    continue
                                evt = env.get("data", env)
                                sym = str(evt.get("s", "")).upper()
                                if sym not in feeds or "U" not in evt:
                                    continue
                                try:
                                    await feeds[sym].on_event(evt)
                                except CrossedBookError as e:
                                    log.warning("%s crossed book: %s -> resync",
                                                sym, e)
                                    try:
                                        await feeds[sym].resync()
                                    except Exception as re:
                                        log.error("%s resync failed: %r", sym, re)
                            elif msg.type in (aiohttp.WSMsgType.CLOSED,
                                              aiohttp.WSMsgType.ERROR):
                                break
                            if t_end and asyncio.get_event_loop().time() >= t_end:
                                break
                        else:
                            pass
                    if t_end and asyncio.get_event_loop().time() >= t_end:
                        break
                    log.warning("ws disconnected -> resync all, backoff %.0fs", backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60.0)
                    for f in feeds.values():
                        f.state = SymbolFeed.NEED_SNAPSHOT
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    log.warning("ws error %r -> retry in %.0fs", e, backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60.0)
                    for f in feeds.values():
                        f.state = SymbolFeed.NEED_SNAPSHOT
                if t_end and asyncio.get_event_loop().time() >= t_end:
                    break
            for s, f in feeds.items():
                stats[s] = {"deltas": f.n_deltas, "resyncs": f.n_resyncs,
                            "gaps": f.n_gaps, "last_u": f.last_u,
                            "bytes": writers_d[s].bytes, "lines": writers_d[s].lines}
                log.info("%s done: %s", s, stats[s])
    finally:
        for w in list(writers_d.values()) + list(writers_s.values()):
            w.close()
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Live L2 recorder (Binance USDT-M @500ms)")
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    ap.add_argument("--outdir", default=str(LAB / "data" / "deltas"))
    ap.add_argument("--duration", type=float, default=0,
                    help="seconds to record; 0 = forever")
    ap.add_argument("--proxy", default="http://127.0.0.1:10808")
    ap.add_argument("--no-proxy", action="store_true")
    ap.add_argument("--snap-limit", type=int, default=1000)
    ap.add_argument("--log-interval", type=float, default=60.0)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    proxy = None if args.no_proxy else (args.proxy or None)
    stats = asyncio.run(run(symbols, Path(args.outdir), proxy,
                            args.duration, args.snap_limit))
    print(json.dumps(stats, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
