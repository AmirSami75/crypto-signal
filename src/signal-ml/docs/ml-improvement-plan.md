# ML Engine Improvement Plan — crypto-signal signal-ml

> **Updated:** 2026-09-05 · **Status:** Phase 1 complete (no edge found); Phase 2 MTF wiring done; LSTM v2 + online loop experimental; Phase 6 (pytorch-forecasting) staged · **Owner:** Hermes

---

## Where the engine actually stands (measured, as of 2026-09-05)

| Component | State | Evidence |
|---|---|---|
| Tree model (1h, pooled 7 symbols, 42 features) | **Shipped, honest, unprofitable** | holdout log-loss 0.7959, net edge −0.31 ATR/trade at all floors ≥0.50 |
| Meta-labeling | **Exhausted** — tried, rejected | 0/7 symbols pass +0.05 net & n≥50 (see table below) |
| LSTM v2 (1h, BTC-only smoke) | **Staged, NOT promoted** | holdout log-loss 0.327, net 0.00% (never cleared 0.5 floor), 30,816 trades |
| Online self-learning loop | **Live in codebase** | `RecordTradeOutcome` RPC serving, `training-status` endpoint 200, samples store wired |
| Multi-timeframe confluence | **Wired end-to-end** | proto + Python engine + backend C# complete, trainer guard in config.toml |
| Weekly retrain cron | **Fixed** | pinned to `9router/b.ai/glm-5.3-flash`, manual fire completed (REJECT verdict) |
| Bracket sweep | **Complete, conclusive** | 120 configs, zero profitable with ≥30 trades |

**Key honest finding (unchanged):** `confidence ≥ 0.60` is TRUE for the label metric (67.8% argmax-correct) but IRREDUCIBLY unprofitable at 1h — fees (~0.30 ATR) exceed edge. No classifier change fixes this.

---

## What's been done since the last update (2026-08-27 → 2026-09-05)

### 1. Bracket sweep — executed, conclusive (2026-09-01)
120 configs (6 TP/SL pairs × 6 confidence floors) over the exact purged holdout, serving tree bundle, net of fees+slippage:
- **Zero configs with ≥30 trades are profitable.**
- Best meaningful: TP2/SL1 @0.45 → −3.2% (35 trades).
- Current bot at floor 0.40 → −47%.
- Full results: `docs/bracket-sweep-2026-09-01.csv`

**Root cause:** serving gate reads P(class==+1) = P(TP-first), which caps ~0.47 (99th pct). A 0.60 floor is structurally unreachable. Expectancy is FLAT and NEGATIVE at every floor (0.40→−0.309, 0.45→−0.308, 0.50→−0.304, 0.55→−0.303 ATR). P(win) is informative (monotone TP rate) but fees ~0.30 ATR vs ~1.5:1 bracket need ~64% TP-first; engine tops out ~62%.

### 2. Meta-labeling — executed, rejected (2026-08-27)
`scripts/experiments/meta_label_gate.py`: meta-learner (HistGradientBoosting, 5 features) pooled, chronological 60/40 split.

| meta-floor | n trades | net E[ATR] | symbols passing +0.05 & n≥50 |
|---|---|---|---|
| 0.50 | 129,434 | −0.311 | 0/7 |
| 0.55 | 96,519 | −0.310 | 0/7 |
| 0.60 | 54,876 | −0.300 | 0/7 |
| 0.65 | 17,110 | −0.272 | 0/7 |
| 0.70 | 0 | — | 0/7 |

**RESULT: FAIL.** The meta-learner is monotone (tighter floor → slightly less bad) but cannot find a subset with positive net return on ≥3 of 7 symbols. Meta-labeling task cancelled on this evidence.

### 3. LSTM v2 + online learning — built, experimental (2026-08-31)
- LSTM v2: attention pooling, early stopping, 3-seed ensemble, temperature scaling. Commit `1678984`.
- Online learning: `RecordTradeOutcome` + `GetTrainingStatus` RPCs, trade-sample JSONL store (idempotent per `(bot_id, decision_candle)`), promotion gate (same rule as batch loop).
- Serving state: registry serves v1 LSTM as `_pooled:1h`; v2 staged NOT promoted (registry rejects `_v2` suffix — promotion is the gate's job).
- Honest numbers: v1 holdout net **−100%** at floor 0.5 (30,816 trades); v2 holdout log-loss **0.3267**, net **0.00%** (took no trades below floor).
- CPU-only torch wheel staged in `wheels/` + constraints pin (V2Ray kills CUDA wheel downloads).

### 4. Multi-timeframe confluence — wired end-to-end (Phase 2, T2.1–T2.3)
- **`features/mtf.py`** — `attach_higher_tf_features(frame, higher, prefix="h4_")` → joins scale-free H4 features (trend_ema_ratio, atr_pct, close_vs_ema20) via backward-asof on close_time (no lookahead). 13/13 tests pass, all invariants verified (coverage, lookahead, warmup, scale-free).
- **Proto** — `context_candles` + `context_interval` fields added to `EvaluateBotDecisionRequest`, Python + C# bindings regenerated.
- **Engine** — `evaluator.py` `_attach_context_features()` attaches MTF columns to the feature row before `choose_direction()`; warns when context arrives but model wasn't trained with MTF columns.
- **Backend** — `MlServiceContracts.cs`, `MlServiceClient.cs`, `BotTickExecutor.cs` (fetches H4 candles via `GetClosedCandlesAsync` with single retry), `TradingOptions.cs` (`MtfContextInterval` + `MtfContextCandles` config).
- **Trainer guard** — `config.toml` `[features].mtf_context = true` gate; `build_barrier_dataset` attaches H4 features during training when enabled; `download_mtf_context_frames()` fetches aligned higher-TF data.
- All 398 ML tests pass. Backend `dotnet build` 0 errors.

### 5. Weekly retrain cron — fixed (2026-09-05)
- Root cause: `drift_skip:silent` (unpinned job + provider/model config drift) + wrong model pin (`cl/` prefix not served by 9router).
- Fix: pinned to `9router/b.ai/glm-5.3-flash`.
- Verified: manual fire completed end-to-end (~13 min). Gate verdict: **REJECT** — BTCUSDT_1h edge −0.1913 → −0.2180 (worse), candidate archived. Consistent with no-edge finding. `failure_streak` reset 3→0, `last_status: ok`.

---

## Priority order for remaining model-side work

### P1 — Multi-timeframe confluence ✅ DONE
Phase 2 fully wired. The pooled model can now consume H4 context features (trend ema ratio, ATR%, close vs EMA20) as 3 extra scale-free columns. Trainer guard in config. **Pending:** actually train with `mtf_context=true` and gate-promote — see P4.

### P2 — Funding / OI features (Binance-native, orthogonal to OHLCV)
Evidence: arXiv:2212.06888 (perp fundamentals), Liu-Tsyvinski (crypto factors). Funding rate level/change, premium index, OI level/ΔOI, topLongShortAccountRatio. All fetchable from `fapi.binance.com` public endpoints via existing proxy config. Add as scale-free causal columns to `features/builder.py` — needs a second data-source pass in `data.py` with point-in-time discipline (funding at settlement timestamps only).
**Expected:** new information the model has never seen → widens the ≥0.60 attainment region.

### P3 — Volatility-regime gate (rule-based terciles first, HMM later)
Evidence: quantstart HMM example (MDD 56%→24%), JFDS RL-MM profitable only w/ vol filter. Compute ATR/vol percentile rank (already have `volatility_*` features); gate serving responses: suppress or down-weight signals when current regime historically degraded calibration. Must be fitted on TRAIN block only.

### P4 — Train + gate the MTF challenger (new, blocking)
- Set `mtf_context = true` in `config.toml [features]`
- Run `python -m crypto_signal train --config config.toml` (CPU torch, ~10 min)
- Gate: purged holdout log-loss + fee-aware bracket backtest vs incumbent
- If REJECT → archive under `rejected/`, record feature_count (42→~51 in metadata)
- If PROMOTE → registry hot-reloads (no restart)

### P5 — Fee-aware EV threshold at serving time
p̂·TP − (1−p̂)·SL − fees − slippage > 0 per requested bracket pair. This mechanically encodes what the 5m failure taught us (fees > edge). Convert confidence gate into EV gate in the servicer response path (`bot_advisor.py`).

### P7 — pytorch-forecasting challengers (TFT first) — STAGED
- **Why:** tree/LSTM see 42 hand-picked features on one timeframe. PF's TFT attacks exactly that: end-to-end **variable selection** (learns which features carry signal), **native multi-timeframe covariates**, and **quantile outputs**.
- **T6.1 — Dependency staging:** `pytorch-forecasting[cpu]` + `lightning` pins in `pyproject.toml`; pre-fetch wheels into `wheels/` (same V2Ray pattern as torch CPU wheel).
- **T6.2 — Quantile→barrier translation layer:** `pf_bridge.py` — `barrier_probabilities_from_quantiles(quantiles, horizon, tp_atr, sl_atr, atr)` → (P(TP), P(SL), P(timeout)). Validated on synthetic known-answer cases first.
- **T6.3 — TFT challenger trainer:** mirrors `lstm_pipeline.py`; small config (hidden 32, attention head 4, quantiles [0.1, 0.5, 0.9]), same purged holdout, same promotion gate.
- **T6.4 — Gate run:** honest — if TFT doesn't beat incumbent on holdout log-loss + net edge, archive it. Variable-selection importances are still useful even if the model loses.
- **Sequencing:** starts only after Phase 2 (MTF features) is merged — TFT wants those MTF covariates as inputs.

### P8 — Sample-uniqueness weights (AFML Ch.4)
Multiple barrier variants per candle share forward windows. Weight = average uniqueness. Improves stability of high-confidence bucket accuracy across re-trains.

### P9 — Deflated Sharpe + trial log
Every config tried counts toward multiple-testing debt. Log N trials in artifacts metadata; compute DSR when strategy-level Sharpe is reported.

---

## Explicitly rejected (with evidence)

| Item | Evidence |
|---|---|
| Deep learning on 1h bars (raw) | No robust dominance after costs (arXiv:2606.00060) |
| Seed ensembles | Measured +0.02pp at 0.60 — not worth complexity |
| Isotonic recalibration | Raw wins ECE 0.010 vs 0.039 — honestly rejected by pipeline |
| Meta-labeling (Task 3) | 0/7 symbols positive at any floor (table above) |
| LSTM as replacement (not challenger) | ROADMAP: wrong sequencing (expensive before cheap) |
| Lowering confidence floor below 0.40 | Fees dominate at 1h — no edge to unlock |
| 5m timeframe as primary | Fee-in-ATR ≈ 1.74 on 5m vs 0.39 on 1h — structurally closed (skill: crypto-exchange-integration §Bracket Economics) |

---

## Target definition (unchanged)

Operationalize as: at serving time, when the engine reports confidence ≥0.60, realized hit rate on that bucket must stay ≥0.60 per symbol on the purged holdout, while attaining on as many requests as possible. Current status: ALREADY TRUE at 43% attainment. P1 (MTF) + P2 (funding/OI) aim to raise attainment without breaking honesty. Net profitability at 1h requires halving fees (maker-only/fee-tier) or wider brackets — that's operational, not model-side.

---

## Operational levers (not model-side, but required)

1. **Maker-only / fee tier** — cuts the ~0.30 ATR fee by 50-80%, the right axis
2. **Bracket selection** — lift TP/SL ratio above 1.5:1 (sweep showed nothing above 2:1 with current model; if fees halved, 1.5/1.0 becomes profitable)
3. **Horizon reduction** — 15m has the same ~62% TP ceiling but different fee structure (still fee-dominant per the ATR math)
4. **Replay / paper first** — measure realised slippage on this exact venue pair before any real-money claim

---

## Self-learning loop (live, weekly cron + online)

- **Weekly cron** (`0 6 * * 1`): retrains pooled + per-symbol bundles, gates on purged holdout + bracket backtest. Pinned to `9router/b.ai/glm-5.3-flash`. If PROMOTE, registry hot-reloads. If REJECT, candidate archived.
- **Online loop** (`ML_ONLINE_LEARNING=true`): every closed bot position is a labelled example. `TradeSampleStore` (JSONL, idempotent per `(bot_id, decision_candle)`) → challenger pools up-weighted samples + replayed history → gate on same holdout → atomic promote via staging+move into hot-reload registry. Rejected challengers archived with verdict in the name.
- **Bot stays Sandbox** as data-collector. No real-money execution until gates 6-8 of `docs/LIVE_TRADING_SAFETY.md` are implemented and a positive bracket is demonstrated.
