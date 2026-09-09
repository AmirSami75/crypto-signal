# E0 — Bracket Geometry × Confidence Sweep

**Status: COMPLETE — verdict negative (2026-09-09)**
**Data:** incumbent `_pooled_1h` strict holdout, 35 symbols, ~116k candles, costs fee 0.04% + slip 0.02% per side

## Question
Does any (tp_atr, sl_atr, conf_floor) cell produce positive NET expectancy for the
incumbent HGB pooled model on the strict holdout under production cost assumptions?

## Method
- `research_lab/experiments/run_e0.py` — reuses pipeline machinery verbatim:
  `build_barrier_dataset`, `_carve_holdout`, `_score_side`, `_expected_values`,
  `run_bracket_backtest`. Features built once per symbol; 42-cell grid swept per symbol.
- Grid: tp/sl ∈ {(1.5,1.0),(2.0,1.0),(2.0,1.5),(2.5,1.0),(3.0,1.0),(3.0,1.5),(4.0,1.5)},
  floors ∈ {0.36,0.40,0.44,0.48,0.52,0.56}

## Result
**Every cell negative.** Best: (2.0,1.5,0.40) −0.303 ATR/trade, PF 0.75, 40.5k trades.
Worst big cells ≈ −0.69 ATR. Confidence floor monotonicity absent — filtering does not
concentrate edge. Larger R:R strictly worse (4.0/1.5 → −0.68).

Cell outliers (PF 10.3 on 208 trades) are small-sample variance, not signal.

## Verdict
- The model's (weak, ~55%) directional edge is smaller than round-trip costs under every
  tested geometry. **Geometry sweep cannot rescue the incumbent. Do not deploy any cell.**
- Per experiment memory (§15): TFT/MTF/4y-burst all REJECT on the same labels. The wall is
  the LABEL ECONOMICS + costs, not model capacity.

## Consequence
E1 must attack the economics, not the architecture:
1. Fee-aware labels (net-of-cost triple barrier: label 1 only when TP-first margin > costs)
2. Longer horizons / wider brackets to amortize fixed costs over more ATR of movement
3. Trade fewer, higher-conviction candles (per-symbol gating) — E0 shows no global floor works

Next: E1 fee-aware relabel on nlp30 (60Gi) — same walk-forward gate, incumbent as baseline.
