# E2 — Funding Ablation on Fee-Aware Labels (7 funded symbols)

**Status: COMPLETE — REJECT (2026-09-09)**
**Population:** BTC/ETH/SOL/XRP/ADA/BNB/DOGE (only symbols with funding history). 806,675 rows (both directions × candles), strict holdout 160,999 rows, production purge gap, costs fee 0.10% + slip 0.05% per side.

## Design
A/B on identical rows and split, same HGB capacity as incumbent:
- **BASELINE** — E1's 1h OHLCV features on net-outcome labels
- **+FUNDING** — adds `funding_rate_last`, `funding_rate_chg_3` via the causal `merge_asof(backward)` join (value published at or before candle open — no lookahead by construction)

Pre-declared gate: +FUNDING must (a) improve strict-holdout log loss, (b) open an economic
gate cell (expectancy>0 AND PF>1 AND ≥30 trades) that BASELINE lacked.

## Result

| arm | strict LL | best gate cell |
|---|---|---|
| baseline | 0.67236 | floor 0.60: 6 trades, −1.332 ATR |
| +funding | 0.67212 | floor 0.60: 6 trades, −1.332 ATR (identical) |

Δ log loss **+0.00024** in funding's favor — two ten-thousandths, far inside noise
(n≈161k, so even a real effect this size is ~0 trades of value). The gate cells are
byte-identical: the model never split on a funding column in the holdout range that
mattered. Six trades at −1.33 ATR is conviction-free sampling, not signal.

## Verdict: REJECT — funding features add no value at 1h resolution

## Why (mechanistically honest)
Funding settles every 8h and moves slowly; at 1h it is nearly a step function that the
price features already span. The information funding carries (crowding/positioning)
expresses itself over multi-day horizons — at the 24-candle horizon the label asks
about, the 8h-settled rate is mostly stale news. Also only 7 of 35 symbols have
history, so the pooled model sees the columns as 80% missing noise on other symbols
(in the E1 full-universe runs they would be even weaker).

## Roadmap consequence (experiment memory)
- Funding at 1h: **dead. Do not revisit without a multi-day horizon label.**
- Remaining levers, in expected-information order:
  1. **E3: finer resolution (5m/15m)** — microstructure (intrabar flows, short-horizon
     mean reversion) lives below 1h; also more samples per day.
  2. **Multi-day horizon labels** where funding/OI actually matter (positioning unwinds).
  3. OI history download (currently absent on disk) — only after a horizon where it can matter.
- The deep-learning question stays parked until ANY feature set shows strict-holdout
  economic edge for even a linear/GBoost model.

## Artifacts
- `results/e2_meta.json`, `results/e2_run.log`
- `research_lab/experiments/run_e2.py` (A/B harness reusable for any feature group)
