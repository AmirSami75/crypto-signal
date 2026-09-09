# E10 — Vol-Targeted Entry Gate on the Incumbent (deployment candidate)

**Status: COMPLETE — REJECT as policy change; range model → dashboard monitoring signal (2026-09-09)**
**Design**: the incumbent's own data (35 symbols 1h), own labels, own 0.40 floor; the only new
element is an HGB range regressor (forward range/ATR over 24 candles) gating entries. Thresholds
from dev quantiles (q90/q95), strict holdout last 20% (purged).

## Result

| floor | gate | trades | expectancy | PF | sl% |
|---|---|---|---|---|---|
| 0.40 | no-gate | 64,065 | −0.3071 | 0.606 | 0.582 |
| 0.40 | skip≥q90 | 63,174 | −0.3000 | 0.613 | 0.581 |
| 0.40 | skip≥q95 | 63,935 | −0.3059 | 0.607 | 0.581 |
| 0.50 | no-gate | 1,654 | −0.2831 | 0.630 | 0.600 |
| 0.50 | skip≥q90 | 1,622 | −0.2724 | 0.640 | 0.598 |

Range skill at 1h/24h: **+3.7% MAE** (vs +12.2% at 15m — the skill decays with horizon).
Best gated cell improves expectancy by +0.011 ATR — inside fee noise and still −0.27 ATR/trade.
Declared deploy gate (beat ungated on expectancy AND PF, ≥200 trades) not met by any cell.

## Decision
- **Do NOT change bot policy.** The vol gate stays off.
- **Ship the range model as a dashboard signal** (`predicted_range_atr`) — zero trading risk,
  gives visibility into why the engine holds.
- E7's whipsaw finding applies at 15m; at the incumbent's 1h/24h the whipsaw channel is already
  priced into the label, so skipping high-range candles buys almost nothing.

## Why expectancy is negative at every floor
Round-trip cost at 1h ≈ 0.41 ATR (lab config) against TP 1.5/SL 1.0: even a perfect-direction
model must overcome 0.41 ATR before break-even; the observed −0.27…−0.31 is the no-edge case
(cost + slippage + timeout drift). Consistent with E1 (−0.30-ish at same costs).

## Artifacts
`run_e10.py`, `results/e10_meta.json`, `results/e10_run.log`
