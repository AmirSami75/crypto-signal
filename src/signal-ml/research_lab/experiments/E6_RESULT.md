# E6 — HGB vs Multi-Task TCN at 15m (§27 model comparison)

**Status: COMPLETE — REJECT (2026-09-09)** · 576s CPU · 15m BTC/ETH/SOL, maker labels, 12h horizon
**Challenger:** causal dilated TCN (kernel 3, dilations 1-2-4-8, 32 ch, ~50k params), lookback 32 candles (8h), focal-loss direction head + Huber heads for future return / MFE / MAE (§7 multi-task). Standardisation fitted on development only; early stopping on the last 15% of development (chronological); holdout scored once. Causality proven by unit test (appending a future step does not alter the prior step's output).

## Result — strict holdout, same 269k rows scored by both

| model | strict LL | best economic cell |
|---|---|---|
| HGB (baseline) | **0.5979** | 474 trades, −1.79 ATR, PF 0.32 |
| TCN (multi-task) | 0.6368 | 43,286 trades, −0.32 ATR, PF 0.65 |

ΔLL(TCN − HGB) = **+0.0389** → TCN is *worse* at ranking. Verdict REJECT on both criteria.

Training curve: val loss plateaued at epoch 3 (1.188) and never improved (best 1.1848 at ep 7); train kept falling → mild overfit, no capacity starvation. More epochs would not help.

### Forecasting heads (diagnostic, holdout MAE vs naive baseline)
| target | TCN MAE | naive baseline | gain |
|---|---|---|---|
| future log-return (12h) | 0.01517 | 0.01510 (predict 0) | **none** |
| MFE (ATR) | 2.736 | 3.014 (predict mean) | 9% |
| MAE (ATR) | 2.741 | 3.017 (predict mean) | 9% |

The return head cannot beat "predict zero" — the classic result for short-horizon
crypto returns. The excursion heads learn ~9% over the mean: the model recognises
*volatility* (how far price will travel) but not *direction*. That is exactly the E3
signal decomposed: the LL gain comes from vol/regime structure, not from directional
skill, which is why no bracket geometry monetises it.

## Why the TCN lost to HGB (mechanism)
1. The 39 features are already heavily engineered lags/rolling stats — the sequence
   dimension adds little the tabular model does not already see through `log_return_72`,
   `volatility_168`, etc. HGB's per-feature thresholds beat convolution on this input.
2. ~360k strided training windows is small for a conv net; HGB used 3× more rows.
3. Focal loss reshapes the probability surface toward hard examples, costing calibration
   (log loss) — appropriate for imbalance, wrong for a gate that consumes calibrated P.

Interesting: at floor 0.45 the TCN trades 90× more (43k) at −0.32 ATR — a *flatter*
probability distribution. That is the worst possible shape for a cost-gated policy.

## Verdict & program state
| exp | lever | verdict |
|---|---|---|
| E0 geometry · E1 fee labels · E2 funding · E3 15m · E4 maker · E5 regimes | structural | all REJECT (E3: signal real, subscale) |
| **E6 TCN + forecasting heads** | **architecture** | **REJECT — worse than HGB by 0.039 LL** |

§8 principle confirmed empirically: a deep model must show incremental value over a
strong classical baseline; here it shows *negative* value. Deep learning is not the
bottleneck. Directional information at ≤12h on OHLCV-derived features is.

## Artifacts
- `research_lab/models/tcn.py` (MultiTaskTCN, focal_bce, multitask_loss)
- `research_lab/labels/forecasting.py` (future return / MFE / MAE targets)
- `research_lab/models/test_tcn_and_forecasting.py` (7 tests: shapes, causality proof, focal, hand-computed targets)
- `research_lab/experiments/run_e6.py`, `results/e6_meta.json`, `results/e6_tcn.pt`, `results/e6_run.log`
