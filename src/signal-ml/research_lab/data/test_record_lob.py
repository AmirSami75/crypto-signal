#!/usr/bin/env python3
"""Synthetic-feed tests for record_lob.SymbolFeed.

Covers: gap detection triggers resync; qty-zero removal; crossed-book
raises; stale-event drop; snapshot overlap rule; contiguous apply order.
No network: snapshot fetcher and writers are injected fakes.
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reconstruct_lob import CrossedBookError  # noqa: E402
from record_lob import SymbolFeed, book_from_snapshot  # noqa: E402

BASE = 1_000_000
SNAP = {
    "lastUpdateId": BASE,
    "bids": [["100.0", "5.0"], ["99.0", "3.0"]],
    "asks": [["101.0", "4.0"], ["102.0", "2.0"]],
    "T": 1_700_000_000_000,
}


def make_feed(snapshots=None):
    """Feed with scripted snapshot fetcher; returns (feed, emitted, snaps, calls)."""
    emitted, snaps, calls = [], [], {"n": 0}
    pool = list(snapshots or [SNAP])

    async def fetch():
        calls["n"] += 1
        s = pool[min(calls["n"] - 1, len(pool) - 1)]
        return dict(s)

    feed = SymbolFeed("BTCUSDT", fetch, emitted.append, snaps.append)
    return feed, emitted, snaps, calls


def evt(U, u, b=None, a=None, T=1_700_000_000_500):
    return {"U": U, "u": u, "b": b or [], "a": a or [],
            "T": T, "s": "BTCUSDT"}


def run(coro):
    return asyncio.run(coro)


# --- required cases -------------------------------------------------------
def test_gap_detection_triggers_resync():
    snap2 = dict(SNAP, lastUpdateId=BASE + 500)
    feed, emitted, snaps, calls = make_feed([SNAP, snap2])
    run(feed.on_event(evt(BASE + 1, BASE + 2,
                          b=[["100.0", "6.0"]], a=[["101.0", "4.0"]])))
    assert feed.state == SymbolFeed.SYNCED
    assert calls["n"] == 1
    # skip ahead: U jumps past last_u + 1 -> gap -> resync
    run(feed.on_event(evt(BASE + 100, BASE + 101)))
    assert calls["n"] == 2, "gap must trigger a snapshot refetch"
    assert feed.n_gaps == 1
    assert feed.n_resyncs == 2
    assert snaps[-1]["lastUpdateId"] == BASE + 500


def test_qty_zero_removal():
    feed, emitted, snaps, calls = make_feed()
    run(feed.on_event(evt(BASE + 1, BASE + 2)))
    assert 100.0 in feed.book.bids
    run(feed.on_event(evt(BASE + 3, BASE + 3, b=[["100.0", "0"]])))
    assert 100.0 not in feed.book.bids, "qty 0 must remove the level"
    assert 99.0 in feed.book.bids


def test_crossed_book_raises():
    feed, emitted, snaps, calls = make_feed()
    run(feed.on_event(evt(BASE + 1, BASE + 2)))
    with pytest.raises(CrossedBookError):
        run(feed.on_event(evt(BASE + 3, BASE + 3, b=[["101.0", "9.0"]])))
    # bid 101.0 >= ask 101.0 -> crossed


# --- sync-protocol edge cases ---------------------------------------------
def test_stale_buffered_event_dropped():
    feed, emitted, snaps, calls = make_feed()
    feed.state = SymbolFeed.SYNCING
    feed.snap_id = BASE
    feed.book = book_from_snapshot(SNAP)
    run(feed.on_event(evt(BASE - 5, BASE - 1)))  # u < snap: stale
    assert feed.state == SymbolFeed.SYNCING
    assert emitted == []


def test_snapshot_overlap_first_event_rule():
    feed, emitted, snaps, calls = make_feed()
    feed.state = SymbolFeed.SYNCING
    feed.snap_id = BASE
    feed.book = book_from_snapshot(SNAP)
    # U <= snap+1 <= u -> accepted as first event
    run(feed.on_event(evt(BASE - 2, BASE + 3, b=[["100.0", "7.0"]])))
    assert feed.state == SymbolFeed.SYNCED
    assert feed.last_u == BASE + 3
    assert emitted and emitted[0]["U"] == BASE - 2


def test_snapshot_too_old_refetches():
    feed, emitted, snaps, calls = make_feed()
    feed.state = SymbolFeed.SYNCING
    feed.snap_id = BASE
    feed.book = book_from_snapshot(SNAP)
    run(feed.on_event(evt(BASE + 50, BASE + 55)))  # U > snap+1: no overlap
    assert calls["n"] == 1, "must refetch snapshot when stream ran ahead"
    assert feed.state == SymbolFeed.SYNCING


def test_contiguous_apply_order_and_contract():
    feed, emitted, snaps, calls = make_feed()
    run(feed.on_event(evt(BASE + 1, BASE + 2, b=[["100.0", "6.0"]])))
    run(feed.on_event(evt(BASE + 3, BASE + 4, a=[["101.0", "0"]])))
    assert [e["u"] for e in emitted] == [BASE + 2, BASE + 4]
    for e in emitted:
        assert set(e) == {"U", "u", "b", "a", "T"}, "delta contract keys"
    assert 101.0 not in feed.book.asks
    assert feed.book.bids[100.0] == 6.0
    assert feed.n_deltas == 2


# --- futures global-ID chaining via `pu` ----------------------------------
def test_pu_chaining_accepts_noncontiguous_U():
    """Futures U/u are global: U != last_u+1 is normal; pu == last_u chains."""
    feed, emitted, snaps, calls = make_feed()
    run(feed.on_event(evt(BASE + 1, BASE + 2)))
    e2 = evt(BASE + 120, BASE + 200, b=[["100.0", "6.0"]])
    e2["pu"] = BASE + 2  # chains to previous u despite U gap
    run(feed.on_event(e2))
    assert feed.state == SymbolFeed.SYNCED
    assert feed.last_u == BASE + 200
    assert calls["n"] == 1, "no resync when pu chains"
    assert feed.n_deltas == 2


def test_pu_mismatch_triggers_resync():
    snap2 = dict(SNAP, lastUpdateId=BASE + 500)
    feed, emitted, snaps, calls = make_feed([SNAP, snap2])
    run(feed.on_event(evt(BASE + 1, BASE + 2)))
    bad = evt(BASE + 120, BASE + 200)
    bad["pu"] = BASE + 999  # does not chain
    run(feed.on_event(bad))
    assert calls["n"] == 2, "pu break must trigger a snapshot refetch"
    assert feed.n_gaps == 1
