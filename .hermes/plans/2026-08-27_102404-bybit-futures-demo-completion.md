# Bybit Futures Demo and Leverage Completion Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Finish the Bybit USDT-linear demo integration and leverage infrastructure, verify it end-to-end with virtual funds, and preserve the existing Paper bots and live-money safety gates.

**Architecture:** Bybit demo is a separate `MarketVenue` using the official v5 demo host `https://api-demo.bybit.com`. It is available only as `Sandbox`; the existing Bitunix adapter must never claim Sandbox because Bitunix has no testnet. Leverage is explicit and auditable: bot configuration stores gross position notional and leverage, risk compares required margin (`notional / leverage`) against available collateral, while exposure limits continue to cap gross notional.

**Tech Stack:** .NET 10, EF Core/PostgreSQL, ASP.NET Core, HttpClientFactory, Bybit v5 REST/HMAC-SHA256, React/TypeScript/Vite, Docker Compose, Python gRPC ML engine.

---

## Current context and assumptions

- Repository: `/home/sudoix/Desktop/project/crypto-signal`
- Existing 1h and 5m bots must remain Paper unless explicitly and separately approved later.
- Global live execution remains disabled.
- Bybit public API was previously confirmed reachable for linear klines.
- Bybit code is partially present in the working tree but not yet fully verified end-to-end.
- API development container previously failed because of package restore/cache and model/snapshot mismatch. The current `compose.dev.yml` now routes NuGet through `host.docker.internal:10808`, mounts a persistent `api_nuget` volume, and the API was last observed healthy after recreation.
- Current uncommitted changes include Bybit venue, Bybit kline source, Bybit broker, leverage fields, risk changes, DTO/frontend changes, and migration files. Review the complete diff before committing; do not overwrite unrelated work.
- Development V2Ray/Xray proxy is configured on the host at port `10808` and must remain reachable from Docker. Avoid exposing it beyond the host/LAN unless firewall policy explicitly allows it.

---

## Phase 0: Establish a clean baseline before more edits

### Task 0.1: Review and classify the current diff

**Files:** all files shown by `git status`.

- Separate Bybit/leverage changes from unrelated pre-existing changes.
- Confirm no credential values, API keys, secrets, or connection strings are present in tracked changes.
- Inspect `git diff --check` and `git diff --stat`.

**Verification:** `git diff --check` passes; secrets scan finds no credential-like values.

### Task 0.2: Verify Docker/proxy baseline

**Command:**

```bash
cd devops
docker compose -f compose.yml -f compose.dev.yml config --quiet
docker ps --format '{{.Names}} | {{.Status}}'
```

**Acceptance:** compose parses; DB and ML are healthy; API is healthy; API can restore through the proxy. If API is unhealthy, fix container restore before continuing.

---

## Phase 1: Complete venue configuration and data plumbing

### Task 1.1: Finalize Bybit venue metadata

**Files:**
- Modify: `src/backend/src/CryptoSignal.Api/Domain/Enums/Trading/MarketVenue.cs`
- Modify: `src/backend/src/CryptoSignal.Api/Application/Options/ExchangeOptions.cs`
- Modify: `src/backend/src/CryptoSignal.Api/Application/Trading/MarketData/TradingHttpClients.cs`
- Modify: `src/backend/src/CryptoSignal.Api/Program.cs`
- Modify: `src/frontend/src/lib/apiTypes.ts`
- Modify: `src/frontend/src/i18n/fa.ts`

Confirm `Bybit` is mapped consistently to:

```text
https://api-demo.bybit.com
```

The named client must use the same timeout, User-Agent, proxy policy, and correlation behavior as other HTTP venues.

**Verification:** backend build and frontend typecheck pass; DI resolves exactly one HTTP client for Bybit.

### Task 1.2: Test-driven Bybit public kline adapter

**Files:**
- Modify/create: `src/backend/src/CryptoSignal.Api/Application/Trading/MarketData/BybitKlineSource.cs`
- Test: add the nearest existing backend market-data test project/file.

Test these cases:

- `5m` maps to Bybit interval `5`
- `1h` maps to `60`
- newest-first wire rows become oldest-first
- forming candle is excluded based on timestamps
- OHLC bounds are widened, never shrunk
- missing rows and gaps fault rather than padding/fallback
- Bybit business `retCode != 0` faults

**Verification:** focused tests pass, then backend test suite passes. Run one real public request through the API after the container is healthy.

### Task 1.3: Add Bybit instrument-rule resolution

**Files:**
- Modify: `src/backend/src/CryptoSignal.Api/Application/Trading/Instruments/InstrumentRuleProvider.cs`
- Test: instrument-rule tests.

Use `/v5/market/instruments-info?category=linear&symbol=BTCUSDT` and parse `priceFilter` and `lotSizeFilter`. Do not hard-code permissive grids. Ensure `status == Trading`, market orders are supported, and minimum notional is respected.

**Verification:** real BTCUSDT rule smoke test returns non-zero tick size, step size, minimum quantity, and minimum notional.

---

## Phase 2: Complete leverage domain and risk semantics

### Task 2.1: Persist leverage with safe defaults

**Files:**
- Modify: `TradingBot.cs`
- Modify: `OrderIntent.cs`
- Modify: `BrokerOrderRequest.cs`
- Modify: `TradingBotCfg.cs`
- Modify: `OrderIntentCfg.cs`
- Modify: `BotDtos.cs`
- Modify: `CryptoSignalDbContextModelSnapshot.cs`
- Create: EF migration for leverage fields if missing.

Rules:

- `Leverage` defaults to `1` for backward compatibility.
- Existing rows migrate to `1`.
- Spot and Replay bots must use exactly `1`.
- Bybit Sandbox may use integer leverage from `1` through the configured platform ceiling.
- No nullable or silently inferred leverage on order intents.

**Verification:** migration applies cleanly; existing bot rows read as 1; migration is idempotent in a fresh database.

### Task 2.2: Make risk leverage-aware and fail-closed

**Files:**
- Modify: `RiskSnapshot.cs`
- Modify: `RiskEngine.cs`
- Modify: `TradingRiskOptions.cs` if needed
- Modify: `BotController.cs`

Rules:

- `EstimatedNotional` remains gross exposure.
- `EstimatedMargin = EstimatedNotional / Leverage`.
- Balance check compares required margin for futures and remains unchanged for leverage 1.
- Exposure and max-notional checks continue to use gross notional.
- Reject leverage `< 1`.
- Reject leverage above platform cap.
- Reject zero/unset platform cap.
- Reject leverage other than 1 on spot/replay.
- Reject shorting unless the policy explicitly allows it.
- Record leverage and estimated margin in the serialized risk snapshot.

**Verification:** add tests for 1x, 2x, over-cap, zero-cap, spot-with-2x, insufficient-margin, and gross-exposure-over-limit cases. Confirm all existing risk tests remain green.

### Task 2.3: Validate bot configuration consistently

Use one shared validation path for create, update, and start. It must not be possible for the UI to accept a configuration that the start endpoint later interprets differently.

**Verification:** API integration tests cover invalid Bybit leverage, invalid spot leverage, zero limits, unsupported shorts, and missing credentials.

---

## Phase 3: Implement and harden the Bybit demo broker

### Task 3.1: Unit-test Bybit signing

**Files:**
- Modify/create: `BybitFuturesBroker.cs`
- Test: signing tests.

Signature input must be exactly:

```text
timestamp + apiKey + recvWindow + queryString_or_jsonBody
```

Use HMAC-SHA256 with the API secret. Query/body bytes must match the sent request exactly. Never log secrets or signatures.

**Verification:** compare a deterministic test vector against an independently computed expected signature.

### Task 3.2: Add explicit demo-only broker behavior

Bybit broker must claim only:

```text
Sandbox + Bybit
```

It must not claim Paper or Live. Paper is owned by the simulator. Live has no broker until all live-trading gates are implemented.

### Task 3.3: Implement order lifecycle safely

Required operations:

- signed demo balance read
- signed set leverage before an opening order
- market order placement with deterministic `orderLinkId`
- TP/SL fields with explicit `tpslMode` and order types
- reconciliation through `/v5/order/realtime` using `orderLinkId`
- ambiguous transport outcome must fault/reconcile, never blind retry
- demo position and closed-PnL reads for later verification

For close orders, ensure `reduceOnly=true` and do not reset leverage unexpectedly.

**Verification:** mock tests for 200/business refusal/4xx/5xx/timeout; no secret leakage; duplicate client ID is idempotent.

### Task 3.4: Add Bybit credentials safely

**Files:**:
- `ConnectionsPage.tsx`
- API connection DTOs/controllers if venue-specific validation is needed.

Bybit demo credentials must be entered by the user in the Bybit demo environment. Never ask the user to paste a secret into chat. Store encrypted at rest and show only a masked preview.

**Verification:** connection create/list/update never returns secret values or logs them.

---

## Phase 4: Dashboard and operations

### Task 4.1: Improve bot form for futures configuration

Add Persian-first fields and explanations:

- venue: Bybit Demo
- mode: Sandbox
- leverage
- gross position notional
- estimated margin preview
- max gross exposure
- short permission
- explicit warning that Bybit Demo keys are isolated from production keys

Disable or force leverage to 1 when a spot venue is selected. Display the effective platform ceiling.

### Task 4.2: Add leverage/margin to monitor and detail pages

Show:

- venue and operating mode
- leverage
- gross notional
- estimated/used margin
- available collateral when known
- liquidation data only when obtained from Bybit; otherwise show “not available”, never estimate silently
- model confidence/EV
- order and reconciliation state
- a clear Demo badge

Keep responsive behavior valid at 375px and preserve Latin digits.

### Task 4.3: Add demo lifecycle controls

Allow the operator to request demo funds only through an explicit action if the Bybit API supports it, with audit logging. Do not include any production fund or withdrawal operation.

---

## Phase 5: Verification and deployment

### Task 5.1: Build and migration verification

Pause the dev API container before host-side builds if its bind-mounted `obj/bin` can be rewritten. Then run:

```bash
cd src/backend
dotnet restore CryptoSignal.slnx --force
dotnet build CryptoSignal.slnx --no-restore --no-incremental
```

Expected: `0 Error(s)`.

Apply and verify migration in PostgreSQL:

```sql
SELECT "MigrationId"
FROM "__EFMigrationsHistory"
ORDER BY "MigrationId" DESC;
```

### Task 5.2: Public Bybit smoke test

Through the running API/container, verify:

- `BTCUSDT` linear 5m klines
- `BTCUSDT` instrument info
- contiguous closed candle window
- no fallback to Bitunix/Binance/Replay

### Task 5.3: Signed demo smoke test

Only after the user creates Bybit Demo credentials:

1. read demo balance
2. verify virtual collateral
3. set 2x leverage on BTCUSDT
4. place the smallest permitted virtual order
5. reconcile by `orderLinkId`
6. observe position
7. close with reduce-only order
8. read closed PnL
9. verify every record has `OperatingMode=Sandbox`, venue Bybit, leverage, and correlation ID

Do not use production Bybit keys or production host for this test.

### Task 5.4: Failure-injection tests

Prove:

- missing demo credentials faults/denies
- wrong host/environment is rejected
- Bybit timeout produces Ambiguous and stops further placement
- duplicate client ID does not create a second position
- stale/gapped candles fault before ML consult
- kill switch blocks order intent
- leverage over cap is denied
- spot 2x is denied
- Bitunix Sandbox resolves to no broker and cannot place
- Live mode remains denied

### Task 5.5: Full regression suite

```bash
cd src/signal-ml
.venv/bin/pytest ../../tests/ml-engine -q

cd ../../src/frontend
npm run typecheck
npm run rtl:audit
npm run build
```

Expected: existing ML tests remain green; frontend typecheck, RTL audit, and production build pass.

---

## Acceptance criteria

The work is complete only when all are true:

- API, DB, ML, and dashboard containers are healthy.
- API development package restore works from a fresh `api_nuget` volume through the host proxy.
- Bybit public 5m data works through the normalized API.
- Bybit rules are fetched from the venue, not hard-coded.
- Bybit demo signing passes independent test vectors.
- Bybit Demo credentials are stored encrypted and never exposed.
- A complete virtual order lifecycle is verified, or clearly blocked pending user credentials.
- Leverage is persisted, risk-checked, included in order payloads, and audited.
- Existing Paper bots remain untouched.
- Bitunix no longer maps Sandbox to production.
- Live execution remains disabled.
- All tests and builds pass.
- No real-money order is sent.

## Risks and tradeoffs

- Bybit demo availability and account/key creation may vary by jurisdiction and account status. Do not bypass restrictions or use production credentials.
- Bybit demo has API feature differences from production; document unsupported endpoints rather than silently approximating them.
- Leverage increases liquidation risk even in demo and must not be treated as a profitability improvement.
- The current model's 5m backtest was strongly negative on Bitunix due to fee-in-ATR economics. Bybit demo execution validates infrastructure, not strategy profitability.
- Do not lower thresholds or enable live mode merely because the Bybit demo order lifecycle works.
- Docker host proxy binding to `0.0.0.0` should be firewalled for production/shared networks.

## Final handoff

After implementation, report these separately:

1. compiled
2. public Bybit endpoint reachable
3. demo credentials verified
4. demo order lifecycle verified
5. leverage lifecycle verified
6. Paper bots unaffected
7. live-money execution enabled — expected to remain **No** until an explicit future safety review
