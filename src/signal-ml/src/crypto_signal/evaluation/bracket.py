"""What a stream of bracket signals would actually have earned, walked candle by candle.

`close_to_close` answers a different question than the one this platform asks. It holds a position from
one close to the next and marks it at the close, which is the right simulator for a model that predicts
a return over a fixed horizon. A bracket order does not work that way: it exits the moment the price
*touches* a level, at a price the close never shows, and whether it wins depends on which of two levels
the intrabar path reached first. A close-to-close simulation of a bracket strategy silently reports the
return of a completely different strategy — one that would have sat through the stop-loss.

So this simulator walks the path, and it shares its first-touch rule with the labeller through
`crypto_signal.domain.barriers`. That sharing is the point: if the backtest resolved ties differently
than the labeller did, the model would be scored against a rulebook it was never trained under, and the
resulting edge would be an artifact of the disagreement.

**Where the pessimism is, and why each piece of it is there.** Every one of these turns a plausible
profit into a smaller or absent one, and each corresponds to something a venue really does.

* **A decision is filled on the *next* candle's open.** The decision is computed from a closed candle,
  so the earliest possible fill is the open after it.
* **The bracket is anchored to the decision close, not to the fill.** That is what the orchestrator
  places — it computes levels from the signal and sends them — so the gap between the close and the fill
  moves the fill toward one barrier and away from the other rather than vanishing. The bet actually taken
  is therefore never quite the bet requested, which is why `median_realised_risk_reward` is reported next
  to `requested_risk_reward`: whether it lands above or below depends on which way the candle opened, and
  a strategy whose two figures diverge is one whose stated risk is not the risk it runs.
* **A signal whose fill has already gapped past a barrier is not taken.** Booking it as an instant win
  at a level the position never held is how a backtest manufactures profit out of latency; booking it as
  a loss would be equally invented. It is counted in `stale_entries_skipped`, which is the number to
  watch: a strategy with many of them is one whose edge lives inside the gap it cannot trade.
* **A take-profit does not slip; a stop-loss and a timeout do.** A take-profit is a resting limit order
  and fills at its price or not at all. A stop-loss is a market order once triggered, and a timeout exit
  is a market order outright. Charging slippage to all three equally would flatter the losses and
  penalise the wins, which is the wrong direction on both counts.
* **A timeout exits at the horizon close; it is never dropped.** Dropping unresolved trades keeps
  exactly the paths that failed to reach either barrier — disproportionately the ones drifting toward
  the far one — and that selection is the same bias `domain.expectancy` documents at the probability
  level, arriving here through the back door.
* **A position still open when the data ends is liquidated at the last close** and marked unresolved,
  rather than granted whatever unrealised profit it happened to be sitting on.

**One position at a time.** While a trade is open, later signals are ignored; the next decision the
simulator reads is the one on the bar the exit happened, filling the bar after. Allowing overlapping
positions on one symbol would count a single favourable move once per open trade, which inflates the
result by a factor nobody can back out afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

import numpy as np
import pandas as pd

from ..data import interval_periods_per_year
from ..domain import (
    ADVERSE_WINS_TIE_BREAK,
    BarrierPair,
    Direction,
    Outcome,
    TouchResult,
    TradeLevels,
    break_even_win_rate,
    first_touch,
    levels_for,
)
from ..log_setup import get_logger
from .close_to_close import performance_metrics


logger = get_logger(__name__)

#: The decision columns the simulator reads, on top of the candles themselves.
DECISION_COLUMNS = ("direction", "take_profit_percent", "stop_loss_percent")
CANDLE_COLUMNS = ("timestamp", "open", "high", "low", "close", "atr")

TRADE_COLUMNS = (
    "decision_index",
    "decision_time",
    "fill_index",
    "fill_time",
    "exit_index",
    "exit_time",
    "direction",
    "decision_close",
    "fill_price",
    "take_profit_price",
    "stop_loss_price",
    "exit_price",
    "outcome",
    "resolved",
    "ambiguous",
    "bars_held",
    "atr",
    "take_profit_atr",
    "stop_loss_atr",
    "realised_risk_reward",
    "entry_gap_percent",
    "gross_return",
    "fee_cost",
    "net_return",
    "return_atr",
    "fee_atr",
    "adverse_excursion_percent",
    "favourable_excursion_percent",
)


@dataclass(frozen=True, slots=True)
class BracketCosts:
    """What the venue takes, per side.

    Separate from the rates the close-to-close backtest uses because they are applied differently: a fee
    is a rate on notional and is charged on both sides unconditionally, while slippage moves a *market*
    fill adversely and has no business touching a limit fill.
    """

    fee_rate: float
    slippage_rate: float

    def __post_init__(self) -> None:
        for name, value in (("fee_rate", self.fee_rate), ("slippage_rate", self.slippage_rate)):
            if not np.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and >= 0, got {value!r}")

    def market_fill(self, price: float, direction: Direction, entering: bool) -> float:
        """A market order's real fill: adverse to the position, on the way in and on the way out.

        Entering long or exiting short means buying, so the price moves up against you; the two other
        combinations mean selling and it moves down. Hence the sign is the direction's, flipped on exit.
        """
        sign = direction.sign if entering else -direction.sign
        return float(price * (1.0 + sign * self.slippage_rate))


def run_bracket_backtest(
    decisions: pd.DataFrame,
    interval: str,
    max_horizon: int,
    costs: BracketCosts,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Simulate a bracket strategy and return `(trades, metrics)`.

    `decisions` carries one row per candle: the candle itself (`timestamp, open, high, low, close, atr`)
    and what the engine decided on it (`direction, take_profit_percent, stop_loss_percent`). A `direction`
    of 0 is no signal. Rows are read in timestamp order; the frame is not required to arrive sorted.

    The shape of the return matches `close_to_close.run_backtest` so the report can treat both alike,
    but the frames are not comparable row for row: this one has a row per *trade*, that one per candle.
    """
    started = time.perf_counter()
    if max_horizon < 1:
        raise ValueError(f"max_horizon must be at least 1 candle, got {max_horizon!r}")
    missing = set(CANDLE_COLUMNS + DECISION_COLUMNS).difference(decisions.columns)
    if missing:
        raise ValueError(f"Bracket backtest is missing columns: {sorted(missing)}")

    frame = decisions.sort_values("timestamp").reset_index(drop=True)
    logger.info(
        "Bracket backtest started | candles=%s | interval=%s | max_horizon=%s | fee=%.3f%% | "
        "slippage=%.3f%% | rule=%s",
        f"{len(frame):,}",
        interval,
        max_horizon,
        costs.fee_rate * 100,
        costs.slippage_rate * 100,
        ADVERSE_WINS_TIE_BREAK,
    )

    high = frame["high"].to_numpy(dtype=np.float64)
    low = frame["low"].to_numpy(dtype=np.float64)
    open_ = frame["open"].to_numpy(dtype=np.float64)
    close = frame["close"].to_numpy(dtype=np.float64)
    atr = frame["atr"].to_numpy(dtype=np.float64)
    sides = frame["direction"].to_numpy(dtype=int)
    take_profit_percent = frame["take_profit_percent"].to_numpy(dtype=np.float64)
    stop_loss_percent = frame["stop_loss_percent"].to_numpy(dtype=np.float64)
    times = frame["timestamp"].to_numpy()

    trades: list[dict[str, Any]] = []
    stale = 0
    index = 0
    # The last candle can hold a decision but never a fill, so decisions stop one short of the end.
    while index < len(frame) - 1:
        direction = Direction(int(sides[index]))
        if not direction.is_open:
            index += 1
            continue

        levels = levels_for(
            direction=direction,
            entry_price=float(close[index]),
            take_profit_percent=float(take_profit_percent[index]),
            stop_loss_percent=float(stop_loss_percent[index]),
            atr=float(atr[index]),
        )
        fill_index = index + 1
        fill_price = costs.market_fill(float(open_[fill_index]), direction, entering=True)

        if _already_through(fill_price, levels.take_profit_price, levels.stop_loss_price, direction):
            stale += 1
            index += 1
            continue

        touch = first_touch(
            high=high,
            low=low,
            open_=open_,
            entry_index=fill_index,
            take_profit_price=levels.take_profit_price,
            stop_loss_price=levels.stop_loss_price,
            direction=direction,
            max_horizon=max_horizon,
        )
        exit_index = fill_index + touch.bars_held - 1
        exit_price = _exit_price(touch, direction, close, exit_index, costs)

        gross_return = direction.sign * (exit_price - fill_price) / fill_price
        # Charged on both notionals. Approximating the exit notional by the entry one would understate a
        # winning trade's cost and overstate a losing one's, in both cases by less than the rounding on
        # a real venue's fee — but the exact form is no harder to write.
        fee_cost = costs.fee_rate * (1.0 + (1.0 + gross_return))
        net_return = gross_return - fee_cost
        held = slice(fill_index, exit_index + 1)
        excursion_low = float(low[held].min())
        excursion_high = float(high[held].max())
        if direction is Direction.LONG:
            adverse, favourable = excursion_low, excursion_high
        else:
            adverse, favourable = excursion_high, excursion_low

        trades.append(
            {
                "decision_index": index,
                "decision_time": times[index],
                "fill_index": fill_index,
                "fill_time": times[fill_index],
                "exit_index": exit_index,
                "exit_time": times[exit_index],
                "direction": int(direction),
                "decision_close": float(close[index]),
                "fill_price": fill_price,
                "take_profit_price": levels.take_profit_price,
                "stop_loss_price": levels.stop_loss_price,
                "exit_price": exit_price,
                "outcome": int(touch.outcome),
                "resolved": bool(touch.resolved),
                "ambiguous": bool(touch.ambiguous),
                "bars_held": int(touch.bars_held),
                "atr": float(atr[index]),
                "take_profit_atr": levels.take_profit_atr,
                "stop_loss_atr": levels.stop_loss_atr,
                "realised_risk_reward": _realised_risk_reward(levels, fill_price, direction),
                "entry_gap_percent": (fill_price - float(close[index])) / float(close[index]) * 100.0,
                "gross_return": float(gross_return),
                "fee_cost": float(fee_cost),
                "net_return": float(net_return),
                "return_atr": float(net_return * fill_price / atr[index]),
                # In the same units as `return_atr`, so a reader can add the two back together and see
                # what the bracket earned before the venue took its cut. At a 0.6%-of-price ATR against a
                # 0.1% round-trip fee this is a third of the stop distance, which is the difference
                # between a bracket that pays and one that cannot.
                "fee_atr": float(fee_cost * fill_price / atr[index]),
                "adverse_excursion_percent": direction.sign * (adverse - fill_price) / fill_price * 100.0,
                "favourable_excursion_percent": (
                    direction.sign * (favourable - fill_price) / fill_price * 100.0
                ),
            }
        )
        # Re-arm on the bar the exit happened. The position was closed intrabar, so that bar's close is a
        # decision the bot could really have acted on; skipping it would impose a cooldown no venue asks
        # for. `exit_index > index` always, so this terminates.
        index = exit_index

    trade_frame = pd.DataFrame(trades, columns=list(TRADE_COLUMNS))
    metrics = _bracket_metrics(trade_frame, frame, interval, max_horizon, costs, stale)
    logger.info(
        "Bracket backtest finished | trades=%s | win_rate=%.2f%% | expectancy=%+.4f%% | "
        "profit_factor=%s | stale_entries=%s | elapsed=%.3fs",
        f"{len(trade_frame):,}",
        metrics["trades"]["win_rate"] * 100,
        metrics["trades"]["expectancy_percent"],
        _format_optional(metrics["trades"]["profit_factor"]),
        f"{stale:,}",
        time.perf_counter() - started,
    )
    return trade_frame, metrics


def _already_through(
    fill_price: float,
    take_profit_price: float,
    stop_loss_price: float,
    direction: Direction,
) -> bool:
    """Has the fill already passed a barrier anchored to the decision close?

    Both sides are checked, and the take-profit side matters as much as the stop side. A fill that has
    gapped past the take-profit would resolve instantly at a level *worse* than the fill, booking a
    negative return as a win — the trade looks like the strategy working while the P&L says otherwise.
    """
    if direction is Direction.LONG:
        return fill_price >= take_profit_price or fill_price <= stop_loss_price
    return fill_price <= take_profit_price or fill_price >= stop_loss_price


def _exit_price(
    touch: TouchResult,
    direction: Direction,
    close: np.ndarray,
    exit_index: int,
    costs: BracketCosts,
) -> float:
    """The price the position actually left at, with slippage where a market order would suffer it."""
    if touch.outcome is Outcome.TAKE_PROFIT_FIRST:
        # A resting limit order. It fills at its own price or it does not fill.
        return float(touch.exit_price)
    if touch.outcome is Outcome.STOP_LOSS_FIRST:
        # `first_touch` has already charged the gap when a candle opened through the stop; slippage is
        # the venue's own execution cost on top of that.
        return costs.market_fill(float(touch.exit_price), direction, entering=False)
    # A timeout exits at the horizon close — the branch `domain.expectancy` insists on keeping, valued
    # here at what the candles actually did rather than at the zero the engine assumes when it cannot see.
    return costs.market_fill(float(close[exit_index]), direction, entering=False)


def _realised_risk_reward(levels: TradeLevels, fill_price: float, direction: Direction) -> float:
    """Reward over risk measured from the fill, not from the decision close.

    The requested ratio is `levels.risk_reward_ratio`; this is what is left of it after entering a candle
    late. NaN is unreachable in practice — `_already_through` has rejected any fill at or past the stop
    before this runs — and is returned rather than raised only so an arithmetic edge cannot abort a run.
    """
    reward = direction.sign * (levels.take_profit_price - fill_price)
    risk = direction.sign * (fill_price - levels.stop_loss_price)
    if risk <= 0:
        return float("nan")
    return float(reward / risk)


def _bracket_metrics(
    trades: pd.DataFrame,
    candles: pd.DataFrame,
    interval: str,
    max_horizon: int,
    costs: BracketCosts,
    stale_entries: int,
) -> dict[str, Any]:
    """Trade statistics, an equity curve, and the win rate this set of bets needed in order to pay."""
    net = trades["net_return"]
    wins = trades.loc[trades["outcome"] == int(Outcome.TAKE_PROFIT_FIRST)]
    losses = trades.loc[trades["outcome"] == int(Outcome.STOP_LOSS_FIRST)]
    timeouts = trades.loc[trades["outcome"] == int(Outcome.TIMEOUT)]
    profitable = net > 0

    gross_profit = float(net.loc[profitable].sum())
    gross_loss = float(-net.loc[~profitable].sum())
    resolved = len(wins) + len(losses)

    statistics = {
        "trades": int(len(trades)),
        "stale_entries_skipped": int(stale_entries),
        "take_profit_first": int(len(wins)),
        "stop_loss_first": int(len(losses)),
        "timeouts": int(len(timeouts)),
        "unresolved_at_end": int((~trades["resolved"]).sum()),
        "ambiguous_candles": int(trades["ambiguous"].sum()),
        # Two win rates, because they answer different questions. The first is what an operator's account
        # experiences — a timeout that closed a hair above the entry is a winning trade. The second is
        # what the model was trained to predict, and is the one to compare against a break-even rate.
        "win_rate": float(profitable.mean()) if len(trades) else 0.0,
        "win_rate_resolved": float(len(wins) / resolved) if resolved else 0.0,
        "average_win_percent": float(net.loc[profitable].mean() * 100) if profitable.any() else 0.0,
        "average_loss_percent": float(net.loc[~profitable].mean() * 100) if (~profitable).any() else 0.0,
        # The ATR-unit companions, and they are not a convenience: the percent pair averages across trades
        # whose barriers sat at different percentages of price, so a model that wins in quiet bars and
        # loses in volatile ones reports a mean win *smaller* than its mean loss on a bracket that asked
        # for the opposite. That reads as an inverted bracket and is not one. Normalising each trade by its
        # own ATR first is the only form in which the two are comparable — and it is the form the barriers
        # were requested in. Note the population differs from the percent pair above by design: these
        # split on the barrier that resolved, so they pair with `win_rate_resolved`, while the percent pair
        # splits on the sign of the return and pairs with `win_rate`.
        "average_win_atr": float(wins["return_atr"].mean()) if len(wins) else None,
        "average_loss_atr": float(losses["return_atr"].mean()) if len(losses) else None,
        "average_timeout_atr": float(timeouts["return_atr"].mean()) if len(timeouts) else None,
        "mean_fee_atr": float(trades["fee_atr"].mean()) if len(trades) else 0.0,
        "expectancy_percent": float(net.mean() * 100) if len(trades) else 0.0,
        # The unit the model's own expected value is quoted in, so the two are directly comparable.
        "expectancy_atr": float(trades["return_atr"].mean()) if len(trades) else 0.0,
        "profit_factor": float(gross_profit / gross_loss) if gross_loss > 0 else None,
        "total_return_percent": float(net.sum() * 100) if len(trades) else 0.0,
        "mean_bars_held": float(trades["bars_held"].mean()) if len(trades) else 0.0,
        "median_bars_held": float(trades["bars_held"].median()) if len(trades) else 0.0,
        "mean_adverse_excursion_percent": (
            float(trades["adverse_excursion_percent"].mean()) if len(trades) else 0.0
        ),
        "worst_adverse_excursion_percent": (
            float(trades["adverse_excursion_percent"].min()) if len(trades) else 0.0
        ),
        "mean_favourable_excursion_percent": (
            float(trades["favourable_excursion_percent"].mean()) if len(trades) else 0.0
        ),
        "mean_entry_gap_percent": float(trades["entry_gap_percent"].mean()) if len(trades) else 0.0,
        "requested_risk_reward": (
            float((trades["take_profit_atr"] / trades["stop_loss_atr"]).mean()) if len(trades) else 0.0
        ),
        # The median, not the mean. The realised ratio has the distance from the fill to the stop in its
        # denominator, so a fill that opened close to the stop sends it toward infinity — one such trade
        # drags a mean far past anything the strategy actually ran, and a mean of 3.8 on a grid that never
        # requests more than 2.0 reads as an improvement rather than as the instability it is.
        "median_realised_risk_reward": (
            float(trades["realised_risk_reward"].median()) if len(trades) else 0.0
        ),
        "long_trades": int((trades["direction"] == int(Direction.LONG)).sum()),
        "short_trades": int((trades["direction"] == int(Direction.SHORT)).sum()),
    }
    # Three rungs, because a single break-even rate cannot say *why* a strategy lost, and the top rung
    # alone actively misleads: a costed result graded against a cost-free bar reports a positive edge for
    # a strategy bleeding a third of an ATR per trade. Read the ladder downward and the erosion is named.
    statistics["break_even_win_rate_requested"] = _break_even_requested(trades, timeouts)
    statistics["break_even_win_rate_before_fees"] = _break_even_realised(
        trades, wins, losses, timeouts, gross=True
    )
    statistics["break_even_win_rate"] = _break_even_realised(
        trades, wins, losses, timeouts, gross=False
    )
    statistics["edge_over_break_even"] = (
        statistics["win_rate_resolved"] - statistics["break_even_win_rate"]
        if statistics["break_even_win_rate"] is not None
        else None
    )

    return {
        "rule": ADVERSE_WINS_TIE_BREAK,
        "interval": interval,
        "max_horizon": max_horizon,
        "fee_rate": costs.fee_rate,
        "slippage_rate": costs.slippage_rate,
        "candles": int(len(candles)),
        "trades": statistics,
        "equity": _equity_metrics(trades, candles, interval),
    }


def _break_even_requested(trades: pd.DataFrame, timeouts: pd.DataFrame) -> float | None:
    """The rate the *requested* bracket needed, ignoring every cost — the top rung of the ladder.

    This is the same number `domain.expectancy` quotes to a caller who asks what a 1.5:1 bet must be right
    about, so it is the rung to hold the model's own `expected_value` against. It is emphatically **not**
    the bar this strategy had to clear, and reporting it alone was a defect: at an ATR of 0.6% of price
    against a 0.1% round trip, the fees alone move the real bar by more than ten points of win rate, so a
    47.8% win rate reads as a +7.8% edge over this rung while the account loses money on every trade.

    Uses the observed mean timeout return rather than the zero the engine assumes: `domain.expectancy`
    reserves `timeout_value_atr` for exactly this caller, on the grounds that a simulator walking real
    candles can see the horizon close instead of guessing at it.

    Averaging the barrier multiples across trades is an approximation — a set of bets at mixed ratios has
    no single break-even rate — so this is a yardstick, not an accounting identity. `None` when there are
    no trades to average.
    """
    if trades.empty:
        return None
    return _solve(
        reward_atr=float(trades["take_profit_atr"].mean()),
        risk_atr=float(trades["stop_loss_atr"].mean()),
        trades=trades,
        timeouts=timeouts,
        column="return_atr",
    )


def _break_even_realised(
    trades: pd.DataFrame,
    wins: pd.DataFrame,
    losses: pd.DataFrame,
    timeouts: pd.DataFrame,
    gross: bool,
) -> float | None:
    """The rate the bracket the strategy *actually ran* needed, from what its trades actually returned.

    `gross=False` is an accounting identity rather than a yardstick, and that is the whole point of it:
    solving `r*W + (1-r)*L` for zero with the realised means is the same arithmetic `expectancy_atr`
    performs, so `win_rate_resolved > break_even_win_rate` and `expectancy_atr > 0` can never disagree.
    That is the property the requested-distance rung lacks.

    `gross=True` strips the fee back out and answers the question the net rung cannot: whether a losing
    result was the model being wrong about direction or the venue being too expensive for this bracket. A
    win rate above the before-fees rung and below the net one is a model with a real edge that the fees
    are eating — a bracket problem, not a model problem, and the two have opposite remedies.

    `None` when either side is empty, because there is no realised win magnitude to average when nothing
    won; substituting the requested distance there is how a yardstick starts flattering. Also `None` when
    the mean win is not positive after costs, which is not a rate to reach but a bracket that cannot pay
    at any win rate.
    """
    if trades.empty or wins.empty or losses.empty:
        return None
    column = "return_atr"
    reward = float(wins[column].mean())
    risk = -float(losses[column].mean())
    if gross:
        reward += float(wins["fee_atr"].mean())
        risk -= float(losses["fee_atr"].mean())
    if reward <= 0 or risk <= 0:
        return None
    return _solve(
        reward_atr=reward,
        risk_atr=risk,
        trades=trades,
        timeouts=timeouts,
        column=column,
        timeout_offset=float(timeouts["fee_atr"].mean()) if gross and len(timeouts) else 0.0,
    )


def _solve(
    reward_atr: float,
    risk_atr: float,
    trades: pd.DataFrame,
    timeouts: pd.DataFrame,
    column: str,
    timeout_offset: float = 0.0,
) -> float | None:
    """One break-even solve, shared by every rung so they cannot drift apart.

    Delegates to `domain.break_even_win_rate` rather than restating its algebra, because the serving path
    quotes the same identity to callers and a second copy here would be a second thing to keep true.
    """
    timeout_share = float(len(timeouts) / len(trades))
    if timeout_share >= 1.0:
        return None
    timeout_value = float(timeouts[column].mean()) + timeout_offset if len(timeouts) else 0.0
    return break_even_win_rate(
        BarrierPair(take_profit_atr=reward_atr, stop_loss_atr=risk_atr),
        timeout_share=timeout_share,
        timeout_value_atr=timeout_value,
    )


def _equity_metrics(trades: pd.DataFrame, candles: pd.DataFrame, interval: str) -> dict[str, Any]:
    """Compound the trades onto the candle timeline so drawdown is measured in the order it happened.

    Each trade's net return lands on the bar it exited, and the bars it was held are marked as exposed.
    The annualised figures come from the shared `performance_metrics`, so they mean the same thing as the
    legacy report's — including that they are computed over *every* bar, flat ones included, which is
    what makes them comparable to buy-and-hold rather than to a fully-invested strategy.

    Sizing is one full position at a time, so `cumulative_return` compounds. A bot trading a fixed quote
    notional will not match it; the per-trade statistics are the transferable numbers.
    """
    returns = pd.Series(0.0, index=candles.index)
    positions = pd.Series(0.0, index=candles.index)
    for row in trades.itertuples(index=False):
        returns.iloc[row.exit_index] += row.net_return
        positions.iloc[row.fill_index : row.exit_index + 1] = float(row.direction)

    metrics = performance_metrics(returns, positions, interval, positions.diff().abs().fillna(0.0))
    metrics["periods_per_year"] = float(interval_periods_per_year(interval))
    return metrics


def _format_optional(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"
