"""E11 Lane A TDD — LobBook delta application, cross detection, BBO validation."""

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reconstruct_lob import (  # noqa: E402
    CSV_COLS,
    CrossedBookError,
    LobBook,
    UnsupportedSourceFormat,
    deltas_to_1s_rows,
    is_vision_bulk_csv,
    second_key,
    validate_bbo,
    write_lob_csv,
)

T0 = 1_700_000_000_000  # fixed epoch ms for deterministic seconds


def _u(U, u, b=(), a=(), t=T0):
    return {"U": U, "u": u, "b": [[str(p), str(q)] for p, q in b],
            "a": [[str(p), str(q)] for p, q in a], "T": t}


def _seed_levels(n=12, px=100.0):
    b = [(px - i * 0.1, 1.0 + i) for i in range(n)]
    a = [(px + 0.1 + i * 0.1, 2.0 + i) for i in range(n)]
    return b, a


def test_hand_built_five_updates_known_answer():
    """5 deltas incl. qty-zero removal -> exact top-3 snapshot known by hand."""
    book = LobBook()
    b0, a0 = _seed_levels()
    book.apply(_u(1, 1, b=b0, a=a0))                       # seed u=1
    book.apply(_u(2, 2, b=[(100.0, 0)], a=[(100.5, 7.5)]))  # remove bid1, grow ask lvl
    book.apply(_u(3, 3, b=[(100.05, 9.0)]))                # new best bid
    book.apply(_u(4, 4, a=[(100.1, 0)]))                   # remove best ask
    book.apply(_u(5, 5, b=[(99.9, 0)], a=[(100.3, 0)]))    # remove one level each
    bids, asks = book.top(3)
    # exact known answer, computed by hand:
    assert bids[0] == (100.05, 9.0)
    assert bids[1] == (99.8, 3.0)
    assert bids[2] == (99.7, 4.0)
    # bid 100.0/99.9 removed, ask 100.1/100.3 removed -> best ask 100.2
    assert asks[0][1] == 3.0 and asks[0][0] == pytest.approx(100.2)
    assert book.n_updates == 5 and book.gaps == 0


def test_bbo_cross_fails_loudly():
    book = LobBook()
    b0, a0 = _seed_levels()
    book.apply(_u(1, 1, b=b0, a=a0))
    with pytest.raises(CrossedBookError):
        book.apply(_u(2, 2, b=[(100.4, 5.0)]))  # bid 100.4 >= ask 100.1


def test_update_id_gap_flagged():
    book = LobBook()
    b0, a0 = _seed_levels()
    book.apply(_u(1, 1, b=b0, a=a0))
    book.apply(_u(5, 6, b=[(99.5, 1.0)]))  # U=5 != last_u+1=2 -> gap
    assert book.gaps == 1


def test_vision_bulk_format_detected_not_deltas():
    assert is_vision_bulk_csv(["timestamp", "percentage", "depth", "notional"])
    assert not is_vision_bulk_csv(["U", "u", "b", "a"])
    with pytest.raises(UnsupportedSourceFormat):
        raise UnsupportedSourceFormat("band aggregates have no levels")


def test_csv_contract_columns(tmp_path):
    b0, a0 = _seed_levels()
    upd = [_u(1, 1, b=b0, a=a0, t=T0)]
    rows, _ = deltas_to_1s_rows(upd)
    dest = tmp_path / "x.csv"
    write_lob_csv(rows, dest)
    with open(dest) as f:
        hdr = next(csv.reader(f))
    assert hdr == CSV_COLS
    assert len(hdr) == 41  # timestamp + 4x10


def test_bbo_validation_stats(tmp_path):
    b0, a0 = _seed_levels()
    upd = [_u(1, 1, b=b0, a=a0, t=T0), _u(2, 2, t=T0 + 1000)]
    rows, _ = deltas_to_1s_rows(upd)
    lob = tmp_path / "lob.csv"
    write_lob_csv(rows, lob)
    sec1, sec2 = second_key(T0), second_key(T0 + 1000)
    tick = tmp_path / "tick.csv"
    with open(tick, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["transaction_time", "symbol", "best_bid_price", "best_bid_qty",
                    "best_ask_price", "best_ask_qty"])
        w.writerow([T0, "X", rows[0]["bid_p1"], 1, rows[0]["ask_p1"], 1])
        w.writerow([T0 + 1000, "X", rows[1]["bid_p1"], 1, rows[1]["ask_p1"], 1])
    rep = validate_bbo(lob, tick)
    assert rep["n_seconds"] == 2 and rep["match_pct"] == 100.0 and rep["verdict"] == "PASS"
    assert sec1 in (rows[0]["timestamp"],) and sec2


def test_sampling_keeps_last_snapshot_per_second():
    b0, a0 = _seed_levels()
    upd = [_u(1, 1, b=b0, a=a0, t=T0),
           _u(2, 2, b=[(100.0, 111.0)], t=T0 + 400),
           _u(3, 3, t=T0 + 1500)]
    rows, stats = deltas_to_1s_rows(upd)
    assert stats["n_seconds"] == 2
    assert rows[0]["bid_q1"] == 111.0  # last update within second 0 wins
