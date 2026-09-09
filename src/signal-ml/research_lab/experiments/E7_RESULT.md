# E7 — Volatility-Targeting Breakout Straddle at 15m

**Status: COMPLETE — REJECT 0/9 cells (2026-09-09)** · 28s
**Structure:** stop entries at close ± trigger·ATR, ride the breach to TP/SL, whipsaw charged as a stop, taker entry / limit TP / market SL+timeout. Direction chosen by the market; the model predicts forward `range_atr` and gates on it. Grid 3 triggers × 3 brackets, threshold chosen on holdout-A, reported on holdout-B (split-half).

## Result
**Range model works — 12.2% MAE gain over mean, corr 0.475.** The volatility prediction is real
and materially better than the directional one (E6 return head: 0%).

**Yet every cell loses, and filtering makes it WORSE:**

| cell (trig/tp/sl) | unconditional B | range-filtered B (top 50%) |
|---|---|---|
| 0.5 / 1.5 / 1.0 | −0.969 ATR, PF 0.22, n 67.9k | −1.108 ATR, PF 0.18, n 35.1k |
| 1.0 / 2.0 / 1.0 | −0.943 ATR, PF 0.29 | −1.050 ATR, PF 0.26 |
| all 9 | −0.94 … −0.97 | −1.05 … −1.11 |

Outcome mix (filtered): SL 50%, TP 41%, whipsaw 8%, timeout 0%.

## The finding that explains E0–E7
Predicting high range **selects candles that are also more likely to whipsaw and stop out** —
the same volatility that carries price to TP carries it to SL first about as often. Range
prediction has no sign, and a symmetric structure cannot extract asymmetric payoff from a
symmetric quantity. The 12% edge in *magnitude* is orthogonal to P&L.

More fundamentally — the cost arithmetic, measured on the actual data:

| pair / tf | ATR/price | round trip @ futures-taker (0.05%+0.02% slip) | @ lab config (0.10%+0.05%) |
|---|---|---|---|
| BTC 15m | 0.26% | **0.55 ATR** | **1.17 ATR** |
| BTC 1h | 0.72% | 0.19 ATR | 0.41 ATR |
| BTC 4h | 1.53% | 0.09 ATR | 0.20 ATR |
| ETH 15m | 0.41% | 0.34 ATR | 0.73 ATR |

At 15m on BTC the lab's cost model charges **1.17 ATR per round trip against a 1.0-ATR stop.**
No bracket strategy can survive costs larger than its risk unit. The signal found in E3
(and the range skill here) were never tradeable at this resolution under these costs — it was
an arithmetic impossibility, not a modelling shortfall. The observed −0.95 to −1.1 ATR per
trade is almost exactly the cost line.

## Verdict & what it changes
REJECT the straddle. But the diagnosis reframes the program:
1. **Resolution and costs pull against each other.** Finer bars → more signal (E3) but ATR
   shrinks relative to fixed bps costs → costs explode in ATR units. 15m is uneconomic for
   any ATR-bracket strategy at realistic fees. 4h costs 0.09–0.20 ATR — that is where a
   bracket can breathe.
2. The lab's config costs (0.10% + 0.05%) are spot-tier; Binance USDT-M perpetual taker is
   0.05% (0.02% maker). Both must be tested, but the *decision* must use the venue the bots
   actually trade (futures testnet).
3. Whipsaw (8%) is the straddle's structural tax; it does not go away with better prediction.

## Next (E8, declared): coarse-resolution re-test
Re-run the fee-aware directional pipeline (E1 machinery) at **4h** on all 35 symbols with
**futures-tier costs** as primary and lab costs as robustness. Hypothesis: the 1h signal was
marginal because 0.41 ATR costs ate it; at 4h the same feature set faces 0.09–0.20 ATR.
If 4h shows no signal, the OHLCV feature family is closed at every resolution.

## Artifacts
- `research_lab/labels/straddle.py` + `test_straddle.py` (6 hand-computed tests)
- `research_lab/experiments/run_e7.py`, `results/e7_meta.json`, `results/e7_run.log`
