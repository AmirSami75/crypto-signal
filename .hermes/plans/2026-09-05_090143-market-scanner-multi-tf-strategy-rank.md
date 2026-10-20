# Plan: Market Scanner + Multi-Timeframe + Strategy Zoo + Ranked Strategy League

**Date:** 2026-09-05 · **Status:** PLANNED (not implemented) · **Owner agent:** Hermes
**Companion doc:** `docs/HANDOFF.md` (read it first — deployment layout, env quirks, safety gates)

---

## Goal

Turn crypto-signal from a two-symbol, one-model, fixed-bracket system into a **market-wide,
multi-timeframe strategy platform**: a scanner that hunts every Binance Futures symbol for
setups, a zoo of 9+ indicator strategies backtested and ranked in a walk-forward "league"
table, and multi-timeframe confluence feeding the existing ML gate — all inside the current
safety envelope (Sandbox/Paper only, gate-checked promotion, Telegram reporting).

---

## Current context / assumptions

Read these before touching anything:

1. **Stack layout** (`docs/PROJECT_STRUCTURE.md`, `docs/ARCHITECTURE.md`):
   - `src/backend` — .NET 10 API: venues (`MarketVenue`), brokers (`IBroker`), kline sources (`IMarketDataSource`, `MarketDataSourceResolver`), bots (`TradingBot`, `BotTickExecutor`), RDS Postgres via EF Core.
   - `src/signal-ml` — Python engine (gRPC `crypto_signal_engine`): `bot_advisor.py` prices a bet from ONE candle window + ONE bracket pair; `crypto_signal/modeling/direction.py` chooses long/short/flat; `crypto_signal/evaluation/bracket.py` backtests a bracket.
   - `src/frontend` — React TS, same-origin `/api` (nginx proxy in production).
   - Deployed on EC2 `3.85.59.30` at `/opt/crypto-signal` (compose `--profile aws`, RDS Postgres, Cloudflare → nginx :80). Local dev mirrors it with V2Ray proxy.
2. **Known honest result** (`docs/bracket-sweep-2026-09-01.csv`): the current tree model has NO
   profitable bracket config on BTCUSDT 1h. The ML gate prices bets with **fixed-percent
   brackets** (`takeProfitPercent`/`stopLossPercent` on `TradingBot`) which on 5m candles
   extrapolate 20+ ATR outside the model's 0.5–4 ATR training range (see `no_edge` analysis,
   2026-09-05). **Anything built here must express brackets in ATR multiples** or the model
   cannot price them honestly.
3. **Model training range**: barrier grid `[0.5, 1.0, 1.5, 2.0, 3.0]` ATR, RR 0.4–4.0
   (`config.toml [barrier]`). Multi-TF features must respect scale-free design (every feature
   is a ratio; verified by `test_every_feature_is_scale_free`).
4. **Bot cadence**: `TradingBot.CadenceSeconds` drives `BotTickExecutor`; positions are per-bot;
   decisions idempotent per `(BotId, CandleOpenTime)`.
5. **Assumption**: Binance Futures Testnet symbol universe = mainnet symbols. Scanner uses the
   venue's `/fapi/v1/exchangeInfo` (already implemented in `InstrumentRuleProvider`).
6. **Research inputs** (this plan's "best ideas", verified from the four repos):
   - **tradingview-mcp** (★4.4k): 9 named indicator strategies (rsi, bollinger, macd, ema_cross,
     supertrend, donchian, rsi_pullback, keltner_breakout, triple_ema), walk-forward validation
     with overfitting verdict, `compare_strategies` ranking, `get_multi_timeframe_analysis`
     (Weekly→Daily→4H→1H→15m alignment), screeners (`scan_by_signal`, `screen_stocks`).
   - **lumibot** (★2k): strategy abstraction = one class, same code backtests and runs live;
     backtest artifacts; scheduled rules.
   - **the0** (★425): bot templates + isolated execution + custom dashboards per bot.
   - **OpenAlice** (★7k): "trading as git" — staged proposals through an approval gate;
     market tools as CLIs; research→thesis→execution loop.

## What we are NOT doing (scope cuts)

- No TradingView account scraping / desktop automation (tradingview-mcp explicitly avoids it;
  we adopt only the *idea* of their indicator/strategy zoo + ranking — implemented natively
  in our Python engine, no TradingView dependency, no MCP server needed).
- No new programming languages (the0's multi-language bots — YAGNI).
- No live trading. Everything stays Sandbox/Paper behind the existing gates.
- No vectorbt/backtrader dependency — the existing `run_bracket_backtest` engine is kept and
  extended (it already models fees, slippage, ties, MFE/MAE).

---

## Architecture / proposed approach

Three new subsystems, all inside the existing boundaries:

1. **Strategy Zoo (Python, signal-ml)** — `crypto_signal/strategies/`: each strategy is a pure
   function `evaluate(frame) -> Signal|None` (BUY/SELL + optional atr-based bracket), registered
   in a `STRATEGIES` dict. A `LeagueRunner` backtests every strategy on every (symbol, timeframe)
   with purged walk-forward splits and writes a ranked league table (JSON + Postgres table).
2. **Market Scanner (.NET, backend)** — `MarketScannerService`: every 5 min pulls the venue's
   24h tickers (Binance `/fapi/v1/ticker/24hr`), ranks symbols by |change|/volume/ATR%, feeds the
   top N symbols' latest candles through the Strategy Zoo via the ML engine (new gRPC
   `ScanMarket` RPC), and records `ScannerSignals`. Existing bots stay exactly as they are —
   the scanner creates **proposals**, never orders.
3. **Multi-timeframe confluence (Python)** — new feature builder that computes the SAME
   scale-free features on 1h/4h context windows and merges them as extra columns
   (`h1_trend_*, h4_trend_*`), letting the existing pooled model consume MTF context without a
   new model type.

Bots gain two optional fields: `StrategyKey` (run a specific zoo strategy instead of/alongside
the ML model) and `Symbols` (explicit list) — plus a new `ScannerBot` mode that trades the
scanner's top proposals. Everything still flows through `BotTickExecutor` → risk engine →
broker, so the safety invariants (fail-closed limits, kill switches, audit trail) hold unchanged.

---

## Step-by-step tasks

### Phase 0 — Foundations (backend: ATR brackets + multi-TF data access)

**T0.1 — Add ATR-based bracket fields to `TradingBot`**
File: `src/backend/src/CryptoSignal.Api/Domain/Models/Trading/TradingBot.cs`
Add nullable fields next to `TakeProfitPercent`:
```csharp
/// <summary>Take-profit distance in ATR multiples. When set, overrides TakeProfitPercent.</summary>
public decimal? TakeProfitAtrMultiple { get; init; }
/// <summary>Stop-loss distance in ATR multiples. When set, overrides StopLossPercent.</summary>
public decimal? StopLossAtrMultiple { get; init; }
```
Test first: add to `src/backend/tests/CryptoSignal.Tests/` a `BotAtrBracketsTests.cs` asserting a
bot with `TakeProfitAtrMultiple=2` prices TP = entry + 2×ATR (mirror the assertion style of
`BinanceFuturesTestnetBrokerSafetyTests.cs`). Run `docker pause crypto-signal-api-1; dotnet test
--filter FullyQualifiedName~BotAtrBrackets` (expect RED), then add fields, rebuild (GREEN).
Commit: `feat(bot): ATR-multiple brackets (TakeProfitAtrMultiple/StopLossAtrMultiple)`.

**T0.2 — Thread ATR brackets through `BotTickExecutor` + DTOs**
Files: `src/backend/src/CryptoSignal.Api/Application/Trading/Execution/BotTickExecutor.cs`
(where `StrategyDecision` levels are computed), `Application/DTOs/Trading/BotDtos.cs`
(`BotInputDto` + `BotDetailDto` + `BotSummaryDto`), migration via
`docs/DATABASE_MIGRATIONS.md` convention (`dotnet ef migrations add BotAtrBrackets`).
Verification: `dotnet build` 0 errors; migration applied to RDS via the API's auto-migrator on
restart; `curl /api/v1/bot/{id}` shows the new fields. Commit.
Telegram report: `tg-report "T0.2 ATR brackets threaded"`.

**T0.3 — Multi-timeframe kline access in backend**
File: `src/backend/src/CryptoSignal.Api/Application/Trading/MarketData/IMarketDataSource.cs`
— add `Task<IReadOnlyList<MarketCandleData>> GetCandlesAsync(string symbol, string interval, int count, CancellationToken ct)`
if the existing `GetClosedCandlesAsync` hard-codes closed-only logic per bot interval (read it
first — `BinanceFuturesTestnetKlineSource` already takes interval as a parameter, so this may be
a no-op). Verification: unit test fetching `BTCUSDT` `1h` and `5m` from the testnet kline source
(fakes allowed, mirror `KlineSourceTests.cs`). Commit.

### Phase 1 — Strategy Zoo (Python, signal-ml)

**T1.1 — Strategy contract + registry**
New file: `src/signal-ml/src/crypto_signal/strategies/__init__.py`
```python
"""Strategy Zoo: named indicator strategies with one contract.

A strategy sees a feature-rich OHLCV frame (plus `atr`) and returns a Signal or None.
No I/O, no state — the same function backtests and serves.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
import pandas as pd

@dataclass(frozen=True, slots=True)
class Signal:
    direction: str            # "LONG" | "SHORT"
    entry_index: int
    reason: str

Strategy = Callable[[pd.DataFrame], Signal | None]

STRATEGIES: dict[str, Strategy] = {}

def register(name: str):
    def deco(fn: Strategy) -> Strategy:
        STRATEGIES[name] = fn
        return fn
    return deco
```
Test: `tests/ml-engine/test_strategy_zoo.py::test_registry_roundtrip` — register a dummy,
assert it is in `STRATEGIES`. RED → implement → GREEN. Commit.

**T1.2 — Implement the 9 strategies (port of tradingview-mcp's zoo, our semantics)**
Files: `src/signal-ml/src/crypto_signal/strategies/rsi.py`, `bollinger.py`, `macd.py`,
`ema_cross.py`, `supertrend.py`, `donchian.py`, `rsi_pullback.py`, `keltner_breakout.py`,
`triple_ema.py`. Shared indicators already exist in `crypto_signal/features/indicators.py`
(EMA/SMA/ATR) — reuse, do not re-implement (DRY). Each file ≤ 60 lines, one `@register`
function, entry rule + exit rule expressed as boolean columns, `Signal` on the transition.
Each strategy gets one parameterized test in `tests/ml-engine/test_strategy_zoo.py` using a
synthetic frame that provably triggers it (e.g. construct a V-shaped close series for RSI).
Command: `cd src/signal-ml && .venv/bin/python -m pytest ../../tests/ml-engine/test_strategy_zoo.py -q`
→ 10+ passed. Commit per 2-3 strategies (small commits).

**T1.3 — LeagueRunner: walk-forward backtest + ranking**
New file: `src/signal-ml/src/crypto_signal/evaluation/league.py`
- Reuses `crypto_signal.evaluation.bracket.run_bracket_backtest` (fees/slippage/tie-breaks) and
  `crypto_signal.modeling.splitting.chronological_blocks` for purged train/test.
- `run_league(frames: dict[symbol->DataFrame], intervals: list[str], strategy_names: list[str])`
  → per (strategy, symbol, interval): trades, win_rate, total_return, profit_factor, Sharpe,
  max_drawdown, plus walk-forward overfit verdict (train/test return ratio: ROBUST ≥0.5,
  MODERATE ≥0, WEAK <0, OVERFITTED = train≫test).
- CLI: `python -m crypto_signal run-league --config config.toml --symbols BTCUSDT,ETHUSDT
  --intervals 1h,15m` writes `artifacts/league/<stamp>.json` + prints ranked table.
Test: `tests/ml-engine/test_league.py` — synthetic 2-symbol frames, assert ranking output has
one row per (strategy,symbol,interval) and deterministic order (sort by total_return desc,
profit_factor tiebreak). RED → implement → GREEN. Commit: `feat(league): walk-forward strategy
ranking runner`.

**T1.4 — First real league run**
Command (on local, proxy on):
```
cd src/signal-ml && .venv/bin/python -m crypto_signal run-league --config config.toml \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT --intervals 1h,15m
```
Expected: JSON artifact with 54 rows (9 strategies × 3 symbols × 2 intervals), ranked. Copy the
top-5 table into `docs/STRATEGY_LEAGUE.md` (new file, honest numbers, date stamp). Commit docs.
⚠️ Gate: no strategy is "adopted" until it shows positive net return on the TEST split — same
honesty as the bracket sweep.

### Phase 2 — Multi-timeframe confluence (Python)

**T2.1 — MTF feature builder**
New file: `src/signal-ml/src/crypto_signal/features/mtf.py`
```python
def attach_higher_tf_features(frame: pd.DataFrame, higher: pd.DataFrame,
                              prefix: str = "h4_") -> pd.DataFrame:
    """Join scale-free higher-timeframe context onto a lower-TF frame.

    Adds, aligned by candle open-time (asof join on the higher TF's close):
      {prefix}trend_ema_ratio   = ema20/ema50 on the higher TF (scale-free)
      {prefix}atr_pct           = atr/close on the higher TF
      {prefix}close_vs_ema20    = close/ema20 - 1
    All values are ratios: the scale-free assertion test must still pass.
    """
```
Uses `pandas.merge_asof`. Test: `tests/ml-engine/test_mtf_features.py::test_scale_free_and_alignment`
— two synthetic frames with known ratio values, assert column values and that NaN rows before
higher-TF warmup are preserved (model handles NaN natively — same convention as warm-up columns).
RED → implement → GREEN. Commit.

**T2.2 — Wire MTF into the serving request (proto + engine)**
Files: `contracts/crypto_signal_engine/contracts/v1/ml_engine.proto` (extend `Candle`-bearing
messages with `repeated Candle context_candles_1h` / `context_candles_4h` + `string
context_interval`), regenerate bindings (`src/signal-ml/scripts/generate_grpc.py`),
`transport/grpc/mappers.py` (map new fields), `application/bot_advisor.py` (call
`attach_higher_tf_features` before `build_features`), backend
`src/backend/src/CryptoSignal.Api/Clients/MlServiceClient.cs` + `BotTickExecutor.cs` (send the
context window: reuse `IMarketDataSource.GetCandlesAsync(symbol, "1h", 168)` — T0.3).
Verification: engine test asserting the MTF columns appear in the feature frame when context is
supplied; backend `dotnet build` 0 errors; manual gRPC probe `GetSignal` with context → 200.
Commits: proto+bindings, engine, backend (3 commits).

**T2.3 — Retrain pooled model with MTF features (smoke config first)**
Command: `cd src/signal-ml && .venv/bin/python -m crypto_signal train --config config.toml`
after adding `mtf_context = true` to `[features]` in `config.toml` (guard: if true, trainer
requires 1h context frames for every symbol).
Verification: feature_count grows (42 → ~51); holdout log-loss reported honestly in
`docs/HANDOFF.md`; **promotion still gate-checked** — no auto-swap. Commit.

### Phase 3 — Market Scanner (backend + engine)

**T3.1 — 24h tickers endpoint client**
File: `src/backend/src/CryptoSignal.Api/Application/Trading/MarketData/BinanceFuturesTickers.cs`
— calls `GET /fapi/v1/ticker/24hr` (no auth) via the existing named HTTP client, returns
symbol/priceChangePercent/quoteVolume/lastPrice. Unit test with a fake handler (mirror
`FakeHttpMessageHandler` in `BinanceFuturesTestnetBrokerTests.cs`). Commit.

**T3.2 — Scanner service + table**
New: `src/backend/src/CryptoSignal.Api/Application/Trading/Scanner/MarketScannerService.cs`
(BackgroundService, 5-min period), `Domain/Models/Trading/ScannerSignal.cs` (entity: Symbol,
Interval, StrategyKey, Direction, Confidence, AtrAtSignal, CreatedAt, TakenByBotId?), EF
migration `ScannerSignals`. Scoring: `score = |change%| * log10(quoteVolume) ` (tunable const).
Top 20 symbols per pass; per symbol fetch last 300 candles of the bot's interval and evaluate
the strategy via new gRPC `ScanSymbols` RPC (batch: request = list of (symbol, candles),
response = list of Signal|None).
gRPC addition in `contracts/.../ml_engine.proto` + engine `application/scanner_service.py`
(evaluates zoo strategies on provided candles — pure, no I/O). Tests: fake-ticker test for
ranking; engine test evaluating one strategy on canned candles. Commits: proto, engine,
backend service + migration.

**T3.3 — Scanner API + dashboard surface**
`src/backend/src/CryptoSignal.Api/API/Controllers/v1/Trading/ScannerController.cs`
(“پیوت اسکنر” permission label, Persian): `GET /api/v1/scanner/signals?interval=5m&take=50`
and `POST /api/v1/scanner/promote/{signalId}` (stages a proposal; does NOT trade).
Frontend: `src/frontend/src/pages/ScannerPage.tsx` + route in `src/frontend/src/routes.ts` +
i18n in `src/frontend/src/i18n/fa.ts` (table: symbol, strategy, direction, confidence, age,
[ایجاد ربات] button that prefills `BotFormModal`).
Verification: `npx tsc --noEmit` clean; `npm run rtl:audit` clean; manual click-through.
Commit.

**T3.4 — ScannerBot mode**
`TradingBot` gains `BotKind` (enum: `Model`, `Scanner`) + `StrategyKey` + `MaxSpreadAtr`.
`BotTickExecutor`: for `Scanner` bots, skip ML advisor; take the newest unclaimed
`ScannerSignal` matching the bot's interval+strategy, claim it atomically
(`UPDATE ... SET TakenByBotId=@bot WHERE Id=@id AND TakenByBotId IS NULL` — idempotency kept),
then reuse the exact existing order pipeline (risk → intent → broker). Risk engine unchanged.
Test: `tests/CryptoSignal.Tests/ScannerBotTests.cs` — two concurrent claims, exactly one wins.
Commit.

### Phase 4 — Leanings from OpenAlice + lumibot (small, high-value)

**T4.1 — "Trading as git" proposal gate** — extend T3.3's `promote` into a two-step
proposal: staged proposal row → operator approves in dashboard → bot created. (This mirrors
OpenAlice's staged-commits and keeps the human gate before anything trades.)
**T4.2 — Backtest artifacts** — league runs already write JSON; add
`artifacts/league/<stamp>/trades/<strategy>_<symbol>_<interval>.csv` (mirror lumibot's
inspectable artifacts). Commit.
**T4.3 — Telegram strategy-league digest** — weekly cron (AWS side, like `monitor.sh`) sends
the top-10 ranked strategies with walk-forward verdicts. Command pattern identical to
`monitor.sh digest`.

### Phase 5 — Deployment + docs

**T5.1** — rsync/tar-push updated repo to AWS (`/opt/crypto-signal`), rebuild images
(compose `--profile aws`), restart stack, verify `/health/ready` + scanner endpoint.
**T5.2** — `docs/HANDOFF.md` new entry; `docs/STRATEGY_LEAGUE.md` kept current; Telegram
report of the full rollout (tg-report convention).
**T5.3** — Local + AWS smoke: create one `Scanner`-kind Sandbox bot on the 5m interval with the
best-ranked strategy; confirm it claims a signal and (only if risk passes) places a testnet
order. If no signal qualifies in 24h, that is a valid honest result — report it.

---

## Tests / validation (summary)

- Python: `cd src/signal-ml && .venv/bin/python -m pytest ../../tests/ml-engine -q` must stay
  green; every new module has RED→GREEN tests as specified per task.
- Backend: `docker pause crypto-signal-api-1 && dotnet test` green; `dotnet build` 0 errors.
- Frontend: `npx tsc --noEmit` + `npm run rtl:audit` clean per task T3.3.
- End-to-end: league artifact with real data; scanner endpoint returns ranked signals; a
  Scanner bot claims exactly one signal under concurrency; Cloudflare dashboard shows the
  Scanner page.
- Honest-metrics rule: league tables show TEST-split numbers only; training-split numbers go
  in the JSON artifact for audit, not the summary.

## Risks / tradeoffs / open questions

1. **SixLabors ImageSharp license** blocks `dotnet publish Release` on AWS (seen 2026-09-02).
   Runtime-target builds of the API are blocked until this is resolved (license key, or swap
   the image dependency, or keep Development target). → Resolves itself if we keep the API on
   the Development image (current AWS state), but must be tracked.
2. **Strategy zoo ≠ edge guarantee**: the sweep proved the *current* ML model lacks edge; the
   zoo strategies may too. The league's walk-forward verdict exists precisely to kill weak
   strategies before they trade. Expect most of the 9 to fail honestly — adopt only positive
   TEST-split performers.
3. **Rate limits**: scanner pulls tickers + N×300 candles every 5 min. Binance weight limits
   allow it (ticker 40w, klines 2w each), but cap symbols per pass (20) and respect
   `429 Retry-After` (add to `TradingHttpClients` resilience).
4. **Scanner→bot claim race** is handled with an atomic UPDATE; verify under concurrency test.
5. **MTF features change the feature vector** → old models incompatible; keep the old model
   files; gate-promote the MTF retrain (existing promotion gate covers this).
6. **Open question**: should Scanner bots also respect `maxConcurrentPositions` per symbol? →
   default yes (risk engine unchanged).
7. **Open question**: TradingView MCP as an MCP server inside Hermes for ad-hoc research — the
   zoo is implemented natively, but the MCP server could still be added for conversational
   research. Deferred: it duplicates what the zoo + scanner give the bots, and MCP adds a
   dependency; revisit after Phase 1 results.

---

## Phase 6 — pytorch-forecasting challengers (TFT first) — ADDED 2026-09-05

**Why added (decision made by Hermes after gap analysis):** our proven bottleneck is MODEL
EDGE — the tree/LSTM see 42 hand-picked features on one timeframe. PF's TFT attacks exactly
that: end-to-end **variable selection** (learns which features carry signal), **native
multi-timeframe covariates**, and **quantile outputs** of the return distribution — which are
the cleanest bridge to trading-native barrier probabilities. N-HiTS/PatchTST ride the same
integration as cheap second challengers. DeepAR is skipped (TFT supersedes it in PF's own
benchmarks). The Lightning/TimeSeriesDataSet infra is a convenience, not the reason.

**What we do NOT adopt:** PF as a serving system or evaluation layer — our purged holdout,
fee-aware bracket backtest, registry, promotion gate, and calibration honesty remain the
arbiters. PF is a *trainer library* only.

### T6.1 — Dependency staging (AWS-proof)
Add `pytorch-forecasting[cpu]` + `lightning` pins to `src/signal-ml/pyproject.toml` (exact
versions, no floats). Pre-fetch wheels into `wheels/` (same pattern as the torch CPU wheel —
V2Ray kills big downloads locally; AWS has direct egress either way). Verify:
`cd src/signal-ml && .venv/bin/pip install -e '.[dev]'` succeeds and
`.venv/bin/python -c "import pytorch_forecasting, lightning; print('pf ok')"` works.

### T6.2 — Quantile→barrier translation layer (the honest bridge)
New file: `src/signal-ml/src/crypto_signal/modeling/pf_bridge.py`
```python
def barrier_probabilities_from_quantiles(
    quantile_forecasts: dict[float, float],   # e.g. {0.1: -0.012, 0.5: 0.001, 0.9: 0.018}
    horizon_bars: int,
    take_profit_atr: float, stop_loss_atr: float, atr: float,
) -> tuple[float, float, float]:
    """Translate a forecast return distribution into (P(TP-first), P(SL-first), P(timeout)).

    Method: interpolate a CDF over the horizon return from the predicted quantiles, then
    integrate the first-passage approximation against the barrier distances (in return
    space: tp = take_profit_atr * atr / price, sl = stop_loss_atr * atr / price). Returns
    probabilities that sum to <= 1 (remainder = timeout mass), matching the engine's
    ALL_CLASSES convention. Validated on synthetic distributions where the answer is known.
    """
```
Tests (`tests/ml-engine/test_pf_bridge.py`): symmetric distribution → symmetric
probabilities; zero-width distribution (all quantiles equal) → degenerate mass on the near
barrier; sum ≤ 1 always; monotone in TP distance. RED → implement → GREEN. **This file is
the correctness-critical piece — sloppy math here fabricates probabilities.**

### T6.3 — TFT challenger trainer
New file: `src/signal-ml/src/crypto_signal/training/tft_pipeline.py` — mirrors
`lstm_pipeline.py`: builds a `TimeSeriesDataSet` from the same downloaded OHLCV frames
(group = symbol, time_idx = candle index, target = log-return, covariates = the existing
scale-free features incl. Phase 2's MTF columns), trains TFT (small: hidden 32, attention
head 4, 1-2 quantiles [0.1, 0.5, 0.9], max_epochs with early stopping), then produces
barrier probabilities via `pf_bridge` and writes a bundle `artifacts/models/_pooled_1h_tft.joblib`
with the SAME serving contract (`predict_proba` over [-1,0,1], `is_sequence=True`) so the
registry can load it without code changes. Walk-forward purged holdout identical to the
tree/LSTM pipelines. Test: bundle round-trip + `predict_proba` shape + calibration sanity
(mean predicted win-rate within tolerance of realized on synthetic data). Commit.

### T6.4 — Gate run (honest)
Train on smoke config first (BTC-only), then full. The TFT challenger faces the same
promotion gate as everything else: purged holdout log-loss AND fee-aware bracket backtest
(net of costs) vs the incumbent. **If it does not beat the incumbent, it is archived under
`rejected/` — that is a valid, expected outcome.** Report numbers in `docs/HANDOFF.md` +
Telegram. Also record TFT's variable-selection importances into the metadata (it tells us
which of the 42 features carry signal — actionable even if the model loses the gate).

### T6.5 — (conditional) N-HiTS second challenger
Only if T6.1–T6.4 landed cleanly: same pipeline, `NHiTS` instead of TFT, one gate run.
Skip otherwise (YAGNI).

### Sequencing
Phase 6 starts only after Phase 2 (MTF features) is merged — TFT wants those MTF covariates.
Do not run Phase 6 in parallel with Phase 2; the feature frames it consumes are Phase 2's
output.

### Risks
- **Translation-layer correctness** is the load-bearing piece (T6.2): validated on synthetic
  known-answer cases before any real data touches it.
- **Dependency weight**: pf+lightning adds ~200MB to the image; pins are exact; AWS wheel
  staging as with torch.
- **RAM**: TFT training on 7 symbols × 1h fit in 8GB (t3.large) with small hidden sizes and
  CPU; the 7-symbol full config OOMs locally at 15GB for LSTM v2 — use smoke config first.
- **No guarantee of edge**: same as the sweep — the gate decides, and a REJECT is a valid
  honest outcome that still yields the variable-importance insights (T6.4).
