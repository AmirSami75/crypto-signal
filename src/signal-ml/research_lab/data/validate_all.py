"""Validate every built 15m micro-features file against UM klines (E9 data gate).

Re-runs the vwap-inside / close-match / bucket-count checks for all
(symbol, month) pairs. Exits non-zero if any file fails, so E9 cannot start
on unvalidated features.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB.parent))       # signal-ml root -> research_lab package
sys.path.insert(0, str(LAB.parent / "src"))  # crypto_signal package

from research_lab.data.build_micro_features import validate  # noqa: E402

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


def main() -> int:
    failures = []
    for symbol in SYMBOLS:
        feat_dir = LAB / "data" / "micro" / symbol / "features"
        kl_dir = LAB / "data" / "micro" / symbol / "klines-15m"
        for f in sorted(feat_dir.glob(f"{symbol}-micro-15m-*.csv")):
            month = f.stem.replace(f"{symbol}-micro-15m-", "")
            z = kl_dir / f"{symbol}-15m-{month}.zip"
            csv = kl_dir / f"{symbol}-15m-{month}.csv"
            if not z.exists() and not csv.exists():
                failures.append((symbol, month, "missing klines"))
                print(f"{symbol} {month}: MISSING KLINES", flush=True)
                continue
            if not csv.exists():
                import zipfile
                with zipfile.ZipFile(z) as archive:
                    archive.extractall(kl_dir)
            raw = pd.read_csv(csv, header=0, usecols=[0, 1, 2, 3, 4, 5, 6],
                              names=["ots", "open", "high", "low", "close", "volume", "cts"])
            raw["timestamp"] = pd.to_datetime(raw["ots"], unit="ms", utc=True)
            feats = pd.read_csv(f, parse_dates=["timestamp"])
            report = validate(feats, raw)
            status = "OK " if report["pass"] else "FAIL"
            print(f"{status} {symbol} {month}: inside {report['vwap_inside_pct']}% "
                  f"close_err_p99 {report['close_err_p99']} buckets {report['buckets']}", flush=True)
            if not report["pass"]:
                failures.append((symbol, month, report))
    print(f"\nvalidated: {failures and len(failures) or 0} failures", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
