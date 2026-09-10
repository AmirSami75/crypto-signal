# E12 — Vol-Proportional Position Sizing on the Incumbent (lab simulation)

**Status: COMPLETE — REJECT as policy change; range-based size signal → dashboard only (2026-09-10)**
**Design**: incumbent's own data (35 symbols 1h), own fee-aware labels, HGB range
regressor (forward range/ATR over 24 candles, +3.7% MAE — same construction as E10).
Size policy `clip(pred_range / dev_median, 0.5, 2.0) × base notional` vs flat
(size = 1) on the same strict holdout (last 20%, purged). Drawdown compared on
exposure-normalized equity (same average notional → fair).

## Result

| floor | policy | trades | expectancy | exp/unit-risk | risk-adj (exp/σ) | PF | maxDD | total |
|---|---|---|---|---|---|---|---|---|
| 0.40 | flat | 64,065 | −0.3071 | −0.3071 | −0.24729 | 0.606 | 20,346.8 | −19,674.1 |
| 0.40 | vol-sized | 64,065 | −0.3370 | −0.3277 | −0.25482 | 0.587 | 21,479.8 | −21,590.8 |
| 0.50 | flat | 1,654 | −0.2831 | −0.2831 | −0.22556 | 0.630 | 536.4 | −468.2 |
| 0.50 | vol-sized | 1,654 | −0.2925 | −0.3054 | −0.22824 | 0.610 | 568.9 | −483.8 |

Dev median range 5.44 ATR; mean size 1.03 (0.40) / 0.96 (0.50) — exposure-matched.
Declared gate (better risk-adjusted expectancy, ≥200 trades, no worse maxDD) met
by no floor: sizing is worse on risk-adj at both floors AND worse on drawdown.

## Decision

- **Do NOT change bot sizing.** Flat sizing stays.
- **Range-based size signal to dashboard** (`predicted_range_atr` / implied size
  multiplier) — zero trading risk, shows what sizing *would* do.
- Mechanism (consistent with E7/E10): sizing up high-predicted-range candles
  concentrates notional exactly where whipsaw/stop-out rates are highest, so
  size-weighting pushes expectancy per unit risk from −0.307 to −0.328. The range
  model predicts magnitude, not sign — scaling by magnitude cannot fix a
  zero-sign policy.

## Artifacts

`run_e12.py`, `results/e12_meta.json`, `results/e12_run.log`
