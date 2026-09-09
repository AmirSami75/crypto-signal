# E4 — Maker-Fill Execution at 15m (12h horizon)

**Status: COMPLETE — REJECT (2026-09-09)**
**Model:** maker entry at decision close (fill only if next candle trades through the limit — unfilled rows dropped), maker fee 0.02% entry + taker exits, horizon 48×15m = 12h, tp 1.5 / sl 1.0 ATR. Same 15m feature set, same HGB, strict holdout 269k rows.

## Result

| floor | trades | expectancy ATR | PF |
|---|---|---|---|
| 0.45 | 474 | −1.792 | 0.32 |
| 0.50 | 26 | −1.076 | 0.49 |
| 0.55 | 5 | +0.506 | 0.01* |

**REJECT.** No cell with ≥30 trades clears expectancy>0 AND PF>1. The single +0.51 ATR
reading is 5 trades with PF 0.01 — noise plus one lucky cluster, exactly the small-sample
trap the lab spec (§13) warns about.

Also honest observation: maker labels' strict LL 0.5980 vs base 0.3511 looks like a huge
margin, but the base rate itself differs (36.9% label balance after unfilled-row
dropping) — the fill filter changes the population. The gate that matters is economic,
and it failed.

## Lab ledger (4 experiments, all REJECT, all recorded)
| exp | lever tested | outcome |
|---|---|---|
| E0 | bracket geometry × confidence | all cells negative |
| E1 | fee-aware net labels | no edge over base rate |
| E2 | funding features at 1h | zero delta |
| E3 | 15m resolution | real signal (+0.064 LL), economics still negative |
| E4 | maker-fill execution + 12h horizon | still negative; fill filter kills volume |

## Where this leaves the program (honest senior assessment)
1. The predictive signal at 15m is real but its amplitude (~0.1-0.2 ATR/candle) is smaller
   than ANY realistic cost structure we can defend: taker ~0.36 ATR, maker-mix ~0.30 ATR
   round trip at these ATR-normalised levels.
2. Execution engineering cannot rescue a signal smaller than costs. The gap is ~2-3×, not
   a rounding error.
3. Remaining hypotheses, in declining credibility:
   - **Regime conditioning**: the signal may concentrate in specific volatility/trend
     regimes; a regime-gated model could trade 10× less often with 2× the per-trade edge.
     (Testable: E5 regime-conditional calibration — no new data needed.)
   - **Portfolio/cross-sectional**: relative-value across the 35 symbols instead of
     directional bets per symbol (different label construction entirely).
   - **True microstructure data**: order-book snapshots / aggTrades at 1s resolution —
     heavy download, out of current infra scope (no GPU, 11G disk on nlp30).
4. What we will NOT do: lower the confidence floor and call 21k negative-expectancy trades
   a strategy; relax cost assumptions; deploy anything that failed the gate.

The production incumbent (HGB 1h pooled) stays exactly as is — the lab has produced no
challenger that beats it, which is itself the correct, honest outcome so far.
