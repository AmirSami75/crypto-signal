# Plan: Remaining Work — 2026-09-06 evening

**Baseline:** Phases 0–3 code-complete and live; Phase 6 challenger cycle closed (3 REJECTs, honest); scanner verified end-to-end (ticker → ScanSymbols → proposals → claim → intent → risk). Everything below is scoped to tonight; each task is independently committable.

---

## T4.2 — Per-strategy trade CSV artifacts (lumibot-style inspectable runs)

**Goal:** every league run leaves one CSV per (strategy, symbol, interval) so a human can audit individual trades, not just summary rows.

**Files:**
- `src/signal-ml/src/crypto_signal/evaluation/league_report.py` — after assembling the league JSON, walk the per-(strategy, symbol, interval) trade frames and write `artifacts/league/<stamp>/trades/<strategy>_<symbol>_<interval>.csv` (columns: entry_time, exit_time, direction, entry_price, exit_price, pnl_quote, pnl_atr, exit_reason).
- `src/signal-ml/src/crypto_signal/evaluation/league.py` — expose the per-pair decision/trade frames from `run_league` (they already exist internally; thread them into the return value instead of discarding).
- Test: `tests/ml-engine/test_league.py` — one synthetic run, assert CSV count == row count and columns present. RED → GREEN.

**Command:** `run-league --symbols BTCUSDT,ETHUSDT,SOLUSDT --intervals 1h,15m` (re-run after change), then commit CSVs for the latest stamp only (not history).

**Commit:** `feat(league): per-strategy trade CSV artifacts (T4.2)`

---

## T4.3 — Weekly Telegram league digest (cron, monitor.sh pattern)

**Goal:** every Monday after the league refresh, a Telegram message with the top-10 ranked strategies (TEST-split numbers + walk-forward verdicts).

**Files:**
- `scripts/league_digest.py` — reads the newest `artifacts/league/*.json`, renders a compact top-10 table (strategy, symbol, tf, trades, net%, verdict), prints it. Pure, no network.
- Cron: one-shot `hermes cron create` pinned to `b.ai/glm-5.3-flash`, deliver `telegram:429361464`, prompt runs the digest script and relays output. Schedule: Mondays 07:30 Tehran (after the 06:00 retrain).
- On AWS later: same script invoked from `monitor.sh digest` (already has the Telegram side).

**Verification:** run the digest script locally on the 20260905 artifact; fire a one-shot cron to confirm Telegram delivery.

**Commit:** `feat(league): weekly Telegram digest script (T4.3)`

---

## T5.1 — AWS deploy of the scanner + TFT deps

**Goal:** EC2 stack runs the same code incl. ScanSymbols RPC, scanner service, new migrations.

**Sequence (each step verified before the next):**
1. **Wheel-stage pytorch-forecasting + lightning** into `wheels/` via the working proxy (exact pins: `pytorch-forecasting==1.8.0`, `lightning==2.5.6` + transitive deps), extend `wheels/constraints.txt` — same pattern as the torch CPU wheel. AWS installs offline.
2. rsync repo to `/opt/crypto-signal` (exclude `node_modules`, `.venv`, `artifacts/league`, `wheels/*.whl` handled separately).
3. Rebuild images: `docker compose --profile aws build` — api **runtime** target (ImageSharp already removed), signal-ml picks up ScanSymbols + pf wheels.
4. `docker compose --profile aws up -d` → check `/health/ready`, `GET /api/v1/scanner` auth-walled, engine capabilities advertise `ScanSymbols`.
5. Migrations apply on api boot (ScannerSnapshotSync + BotAtrBrackets already in history on AWS? — verify `__EFMigrationsHistory` first; if the hand-written MarketScanner was applied there, reconcile before upgrading).
6. **Do NOT enable `Scanner:Enabled` on AWS yet** — proposals are useful but the AWS deployment has real keys in env; keep the scanner off until the operator decides. Report state honestly.

**Commit:** any compose/env adjustments as `chore(aws): scanner deployment support (T5.1)`.

---

## Optional (only if time remains) — Scanner polish

- ScannerSignal table growth: add cleanup of signals older than 7 days (simple DELETE in the scanner pass, keeps the table bounded).
- ScannerPage: show claimed signals toggle (currently hard-filtered to unclaimed).

---

## Explicitly deferred (needs you)

- **Testnet API keys** in `devops/env/dev/api.env` → only then can the scanner Sandbox bot pass `DataFreshness/SufficientBalance` and place an actual testnet order. Risk denial until then is correct fail-closed behavior.
- **Real-money anything** — unchanged standing gates.

## Order of execution

T4.2 → T4.3 → T5.1 (AWS last, it's the longest and most fragile over V2Ray). Each task: implement → verify → commit → report line in HANDOFF §4. Done by tonight.
