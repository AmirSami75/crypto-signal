# E8 — Coarse-Resolution Re-test: Fee-Aware Directional HGB at 4h, 35 Symbols

**Status: COMPLETE — REJECT after audit (2026-09-09)** · 15s run + 4-part adversarial audit
**Thesis:** E7 showed 15m costs are 1.17 ATR/round-trip vs a 1.0 ATR stop. At 4h the same bps
costs are 0.06 ATR (futures) / 0.12 ATR (lab) — if OHLCV features carry *any* direction, this is
where a bracket can afford it.

## Setup
- 4h bars from 1h CSVs by exact aggregation on UTC 4h boundaries; verified **0.0 OHLC diff vs
  Binance-native 4h** over 14,621 overlapping BTC bars.
- 35 symbols, 223,745 4h candles, 2020-01 → 2026-09. Fee-aware labels (E1 labeler, unit-tested),
  TP 1.5 / SL 1.0 ATR, horizon 24 bars = 4 days. 435k (symbol, candle, side) rows.
- Strict 20% chronological holdout (2026-02-15 → 2026-09-08, 85k rows), purge 1,680 rows.
- Two cost tiers, each with own labels/model/gate. Futures (0.05%+0.02%) PRIMARY.

## Raw result — the declared gate said PASS

| tier | LL vs base | AUC | floor 0.50 | 0.55 | 0.60 | 0.65 |
|---|---|---|---|---|---|---|
| futures | 0.6729 vs 0.6728 (**−0.0001**) | 0.527 | n 2814 +0.023 PF 1.04 | n 586 +0.061 PF 1.11 | n 151 +0.162 PF 1.31 | n 29 +0.71 |
| lab | 0.6728 vs 0.6726 (−0.0002) | 0.526 | n 2610 −0.029 | n 434 −0.131 | n 82 +0.089 PF 1.16 | n 22 |

Unconditional (take everything): −0.083 ATR (futures), −0.172 (lab). Floors 0.50–0.60 futures
met "expectancy>0 ∧ PF>1 ∧ n≥30". **First gate-PASS in eight experiments.**

## Audit — the PASS does not survive

| attack | floor 0.50 | 0.55 | 0.60 |
|---|---|---|---|
| bootstrap 95% CI on expectancy | [−0.023, **+0.069**] | [−0.035, +0.152] | [−0.025, +0.358] |
| t-stat | 0.99 | 1.21 | 1.63 |
| positive symbols / traded | 15/35 | 13/35 | 13/23 |
| **top symbol share of P&L** | **BCHUSDT 92%** | **BCHUSDT 93%** | BCHUSDT 67% |
| quarters (sum) | +74 / −82 / +73 | +0.3 / −0.3 / +36 | −0.3 / +14 / +11 |
| **sequential (1 position per symbol+side)** | n 665 **−0.074** PF 0.88 | n 211 **−0.029** PF 0.95 | n 60 **−0.114** PF 0.82 |
| null: gate PASS rate, label-shifted refits | **7 / 20 = 35%** | | |

Four independent kills, any one sufficient:
1. **Every CI includes zero.** No cell is distinguishable from no-edge.
2. **One coin.** BCHUSDT supplies 92–93% of P&L at the floors with meaningful n. Remove it and the
   cells are flat-to-negative. That is a BCH-2026 bet, not a strategy.
3. **Overlap inflation.** Per-candle rows count the same 4-day move up to 24×. A real book holding one
   position per symbol+side trades 665/211/60 times and **loses in all three cells**. This is the
   number the bots would actually realise.
4. **Chance rate 35%.** With labels circularly shifted (feature→label link destroyed), the declared
   gate passes 7/20 refits. The gate as specified has a false-positive rate of ~1/3 on this data;
   the observed PASS carries essentially no evidence.

Also: LL margin is **negative** at both tiers — the model is *worse* than the base rate on
strict holdout. The 4h classifier has no calibrated information; the floor cells were
selecting on noise that happened to coincide with BCH's run.

## Verdict
**REJECT.** The 4h OHLCV feature family contains no directional information the bracket can
monetise, even at 0.06 ATR costs. With E3/E6 (15m: signal exists but is volatility, not
direction) and E0–E2 (1h: none), this closes the OHLCV-only feature family at **every**
resolution tested: 15m, 1h, 4h.

## Methodological consequence — gate upgrade (binding from E9 on)
The E0–E8 gate (expectancy>0 ∧ PF>1 ∧ n≥30, per-candle rows) is **not sufficient**: it passed
a shuffled-label null 35% of the time. New minimum gate:
1. **Sequential** (non-overlapping, one position per symbol+side) expectancy > 0 and PF > 1.
2. Bootstrap 95% CI lower bound > 0 on sequential trades.
3. Top-symbol P&L share < 40% and ≥ 60% of traded symbols positive.
4. Null gate-pass rate ≤ 5% over ≥ 20 label-shift refits.
5. Strict-holdout log-loss margin > 0 (model must beat base rate before any economics count).

## Program status after E0–E8
Eight gated experiments, eight REJECTs. The consistent picture: OHLCV-derived features at any
resolution predict *magnitude* (E6/E7: +9–12% over baseline) but carry **no sign**. Direction
requires information that is not in the candles: order flow / book imbalance (§4 microstructure),
cross-sectional relative value, or exogenous data (funding at finer granularity, OI, liquidations).
Any of those needs a new data pipeline before another model is worth training.

## Artifacts
- `run_e8.py`, `audit_e8.py`; `results/e8_meta.json`, `e8_audit.json`, `e8_run.log`, `e8_audit.log`
- `run_e1.py` now also merges `fee_atr` (cost diagnostic)
