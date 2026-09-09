# E3 — 15m Resolution Experiment (BTC/ETH/SOL)

**Status: COMPLETE — REJECT on economics, PASS on signal (2026-09-09)**
**Data:** 15m candles from disk, 2020→2026, 680k candles × 2 directions = 1.36M rows. Horizon rescaled 24×15m = 6h (same forward span as 1h labels); tp 1.5 / sl 1.0 ATR unchanged; costs fee 0.10% + slip 0.05% per side. Strict holdout 272k rows with production purge.

## Result — the split verdict

**Signal: REAL.** Strict-holdout log loss **0.5734** vs base-rate 0.6378 → margin **+0.0644**.
First genuine predictive improvement in the lab (E1 margin was +0.0008, E2 +0.0002).
The 15m feature set carries information the 1h set does not — resolution was hiding edge.

**Economics: still negative.** Full confidence frontier (0.40→0.60):

| floor | trades | expectancy ATR | PF |
|---|---|---|---|
| 0.40 | 21,280 | −0.833 | 0.36 |
| 0.44 | 696 | −1.550 | 0.26 |
| 0.48 | 53 | −1.633 | 1.28 |
| 0.50 | 13 | −0.595 | 1.70 |

Every cell negative expectancy. Pre-declared gate (LL margin >0.01 AND economic cell
with expectancy>0, PF>1, ≥30 trades) → REJECT.

## Interpretation (senior read)
1. **The model ranks bets honestly** (LL margin real) but its absolute probabilities are
   miscalibrated for profitability: at every floor, taking the bet loses ~1 ATR after costs.
   The 0.48-0.50 cells' PF>1 with negative expectancy = a few large winners vs many medium
   losers; not tradeable at n=13-53.
2. **Pattern across E0-E3 is now crisp:** predictive signal exists (grows as resolution
   rises) but the tp1.5/sl1.0/6h geometry monetizes none of it. The binding constraint is
   the *cost-per-signal ratio*: ~0.36 ATR round trip vs a signal worth perhaps 0.1-0.2 ATR
   per candle.
3. Levers that remain, in order: (a) **cheaper execution** — maker entries (limit orders,
   no taker fee/slippage) would cut cost to ~0.08-0.1 ATR; (b) **longer horizons** so the
   signal amplitude grows relative to fixed costs; (c) **calibration to profitability**
   (train on net outcome with cost-aware loss weighting) — E1 did this at 1h where there
   was no signal to calibrate; at 15m there is.

## Next: E4 (declared)
15m fee-aware labels + **maker-fill assumption** (entry via limit at signal price:
zero slippage, maker fee 0.00% vs taker 0.04% — Binance USDT-M realistic) + horizon
48×15m = 12h. If the maker cell clears expectancy>0/PF>1/≥30 trades, the path to a
live challenger is execution design, not model capacity — and the same fill model must
then be enforced in the production risk engine before any paper deployment.

## Artifacts
- `results/e3_gate.csv`, `results/e3_meta.json`, `results/e3_run.log`
- `research_lab/experiments/run_e3.py` (resolution A/B harness, floor frontier sweep)
