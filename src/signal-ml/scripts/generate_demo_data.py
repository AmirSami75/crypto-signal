"""Create deterministic synthetic OHLCV data for an offline pipeline smoke test.

This data is deliberately synthetic and must never be interpreted as market evidence.
"""

from pathlib import Path

import numpy as np
import pandas as pd


def main() -> None:
    rng = np.random.default_rng(42)
    rows = 6_000
    timestamp = pd.date_range("2022-01-01", periods=rows, freq="h", tz="UTC")

    innovations = rng.normal(0, 0.0045, rows)
    returns = np.zeros(rows)
    regime = np.sin(np.arange(rows) / 350) * 0.00035
    for index in range(1, rows):
        returns[index] = 0.12 * returns[index - 1] + regime[index] + innovations[index]

    close = 30_000 * np.exp(np.cumsum(returns))
    open_ = np.r_[close[0], close[:-1]]
    intrabar = rng.uniform(0.0005, 0.006, rows)
    high = np.maximum(open_, close) * (1 + intrabar)
    low = np.minimum(open_, close) * (1 - intrabar)
    volume = rng.lognormal(mean=8.2, sigma=0.55, size=rows) * (1 + np.abs(returns) * 30)
    quote_volume = volume * close

    frame = pd.DataFrame(
        {
            "timestamp": timestamp,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "close_time": timestamp + pd.Timedelta(hours=1) - pd.Timedelta(milliseconds=1),
            "quote_volume": quote_volume,
            "trade_count": rng.integers(100, 2_000, rows),
            "taker_buy_base_volume": volume * rng.uniform(0.42, 0.58, rows),
            "taker_buy_quote_volume": quote_volume * rng.uniform(0.42, 0.58, rows),
        }
    )
    destination = Path(__file__).resolve().parents[1] / "data" / "DEMOUSDT_1h.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(destination, index=False)
    print(f"Wrote {len(frame):,} synthetic rows to {destination}")


if __name__ == "__main__":
    main()

