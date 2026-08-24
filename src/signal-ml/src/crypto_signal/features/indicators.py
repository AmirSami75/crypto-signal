"""Technical indicators, as plain series transforms.

Each function takes price series and returns a series of the same length and index, with leading NaNs
where the window has not filled yet. None of them look forward: value *t* uses candle *t* and earlier,
which is what makes the whole feature set safe to compute over a full history and then split in time.

Kept separate from the feature builder so the pieces are testable on their own and so the serving layer
can ask for a raw ATR without dragging in forty columns it does not want.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def relative_strength_index(close: pd.Series, window: int = 14) -> pd.Series:
    """Wilder's RSI, on the 0-100 scale."""
    change = close.diff()
    gain = change.clip(lower=0).ewm(alpha=1 / window, adjust=False).mean()
    loss = (-change.clip(upper=0)).ewm(alpha=1 / window, adjust=False).mean()
    relative_strength = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + relative_strength))


def average_true_range(frame: pd.DataFrame, window: int = 14) -> pd.Series:
    """Wilder's ATR in price units.

    This is the yardstick the whole barrier design rests on: a take-profit "1.5 ATR away" means the same
    kind of bet on any market, where "1.5% away" does not. Both the labeller and the servicer take their
    ATR from here, because two implementations of the same yardstick is two different yardsticks.
    """
    previous_close = frame["close"].shift(1)
    ranges = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    )
    true_range = ranges.max(axis=1)
    return true_range.ewm(alpha=1 / window, adjust=False).mean()


def bollinger_z_score(close: pd.Series, window: int = 20) -> pd.Series:
    """How many rolling standard deviations the close sits from its rolling mean."""
    mean = close.rolling(window).mean()
    deviation = close.rolling(window).std()
    return (close - mean) / deviation.replace(0, np.nan)


def stochastic_position(
    close: pd.Series, high: pd.Series, low: pd.Series, window: int = 14
) -> pd.Series:
    """Where the close sits inside the window's range, 0 at the low and 1 at the high."""
    rolling_low = low.rolling(window).min()
    rolling_high = high.rolling(window).max()
    return (close - rolling_low) / (rolling_high - rolling_low).replace(0, np.nan)
