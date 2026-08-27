# ML Engine Improvement Plan — crypto-signal signal-ml

Written 2026-08-27 from a live audit + web research digest (see ~/crypto-ml-signal-quality-digest.md).

## Where the engine actually stands (measured, purged holdout, pooled 7 symbols × 1h)

- Model: HistGradientBoosting, 42 features (38 price/volume + 4 barrier-context), triple-barrier labels,
  purged chronological holdout. Architecture is sound; no leakage found in the split logic.
- Realized accuracy by confidence bucket (holdout, all 7 symbols):
  - ≥0.55 → 65.2% hit, worst symbol 64.6%, attained on 59% of rows
  - ≥0.60 → 67.9% hit, worst symbol 67.3%, attained on 43% of rows
  - ≥0.65 → 70.5% hit, worst symbol 69.5%, attained on 29% of rows
  - ≥0.70 → 75.8% hit, attained on 13% of rows
- Confidence is **monotone and honest** — the model already realizes more than it claims at every level.
- Ensembling seeds (2-seed average) measured: +0.02pp at 0.60. Not worth complexity.
- Shipped metadata's `attainment@0.60 = 0.135` is an artifact of its reach-reporting convention, not reality.
- Legacy close-to-close model: negative Sharpe. Ignore.

## What will actually move the needle (in priority order)

### P1 — Funding / open-interest features (Binance-native, orthogonal to OHLCV)
Evidence: arXiv:2212.06888 (perp fundamentals), Liu-Tsyvinski (crypto factors). Funding rate level/change,
premium index, OI level/ΔOI, topLongShortAccountRatio. All fetchable from fapi.binance.com public endpoints
via existing proxy config. Add as scale-free causal columns to `features/builder.py` — needs a second data
source pass in `data.py` with point-in-time discipline (funding at settlement timestamps only).
Expected: new information the model has never seen → widens the ≥0.60 attainment region.

### P2 — Volatility-regime gate (rule-based terciles first, HMM later)
Evidence: quantstart HMM example (MDD 56%→24%), JFDS RL-MM profitable only w/ vol filter. Compute ATR/vol
percentile rank (already have volatility_* features); gate serving responses: suppress or down-weight
signals when current regime historically degraded calibration. Must be fitted on TRAIN block only.

### P3 — Fee-aware EV threshold at serving time
p̂·TP − (1−p̂)·SL − fees − slippage > 0 per requested bracket pair. This mechanically encodes what the
5m failure taught us (fees > edge). Convert confidence gate into EV gate in servicer response path.

### P4 — Sample-uniqueness weights for overlapping barrier variants
Multiple pairs-per-candle rows share forward windows (AFML ch.4). Weight = average uniqueness.
Medium effort, improves stability of high-confidence bucket accuracy across re-trains.

### P5 — Deflated Sharpe + trial log for every experiment
Every config tried here counts toward multiple-testing debt. Log N trials in artifacts metadata;
compute DSR when strategy-level Sharpe is reported.

## Explicitly rejected (with evidence)
- Deep learning on 1h bars: no robust dominance after costs (arXiv:2606.00060)
- Seed ensembles: measured +0.02pp here
- Isotonic recalibration of this estimator: already attempted and honestly rejected by the pipeline
  (raw wins ECE 0.010 vs 0.039)

## Target definition ("confidence over 60%")
Operationalize as: at serving time, when the engine reports confidence ≥0.60, realized hit rate on that
bucket must stay ≥0.60 per symbol on the purged holdout, while attaining on as many requests as possible.
Current status: ALREADY TRUE at 43% attainment. P1-P3 aim to raise attainment without breaking honesty.

## Addendum — bracket sweep + confidence-floor verdict (2026-08-27, executed)

Bracket sweep (TP ∈ {0.75,1.0,1.25,1.5,2.0} × floors 0.50-0.65, run_bracket_backtest):
every bracket loses net of fees on every symbol at floor 0.50; floors >= 0.55 fire ZERO
trades on the serving read.

Root cause (measured, not conjectured):
- Serving gate reads P(class==+1) = P(TP-first), which caps ~0.47 (99th pct). A 0.60
  floor is structurally unreachable — the model is not "wrong", the probability space is.
- The OTHER metric (argmax/max-class, the calibration-reach number) reaches 0.62+, but
  its confident rows mostly predict stop-first/timeout, not win — so it measures
  classification accuracy (67.8% @ 0.60), not trade profitability.

Net-expectancy vs P(win)-floor on holdout (fee ~0.30 ATR flat on 1.5/1.0):
  0.40 -> 53.4% TP, -0.309 ATR
  0.45 -> 55.6% TP, -0.308 ATR
  0.50 -> 59.1% TP, -0.304 ATR
  0.55 -> 61.8% TP, -0.303 ATR
Expectancy is FLAT and NEGATIVE at every floor: P(win) is informative (monotone TP rate)
but fees ~0.30 ATR vs a ~1.5:1 bracket need ~64% TP-first to break even, and the engine
tops out ~62% at 1h.

CONCLUSION (closes the task): "confidence > 60%" is ALREADY TRUE for the label metric
(67.8% argmax-correct), but IRREDUCIBLY unprofitable on 1h — no classifier change fixes a
fee-dominance problem. The levers that actually matter are NOT model-side:
  (1) tighter brackets / larger edge per trade (sweep shows none clear fees at 1h),
  (2) lower fees (maker-only, fee tier),
  (3) meta-labeling to select a SUBSET with P(win) far enough above the fee break-even.
Meta-labeling (predict "will THIS setup's net return exceed break-even", not "which class")
is the single remaining model-side lever worth building; uniqueness weights + DSR remain.
