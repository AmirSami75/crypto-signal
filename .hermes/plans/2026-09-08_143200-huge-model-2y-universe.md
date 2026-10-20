# Huge Model — 2-Year × Full-Market Training on 10.224.2.30 — Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Train one barrier-conditional pooled model on a 2-year window (2024-09-08 → 2026-09-08) across the full tradeable USDT spot universe, on host `10.224.2.30`, and ship the bundle through the existing model registry without breaking paper/sandbox serving.

**Architecture:** Single pooled `HistGradientBoostingClassifier` bundle (`_pooled_1h`) trained by `crypto_signal/training/barrier_pipeline.py` in `Desktop/project/crypto-signal/src/signal-ml` (canonical — `crypto-ml-signal` is legacy). Universe is fetched from Binance `exchangeInfo`, filtered to liquid USDT spot, downloaded via the existing `fetch_historical_ohlcv` (proxy-aware) into `data/<SYMBOL>_1h.csv`, then `train_barrier_model` with the standard 4-block split (`holdout → fit → calibrate → assess`) and 3-fundamental + report. TFT/LSTM challengers are out of scope unless explicitly enabled.

**Tech Stack:** Python 3.11, `crypto-signal` CLI (`config.toml` → `AppConfig`), `pandas`, `scikit-learn`, `joblib`, Binance REST `api/v3/klines`, `10.224.2.30` as training host (verify CPU/RAM/GPU/disk/Docker), `host.docker.internal:10809` proxy bridge.

---

## 1. Current context / assumptions

- Canonical training repo: `Desktop/project/crypto-signal/src/signal-ml` (`config.toml`, `src/crypto_signal/*`). `Desktop/project/crypto-ml-signal` is the frozen 0.1.x archive — do not train there.
- Current pooled set: 7 symbols (`BTCUSDT ETHUSDT BNBUSDT SOLUSDT XRPUSDT ADAUSDT DOGEUSDT`), `interval=1h`, `start=2020-01-01`, ~58 555 rows/symbol (~6.7 yr), 410 540 total 1h rows. Files live at `src/signal-ml/data/<SYMBOL>_1h.csv` (~8 MB/symbol 1h). Artifacts at `src/signal-ml/artifacts/models/` (`_pooled_1h.joblib` 582 KB, `BTCUSDT_1h.joblib` 572 KB).
- Barrier config: `grid_atr=[0.5,1,1.5,2,3]`, `pairs_per_candle=3`, `max_horizon=24`, `holdout_fraction=0.2`, `calibration_blocks=[0.6,0.2,0.2]`, `atr_window=14`. ~366 k labelled rows for a 2-yr 7-symbol pool; full universe scales linearly with symbol count.
- `10.224.2.30` is pingable (2 ms), port 22 open, but SSH with `Desktop/automation/maxi-srv.pem` (`ubuntu`/`root`) failed (`Too many authentication failures`, `Permission denied (publickey)`). `~/.ssh/config` has only `aws-crypto`. Credentials for `.30` are not in repo. Host resources (vCPU/RAM/disk/GPU) are unmeasured — assumed "huge" per user, must be probed before committing to a full-universe run.
- Exchange universe: ~487 USDT spot trading symbols today; ranked by `quoteVolume` (24 h ticker). Top includes `USDCUSDT`, `BTCUSDT`, `ETHUSDT`; tail includes dust (`USDPUSDT` 8 k). A usable liquid set is far smaller than 487 after filtering stablecoins/de-list risk/low volume.
- Proxy: `network.proxy_url=http://127.0.0.1:10808` (V2RayN). Training on `10.224.2.30` may not have that proxy; downloads may run direct or need a forwarded proxy/env `HTTPS_PROXY`.
- LIVE remains disabled (`LIVE_TRADING_SAFETY.md`); training touches no live orders. Existing bots stay on `PAPER`.

## 2. Proposed approach

1. **Probe the host first**, then pick the universe size that fits its RAM/disk — not the reverse.
2. **Fix the time window** to an explicit 2-year slice (`start=2024-09-08T00:00:00Z`, `end=2026-09-08T00:00:00Z`) in a dedicated `config.2y.toml` so the run is reproducible and does not silently shift as `end=""` moves.
3. **Filter the universe** to a liquid, reproducible set (top-N by quoteVolume, exclude stable/stable pairs, optional `BTC`-only quote, min volume cutoff). Record the decision in the plan and in `metadata.json`.
4. **Batch-download with resume** (`download_barrier_candles --refresh` or `fetch_historical_ohlcv` per symbol), rate-limited (`pause_seconds=0.08`, retry on 429/5xx), behind whatever proxy `.30` actually has. Verify gaps/coverage before training.
5. **Train pooled** once on `.30`, reusing the existing 4-block split and `pairs_per_candle=3`. Consider sharding only if RAM estimate exceeds host. Keep the current TFT/LSTM code paths untouched.
6. **Measure honestly**, then promote through the registry only if strict holdout meets a pre-registered gate.

## 3. Step-by-step plan

### Task 1: Lock the active workspace and inventory

**Objective:** Avoid training the wrong checkout.

**Files:**
- Read: `Desktop/project/crypto-signal/src/signal-ml/config.toml:1-60`
- Read: `Desktop/project/crypto-signal/.hermes/plans/` (existing plans)
- Read: `Desktop/project/crypto-signal/src/signal-ml/pyproject.toml`

**Steps:**
1. Confirm `Desktop/project/crypto-signal/src/signal-ml/config.toml` is the canonical config (contains `symbols=[7]`, `grid_atr`, `pairs_per_candle=3`).
2. Run: `wc -l ~/Desktop/project/crypto-signal/src/signal-ml/data/*_1h.csv; du -sh ~/Desktop/project/crypto-signal/src/signal-ml/data` — record per-symbol rows and on-disk size.
3. Run: `ls -lh ~/Desktop/project/crypto-signal/src/signal-ml/artifacts/models/*.joblib; cat ~/Desktop/project/crypto-signal/src/signal-ml/artifacts/models/metadata.json` (if present) — record baseline bundle versions.

**Verification:** `git -C ~/Desktop/project/crypto-signal status --porcelain` clean before config edits.

### Task 2: Gain access to 10.224.2.30 and probe resources

**Objective:** No training commitment before knowing what "huge" means in GB and vCPU.

**Steps:**
1. Ask user for the correct SSH user + key/password for `10.224.2.30` (or a jump host/bastion). Note: `maxi-srv.pem` is for `aws-crypto` only; `.30` auth failed repeatedly.
2. Once in, run: `free -h; nproc; lscpu | head -15; df -h; nvidia-smi 2>&1 | head -20; docker info 2>&1 | head -20; python3 -c "import sys; print(sys.version)"` — record.
3. Check proxy egress on host: `curl -I https://api.binance.com/api/v3/ping --max-time 10; env | grep -i proxy` — decides whether downloads can run on `.30` or must be staged locally then rsynced.

**Acceptance:** Resource numbers (RAM, disk free, GPU model/VRAM, Docker available) written into the task's notes. If host lacks Docker, training runs bare-metal inside its `.venv`.

### Task 3: Define the universe and the 2-year window (decision record)

**Objective:** Make "all the symbol in the market" precise and auditable.

**Files:**
- Create: `Desktop/project/crypto-signal/src/signal-ml/config.2y.toml` (new)
- Modify: none yet

**Steps:**
1. Fetch spot universe: `curl --proxy http://127.0.0.1:10808 https://api.binance.com/api/v3/exchangeInfo?permissions=SPOT` then filter `symbol.endswith("USDT") and status=="TRADING"` → 487.
2. Rank by `https://api.binance.com/api/v3/ticker/24hr` `quoteVolume`. Draft candidates:
   - **A (conservative):** top-50 by quoteVolume, exclude `USDCUSDT USD1USDT TUSDUSDT USDPUSDT RLUSDUSDT` (stable/stable) → ~45 symbols.
   - **B (standard):** top-100 liquid → ~95 after stable filter.
   - **C (full):** all 487 — not recommended without >64 GB RAM; keep as stretch goal with sharding.
3. Present A vs B vs C to user with volume cutoff (e.g., keep `quoteVolume > 5M`). Default recommendation: **B (top-100)** for "huge model" that still fits one pooled fit.
4. Fix window: `start="2024-09-08T00:00:00Z"`, `end="2026-09-09T00:00:00Z"` (exclusive, yields exactly 2×365×24 = 17 520 1h candles max per symbol before gaps). Write into `config.2y.toml` with `symbols=[chosen list]`, `interval=1h`, `data_dir="data"`.

**Code sketch (`config.2y.toml`):**
```toml
[market]
symbol = "BTCUSDT"
symbols = ["BTCUSDT","ETHUSDT", /* ... chosen 45 or 95 */]
interval = "1h"
start = "2024-09-08T00:00:00Z"
end = "2026-09-09T00:00:00Z"
raw_data_path = "data/BTCUSDT_1h.csv"
data_dir = "data"
[barrier]
max_horizon = 24
atr_window = 14
grid_atr = [0.5, 1.0, 1.5, 2.0, 3.0]
pairs_per_candle = 3
holdout_fraction = 0.2
calibration_blocks = [0.6, 0.2, 0.2]
per_symbol_overrides = ["BTCUSDT"]
```

**Verification:** `src/signal-ml/.venv/bin/python -c "from crypto_signal.config import load_config; c=load_config('src/signal-ml/config.2y.toml'); print(len(c.market.symbols), c.market.start, c.market.end)"`

### Task 4: Estimate RAM / disk / time before downloading

**Objective:** Size the job so it does not OOM on `.30`.

**Steps:**
1. Compute per-symbol candle ceiling: 17 520. Pool: 45 → ~788 k candles pre-label; 95 → ~1.66 M; 487 → ~8.5 M. Labelled rows = `candles × pairs_per_candle × 2_directions_unpacked`? Barrier dataset is ~`candles × pairs_per_candle` before direction doubling (see `build_barrier_dataset`); at `pairs=3` expect ~2.4–5 M rows for 45, ~5–10 M for 95. Cross-check against current 7-symbol run (~1.2 M rows from ~410 k candles).
2. RAM rule of thumb from config comment: `pairs=6` on 7 symbols hit 5.1 GB / 2.4 M rows. Scale linearly. Record estimate in plan.
3. Decide `pairs_per_candle` stays 3 unless RAM headroom > 64 GB. Decide disk: `1h` at ~8 MB/58 k rows → 1h/2yr ~2.4 MB/symbol → 45 → ~110 MB, 95 → ~230 MB; trivial. 5 m is 5× larger — not needed for 1h model.

**Verification:** Estimate table appended to `config.2y.toml` header comment.

### Task 5: Download the 2-year slice (batched, resumable)

**Objective:** Populate `data/<SYMBOL>_1h.csv` for every chosen symbol with exactly the 2-year slice.

**Files:**
- Modify: `Desktop/project/crypto-signal/src/signal-ml/data/` (new/updated CSVs)
- Use: `src/crypto_signal/training/barrier_pipeline.py:download_barrier_candles` / `src/crypto_signal/data.py:fetch_historical_ohlcv`

**Steps:**
1. Local smoke: `src/signal-ml/.venv/bin/python -m crypto_signal --config src/signal-ml/config.2y.toml download --refresh` on 2 symbols — verifies proxy + pagination.
2. Full run: same command for full universe; it skips existing CSVs unless `--refresh`. On `.30`, run with host-appropriate proxy (`proxy_url` in `config.2y.toml` or `HTTPS_PROXY` env). If host cannot reach Binance, download locally then `rsync -av data/*_1h.csv 10.224.2.30:/path/to/project/src/signal-ml/data/`.
3. Handle rate limits: default `pause_seconds=0.08`, retry on 429/5xx with exponential backoff (already in `data.py`). For 95 symbols × ~18 pages/symbol ≈ 1 710 requests → ~2–3 min plus backoff.

**Commands:**
```bash
# local or on .30 (inside src/signal-ml)
.venv/bin/python -m crypto_signal --config config.2y.toml download --refresh --json 2>&1 | tee artifacts/logs/download-2y-$(date +%F).log
ls -lh data/*_1h.csv | wc -l
```

**Verification:** Every CSV `head -1` == header, `wc -l` within [17 000, 17 550] per symbol (allow exchange gaps/halts), `tail -1` timestamp ≥ `2026-09-07`. Re-run without `--refresh` is no-op.

### Task 6: Validate candles and feature build (no leakage)

**Objective:** Fail before fitting if data is gapped or misaligned.

**Files:**
- Read: `src/crypto_signal/data.py:validate_ohlcv`, `src/crypto_signal/features/*`

**Steps:**
1. Run: `.venv/bin/python -c "from crypto_signal.data import load_ohlcv; from pathlib import Path; ... validate each CSV"` — check monotonic `timestamp`, no duplicate `open_time`, `high>=low`, volume ≥0.
2. Feature dry-run on 3 symbols: `build_features` on subset — confirms no NaN explosion and MTF `h4` context frames align (`mtf_context=false` per config — keep false for this run unless user opts in).
3. Log gap report: symbols with < 17 000 rows flagged for exclusion or re-download.

**Verification:** Validator script exits 0; gap report attached to training log.

### Task 7: Single-symbol smoke training on .30

**Objective:** Prove the training path works on the host before the full pool.

**Steps:**
1. Copy a minimal `config.2y-smoke.toml` with `symbols=["BTCUSDT"]`, same window, `pairs_per_candle=3`.
2. On `.30`: `.venv/bin/python -m crypto_signal --config config.2y-smoke.toml train --json 2>&1 | tee artifacts/logs/train-smoke-2y.log` — expect `_pooled_1h`-equivalent output (actually `BTCUSDT_1h` bundle) plus `metadata.json`.
3. Check `artifacts/models/*.joblib` created, `REPORT.md` rendered, no OOM.

**Verification:** Bundle loads: `.venv/bin/python -c "import joblib; joblib.load('artifacts/models/BTCUSDT_1h.joblib')"`.

### Task 8: Pooled full-universe training on .30

**Objective:** Produce the huge pooled bundle.

**Files:**
- Create: `src/signal-ml/artifacts/models/_pooled_1h.2y.joblib` (or overwrite `_pooled_1h.joblib` after gate), `metadata.json`, `REPORT.md`

**Steps:**
1. On `.30`: `.venv/bin/python -m crypto_signal --config config.2y.toml train --json 2>&1 | tee artifacts/logs/train-2y-full-$(date +%F_%H%M).log`
2. This calls `train_barrier_model` → `build_barrier_dataset` → `fit_calibrated_model` (HistGradientBoosting) → strict holdout scoring → `write_json/write_text` + `joblib.dump`.
3. If OOM, halve `pairs_per_candle` to 2 or shard: train two pools (e.g., top-50 and next-45) and compare — do not silently reduce holdout fraction.

**Time budget:** Current 7-symbol run is minutes on a 16 GB host; 45-symbol 2-yr pool is ~4× rows → expect 10–30 min on a "huge" box, plus 5–15 min for calibration/backtest. TFT variant would be hours — out of scope.

**Verification:** Log contains `Barrier training finished | ... strict holdout ...`, `artifacts/models/_pooled_1h.joblib` + `metadata.json` updated, `REPORT.md` shows `Strict holdout` block.

### Task 9: Honest evaluation and gate

**Objective:** Decide whether the huge model ships.

**Files:**
- Read: `src/signal-ml/artifacts/models/metadata.json`, `src/signal-ml/artifacts/logs/*.log`, `src/signal-ml/tests/ml-engine/*` (if any)

**Steps:**
1. Compare strict holdout metrics (log-loss, PR-AUC, calibration) and backtest (Sharpe, max drawdown, hit rate) against the 7-symbol baseline stored in `artifacts/models/metadata.json.previous`.
2. Gate (suggestion): promote only if strict holdout log-loss ≤ baseline + 0.01 *and* backtest Sharpe ≥ 0 *and* no critical NaNs. Keep the previous bundle (`artifacts/models/archive/`) regardless.
3. Run: `.venv/bin/pytest tests/ml-engine -q` — must stay green; inference tests use the registry which loads whatever `*.joblib` is present.

**Verification:** Gate decision written as a one-line `PROMOTE: yes/no — reason` in `HANDOFF.md` and in the training log.

### Task 10: Promote to serving registry and wire the .NET side

**Objective:** Make the new bundle the one the API actually serves.

**Files:**
- Modify: `src/signal-ml/artifacts/models/_pooled_1h.joblib` (if promoted)
- Read: `src/signal-ml/src/crypto_signal_engine/application/registry.py`, `src/signal-ml/src/crypto_signal_engine/settings.py:ML_MODEL_DIR`, `devops/compose.yml`

**Steps:**
1. Registry loads every `*.joblib` under `ML_MODEL_DIR` (`artifacts/models`). If training moved sideways to `artifacts/models.2y/`, either copy promoted bundle into `artifacts/models/` or point `ML_MODEL_DIR` (Compose `env`) at the new dir and restart `signal-ml`.
2. Restart `signal-ml` container / systemd unit: `docker compose -f devops/compose.yml restart signal-ml` or `systemctl restart crypto-signal-ml`.
3. Verify: `curl http://127.0.0.1:8000/api/v1/ml/model?symbol=BTCUSDT&interval=1h` returns bumped `modelVersion` / `trainedAt` and `featureCount` matching the new metadata. Check `GET /health/ready` still 200.

**Verification:** `grpcurl` or `GET /api/v1/ml/capabilities` lists the new model version; dashboard shows it.

### Task 11: Backfill gap — sync artifacts back to the dev machine

**Objective:** Keep the build host and `.30` from diverging.

**Steps:**
1. If training ran remotely, `rsync -av 10.224.2.30:/path/src/signal-ml/artifacts/models/* ~/Desktop/project/crypto-signal/src/signal-ml/artifacts/models/` and same for `artifacts/logs/`.
2. Commit a pointer change if config was promoted: `git add src/signal-ml/config.2y.toml src/signal-ml/artifacts/models/metadata.json` — do **not** commit multi-MB `.joblib` unless LFS is configured (keep them in registry/host storage and in `artifacts/models/archive/`).

### Task 12: Document and hand off

**Objective:** Next agent starts with truth, not folklore.

**Files:**
- Modify: `Desktop/project/crypto-signal/docs/HANDOFF.md`
- Modify: `Desktop/project/crypto-signal/README.md` (if serving behavior changed)

**Steps:**
1. Append to `docs/HANDOFF.md`: window `[2024-09-08, 2026-09-08)`, universe list + filter rule, row counts, strict holdout metrics, gate verdict, bundle filename + version, host `10.224.2.30` resource snapshot, disk/RAM/time cost.
2. Note open follow-ups: per-symbol overrides for thin markets, 5 m pool in same window, TFT challenger on GPU if `10.224.2.30` has one, weekly retrain cron pointing at `config.2y.toml`.

---

## 4. Files likely to change

- `Desktop/project/crypto-signal/src/signal-ml/config.2y.toml` — **new**, the only config for this run (keep `config.toml` as 7-symbol baseline).
- `Desktop/project/crypto-signal/src/signal-ml/data/*_1h.csv` — new/updated per universe.
- `Desktop/project/crypto-signal/src/signal-ml/artifacts/models/_pooled_1h.joblib`, `metadata.json`, `REPORT.md`, `artifacts/logs/*` — training outputs.
- `Desktop/project/crypto-signal/docs/HANDOFF.md` — required update.
- `devops/compose.yml` / `devops/compose.dev.yml` — only if `ML_MODEL_DIR` changes (unlikely).

## 5. Tests / validation

- `src/signal-ml/.venv/bin/pytest src/signal-ml/tests -q` (or `tests/ml-engine` depending on layout) — must pass before and after promotion.
- `src/signal-ml/.venv/bin/python -m crypto_signal --config config.2y.toml --help` — config loads.
- `curl http://127.0.0.1:8000/health/ready` and `GET /api/v1/ml/model` — serving contract.
- Manual: `src/signal-ml/.venv/bin/python -m crypto_signal --config config.2y.toml train --json` — strict holdout reported, not training-set accuracy.

## 6. Risks, tradeoffs, and open questions

| Risk | Mitigation |
|---|---|
| **Universe too large → OOM / 10× fit time** | Filter to top-50/100 liquid; keep `pairs_per_candle=3`; shard only if host shows > 32 GB and still OOM. |
| **Survivorship bias from picking today's top-100** | Record the exchangeInfo snapshot date in metadata; future work can rebuild universe from 2024-09-08 rankings (needs historical listings archive). |
| **Stablecoin pairs pollute pooled distribution** | Exclude `USDC/USDT TUSD USDP USD1 RLUSD` explicitly. |
| **Host cannot reach Binance** | Download locally then rsync; or set `network.proxy_url=off` if host has direct egress. |
| **SSH to 10.224.2.30 still blocked** | **Open question — needs user:** correct SSH user/key or bastion. Host pings but rejects `maxi-srv.pem`. Provide `ssh -i <key> <user>@10.224.2.30` that works, plus `sudo` policy if Docker needs it. |
| **Creds in repo** | Do not commit `10.224.2.30` passwords or stable keys; use `~/.ssh/config` Host entry `nlp30` or env `SSH_KEY`. |
| **Joblib bloat in git** | Keep bundles out of git (add `artifacts/models/*.joblib` to `.gitignore` if not already). |
| **Window anchored to `end=""`** | Explicit `end` in `config.2y.toml` prevents the 2-year slice from drifting on reruns. |

**Open questions for you:**
1. Confirm SSH login for `10.224.2.30` (user + key path). Should I add a `~/.ssh/config` Host `nlp30` for the team?
2. Confirm universe: **A top-50, B top-100 (recommended), or C full 487**? And should we keep only `*USDT` spot (yes) vs include `*BTC`/`*ETH` quotes?
3. Keep `interval=1h` (recommended for the huge pooled baseline) or also build `5m` in the same window? 5 m is ~5× rows and needs tighter `pairs_per_candle`.
4. Should `10.224.2.30` become a permanent training runner (cron weekly on `config.2y.toml`) or is this a one-off huge run?

## 7. Quick effort sketch

```
Probe host (Task 2)              15 min  (blocked on creds)
Define universe + config.2y      20 min
Estimate RAM                      10 min
Download 45–95 × 17.5k candles   10 min  (plus retries)
Smoke BTC-only train              10 min
Full pooled train (30–60 min wall clock on huge box)
Gate + promote                   15 min
Sync + docs                      15 min
```

**Deliverable of this plan:** `src/signal-ml/config.2y.toml` plus a logged, gated `_pooled_1h` bundle from `10.224.2.30` that `GET /api/v1/ml/model` serves. If the host turns out not to be reachable, the same plan runs locally — slower, but identical — and can be rsynced to `.30` once access is fixed.

