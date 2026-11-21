# crypto-signal — Project Handoff

> **Living document.** Every feature developed on this project MUST create/update this file at the end
> of the work: what changed, what was verified, what remains. The next agent (Hermes, Cline, OpenCode,
> Claude Code, or a human) starts here.
>
> **Last updated:** 2026-11-21 · **Branch:** `main` · **HEAD:** see `git log` — local-only environment;
> clean DB + fresh Binance Futures **testnet** connection; one wildcard **scanner bot**
> (`binance-demo-scanner-5m`, Sandbox, 5m, 10 USDT/trade, TP 2 ATR / SL 1 ATR) trades the whole market
> on a real venue. First sandbox round trip closed: FETUSDT short, entry 0.1075 → exit 0.1074,
> **+0.0013 USDT net**. Two broker defects found and fixed on the way (priceless RESULT responses,
> closing orders refused by the side guard). Nothing committed since `f879b66`.

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
| ML suite | 398/398 pass | `pytest ../../tests/ml-engine` from `src/signal-ml/.venv` (22s; includes 13 MTF feature tests) |
| Backend tests | 15/15 BinanceFuturesTestnet broker tests pass · `dotnet build` 0 errors | `dotnet test --filter FullyQualifiedName~BinanceFuturesTestnet` |
| Frontend | tsc clean, RTL audit clean, prod build passes | `npx tsc --noEmit` |
| Working tree | Clean, everything committed | `git status --porcelain` = 0 |
| Proxy bridge | socat container `crypto-signal-proxy-1`: host `127.0.0.1:10808` → `0.0.0.0:10809`; containers use `host.docker.internal:10809` | in-container `fapi/v1/ping` via proxy → HTTP 200 |
| ML models | 1h tree bundle + 5m pooled serving; LSTM challenger (`_pooled_<interval>`, `is_sequence=true`) written but **experimental — never auto-promoted** | `src/signal-ml/src/crypto_signal/modeling/lstm.py` |
| Containers | api, dashboard, db, signal-ml, proxy — all up | `docker compose ps` |

## 3. Recent work log (newest first)

- **2026-11-21 — visual pass: the dashboard reads like a trading terminal**

  Design-system upgrade (ui-ux-pro-max `--design-system` on "crypto trading dashboard dark data
  dense", dials density 8 / motion 5), applied at the token + primitive layer so every page inherits it.

  - **Palette.** Dark ground moved from neutral grey (#17191c) to a cool, deep navy (#070b12) with
    layered surfaces (#0d141e / #121b27 / #172130) and cool hairlines; brand nudged to #2f8fff and
    success to #2ee0a5 so profit reads as light rather than as a green sticker. Light keeps a white
    panel on a barely-cool ground (#f6f8fb). `--ink-faint` on light was **3.36:1** — under AA — and is
    now #6f6f74 (4.9:1).
  - **Backdrop.** New `.app-aurora` layer: two wide radial washes (brand from the trailing corner,
    emerald from the leading one) plus a 72px hairline grid masked to the top, `pointer-events: none`
    and `aria-hidden`. Applied to the dashboard shell and the sign-in shell, so the product's tone is
    visible before authentication.
  - **Panels.** `Card` now renders `.panel`: hairline + a one-pixel inset top highlight (a lit bezel)
    and a subtle vertical gradient, radius 16px. New `interactive` prop adds lift-on-hover. Stat
    values moved to `.stat-value` (28px, tabular, `-0.02em`) and the tone bar became a vertical bloom
    instead of a solid stripe.
  - **Tables.** `.data-table`: sticky `thead` with an 8px backdrop blur, zebra as a tint instead of a
    stripe, whole-row hover lit with 8% brand, row hairlines that stop at the last row.
  - **Shell.** Sidebar and drawer are translucent with `backdrop-blur-xl`; the active nav entry carries
    a `nav-rail` gradient marker on the leading edge; the mode badge in the header gained a breathing
    `.live-dot` (disabled under `prefers-reduced-motion`); the operating-mode readout is now a lit
    inset panel.
  - **Bug found by exercising the surface.** `isSessionShape` never validated `fullName`, which
    `UserMenu` calls `.trim()` on — a stored session from an older build (or a hand-edited one) passed
    the check and crashed the whole layout into the error boundary. It is now required, so a stale
    session signs out instead of white-screening.
  - **Verified in the real browser** (1440/768/375, both themes): 18 panels and 12 nav entries render,
    aurora and nav marker present, sticky+blurred table headers on `/scanner` and `/bots`, no horizontal
    overflow at any width, contrast on both palettes — ink 16.8/19.8, muted 7.5/6.3, faint 4.8/4.9,
    accent 10.7/5.7, success 13.1/5.4, danger 8.5/6.5 (all ≥ AA). `npm run check` (typecheck + 77-file
    RTL audit) and `npm run build` pass.

- **2026-11-21 — clean slate + first live sandbox bot on Binance Futures testnet**

  The DB was wiped (schema dropped, rebuilt by migrations + seeders: 20 tables, 6 migrations, 1 user,
  2 roles, 42 permissions; pre-wipe dump at `~/crypto-signal-db-backups/pre-wipe-20261121-111024.dump`)
  and the trust in the old trading book went with it: 152 scanner proposals on the first pass, zero bots.

  - **Connection:** user supplied a fresh `Bianance-Demo-Future` key. Signed `/fapi/v2/balance` → 200,
    **5,000 USDT + 5,000 USDC + 0.01 BTC available**. The old Bitunix demo key authenticated but its
    futures account was empty on every margin coin (and Bitunix publishes no demo API at all — the app's
    50,000 USDT virtual account is unreachable from a key), so this venue is now the operational one.
  - **Bot:** `binance-demo-scanner-5m` — Kind=Scanner, wildcard `*`, BinanceFuturesTestnet, Sandbox, 5m,
    10 USDT/trade, leverage 1, TP 2.0 ATR / SL 1.0 ATR (percent fields 0.6/0.3 as fallback only),
    max 1 position, max daily loss 10, 30 orders/day. Created and started through the API (not SQL) so
    the config went through its own validation.
  - **Account must be in Hedge Mode.** The adapter always sends `positionSide` (LONG/SHORT); a one-way
    account rejects every order with `-4061 Order's position side does not match user's setting`. Set
    `dualSidePosition=true` on the testnet account once; from then on orders are accepted.
  - **Defect 1 — priceless fills.** The synchronous RESULT response can report `executedQty > 0` with
    `avgPrice` **and** `cumQuote` both `0.0000000`. The parser only synthesised a fill when it had a
    price, so no fill row was built: `BotPositions` stayed empty while the venue held a real FETUSDT
    short (93 @ 0.1075). Fixed twice: `cumQuote / executedQty` as a first fallback, and a follow-up
    `GET /fapi/v1/order` when both are zero (POST only, so the reconcile cannot recurse).
  - **Defect 2 — no close could ever be sent.** The adapter rejected any order whose side was the
    opposite of its direction, which is exactly the executor's close shape (position direction + opposite
    side). Every stop-loss exit died with "the futures order side does not match the intended position
    direction". The guard is gone; `reduceOnly` is never sent (Hedge Mode rejects it, and
    `positionSide` + side already express the reduction). `positionSide` for `TradeDirection.Flat` is BOTH.
  - **Verified end to end on the venue:** scan (250 symbols → 152 proposals) → claim → decision
    (FETUSDT short, confidence 0.50) → risk allowed → order accepted → position row written → next candle
    touched the stop → exit order **filled** → position closed. Real numbers: entry 0.1075, exit 0.1074,
    gross +0.0093, fees 0.0080, **net +0.0013 USDT**, reason `stop_loss_touched`. The second trade
    (BERAUSDT short 133.3 @ 0.075) opened with its fill priced, i.e. the fix holds on the entry path too.
  - **Tests:** backend `BinanceFuturesTestnet` 20/20 (three new: priceless RESULT, close shape accepted,
    Flat order omits reduceOnly). `FakeHttpMessageHandler` now supports per-method scripting
    (`Respond("GET", path, …)`), which the follow-up test needs.
  - **Reconciled by hand** (the two defects predate their fixes): `BotPositions` rows written/closed from
    venue truth and `ExchangeOrders.AverageFillPrice` backfilled. No further divergence is expected now.
  - **Wildcard symbol reaching the charts endpoint.** A scanner bot's symbol is `*`, and the monitor's
    price panel passed it straight to `/api/v1/charts/{venue}/candles`, so the venue answered
    `400 (Bad Request)` and the card showed that raw text. `LivePriceCard` now charts the market the bot
    actually holds (`openPositions[0].symbol`) and falls back to BTCUSDT while flat; the overview's
    `MarketPulse` does the same for `*`. The endpoint also refuses `*` up front with a clear message
    instead of relaying the venue's 400 and a 500 stack trace. `npm run check` (77 files) and
    `npm run build` both pass.

- **2026-11-10 (11:40–12:15) — one bot on the Bitunix demo account**

  Every bot was retired (soft-deleted, 8 of them) and a single scanner bot now runs the Bitunix demo
  connection: venue Bitunix, mode SANDBOX, wildcard `*`, 5m, 5 USDT per trade, shorts allowed. Making that
  possible needed three things the venue never had:

  - **Bitunix could not claim SANDBOX** — `Supports` was `Live`-only, so a demo bot resolved to no broker
    and faulted. Bitunix publishes no separate demo host (a demo key authenticates against the same
    `fapi.bitunix.com`), so Sandbox now resolves to the same adapter; the live gate stays in the risk layer.
  - **Bitunix had no instrument rules**, and the provider throws for a venue it cannot ask — so no intent
    was ever built (silently: the tick just ended). Added `FetchBitunixAsync`, which indexes the public
    `trading_pairs` listing (794 contracts, cached 6h) and derives the grid from `basePrecision` /
    `quotePrecision` (`10^-n`), with `minTradeVolume` and `maxMarketOrderVolume` as the quantity bounds.
  - **The order body was missing `tradeSide`**, which Bitunix requires to tell an opening order from a
    closing one; it answered `10002 Parameter error`. Now sends `tradeSide` (OPEN/CLOSE from side vs
    direction) and `effect` (`IOC` for market).
  - **The balance check only covered buys**, so a futures SHORT — which reserves margin exactly like a
    long — shipped with 0 available and was refused by the venue instead of by us. `CheckSufficientBalance`
    now checks any order that opens exposure.
  - Current blocker, honestly: the demo account reports **0 available USDT**, so every proposal is denied
    locally with `SufficientBalance: available balance 0 is below the required margin ~4.98`. The wiring is
    proven up to the venue boundary (signature accepted, parameters valid); the account needs funding.

- **2026-11-10 (10:20–10:50) — restart after power-off; the close path had never worked**

  The machine came back from an unclean shutdown. `db` recovered from WAL, `api` needed a
  `docker restart` (its `dotnet watch` had exited when Postgres was down), and the league campaign had
  already finished at its 23:55 deadline (`FINAL.md`, 1,398 rows). Bringing the stack up exposed four
  more defects, all on the exit path:

  - **Every close violated a check constraint.** `ApplyToPositionAsync` set `Quantity = 0m` on the closed
    position, but `CK_BotPositions_Quantity_Positive` requires `Quantity > 0` — so the save always threw
    `23514`, the tick ended, and the position stayed `Open` while the venue-side fill was already
    recorded. Fixed by keeping the closed size (status says "closed", not a zeroed quantity). Verified:
    ZKUSDT now settles at exit 0.00919, realized **−0.1896 USDT**, reason StopLossTouched.
  - **A close was denied by its own exposure limit.** `CheckExposure` counted the closing order against
    `MaxConcurrentPositions`, so a bot at its cap could open but never flatten. `RiskSnapshot` now
    carries `ReducesExposure` (side opposite the direction) and the check returns early for it.
  - **A stranded intent left the book wrong.** If a tick dies between "venue filled it" and "position
    saved", the intent stays `Submitted` and the position stays open on a flat book. Added
    `SettleStrandedIntentsAsync`, called at the start of every tick before the already-evaluated
    shortcut: it finishes the position from the recorded fill and marks the intent `Filled`. That is what
    actually settled ZKUSDT.
  - **Paper mode refused every SHORT.** `PaperBroker` refused shorts with a "every venue is spot" comment
    that is false for the futures venues — so every scanner SHORT proposal was rejected in paper. Now only
    spot venues refuse.
  - **The learning loop could not write.** `artifacts` is mounted `:ro` while `ML_TRADE_SAMPLES_PATH`
    pointed inside it — the whole online-learning store silently failed with `Read-only file system`.
    `compose.dev.yml` now mounts `artifacts/online` as its own writable volume (the rest stays ro) and
    sets `ML_CALIBRATION_PATH` explicitly. Verified: a real closed trade now stores a sample.
  - Exit decisions are booked on the **tick's** candle, with an existence check: booking on the candle
    that originally touched the level collided with the `(BotId, CandleOpenTime)` unique index and killed
    the scheduler cycle.
  - Tests: backend **44 pass**; ML **453 pass**.

- **2026-11-09 (18:40–19:05) — wildcard bot could not price a fill, and could not exit**

  Three silent defects, all on the wildcard (`Symbol = "*"`) scanner path, found by watching one real
  paper trade end to end:

  - **Rules were resolved for the bot's symbol, not the market's.** `GetRulesAsync(bot.Venue, bot.Symbol)`
    asked the venue about `*`. Binance answered BTCUSDT's grid, so a 0.2341 FRAXUSDT entry quantised onto
    a 0.10 tick and filled at **0.30**, and a 156-unit order was refused a 120-unit cap that belonged to
    BTC. Fixed in two places: the executor resolves rules for `decision.Symbol`, and
    `InstrumentRuleProvider` now detects that the venue ignored the `symbol` filter (Binance's futures
    testnet does, answering with its flagship pair) and resolves from a cached full listing instead of
    silently borrowing the wrong instrument. Verified live: ZKUSDT opened at **0.00925** (market price),
    2164 units, 20 USDT notional. 3 new tests in `InstrumentRuleProviderTests.cs`.
  - **A scanner position could never close.** `RunScannerBotAsync` returned `Hold` whenever a position was
    open; nothing emitted `BotDecisionAction.Close` anywhere in the codebase. Added
    `EvaluateScannerExitAsync`: tests the last closed candle against the position's own bracket, stop first
    when one candle touches both (an ambiguous bar must not book the better outcome), plus
    `max_holding_periods_reached`. Verified live: the open position is now managed
    (`position open; no exit level touched`) instead of skipped.
  - **Outcome reporting named the wrong market.** `ReportTradeOutcomeAsync` sent `bot.Symbol` (`*`) and the
    bot's configured percentages rather than the ATR bracket actually traded — so even a closed trade
    would have taught the calibrator about a market that does not exist. Now sends `position.Symbol` and
    the bracket implied by the position's own TP/SL.
  - **Quantity cap moved into sizing:** `BuildIntent` clamps to the venue's `MARKET_LOT_SIZE.maxQty`
    before quantising, so a large order is reduced rather than denied by the risk layer.
  - Tests: backend **44 pass** (41 previous + 3 new), ML **453 pass**. Position book reset once because the
    three rows created before these fixes carried a `*` symbol and a wrong entry price.

- **2026-11-09 (18:20–18:40) — fast learning loop + scanner deadline + campaign watchdog**

  - **Per-trade calibration (`online_calibration.py`).** After every closed trade the engine re-prices
    the decision that opened it (the outcome RPC already carries the candle window and the bracket, so
    no wire change was needed), stores `(predicted confidence, won)` per `SYMBOL|INTERVAL`, and — once a
    market has 60 resolved trades — applies a binned, shrunk, **isotonic** map to `p_win` before the
    candidates are priced. Loss/timeout mass is scaled so every row still sums to 1. Curves are refit on
    load from a JSON store (`ML_CALIBRATION_PATH`, default `artifacts/online/calibration.json`), so a
    restart does not forget the market. Verified by `tests/ml-engine/test_online_calibration.py` (9
    tests: readiness threshold, flat-curve rejection, monotonicity, row normalisation, and a
    `choose_direction` case where the correction turns a qualified bet flat). Full ML suite: **450 pass**.
  - **Scanner deadline scaled to the listing.** Every pass since ~18:00 failed with
    `DeadlineExceeded`: the market-wide scan shared the interactive 10 s gRPC budget while the league
    campaign saturated the CPU. `ScanSymbolsAsync` now takes a per-call deadline and `ScannerOptions`
    exposes `ScanDeadlineSeconds` (180). Verified live: pass `01a1c0d3` → **19 signals from 248 symbols,
    19 model-priced, 19 with a points head, ~25 s**. Before the fix: four consecutive cycle failures.
  - **Campaign survives the session (`scripts/model_league/watchdog.sh`).** The runner is resumable; the
    watchdog restarts it every 2 min if absent and stops at the same 23:55 deadline. It was needed: both
    earlier launches died with their parent shell. Running detached under `setsid`.
  - **`scripts/status_board.sh`** — one read-only screen (containers, health, last passes, league rows,
    calibration markets) for whoever picks the box up next.
  - Still open: the order path after risk (testnet key 401), and no closed trades yet — so the
    calibration store is legitimately empty and the loop is test-verified, not live-proven.

- **2026-11-09 (evening) — model league campaign (runs until 23:55)**
  - New harness `src/signal-ml/scripts/model_league/` (`core.py`, `candidates.py`, `runner.py`): 14
    candidates — prior baseline, logistic, ridge on R, Gaussian NB, decision tree, random forest, extra
    trees, HGB classifier + R head, LightGBM ×2, XGBoost ×2, MLP on R — over one shared barrier dataset.
  - Scoring: purged chronological 70/15/15 by timestamp, holdout scored once, ranked at a **4.5 / 3.0
    ATR** bracket (fee ≈ 0.2R) with the production **1.5 / 1.0** bracket reported alongside; fees
    10 bps + 5 bps slippage per side are subtracted per trade. Zero-trade models are ranked last with a
    ⚠, not as winners.
  - Resumable by construction: one forked process per candidate with a per-model timeout, append-only
    `artifacts/model_league/results.jsonl`, `REPORT.md` regenerated after every model, Telegram digest
    every 90 min. Restart skips rows that already exist.
  - First split (1h · seed 42, 7 symbols) — every family is **negative after fees**; best was the R head
    `hist_gb_r` at **−0.134 R/trade over 14,884 trades**, `mlp_r` −0.134, `lightgbm_r` −0.133; the
    prior baseline −0.149; classifiers with zero trades ranked last. The honest finding is the fee drag,
    not a winner: gross expectancy is ~0 while fees cost ~0.2R per trade at this stop.
  - Campaign command (still running): `python -m scripts.model_league.runner --until 23:55 --intervals
    1h,5m --seeds 42,7 --symbols-5m BTCUSDT --digest-minutes 90`. Log:
    `artifacts/model_league/campaign.log`.

- **2026-11-09 (later) — live scanner bot + professional desk page**
  - **5m bundle retrained with the points head** (`config_5m.toml` at cv_splits 3 / max_iter 180, BTCUSDT,
    382 s). Holdout: log loss 0.6859, balanced accuracy 0.4068, points Spearman **−0.0098**, expectancy
    at the zero threshold **+0.048R** (95 % lower bound +0.043) over 181,932 rows. The positive mean is
    the barrier geometry, not ranking skill — no edge claim. Copied to `artifacts/models/` (old bundle
    archived); engine serves it (`version=d0d2ba384510`) and reports `points_available=true`.
  - **Wildcard scanner bot made operational** (`scanner-test rsi 5m`, Kind=Scanner, Symbol=`*`,
    BinanceFuturesTestnet Sandbox, $20/trade, 2×): start gate now accepts `*` for Scanner bots; the tick
    reads its clock window from BTCUSDT and the claimed market's own price after the claim; it claims the
    **highest-scoring** unclaimed proposal (not the oldest), only within `ScannerMaxSignalAgeMinutes`
    (30) and `ScannerMinimumScore` (0.05R in dev), and only for symbols the risk allowlist permits.
    Repeated ticks no longer re-record the same candle, and a no-op advances `LastTickAt`.
  - **Risk provenance fixed for wildcard bots:** the allowlist / kill-switch symbol checks and the order
    intent now use the **decision's** symbol, not the bot's `*` placeholder. Before the fix every scanner
    order was denied with `SignalProvenance: the intent is for * but the bot trades ARBUSDT`; after it the
    only remaining denial is the balance.
  - **Broker diagnostics:** a non-200 balance read now logs status + a 240-char body excerpt instead of
    returning null silently. First honest reading: `status=401, {"code":-2015,"msg":"Invalid API-key, IP,
    or permissions for action"}` — the stored `Demo-Binance` testnet key is dead.
  - **Dashboard:** new `/desk` page (`DeskPage.tsx`) — live pill + served-model stamp, 5 KPI tiles,
    top-12 opportunity board (signed score in R, confidence, strategy, ATR, age), bot fleet cards with an
    audit timeline, and a merged live event feed; 15 s refresh, per-source error banners, skeletons.
    `npm run check` (typecheck + RTL audit, 77 files) and `npm run build` both exit 0.
  - **Verified this round:** ML 441 passed · backend 41 passed · frontend check+build clean · scanner pass
    **249 symbols → 21 model-priced proposals** · bot claimed `model Long TRADOORUSDT`, built an intent,
    and was denied by the risk engine **only** on `DataFreshness,SufficientBalance` (the dead key). The
    order path downstream of risk is therefore unproven until the key is replaced.

- **2026-11-09 — Points (R-multiple) objective + all-symbol scanner (uncommitted)**
  - **Labels:** every barrier variant now carries `r_multiple` — `+risk_reward_ratio` on a take-profit,
    exactly `-1` on a stop, `timeout_return_atr / stop_loss_atr` on a timeout. Kept beside the 3-class
    `target`, never in `feature_columns` (`labeling/triple_barrier.py`).
  - **Points head:** `train` fits a `HistGradientBoostingRegressor` on realized R with the same features
    and folds, scores it once on the strict holdout, stores it as `points_model` in the bundle and
    records MAE / Spearman / top-decile R / `expectancy_at_threshold` (with a one-sided 95 % lower
    bound) under `metadata.bundles[].points` (`modeling/estimator.py`, `training/barrier_pipeline.py`).
  - **Serving:** `ModelRegistry` loads `points_model` when present (`has_points` on the descriptor;
    `None` on every pre-points bundle, verified by restarting signal-ml against the existing bundles).
    `choose_direction` ranks by expected points when the head exists and enforces
    `minimum_expected_points`; the ATR expected-value rule remains for bundles without one. A broken
    head logs and degrades instead of refusing the request. Wire: `points_available` + `expected_points`
    on `GetSignalResponse` / `EvaluateBotDecisionResponse` / `ScanSymbolResult`.
  - **Gate:** the reject branch now moves the candidate to `rejected/`, restores the pre-run snapshot of
    every managed bundle, and restores `metadata.json` so the next gate compares against the incumbent
    instead of the rejected candidate (`scripts/self_learning_loop.py`).
  - **All-symbol scanner:** candle fetch is a bounded fan-out (`MaxConcurrency`, default 8), the symbol
    list is filtered to uppercase tickers (Binance lists non-ASCII names the engine's contract cannot
    address), and `ScanSymbolsRequest.model` asks the engine to price every symbol in the same call.
    A model row replaces the zoo duplicate for that symbol; `StrategyKey="model"`, `Score` = expected
    points when a head exists, else calibrated confidence.
  - **Verified:** 441 ML tests + 41 backend tests pass; a smoke `train` on BTC 1h wrote a bundle with
    `points_model` (holdout Spearman 0.034, expectancy −0.003 R over 21,506 trades — the 1h edge is still
    absent, now measured in the metric that matters); a live pass scanned **248 symbols** and recorded
    **28 model-priced proposals** at confidence ≥ 0.50 in ~90 s.
  - **Not done yet:** the 5m bundle (what the scanner trades) predates the head, so every model row
    reports `points_available=false` until it is retrained; bot decision DTOs/UI do not surface
    `expected_points` yet; the fast per-trade calibration loop is still the LSTM-v2/50-sample design.

- **2026-11-09 — AWS retired; local stack is now the operational environment**
  - All three images rebuilt from a clean daemon (no cached images): `signal-ml`, `api`, `dashboard`;
    `db` on postgres 18.3-alpine, `proxy` (socat 10809) reused. `docker compose ps` →
    api/dashboard/db/signal-ml/proxy all up, api + ml healthy.
  - **Verified live:** `GET /health/ready` → healthy (postgres + python-ml, `mode=PAPER, markets=3`);
    `cs-admin` login → token; `GET /api/v1/bot` → 8 bots; `GET /api/v1/ml/model?symbol=BTCUSDT&interval=1h`
    → 200 (`trainedAt 2026-11-09T02:40:33Z`, 42 features); dashboard `:5173` → 200 (Persian title).
  - **Scheduler + scanner running:** `Bot scheduler started … polling every 10s`; scanner first pass
    `7 signals from 20 symbols, 5 strategies each`, 7 `ScannerSignals` rows written (verified in SQL).
    All 8 existing bots are Stopped (4) or Faulted (5) from stale September faults — no ticks yet.
  - **Infra fixes needed for this host (uncommitted):**
    - `devops/compose.dev.yml`: db publishes on **127.0.0.1:55432** (host 5432 belongs to Hindsight's
      embedded Postgres, `--network host`); build steps no longer use `network: host` (Docker 29 refuses
      it without a `network.host` entitlement that compose cannot grant) — the signal-ml build reaches
      the V2Ray relay via `host.docker.internal:10809` through the socat `proxy` service instead.
    - `.dockerignore`: exclude `src/signal-ml/research_lab` (35 GB), `checkpoints`, `lightning_logs`,
      `tmp`, `**/.venv` — the build context was transferring >14 GB before it was cut.
  - **Honest state of the served model:** the 06:00 weekly retrain REJECTed (`metadata.json.previous`
    carries `promoted: false`), but the reject branch still archives nothing and restores nothing, so
    `artifacts/models/_pooled_1h.joblib` + `BTCUSDT_1h.joblib` are the **rejected candidate**; the
    pre-overwrite pair sits in `archive/20261109T02{3858,4033}_pre-overwrite_*`. Not restored — flagged
    for a decision, because every weekly candidate has been left live, so `archive/` also holds
    previously-rejected bundles and "the incumbent" has no clean definition yet.
  - Binance futures reachable through the proxy again (`/fapi/v1/klines` 200, weight 1) — the September
    429 faults are stale, not an outage.

- **2026-09-06 (evening) — TFT smoke run completed end-to-end; both challengers gated**
  - Machine rebooted mid-session (tmpfs wiped — logs now under `src/signal-ml/tmp/`, reboot-safe path). All containers restarted healthy.
  - **Memory fix**: stride-1 TFT training (350k windows × 24 × 46) OOM-killed the 15GB host. New `[tft].stride` config: emit a window every Nth candle — adjacent windows share `lookback−1` bars, so stride 4 discards almost no signal while cutting RAM 4×. 350k → 26k windows.
  - **Five PF-1.8 fixes** (`f637b31`): `time_varying_known_reals` plural rename; `stop_randomization`; string series ids; `QuantileLoss(quantiles=cfg)` (default 7 levels silently misaligned the 5-level CDF); predict via `tft.predict(mode="quantiles")` + per-row monotone projection for quantile crossing.
  - **Smoke result (BTCUSDT 1h, 2y, stride 4)**: holdout log-loss **4.19**, net **−26.5%** vs B&H +12.0% → **gate REJECT**, incumbent untouched. Honest diagnosis: the label-space proxy target (quantiles over {0,1,2}) is nearly uninformative — a continuous-return target is the next lever. Both fixes and the diagnosis are in `ml-improvement-plan.md` §Challenger results (`fab7495`).
  - `train` CLI now archives any existing bundle to `archive/<stamp>_pre-overwrite_…` before overwrite (`d435e3a`) — last night's manual incumbent recovery can't be needed again.

- **2026-09-06 (later) — MTF challenger trained and REJECTED by the gate; three trainer bugs fixed**
  - **Trainer fixes** (`b50bcdc`): `mtf_context=true` had silently produced plain 42-feature models three ways — `download_mtf_context_frames()` was documented but never written (higher_frame always None); `_label_one_symbol` diffed columns against a frame the in-place attach had already mutated (diff always empty → `KeyError(())`); `df[tuple]` single-key lookup instead of `df[list]`. Also the holdout backtest rebuilt features without the MTF join and scored with base columns → `not in index`. All fixed; 425/425 tests.
  - **Real MTF run**: all 7 symbols attached `h4_trend_ema_ratio`, `h4_atr_pct`, `h4_close_vs_ema20` (features 42→45). Pooled strict holdout log-loss **0.7968** (incumbent 0.7959), holdout bracket expectancy **−0.4277 ATR over 113 trades** (incumbent −0.122). **Gate: REJECT** on both metrics — the H4 confluence features carried no incremental edge at 1h. Challenger archived under `rejected/_pooled_1h_mtf_20260906_logloss0.7968_edge-0.4277.joblib`.
  - **Operational note**: the bare `train` CLI overwrites bundles in place (unlike `self_learning_loop.py`, which archives first). The plain-42 incumbent was re-trained with `mtf_context=false` to restore the serving artifact; scores logged in `/tmp/restore_train.log`. TODO: make the `train` CLI archive-or-gate like the loop.
  - Honest takeaway: three independent edge attempts (bracket sweep 120 configs, weekly retrain data refresh, MTF context) all REJECT. The 1h pooled model's edge is not recoverable by inputs available to it; a different horizon or label definition is the remaining lever.

- **2026-09-06 — Plan Phases 1–3 + 6 implemented: scanner end-to-end, TFT challenger staged, strategy zoo wired**
  - **Scanner gRPC + engine** (`6feacd2`): `ScanSymbols` RPC in `ml_engine.proto` (batch of symbol candle windows × strategy specs → signals); `application/scan_service.py` runs the 9-strategy zoo over each window (pure, no I/O); servicer handler with the standard error policy. 13 new tests (425 total, all green).
  - **TFT challenger** (`197b53b`, Phase 6 T6.2/T6.3): `modeling/pf_bridge.py` translates quantile forecasts → (P(TP-first), P(SL-first), P(timeout)) by CDF interpolation with a conservative first-passage coupling — handles long AND short sides; 14 known-answer tests. `training/tft_pipeline.py` mirrors the LSTM pipeline (same frames, labels, purged holdout, cost-aware backtest); `TftBundle` joblibs without torch/lightning and serves the standard `predict_proba([-1,0,1])` contract. `[tft]` config section, `train-tft` CLI, `[tft]` pip extra. **Not yet run**: needs `pip install -e '.[tft]'` (pytorch-forecasting + lightning — wheel-stage for AWS per V2Ray constraint) before the first gate run.
  - **Scanner backend** (`f36beda`, Phase 3 T3.1/T3.2/T3.4): `ScannerSignal` entity + migration; `TradingBot.Kind` (Model|Scanner) + `StrategyKey`; `BinanceFuturesTickerSource` (`/fapi/v1/ticker/24hr`, ranked `|change%| × log10(volume)`); `MarketScannerService` (5-min pass, top-20 symbols, `ScanSymbols` RPC, proposals only); **scanner-kind bot claims a signal with a conditional UPDATE (exactly one winner under concurrency)** then walks the same intent → risk → place pipeline (steps 6–8 extracted into `ActOnDecisionAsync`, shared with model bots — one safety argument, not two). `ScannerController`: `GET /api/v1/scanner` + `GET /promote/{id}` (prefill only, no trade). Backend suite 32/32.
  - **Scanner frontend** (`8179780`, T3.3): `ScannerPage` (ranked proposals table, debounced symbol/strategy filters, pagination), `/scanner` route + nav entry (`scannerGet`), full Persian i18n, RTL audit clean (71 files), tsc clean.
  - Strategy zoo itself (9 strategies + league runner + `STRATEGIES` registry) landed earlier in this session; 412→425 Python tests green.

- **2026-09-05 — Phase 2 MTF confluence wired end-to-end + weekly retrain cron fixed**
  - **MTF feature builder** (`src/signal-ml/src/crypto_signal/features/mtf.py`): `attach_higher_tf_features(frame, higher, prefix="h4_")` joins scale-free H4 features (trend_ema_ratio, atr_pct, close_vs_ema20) via backward-asof on close_time (no lookahead). 13/13 tests pass, all invariants verified (coverage, lookahead, warmup, scale-free).
  - **Proto + bindings**: `context_candles` + `context_interval` fields added to `EvaluateBotDecisionRequest` in `ml_engine.proto`; Python (`ml_engine_pb2.py`) + C# (`MlEngine.cs`) bindings regenerated.
  - **Engine**: `evaluator.py` `_attach_context_features()` attaches MTF columns to the feature row before `choose_direction()`; warns when context arrives but model wasn't trained with MTF columns.
  - **Backend**: `MlServiceContracts.cs` + `MlServiceClient.cs` + `BotTickExecutor.cs` (fetches H4 candles via `GetClosedCandlesAsync` with single retry per crypto-exchange-integration skill fault-recovery guide) + `TradingOptions.cs` (`MtfContextInterval`/`MtfContextCandles` config).
  - **Trainer guard**: `config.toml [features].mtf_context = true` gate; `download_mtf_context_frames()` + `build_barrier_dataset(mtf_context=...)` + `_label_one_symbol(mtf_context=True)` threads MTF features through training. Verified: 398/398 ML tests pass; `dotnet build` 0 errors.
  - **Weekly retrain cron fixed**: root cause was `drift_skip:silent` (unpinned job + provider/model config drift) + wrong model pin (`cl/` prefix not served by 9router). Fix: pinned to `9router/b.ai/glm-5.3-flash`. Manual fire completed end-to-end (~13 min): candles refreshed, model trained, **gate verdict REJECT** (BTCUSDT_1h edge −0.1913 → −0.2180, worse — correctly blocked). `failure_streak` reset 3→0, `last_status: ok`.
  - Commits: 1) proto+bindings, 2) engine (mtf.py + evaluator + mappers + bot_advisor + models), 3) trainer (config + barrier_pipeline + triple_barrier), 4) backend C# (contracts + client + executor + trading options), 5) cron fix (job pin).
  - **Updated** `docs/ml-improvement-plan.md` (formerly 2026-08-27) with all results, honest conclusions, and remaining priorities.

- **2026-09-01 — Cron pipeline fixed; first full gate cycle ran** — the weekly retrain job was silently drift-skipped (unpinned job + provider/model change) then 401'd (wrong pin to nonexistent `custom` provider); correctly pinned to `9router` + `b.ai/glm-5.3-flash`. First real run completed end-to-end (~12 min): candles refreshed via proxy, candidates trained, **gate verdict REJECT** (candidate BTCUSDT edge −0.191 vs incumbent −0.122, pooled log-loss 0.7962 vs 0.7959) — candidate archived under `rejected/`. Consistent with the bracket sweep's no-edge finding; the gate refused a worse model, engine still serves the incumbent. Bracket sweep committed (`63622e1`): 120 configs, zero profitable with ≥30 trades — parameter tuning ruled out, edge must come from richer inputs.
- **2026-08-31 (evening) — LSTM v2 (advanced) + online self-learning loop** — commit `1678984`
  - **LSTM v2** (`src/signal-ml/src/crypto_signal/modeling/lstm_v2.py`): additive attention pooling over the lookback window, early stopping on a chronological validation slice (`patience`), 3-seed ensemble with probability averaging, temperature scaling fitted on validation (`calibration_method="temperature"`). Serving contract unchanged (`predict_proba`, `is_sequence`, joblib state_dict round-trip). Batched `predict_proba_windows` matches the single-window path to ~1e-9 (verified).
  - **Pipeline** (`training/lstm_pipeline.py`): `train_lstm_v2_bundle` writes `_pooled_<interval>_v2.joblib` + metadata (per-member losses, seed spread, epochs run). CLI: `train-lstm-v2`. Config: `[lstm_v2]` section in `config.lstm.toml` (+ validation in `config.py`).
  - **Real run (BTCUSDT-only smoke config, data through 2026-08-26):** holdout log-loss **0.327**, 3 members (val loss 0.78–0.83, early-stopped at 3–4 epochs), temperature 1.59, seed spread 0.17. Net holdout return 0.00% — the model never cleared the 0.5 confidence floor on the holdout, which is honest, not broken.
  - **Online learning** (engine): `application/online_learning.py` — `TradeSampleStore` (append-only JSONL, idempotent per `(bot_id, decision_candle)`), `promotion_gate` (no-metric-worse/≥1-better, same rule as the batch loop), `OnlineTrainer` (background thread: stored samples up-weighted ×5 + replayed history → v2 challenger → gate vs incumbent on the same holdout → promote writes `<SYMBOL>_<interval>.joblib`, registry hot-reloads). `application/online_service.py` validates/admits samples. Enabled via `ML_ONLINE_LEARNING=true` (default off), store at `ML_TRADE_SAMPLES_PATH`, trigger threshold `ML_ONLINE_TRAINING_MIN_SAMPLES` (default 50).
  - **Proto**: `RecordTradeOutcome` + `GetTrainingStatus` RPCs (messages at end of `ml_engine.proto`); Python bindings regenerated.
  - **Backend**: `MlServiceClient.RecordTradeOutcomeAsync/GetTrainingStatusAsync`, contract records in `MlServiceContracts.cs`, `BotTickExecutor.ReportTradeOutcomeAsync` fires best-effort on every position close (window + bracket + close reason + realized pnl), `GET /api/v1/ml/training-status` on `MlController` with Persian permission label.
  - **Frontend**: M-Engine page gains an online-learning panel (market / samples / since-training / verdict table), i18n in `fa.ts`.
  - **Verified live:** all 5 containers healthy; `GET /api/v1/ml/training-status` → 200 with `onlineLearningEnabled: true` (new RPC working end-to-end); capabilities advertise `RecordTradeOutcome`. Verified: 358/358 ML tests (9 new: store round-trip, dedup on reload, filter, gate verdicts), 15/15 backend, tsc clean, RTL audit clean (70 files), prod build passes. Reason-code vocabulary test bounds its proto slice to the bot-decision section.
  - **Container build fix:** torch 2.13 CUDA wheel (527MB + ~1GB nvidia deps) un-downloadable through V2Ray. Solution: CPU-only torch wheel (`torch-2.13.0+cpu`, 192MB) fetched from `download.pytorch.org/whl/cpu` into `wheels/` + `wheels/constraints.txt` pinning `torch==2.13.0+cpu`; Dockerfile copies `wheels/` and passes `-c constraints --find-links ./wheels` so the resolver takes the local CPU wheel. Engine is CPU-only by design, so this is the correct artifact, not a workaround compromise.
  - **Serving state:** registry serves v1 LSTM as `_pooled:1h`; v2 staged but NOT promoted (registry rejects the `_v2` suffix as unparseable — promotion is the gate's job). Honest numbers: v1 holdout net **-100%** (30,816 trades at the 0.5 floor); v2 holdout log-loss **0.3267**, net **0.00%** (took no trades below the floor) — strictly safer, but on a smaller BTC-only slice so not directly comparable to the tree's 0.7959 on 7 symbols. First online challenger run will gate v2 (or a retrain) against the incumbent on the SAME holdout.
  - **RAM note:** full 7-symbol 1h v2 run OOM-killed on 15GB host; use the smoke config (BTC-only) or per-symbol runs until more RAM or a 5m config.
- **2026-08-31 — Binance Futures Testnet integration + LSTM challenger (E1)** — commits `afd5e5c`, `6a49352`
  - `BinanceFuturesTestnetBroker` (`/fapi/v1/order|leverage`, `/fapi/v2/balance`), Sandbox-only, shorts + explicit leverage, reduceOnly closes, HMAC-SHA256, credentials from connection → env fallback.
  - New `BinanceFuturesTestnet` venue end-to-end: enum, options, HTTP client, kline source (`/fapi/v1/klines`), instrument rules (`/fapi/v1/exchangeInfo`), DTOs, frontend types + i18n + BotDetail stats (leverage/notional/margin/available balance).
  - Proxy re-architected: socat bridge container (10809) instead of direct 10808; NU1900 `NoWarn`'d (vuln-data check unreachable from containers was failing restore).
  - LSTM challenger pipeline: `train-lstm` CLI, config `[lstm]` section, serving metadata `is_sequence`/`lookback`; honest holdout backtest, same cost-aware bar as tree model.
  - Fix `6a49352`: `lstm_pipeline` reads parsed `LstmSection`, not raw TOML dict.
- **2026-08-29 — M Engine page** — commits `02384d4`, `c7a9e85` — model metadata, confidence calibration, markets table.
- **2026-08-27/29 — Bybit demo adapter, leverage threading, proxy fixes, ML uniqueness weights** — commits through `0bf4808`.

## 4. Remaining work (next up)

1. ~~**Rebuild signal-ml image**~~ — DONE (CPU torch via `wheels/` + constraints pin; engine container live with the new RPCs)
2. ~~**Commit** the LSTM v2 + online-learning work~~ — DONE as `1678984`
3. **Sandbox order lifecycle** — IN PROGRESS: connection stored, bot `binance-futures-demo` (Sandbox, BTCUSDT 1h, 2x, 60 USDT) ACTIVE with confidence floor 0.40. Waiting for the first candle whose edge clears 40% to exercise place → reconcile → close. Verify fills reconcile (`exchangeOrderId` set, position row created) and the close reports the outcome to the online learner.
4. ~~**Watch the online loop in the wild**: bot closes feed `trade_samples.jsonl`; ~50 closes trigger the first challenger run — verdict on `/m-engine`.~~ — Bot now running, online learner enabled; samples accumulating as positions close.
5. Full 7-symbol v2 training run needs more RAM than the 15GB host allows (OOM-killed); per-symbol runs or a 5m config are the workarounds.
6. ~~**Weekly retrain cron fixed**~~ — DONE: pinned to `9router/b.ai/glm-5.3-flash`, manual fire completed (REJECT verdict, candidate archived), `failure_streak` 3→0. Next scheduled run 2026-09-07 06:00 UTC+3:30.
7. ~~**Phase 2 — Train + gate the MTF challenger**~~ — wiring DONE; the *run* is pending (see item 13).
8. ~~**NO EDIBLE EDGE — bracket sweep conclusive (2026-09-01).**~~ — Confirmed; documented in `docs/ml-improvement-plan.md` §What's been done. Bot stays Sandbox.
9. ~~**EX-006 circuit breaker + backoff**~~ — deferred to Phase D (not a model-lever).
10. ~~**RISK-003 freshness checks**~~ — deferred to Phase D.
11. Before any real money (standing gates): bracket sweep → 4-week soak → manual approval → rotate the screenshotted Bitunix key → gateway running for retrain cron.
12. Minor: duplicated `EstimatedNotional`/`EstimatedMargin` doc-block in `BotDtos.cs` (`afd5e5c`) — cosmetic.
13. ~~**Run the queued challengers + gate them**~~ — DONE (2026-09-06), both REJECT: (a) MTF retrain ran with 45 features — log-loss 0.7968 vs 0.7959, edge −0.428 ATR vs −0.122 → archived; incumbent restored+verified. (b) TFT smoke (BTC, 2y, stride 4) completed end-to-end after 5 PF-1.8 fixes (`f637b31`) — log-loss 4.19, net −26.5% vs B&H +12% → the label-space proxy target is the weak point; continuous-return target is the next lever (see ml-improvement-plan §Challenger results).
14. **Scanner first live pass** — enable `Scanner:Enabled` in appsettings (or env `Scanner__Enabled=true`), restart api, confirm the first scan pass writes `ScannerSignals` rows; then create one Scanner-kind Sandbox bot (5m, best league strategy) and verify it claims exactly one signal under concurrent ticks. If no signal qualifies, that is a valid honest result.
15. ~~**League run with real data**~~ — DONE (2026-09-06): 54 combos, `docs/STRATEGY_LEAGUE.md` — 50 WEAK, only `rsi_pullback` 15m positive (+0.7–0.9%, 5–8 trades, MODERATE); adoption gate passes nothing.
16. ~~**Phase 4/5 leftovers**~~ — DONE (2026-09-07): T4.2 per-strategy CSVs (`0470d2f` — `artifacts/league/<stamp>/trades/*.csv`, TEST-split only), T4.3 weekly Telegram digest (`d8146d0` — `scripts/league_digest.py`, cron `5b6f266c7139` Mondays 07:30 Tehran), T5.1 AWS deploy — images rebuilt on EC2, wheels staged in `/opt/crypto-signal/wheels/`, stack healthy (api/dashboard/signal-ml/proxy), scanner live on AWS (first pass: 3 signals / 20 symbols). AWS compose convention: `COMPOSE_FILE='compose.yml:compose.dev.yml:compose.aws.yml'` — bare up drops the JWT env (api exit 134). Deploy = build **all three** images (`signal-ml`, `api`, `dashboard`) — partial builds leave stale UI: dashboard missed `8179780` (scanner page) until rebuilt 2026-09-07.

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
| MTF features | `src/signal-ml/src/crypto_signal/features/mtf.py` |
| i18n (Persian) | `src/frontend/src/i18n/fa.ts` |
| Compose / env | `devops/compose*.yml`, `devops/env/dev/` |
| Plans | `.hermes/plans/`, `docs/AUTO_TRADING_PLAN.md`, `docs/FUTURES_LEVERAGE_PLAN.md`, `docs/LIVE_TRADING_SAFETY.md`, `docs/ml-improvement-plan.md` |

---

### Changelog rule
When you finish a feature: add a dated bullet to §3, update §2 evidence table rows you touched, move items between §4 (remaining) and §3 (done), and bump the "Last updated / HEAD" stamp above. Keep it honest — unverified claims do not go in §2.
