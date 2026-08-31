# crypto-signal — Project Handoff

> **Living document.** Every feature developed on this project MUST create/update this file at the end
> of the work: what changed, what was verified, what remains. The next agent (Hermes, Cline, OpenCode,
> Claude Code, or a human) starts here.
>
> **Last updated:** 2026-08-31 · **Branch:** `main` · **HEAD:** `6a49352`

---

## 1. What this project is

Autonomous crypto futures-trading platform:
- **Backend:** .NET 10 API (`src/backend`) — bots, decision engine, risk engine, venue brokers, auth/permissions, PostgreSQL.
- **ML engine:** Python gRPC service (`src/signal-ml`) — triple-barrier labeling, gradient-boosted bundles, experimental LSTM challenger, serving + self-learning loop.
- **Frontend:** React + Vite dashboard (`src/frontend`) — Persian/RTL, Latin digits, i18n in `src/frontend/src/i18n/fa.ts`.
- **Devops:** Docker Compose (`devops/compose.yml` + `compose.dev.yml`), V2Ray proxy bridge, socat relay.

## 2. Verified state (as of 2026-08-31)

| Area | State | Evidence |
|---|---|---|
| API container | Up, healthy | `docker compose ps` · `GET /health/ready` → healthy (db + python-ml) |
| Binance Futures Testnet venue | **Live in codebase, verified** | kline route 200 (96 candles, BTCUSDT close 78063.8); 15/15 broker tests |
| Bybit Demo venue | Live, verified | kline route 200 (regression) |
| Bitunix | LIVE-only broker; **Sandbox resolves to NO broker** (no testnet exists) | `BrokerResolver` single-owner check |
| ML suite | 349/349 pass | `pytest ../../tests/ml-engine` from `src/signal-ml/.venv` (18s) |
| Backend tests | 15/15 BinanceFuturesTestnet broker tests pass | `dotnet test --filter FullyQualifiedName~BinanceFuturesTestnet` |
| Frontend | tsc clean, RTL audit clean, prod build passes | `npx tsc --noEmit` |
| Working tree | Clean, everything committed | `git status --porcelain` = 0 |
| Proxy bridge | socat container `crypto-signal-proxy-1`: host `127.0.0.1:10808` → `0.0.0.0:10809`; containers use `host.docker.internal:10809` | in-container `fapi/v1/ping` via proxy → HTTP 200 |
| ML models | 1h tree bundle + 5m pooled serving; LSTM challenger (`_pooled_<interval>`, `is_sequence=true`) written but **experimental — never auto-promoted** | `src/signal-ml/src/crypto_signal/modeling/lstm.py` |
| Containers | api, dashboard, db, signal-ml, proxy — all up | `docker compose ps` |

## 3. Recent work log (newest first)

- **2026-08-31 — Binance Futures Testnet integration + LSTM challenger (E1)** — commits `afd5e5c`, `6a49352`
  - `BinanceFuturesTestnetBroker` (`/fapi/v1/order|leverage`, `/fapi/v2/balance`), Sandbox-only, shorts + explicit leverage, reduceOnly closes, HMAC-SHA256, credentials from connection → env fallback.
  - New `BinanceFuturesTestnet` venue end-to-end: enum, options, HTTP client, kline source (`/fapi/v1/klines`), instrument rules (`/fapi/v1/exchangeInfo`), DTOs, frontend types + i18n + BotDetail stats (leverage/notional/margin/available balance).
  - Proxy re-architected: socat bridge container (10809) instead of direct 10808; NU1900 `NoWarn`'d (vuln-data check unreachable from containers was failing restore).
  - LSTM challenger pipeline: `train-lstm` CLI, config `[lstm]` section, serving metadata `is_sequence`/`lookback`; honest holdout backtest, same cost-aware bar as tree model.
  - Fix `6a49352`: `lstm_pipeline` reads parsed `LstmSection`, not raw TOML dict.
- **2026-08-29 — M Engine page** — commits `02384d4`, `c7a9e85` — model metadata, confidence calibration, markets table.
- **2026-08-27/29 — Bybit demo adapter, leverage threading, proxy fixes, ML uniqueness weights** — commits through `0bf4808`.

## 4. Remaining work (next up)

1. **Binance Futures Testnet order lifecycle** (task p3e, in progress): user enters testnet API key/secret via **Connections page** → verify place → reconcile → close on a Sandbox bot. *This is the only step between the venue being code-complete and being usable.*
2. Futures instrument-rules coverage check for non-BTC symbols on `/fapi/v1/exchangeInfo`.
3. LSTM: needs to beat the tree bundle on purged-holdout, net-of-costs backtest before any promotion (gate in `docs/ml-improvement-plan.md`).
4. Before any real money (standing gates): bracket sweep → 4-week soak → manual approval → rotate the screenshotted Bitunix key → gateway running for retrain cron.
5. Minor: `BotDtos.cs` shows a duplicated `EstimatedNotional`/`EstimatedMargin` doc-block in the `afd5e5c` diff — worth a 2-minute glance; harmless today.

## 5. Environment quirks (read before building)

- **Pause before host builds:** the api container's `dotnet watch` rewrites host `obj/` with container paths within ~8s of any obj/bin deletion → host builds fail with NETSDK1064. `docker pause crypto-signal-api-1` before host builds, `unpause` after; clean `obj/bin` when switching host/container builds.
- **Dev login:** `cs-admin` — password is `AuthGlobalVariables.DefaultPassword` in `src/backend/src/CryptoSignal.Auth/Domain/Constants/AuthGlobalVariables.cs` (older passwords floating in notes are stale). Lockout after 5 failures → unlock via `UPDATE "Users" SET "IsLocked"=false, "FailedLoginAttempts"=0 WHERE "UserName"='cs-admin';` (db: user `crypto_signal`, db `crypto_signal`).
- **Health endpoint:** `/health/ready` (and `/health/live`) — plain `/health` is 404.
- **Charts API:** `GET /api/v{v}/charts/{Venue}/candles?symbol=…&interval=…` — venue segment is the enum name, e.g. `BinanceFuturesTestnet`. Requires Bearer auth.
- **Proxy:** all external exchange/NuGet traffic goes through host V2Ray (`127.0.0.1:10808`) → socat bridge → containers (`host.docker.internal:10809`). Internal services (db, signal-ml) bypass via NO_PROXY. socat listens on `0.0.0.0:10809` on the host — LAN-open relay, by design.
- **Compose:** always both files — `docker compose -f devops/compose.yml -f devops/compose.dev.yml …`.
- **Safety invariants (non-negotiable):** risk limits fail-closed; zero limits refuse bot start; kill switches block order intents + audit; no silent venue fallback (unreachable venue faults bot); positions scoped per bot; every record stamps `OperatingMode`; decisions idempotent by `(BotId, CandleOpenTime)`; LIVE has **no broker by design** until gates 6–8 of `docs/LIVE_TRADING_SAFETY.md` are implemented.
- **Secrets:** never persist credentials/keys/passwords in docs, logs, or summaries → `[REDACTED]`.

## 6. Where things live

| Thing | Path |
|---|---|
| Brokers | `src/backend/src/CryptoSignal.Api/Application/Trading/Brokers/` |
| Kline sources | `src/backend/src/CryptoSignal.Api/Application/Trading/MarketData/` |
| Risk engine | `src/backend/src/CryptoSignal.Api/Application/Trading/Risk/` |
| Backend tests | `src/backend/tests/CryptoSignal.Tests/` |
| ML models/training | `src/signal-ml/src/crypto_signal/{modeling,training}/` |
| ML tests | `tests/ml-engine/` |
| i18n (Persian) | `src/frontend/src/i18n/fa.ts` |
| Compose / env | `devops/compose*.yml`, `devops/env/dev/` |
| Plans | `.hermes/plans/`, `docs/AUTO_TRADING_PLAN.md`, `docs/FUTURES_LEVERAGE_PLAN.md`, `docs/LIVE_TRADING_SAFETY.md`, `docs/ml-improvement-plan.md` |

---

### Changelog rule
When you finish a feature: add a dated bullet to §3, update §2 evidence table rows you touched, move items between §4 (remaining) and §3 (done), and bump the "Last updated / HEAD" stamp above. Keep it honest — unverified claims do not go in §2.
