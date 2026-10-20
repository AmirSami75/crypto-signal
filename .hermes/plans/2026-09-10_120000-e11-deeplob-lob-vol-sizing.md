# E11 DeepLOB-on-bookDepth Prototype + Vol-Sizing Signal — Implementation Plan

> **For Hermes:** implement lane by lane with disjoint write scopes; lane C starts after A+B contracts verified.

**Goal:** Test whether LOB-level deep learning predicts direction where candles and aggregated flow failed, while shipping the proven vol skill as a sizing signal.

**Architecture:** (1) Reconstruct 10-level LOB snapshots from Binance UM `bookDepth` bulk deltas, validated against `bookTicker` BBO. (2) Reimplement DeepLOB (conv→inception→LSTM→3-class, PyTorch) on (1,100,40) tensors. (3) Gate under E8-upgrade rules. (4) Independently, add vol-based position sizing from the existing range model.

**Tech Stack:** Python, PyTorch (CPU), HGB baseline, existing `research_lab` gates.

---

### Lane A: bookDepth ingest + 10-level reconstruction (OWNER: data)

**Objective:** Reconstructed L1–L10 snapshots for BTCUSDT/ETHUSDT/SOLUSDT, 6 months, BBO-validated.

**Files:**
- Create: `src/signal-ml/research_lab/data/ingest_bookdepth.py`
- Create: `src/signal-ml/research_lab/data/reconstruct_lob.py`
- Create: `src/signal-ml/research_lab/data/test_reconstruct.py`

**Steps:**
1. Extend `ingest_binance.py` key patterns (already supports dtype dispatch) with `bookDepth` daily zips: `data/futures/um/daily/bookDepth/<SYM>/<SYM>-bookDepth-YYYY-MM-DD.zip`. Reuse `fetch()` resume logic.
2. Reconstruction contract (Lanes B/C consume this — fixed):
   - Input: bookDepth deltas (`U/u` update IDs, `b/a` [[price, qty]]) applied in sequence from each day's first snapshot; output snapshots sampled every 1 second.
   - Output: `research_lab/data/micro/<SYM>/lob/<SYM>-lob-1s-YYYY-MM.csv` with columns `timestamp, bid_p1..10, bid_q1..10, ask_p1..10, ask_q1..10` (prices float, qty float).
   - Validation: reconstructed BBO must equal `bookTicker` BBO for ≥99.9% of seconds (tolerance 1 tick); update-ID gaps logged, days with gaps >1% flagged and excluded.
3. TDD: hand-built delta sequence test (5 updates incl. qty-zero removal) with known snapshot answer; BBO-cross test must fail loudly.
4. Verify: `pytest research_lab/data/test_reconstruct.py`; validation report printed per day.
5. Scope: BTCUSDT/ETHUSDT/SOLUSDT, 2026-03-01 → 2026-08-31 (6 months ≈ depth bulk ~2–5 GB/symbol). Do NOT touch aggTrades code, models, runners.
6. Commit: `feat(lab): E11 lane A bookDepth reconstruction with BBO validation`.

### Lane B: DeepLOB reimplementation (OWNER: modeling)

**Objective:** `MultiTaskDeepLOB` PyTorch module with unit-tested shapes and causality.

**Files:**
- Create: `src/signal-ml/research_lab/models/deeplob.py`
- Create: `src/signal-ml/research_lab/models/test_deeplob.py`

**Steps:**
1. Architecture (from Zhang et al. 1808.03668, reimplemented not copied — original has no license): 3 conv blocks (1×2 stride + 4×1, LeakyReLU, BatchNorm) → inception (1×1, 3×1, 5×1, maxpool) → LSTM(64) → FC softmax 3-class (up/flat/down). ~150k params.
2. Input contract: `(B, 1, 100, 40)` — 100 consecutive 1s snapshots × 40 features (10 levels × bid/ask × price/qty), rolling-day z-scored (normalization fitted on dev only).
3. Labels: mid-price move over k∈{10, 50} events with ±α dead zone (α from dev volatility quantile, S-razmi convention) — labels computed in Lane C; Lane B takes label indices as input.
4. TDD: shape test (B,1,100,40)→(B,3); causality test (append future snapshot, first-99 outputs unchanged); gradient-flow smoke (one optimizer step reduces loss on 64 synthetic samples).
5. Verify: `pytest research_lab/models/test_deeplob.py` (expect ≥4 passed).
6. Scope: models dir only. No data fetching, no runners.
7. Commit: `feat(lab): E11 lane B DeepLOB reimplementation with causality proof`.

### Lane C: E11 runner + gate (OWNER: evaluation; starts after A+B verified)

**Objective:** Purged walk-forward E11 with HGB baseline on identical rows and E8-upgrade gate.

**Files:**
- Create: `src/signal-ml/research_lab/experiments/run_e11.py`
- Create: `src/signal-ml/research_lab/experiments/E11_RESULT.md`

**Steps:**
1. Consume Lane A CSVs + Lane B module (import, do not modify). Rows: pooled 3 symbols, chronological 70/15/15 (train/dev/hold) with purge = horizon rows × symbols at each boundary.
2. HGB baseline on flattened snapshot features (same rows) first; TCN trains only if HGB LL margin > 0 on dev (E6 rule).
3. Fee-aware labels at futures costs (0.05% taker + 0.02% slip), TP 1.5/SL 1.0 ATR on 1s→15m aggregated horizon; gate = E8-upgrade 5 conditions (sequential, CI lower>0, top-symbol<40%, null ≤1/20 over 20 refits, LL margin>0).
4. Prior recorded before run: ~70% REJECT expected (Bybit result + fee wall). REJECT closes LOB-event question; PASS proceeds to serving-contract work (separate plan).
5. Verify: `run_e11.py` exit 0 + `e11_meta.json` written + verdict line in log.
6. Commit: `feat(lab): E11 DeepLOB vs HGB on LOB snapshots — <verdict>`.

### Lane D: vol-based position sizing (OWNER: sizing; independent, parallel with A/B)

**Objective:** Scale incumbent entries by predicted range instead of gating them (E10 showed gating buys +0.011 ATR; sizing uses the skill without blocking trades).

**Files:**
- Create: `src/signal-ml/research_lab/experiments/run_e12.py`
- Modify: none in serving path (lab-only simulation).

**Steps:**
1. Reuse E10 artifacts (range model + incumbent labels on 1h universe). Policy: size = clip(pred_range / median_range, 0.5, 2.0) × base notional; compare vs flat sizing on strict holdout by expectancy-per-unit-risk and max drawdown.
2. Deploy gate: sizing must improve risk-adjusted expectancy (expectancy / stdev) vs flat with ≥200 trades, no worse max drawdown. Else dashboard-only.
3. Verify: exit 0 + meta JSON + verdict.
4. Commit: `feat(lab): E12 vol sizing simulation — <verdict>`.

---

**Verification fan-in (after all lanes):** `pytest research_lab -q` (expect all green) + `git log --oneline -5` + LEDGER.json entries for E11/E12.

**Risks:** bookDepth reconstruction bugs (mitigated: BBO validation gate); 6-month depth bulk size (mitigated: 3 symbols, daily zips resumable); DL needs no GPU (CPU ok: ~150k params, 1s snapshots subsampled); fee-tier numbers (VIP0 futures 0.05%/0.02% standard tier knowledge — confirm on fee page before economics).

**Open:** Tardis vs bulk DIY (bulk first; Tardis fallback); Kaiko samples unchecked.
