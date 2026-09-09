# E9 — Microstructure Direction: Trade-Flow Features at 15m

**Status: COMPLETE — REJECT (2026-09-09)**
**Data**: 72/72 months × 3 symbols UM-futures aggTrades (52 GB raw → 108 validated 15m feature files,
mean 99.993% vwap-inside, close error 0.0 vs UM klines) — the cleanest dataset the lab has built.
**Design**: aggressor-split flow (delta_pct, large_trade_share, flow-memory lags/rolls 4/12/48,
log trade size/count) + kline ret_1/ATR14, both sides, fee-aware labels at futures costs
(TP 1.5 / SL 1.0 ATR, H=48 = 12h), strict holdout 2026-05 → 2026-08 (70,522 rows), purge 288.

## Result

| metric | value |
|---|---|
| rows | 420,442 (70,080 buckets × 3 symbols × 2 sides) |
| label balance dev / hold | 0.396 / 0.390 (stable) |
| strict-holdout LL vs base rate | 0.6668 vs 0.6688 — **margin +0.0020** |
| AUC | 0.5125 |
| floor cells 0.50 / 0.55 / 0.60 | model's holdout max p < 0.50 → **zero sequential trades** |

**VERDICT: REJECT.** The margin is 30× smaller than the candle-feature margin at the same
15m resolution (E3: +0.064). Aggregated trade flow adds almost nothing the candles don't
already have at 12h horizon, and the model never gets confident enough to clear any floor.

## Why — the horizon mismatch

The OFI literature (Cont/Kukanov/Stoikov; DeepLOB family) measures sign at **second-to-minute
horizons with per-event features**. E9 tested flow aggregated to 15m buckets over 12h — two
orders of magnitude past where the documented effect lives. By then the aggressor signal has
been arbitraged into the kline's own close (which is in the feature set anyway, via ret_1).

## The complete map after E9

| information source | tested | sign found? |
|---|---|---|
| OHLCV candles 1h/4h (E1, E8) | ✅ | no |
| OHLCV candles 15m (E3/E6/E7) | ✅ | no — magnitude only (+9-12%) |
| funding (E2) | ✅ | no |
| aggregated trade flow 15m/12h (E9) | ✅ | no |
| **tick/second-level flow** | ❌ not testable | literature says yes, but: |

The one untested cell is tick-level OFI — and it is closed by arithmetic, not modelling:
a taker round-trip at 15m already costs 0.55 ATR; at tick horizons every taker round trip
costs more than the documented OFI edge. Exploiting tick-level sign requires a **maker/HFT
market-making operation** (colocated, fee-tier-9, resting-queue infrastructure) — a different
product class from these bots, not a model upgrade.

## Conclusion for the direction question

Every information source Binance publishes at our accessible granularity has been tested with
honest gates. None carries exploitable *sign* at horizons our fee structure can afford. The
bots' HOLD-heavy behaviour is the correct response to the data, not a bug. Deep learning
cannot change this: E6 proved a TCN extracts less than HGB from the same rows, and no
architecture extracts information the rows do not contain (§8, §27).

**Program recommendation**: freeze directional research; the incumbent 1h HGB with honest
0.40 floor stays in production. Any future edge work must start from a *new data acquisition*
(own order-book recorder, L2 depth) *and* a maker-style execution model — decide that as a
product decision, not a modelling one.

## Artifacts
- `research_lab/data/ingest_binance.py` (52 GB, 144 files, 0 failures)
- `research_lab/data/build_micro_features.py`, `validate_all.py` (72/72 PASS)
- `run_e9.py`; `results/e9_run.log`
