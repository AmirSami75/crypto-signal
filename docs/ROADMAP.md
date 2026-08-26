# Roadmap — what's next, and where LSTM fits

*2026-08-26 · state: platform production-grade, model honest but unprofitable, zero trades by design*

---

## The LSTM question first, because you asked

**Short answer: not yet. Add it as experiment E1 after the bracket sweep, not before.**

The current model is a `HistGradientBoostingClassifier` — gradient-boosted trees over 42
tabular features (2.4M labelled rows, pooled across 7 symbols). Its holdout backtest loses
-13% net of fees at >50% confidence. That is a *strategy* problem, and an LSTM does not
automatically fix strategy problems; it swaps one estimator for another with different failure
modes:

| | Boosted trees (now) | LSTM |
|---|---|---|
| Tabular features, 2.4M rows | strong — this is their home turf | weak without massive data |
| Learns sequence shape automatically | no — needs manual lags/rolling stats | yes |
| Training cost | 5 min on CPU | hours, GPU strongly advised |
| Serving change | none — joblib swap | new runtime (torch), new input contract (sequences), bigger gRPC payloads |
| Failure mode you can debug | feature importance, tree dumps | opaque; silent drift harder to catch |

The honest sequencing argument: **the cheapest experiment that could make money is the bracket
sweep** (hours, no new code). An LSTM is the most expensive experiment available (new runtime,
new pipeline, GPU, weeks). You run cheap experiments before expensive ones — especially when the
cheap one might reveal the problem was never the model class.

Where LSTM genuinely earns its place: if the sweep shows *no bracket works* with current
features, sequence structure is the main thing left untried. Then build it — as a **challenger
inside the promotion gate we already built**, not as a replacement.

---

## Track 1 — Strategy validation (do now)

### 1.1 Bracket sweep · ~half day · answers "can this work at all?"
Backtest every TP/SL pair from the barrier grid (0.5–3 ATR, R:R 0.4–4) against the strict
holdout, reporting per-bracket: win rate vs break-even ladder, expectancy ATR, trade count,
max drawdown. Deliverable: a table showing whether **any** cell clears costs. Reuses the
existing backtester; no serving changes.
**Decision point:** positive cells exist → retune bot, proceed. None → go to 1.2 + start E1.

### 1.2 Feature review · ~1 day
42 features audited for: leakage (anything using future info), venue-dependence (Bitunix volume
semantics differ from Binance training data), staleness. Drop or fix offenders, retrain once,
compare through the gate. Cheap wins sometimes live here.

## Track 2 — LSTM challenger (E1, after 1.1 verdict)

Only if the sweep says trees have hit their ceiling:

1. **Sequence dataset builder** (~2 days): windows of N=64 candles → per-candle barrier labels,
   same labelling code as today so results are comparable. Stored parquet, not in the DB.
2. **Model** (~3 days): small Conv1D+LSTM (≈100k params — deliberately small; 400k candles is
   not much for deep nets), output = same three-way TP/SL/timeout head. PyTorch, CPU-trainable
   overnight, GPU optional.
3. **Serving path** (~2 days): export to ONNX so gRPC serving needs no torch runtime; the
   engine loads it beside the boosted model behind a version tag.
4. **Challenger protocol**: candidate LSTM vs incumbent boosted — identical holdout, identical
   brackets, and the existing `self_learning_loop.py` promotion gate decides. Loser gets
   archived with its scores, same as any rejected retrain.

Budget: ~1–2 weeks part-time. Success criterion set in advance: beats incumbent on holdout log
loss AND net edge, or it never serves.

## Track 3 — Operational (parallel, low intensity)

- **Soak the demo bot** (running): let `bitunix-demo-auto` accumulate decisions/outcomes for the
  calibration report. Target: ≥20 closed trades before drawing conclusions.
- **Gateway + cron**: `hermes gateway start` so Monday retrains fire unattended.
- **Rotate the Bitunix API key** (it appeared in a screenshot).
- **Sync the Google Sheet**: File → Import → replace from the updated xlsx in ~/Downloads.
- **Restricted-live phase** (Phase 8): only after 4 clean soak weeks AND a positive bracket —
  tiny notional caps, manual approval gate, spot-only.

---

## Recommended order

```
now ──► 1.1 bracket sweep ──► verdict ──┬── positive ► retune bot → soak → Phase 8 prep
                                        └── negative ► 1.2 features → E1 LSTM challenger
Track 3 items woven in between (gateway/key/sheet are minutes each)
```
