"""E4 — maker-fill execution model at 15m.

Hypothesis (E3 consequence): the 15m signal (LL margin +0.064) is real but the
taker cost wall (~0.36 ATR round trip) eats it. A maker entry — a resting LIMIT
at the decision close, filled on the next candle — removes entry slippage and
halves the fee (maker 0.00-0.02% vs taker 0.04-0.05%). Realistic for liquid
pairs; NOT free: the limit only fills if price trades back through it, so we
model entry as:

  - LONG:  limit at decision close fills when next candle's LOW <= limit
  - SHORT: limit at decision close fills when next candle's HIGH >= limit
  - unfilled by candle open+horizon → skipped (no phantom trades)
  - entry fee = maker fee; exits keep the production simulator's rules
    (TP = resting limit at TP price, SL = market with slippage, timeout market)

Horizon 48×15m = 12h so the signal amplitude can grow against fixed costs.

Gate (pre-declared): some confidence cell with expectancy>0 AND PF>1 AND
>=30 trades in the SAME cell, under the maker cost model, on the strict holdout.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

_LAB = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_LAB / "src"))
sys.path.insert(0, str(_LAB))

from crypto_signal.config import load_config  # noqa: E402
from crypto_signal.data import load_ohlcv  # noqa: E402
from crypto_signal.evaluation.bracket import BracketCosts  # noqa: E402
from crypto_signal.features import WARMUP_COLUMNS, build_features  # noqa: E402
from crypto_signal.modeling.estimator import aligned_probabilities  # noqa: E402
from research_lab.labels.fee_aware import FeeAwareConfig  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
NON_FEATURE = {"timestamp", "symbol", "label", "net_atr", "resolved",
               "open", "high", "low", "close", "atr"}


def maker_label_symbol(frame: pd.DataFrame, direction_sign: int, config: FeeAwareConfig,
                       maker_fee_rate: float) -> pd.DataFrame:
    """Fee-aware labels under a maker entry at the decision close.

    Differences from the taker labeller:
    - entry price = decision close (the resting limit), not next open with slip
    - unfilled: for a LONG the next candle must trade at/below the limit (LOW <=
      limit); a SHORT's HIGH must reach the limit. If the FIRST candle after the
      decision gaps away from the limit, the order does not fill → row dropped.
    - fee = maker fee on entry + taker on the exit side (conservative mix)
    - timeout exits at market (taker) as in production
    """
    high = frame["high"].to_numpy(dtype=np.float64)
    low = frame["low"].to_numpy(dtype=np.float64)
    close = frame["close"].to_numpy(dtype=np.float64)
    atr = frame["atr"].to_numpy(dtype=np.float64)
    n = len(frame)
    horizon = config.max_horizon
    tp = config.take_profit_atr
    sl = config.stop_loss_atr

    entry = close  # resting limit at the decision close
    tp_price = entry + direction_sign * tp * atr
    sl_price = entry - direction_sign * sl * atr

    taker_side_cost = 2.0 * config.fee_rate + config.slippage_rate  # exit side only
    maker_entry_cost = maker_fee_rate
    # total round-trip cost as a rate; converted to ATR per row below
    fee_rate_total = maker_entry_cost + taker_side_cost

    # Fill test on the first candle after the decision: touch the limit?
    filled = np.zeros(n, dtype=bool)
    if n > 1:
        next_high = np.full(n, np.nan)
        next_low = np.full(n, np.nan)
        next_high[: n - 1] = high[1:]
        next_low[: n - 1] = low[1:]
        with np.errstate(invalid="ignore"):
            if direction_sign > 0:
                filled = next_low <= entry
            else:
                filled = next_high >= entry

    tp_first = np.full(n, horizon + 1, dtype=np.int32)
    sl_first = np.full(n, horizon + 1, dtype=np.int32)
    for h in range(1, horizon + 1):
        if h >= n:
            break
        fh = np.full(n, np.nan)
        fl = np.full(n, np.nan)
        fh[: n - h] = high[h:]
        fl[: n - h] = low[h:]
        with np.errstate(invalid="ignore"):
            if direction_sign > 0:
                hits_tp = fh >= tp_price
                hits_sl = fl <= sl_price
            else:
                hits_tp = fl <= tp_price
                hits_sl = fh >= sl_price
        un_tp = tp_first == horizon + 1
        un_sl = sl_first == horizon + 1
        tp_first = np.where(hits_tp & un_tp, h, tp_first).astype(np.int32)
        sl_first = np.where(hits_sl & un_sl, h, sl_first).astype(np.int32)

    touched = (tp_first <= horizon) | (sl_first <= horizon)
    tp_wins = (tp_first < sl_first) & touched
    sl_wins = touched & ~tp_wins

    future_close = np.full(n, np.nan)
    if n > horizon:
        future_close[: n - horizon] = close[horizon:]
    with np.errstate(invalid="ignore"):
        signed_move = (future_close - entry) * direction_sign / atr
    fee_atr = fee_rate_total * entry / atr

    net = np.where(
        tp_wins, tp - fee_atr,
        np.where(sl_wins, -sl - fee_atr, signed_move - fee_atr),
    )

    label = (net > 0).astype(np.int8)
    valid = filled & np.isfinite(net) & (atr > 0)
    valid[n - horizon:] = False if n > horizon else valid[n - horizon:]

    out = pd.DataFrame({
        "timestamp": pd.to_datetime(frame["timestamp"].to_numpy(), utc=True),
        "label": label, "net_atr": net, "fee_atr": fee_atr,
        "resolved": np.where(tp_wins, "tp", np.where(sl_wins, "sl", "timeout")),
    })
    return out[valid].reset_index(drop=True)


def main() -> int:
    started = time.perf_counter()
    config = load_config(_LAB / "config.2y.toml")
    barrier = config.barrier

    # Binance USDT-M: maker 0.02%, taker 0.05%. Use 0.02% maker entry, taker exit
    # (TP is a resting limit too — but keep taker on exit side as a conservative mix).
    maker_fee = 0.0002
    fee_config = FeeAwareConfig(
        take_profit_atr=barrier.backtest_take_profit_atr,
        stop_loss_atr=barrier.backtest_stop_loss_atr,
        max_horizon=48,  # 48 × 15m = 12h
        fee_rate=config.backtest.fee_rate,
        slippage_rate=config.backtest.slippage_rate,
    )
    print(f"maker_fee={maker_fee} tp={fee_config.take_profit_atr} sl={fee_config.stop_loss_atr} "
          f"horizon={fee_config.max_horizon}×15m=12h", flush=True)

    pieces = []
    for symbol in SYMBOLS:
        raw = load_ohlcv(_LAB / "data" / f"{symbol}_15m.csv", "15m")
        feats = build_features(raw, atr_window=barrier.atr_window)
        frame = feats.frame.copy()
        frame["timestamp"] = pd.to_datetime(raw["timestamp"].to_numpy(), utc=True)
        for column in ("open", "high", "low", "close"):
            frame[column] = raw[column].astype(float).to_numpy()
        frame["atr"] = feats.atr.to_numpy(dtype=np.float64)
        warm = feats.frame[list(WARMUP_COLUMNS)].notna().all(axis=1).to_numpy()
        frame = frame[warm & (frame["atr"] > 0)].reset_index(drop=True)
        for sign in (+1, -1):
            side = frame.copy()
            side["direction_sign"] = float(sign)
            labelled = maker_label_symbol(side, sign, fee_config, maker_fee)
            merged = side.merge(
                labelled[["timestamp", "label", "net_atr", "resolved"]],
                on="timestamp", how="inner",
            )
            merged["symbol"] = symbol
            pieces.append(merged)
        print(f"  {symbol}: {len(frame):,} candles", flush=True)
    dataset = pd.concat(pieces, ignore_index=True)
    print(f"rows: {len(dataset):,} | balance: {dataset['label'].mean():.4f}", flush=True)

    times = pd.to_datetime(dataset["timestamp"], utc=True)
    order = np.argsort(times.to_numpy(), kind="stable")
    dataset = dataset.iloc[order].reset_index(drop=True)
    cut = int(len(dataset) * (1.0 - barrier.holdout_fraction))
    purge = fee_config.max_horizon * 2 * len(SYMBOLS)
    dev = dataset.iloc[: cut - purge]
    hold = dataset.iloc[cut + purge:]
    print(f"development: {len(dev):,} | holdout: {len(hold):,}", flush=True)

    feature_columns = [c for c in dev.columns if c not in NON_FEATURE]
    model = HistGradientBoostingClassifier(
        max_iter=config.model.max_iter,
        max_leaf_nodes=config.model.max_leaf_nodes,
        learning_rate=config.model.learning_rate,
        min_samples_leaf=config.model.min_samples_leaf,
        l2_regularization=config.model.l2_regularization,
        early_stopping=False,
        random_state=config.model.random_state,
    )
    model.fit(dev[feature_columns], dev["label"].to_numpy())
    p_win = aligned_probabilities(model, hold[feature_columns])[:, 2]
    y = hold["label"].to_numpy()
    eps = 1e-6
    ll = float(-np.mean(y * np.log(p_win + eps) + (1 - y) * np.log(1 - p_win + eps)))
    base = float(y.mean())
    print(f"strict LL {ll:.4f} | base rate {base:.4f}", flush=True)

    # Economic gate under the maker cost model. The bracket simulator charges
    # taker fee on both sides, so adjust: run with fee_rate=maker_fee and
    # slippage only on non-limit exits — the simulator already prices TP as a
    # resting limit (no slippage) and SL/timeout as market (slippage applied).
    maker_costs = BracketCosts(fee_rate=maker_fee, slippage_rate=config.backtest.slippage_rate)
    from crypto_signal.evaluation.bracket import run_bracket_backtest
    from crypto_signal.domain import percent_from_atr

    hold = hold.copy()
    hold["p_win"] = p_win
    gate_rows = []
    for floor in (0.45, 0.50, 0.55, 0.60, 0.65):
        take = hold[hold["p_win"] >= floor]
        sims = []
        for (_s, sgn), group in take.groupby(["symbol", "direction_sign"]):
            g = group.sort_values("timestamp")
            g_entry = g["close"].to_numpy(dtype=float)
            g_atr = g["atr"].to_numpy(dtype=float)
            decisions = pd.DataFrame({
                "timestamp": g["timestamp"].to_numpy(),
                "open": g["open"], "high": g["high"], "low": g["low"], "close": g["close"],
                "atr": g["atr"],
                "direction": np.full(len(g), int(sgn), dtype=int),
                "take_profit_percent": [percent_from_atr(p, fee_config.take_profit_atr, a) for p, a in zip(g_entry, g_atr)],
                "stop_loss_percent": [percent_from_atr(p, fee_config.stop_loss_atr, a) for p, a in zip(g_entry, g_atr)],
            })
            try:
                _t, metrics = run_bracket_backtest(decisions, "15m", fee_config.max_horizon, maker_costs)
                sims.append(metrics["trades"])
            except ValueError:
                continue
        if sims:
            trades = sum(s["trades"] for s in sims)
            exp_values = [s["expectancy_atr"] for s in sims if s["trades"]]
            pf_values = [s["profit_factor"] for s in sims if s["trades"] and s["profit_factor"]]
            if trades and exp_values:
                cell = {
                    "floor": floor, "trades": trades,
                    "expectancy_atr": round(float(np.mean(exp_values)), 4),
                    "pf_mean": round(float(np.mean(pf_values)), 3) if pf_values else None,
                }
                gate_rows.append(cell)
                print(f"  floor {floor}: {cell}", flush=True)

    gate = pd.DataFrame(gate_rows)
    out = _LAB / "research_lab" / "results"
    gate.to_csv(out / "e4_gate.csv", index=False)
    econ_ok = bool(
        len(gate)
        and ((gate["expectancy_atr"] > 0) & (gate["pf_mean"] > 1.0) & (gate["trades"] >= 30)).any()
    )
    verdict = "PASS" if econ_ok else "REJECT"
    (out / "e4_meta.json").write_text(json.dumps({
        "log_loss": ll, "base_rate": base, "maker_fee": maker_fee,
        "gate": gate_rows, "verdict": verdict,
        "fee_config": {k: getattr(fee_config, k) for k in
                       ("take_profit_atr", "stop_loss_atr", "max_horizon", "fee_rate", "slippage_rate")},
    }, indent=2))
    print(f"E4 VERDICT: {verdict} ({time.perf_counter()-started:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
