# E1 — Fee-Aware Relabel (net-outcome binary labels)

**Status: COMPLETE — REJECT at the tightened gate (2026-09-09)**
**Config:** tp 1.5 / sl 1.0 ATR, horizon 24, fee 0.10% + slip 0.05% per side (conservative), 35 symbols, 1.78M rows (both directions × candles), strict holdout 354k rows with production purge gap.

## Hypothesis
E0 showed no geometry beats costs when the model trains on zero-timeout 3-class labels.
Relabeling by NET outcome (timeout exits at market net of fees; binary P(net>0)) with the
SAME HGB should isolate whether label economics were the wall.

## Result
- Label balance: 39.6% net-positive — the honest base rate with real costs.
- Strict holdout log loss **0.6642** vs base-rate 0.6634 → effectively no edge beyond the prior.
- Economic gate (declared before the run, tightened after first PASS was found dishonest):
  cell must show expectancy > 0 AND PF > 1 AND ≥ 30 trades **in the same cell**.

| floor | trades | expectancy ATR | PF mean |
|---|---|---|---|
| 0.50 | 42 | +0.0386 | 0.676 |
| 0.55 | 3 | −0.2033 | — |

**REJECT.** The 0.50 floor's +0.039 ATR on 42 trades is fee noise with PF 0.68 (losers bigger
than winners). No cell passes.

## What this proves
1. **Labels were NOT the (only) wall.** With honest net-outcome labels, the same HGB capacity
   learns nothing beyond the base rate. The incumbent's 3-class labels at least captured
   timeout structure; net-P&L labels reveal the 1h OHLCV feature set has ~zero priced edge
   after costs.
2. E0 (no geometry works) + E1 (no relabel works) triangulate: **the information is not in
   the current 42 features at 1h resolution.** Deep architectures on the same inputs would
   interpolate the same nothing — confirmed by TFT's independent failure.
3. Cost assumptions (0.30% round trip incl. slippage) are the incumbent's own; relaxing them
   would be manufacturing edge.

## Consequence for the roadmap
Feature resolution must change before model capacity does:
- **E2 (next):** funding + OI ablation on the 7 funded symbols (backward-looking merges exist).
- **E3:** finer resolution (5m/15m) where microstructure lives; per-symbol funding context.
- Deep learning (TCN) only AFTER a feature set demonstrates holdout edge for even a linear
  model. Capacity amplifies signal; it does not create it.

## Artifacts
- `results/e1_gate.csv`, `results/e1_meta.json`, `results/e1_run.log`
- `research_lab/labels/fee_aware.py` + `test_fee_aware.py` (8 unit tests, hand-computed verdicts)
- Full suite: 435 passed.
