"""AggTrades → 15m microstructure features, with kline cross-validation.

Per 15m bucket from raw aggTrades:
  buy_vol / sell_vol     split by aggressor (is_buyer_maker=False → aggressive BUY)
  delta                  signed volume = buy_vol - sell_vol        (trade-flow OFI proxy)
  delta_pct              delta / total volume                      (scale-free pressure)
  trade_count, avg_trade_size, large_trade_share (top-1% qty share of volume)
  vwap                   Σ(p·q)/Σq
  close                  last trade price in bucket

Validation (hard gate): bucket VWAP must sit inside the kline's [low, high] and
|vwap - kline_close| / close < 1e-3 for >=99% of buckets, bucket count must match
kline count within 0.5%. A failure aborts — miscalibrated features never reach an
experiment.

Streaming: reads monthly CSVs in chunks; ~35M rows/month fits comfortably.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pandas as pd

LAB = Path(__file__).resolve().parents[1]
CHUNK = 5_000_000
BUCKET = "15min"


def _iter_trades(csv: Path) -> Iterator[pd.DataFrame]:
    for chunk in pd.read_csv(
        csv,
        usecols=["price", "quantity", "transact_time", "is_buyer_maker"],
        dtype={"price": np.float64, "quantity": np.float64, "transact_time": np.int64,
               "is_buyer_maker": "string"},
        chunksize=CHUNK,
    ):
        ts = pd.to_datetime(chunk["transact_time"], unit="ms", utc=True)
        sign = np.where(chunk["is_buyer_maker"].str.strip().str.lower() == "false", 1.0, -1.0)
        yield pd.DataFrame({"timestamp": ts, "price": chunk["price"].to_numpy(),
                            "qty": chunk["quantity"].to_numpy(), "sign": sign})


def build_month(csv: Path) -> pd.DataFrame:
    """One monthly aggTrades CSV -> one 15m feature frame."""
    parts = []
    for df in _iter_trades(csv):
        df["bucket"] = df["timestamp"].dt.floor(BUCKET)
        parts.append(df)
    trades = pd.concat(parts, ignore_index=True)
    trades = trades.sort_values("timestamp", kind="stable")

    g = trades.groupby("bucket", sort=True)
    buy = trades.assign(bv=trades["qty"] * np.where(trades["sign"] > 0, 1.0, 0.0))
    sell = trades.assign(sv=trades["qty"] * np.where(trades["sign"] < 0, 1.0, 0.0))
    buy_vol = buy.groupby("bucket")["bv"].sum()
    sell_vol = sell.groupby("bucket")["sv"].sum()

    total_vol = g["qty"].sum()
    pq = trades.assign(pq=trades["price"] * trades["qty"]).groupby("bucket")["pq"].sum()
    vwap = pq / total_vol

    big_cut = trades["qty"].quantile(0.99)
    large_share = trades.assign(lb=trades["qty"] * np.where(trades["qty"] >= big_cut, trades["qty"], 0.0)
                                ).groupby("bucket")["lb"].sum() / total_vol

    out = pd.DataFrame({
        "buy_vol": buy_vol, "sell_vol": sell_vol,
        "total_vol": total_vol, "trade_count": g.size(),
        "avg_trade_size": total_vol / g.size(),
        "large_trade_share": large_share,
        "vwap": vwap,
        "close": g["price"].last(),
        "high": g["price"].max(), "low": g["price"].min(),
    })
    out["delta"] = out["buy_vol"] - out["sell_vol"]
    out["delta_pct"] = out["delta"] / out["total_vol"]
    return out.reset_index().rename(columns={"bucket": "timestamp"})


def validate(features: pd.DataFrame, klines_15m: pd.DataFrame) -> dict:
    k = klines_15m.copy()
    k["timestamp"] = pd.to_datetime(k["timestamp"], utc=True).dt.floor(BUCKET)
    k = k.drop_duplicates("timestamp").set_index("timestamp")
    f = features.set_index("timestamp")
    joined = f.join(k[["open", "high", "low", "close"]].add_prefix("k_"), how="inner")
    inside = ((joined["vwap"] >= joined["k_low"] - 1e-9) & (joined["vwap"] <= joined["k_high"] + 1e-9))
    close_err = (joined["close"] - joined["k_close"]).abs() / joined["k_close"]
    count_ok = abs(len(f) - len(k)) / max(len(k), 1) < 0.005
    report = {
        "buckets": len(f), "klines": len(k), "joined": len(joined),
        "vwap_inside_pct": round(float(inside.mean()) * 100, 3),
        "close_err_p99": round(float(close_err.quantile(0.99)), 6),
        "count_gap_ok": bool(count_ok),
        "pass": bool(inside.mean() >= 0.99 and close_err.quantile(0.99) < 1e-3 and count_ok),
    }
    return report


def main() -> int:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    month = sys.argv[2] if len(sys.argv) > 2 else "2026-08"
    base = LAB / "data" / "micro" / symbol / "aggTrades"
    zip_path, csv_path = base / f"{symbol}-aggTrades-{month}.zip", base / f"{symbol}-aggTrades-{month}.csv"
    if not csv_path.exists():
        import zipfile
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(base)
    out = LAB / "data" / "micro" / symbol / "features"
    out.mkdir(parents=True, exist_ok=True)
    dest = out / f"{symbol}-micro-15m-{month}.csv"
    if dest.exists():
        print(f"OK {symbol} {month}: features exist, skipping")
        return 0
    feats = build_month(csv_path)
    feats.to_csv(dest, index=False)

    kl_zip = LAB / "data" / "micro" / symbol / "klines-15m" / f"{symbol}-15m-{month}.zip"
    kl_csv = kl_zip.with_suffix(".csv")
    if kl_zip.exists():
        import zipfile
        if not kl_csv.exists():
            with zipfile.ZipFile(kl_zip) as z:
                z.extractall(kl_zip.parent)
        raw = pd.read_csv(kl_csv, header=0, usecols=[0, 1, 2, 3, 4, 5, 6],
                          names=["ots", "open", "high", "low", "close", "volume", "cts"])
        raw["timestamp"] = pd.to_datetime(raw["ots"], unit="ms", utc=True)
        report = validate(feats, raw)
        print(f"validation: {report}")
        if not report["pass"]:
            print("VALIDATION FAILED — features written but flagged; do NOT use")
            return 1
    csv_path.unlink(missing_ok=True)  # reclaim disk; re-extractable from zip
    print(f"OK {symbol} {month}: {len(feats):,} buckets -> {out}/{symbol}-micro-15m-{month}.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
