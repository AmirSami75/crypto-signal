# E5 - Regime-Conditional Calibration (15m maker model)

**Status: COMPLETE - REJECT (2026-09-09)**
**Design:** vol regime (72-bar realized vol vs 720-bar rolling median, causal shift-1) x trend regime (|ema_ratio_26| vs its median) = 4 buckets. Split-half holdout: select buckets on first half, evaluate on second. Same E4 maker machinery (fee 0.02% entry, 12h horizon, floor 0.45).

## Result

Selection half (first 50% of holdout), per bucket (vol,trend):

| bucket | trades | expectancy ATR | PF |
|---|---|---|---|
| 0,0 (low vol, no trend) | 20 | -14.03 | 0.04 |
| 0,1 (low vol, trend) | 41 | -6.92 | 0.10 |
| 1,0 (high vol, no trend) | 41 | -5.52 | 0.09 |
| 1,1 (high vol, trend) | 156 | -1.52 | 0.38 |

**Zero buckets positive on the selection half. Gate dies at step 1 - OOS evaluation not run.**

## Interpretation
1. The E3 signal does NOT concentrate in any (vol, trend) regime at this horizon/floor - every bucket is worse than the unconditioned E4 average (-1.79 ATR), with tiny-sample buckets catastrophic. Regime conditioning does not sharpen this edge; it slices it thinner.
2. Note the monotonic pattern: the trend+vol bucket (1,1) is the least-bad and has the most volume. Weak evidence the edge lives in ACTIVE markets - consistent with microstructure intuition - but -1.52 ATR is still 5x from viability.
3. Pattern across E0-E5: five structural levers tested (geometry, labels, derivatives data, resolution, execution, regimes). The 15m directional signal's amplitude (~0.1-0.2 ATR) cannot cover ~0.3 ATR costs in any tested condition. Per-symbol directional betting on 1h-15m OHLCV+funding is exhausted as a research direction for this infrastructure.

## Program-level conclusion
The lab has now falsified every cheap-to-medium lever. Remaining directions require new infrastructure or new bet structure:
- Cross-sectional (relative value across 35 symbols) - different label machinery
- Order-book/aggTrades microstructure - new data pipeline (heavy)
- Longer-horizon swing labels (multi-day) where funding/OI can matter
The honest summary for the user: five experiments, five rejections, one real-but-subscale signal found, zero viable challengers, incumbent unchanged. This is what a working research lab looks like when the edge is not there yet.

## Artifacts
- results/e5_meta.json, results/e5_run.log
- research_lab/experiments/run_e5.py (split-half regime harness)
