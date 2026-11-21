# ML engine → all-market, risk-reward (points) refactor

> **Status:** design for approval · **Date:** 2026-11-09 · **Owner:** Hermes (default profile)
> **Branch:** `main` · **No commits until the user approves the summary.**

## 1. Why

The user asked for four things that are one redesign:

1. Watch **every symbol in the market**, not a hand-picked few.
2. Judge each market for a **position opportunity** and surface it, then trade it.
3. Change the model objective to **risk-reward points**: +1 for a win, −1 for a loss, and let every
   loss feed back into the model.
4. Review the whole flow once, rewrite it, and make the model actually run.

## 2. What exists today (evidence)

| Layer | Current behaviour | Where |
|---|---|---|
| Labels | 3-class triple-barrier: TP-first / timeout / SL-first, sampled ATR pairs + `direction_sign` | `labeling/triple_barrier.py:232,298,380` |
| Objective | multiclass log-loss over those 3 classes | `modeling/estimator.py` |
| Decision | `EV = p_tp·TP_atr − p_sl·SL_atr`, open only if `confidence ≥ floor` **and** `EV ≥ floor`; timeout valued 0 | `modeling/direction.py:148`, `training/barrier_pipeline.py:1004` |
| Serving | `<SYM>_<tf>.joblib` overrides `_pooled_<tf>.joblib`; registry rejects `_v2` suffixes | `crypto_signal_engine/infrastructure/model_registry.py` |
| Universe scan | top-20 by `|change%| × log10(quoteVolume)`, 5 strategies, **no model score** | `MarketScannerService.cs:92-168` |
| Online learning | JSONL sample store → **LSTM v2** challenger after 50 closes/market, samples up-weighted ×5, gate on log-loss + edge | `crypto_signal_engine/application/online_learning.py` |
| Gate | never promotes in practice; on REJECT it archives nothing and restores nothing → the rejected candidate stays served | `scripts/self_learning_loop.py:150-205` |

Measured today (2026-11-09, through the V2Ray relay):

- **522** USDT perpetuals `TRADING`; **804** ticker rows; **207** symbols with >$10M daily volume.
- 30 symbols × 300×5m candles = **1.1 MB**, 1.8 s at concurrency 10 → **522 symbols ≈ 19 MB, ~30 s**,
  ~1,044 request weight per full pass (limit 2,400/min) — a full-universe 5m pass every 5 min is feasible
  with a token-bucket guard.

## 3. Target design

### 3.1 Universe coverage (tiered, weight-budgeted)

- **U0 – universe (60 s):** `/fapi/v1/ticker/24hr` → USDT perps, `TRADING`, `quoteVolume ≥ 5M`
  (≈250 symbols), keep all 522 tracked for monitoring.
- **U1 – deep scan (5 min):** candles + model for the ranked frontier: top **K=120** by a cheap
  pre-score (volatility z, volume z, |change|) **plus** every symbol with an open position or active bot.
- **U2 – promotion:** a pre-score candidate is promoted to a full model evaluation; only those with
  `expected_points ≥ min_expected_points` become `ScannerSignals`.
- Rate governor: token bucket (≤1,200 weight/min), honour `Retry-After`, exponential backoff on 429/418.

### 3.2 Points objective (risk-reward, ±1R)

- Replace the training target with the **realized R-multiple** of the sampled bet:
  `R = +TP/SL` when TP first, `R = −1` when SL first, `R = realized_at_horizon / SL` on timeout.
  With a symmetric bracket this is exactly the user's **+1 / −1**.
- Train a **regression head** (`HistGradientBoostingRegressor`) on `R`, keeping the 3-class classifier
  for calibration and for the existing wire contract. Decision uses the regressor's mean:
  `expected_points = ŷ` and requires `expected_points ≥ min_expected_points` (default **+0.10R**) **and**
  `P(win) ≥ min_confidence`.
- Report `expected_points`, `risk_reward`, and `p_win` through `EvaluateBotDecision` and
  `ScanSymbols` (additive proto fields; unknown fields default to the old path for compatibility).

### 3.3 Two-speed learning ("every loss teaches it")

- **Fast loop (every closed trade):** store `(features snapshot, bracket, realized R, ts)`; update a
  **per-market calibration** (isotonic / logistic on the last 200–500 resolved samples) mapping raw score
  → realized win probability. Cheap (<1 ms), immediate, and it is what changes the *next* decision.
- **Slow loop (every 50 new closes or nightly):** refit on rolling 120 days + all live samples with
  `weight = 1 + 1.0·1[loss]` and age decay; gate against a **frozen baseline bundle**
  (`<stem>_baseline.joblib`, written only at promotion) using **expected points per trade** with a
  ≥30-trade minimum and a one-sided 95 % CI lower bound > 0, plus no worse calibration (ECE).
- **Gate fix (mandatory):** REJECT → move the candidate to `rejected/` and restore the pre-overwrite
  pair; PROMOTE → archive the incumbent and write `_incumbent_metadata.json`. A gate that leaves its
  loser live is not a gate — this is why today's served bundle is a REJECT.

### 3.4 Operational chain

`universe → scan → ScannerSignal(points) → ScannerBot claims (atomic UPDATE) → risk engine →
BinanceFuturesTestnet order → reconcile → close → RecordTradeOutcome → fast calibration → slow refit`.

One Sandbox bot (5m, TP 2.0 ATR / SL 1.0 ATR, `min_expected_points 0.10`) exercises the chain end to end.

## 4. Lanes (disjoint write scopes)

| Lane | Scope (files) | Deliverable | Verify |
|---|---|---|---|
| **L1 points-model** | `src/signal-ml/src/crypto_signal/{labeling,modeling,training,domain}/*`, `tests/ml-engine/*` | R-multiple target + regression head + decision thresholds | `pytest tests/ml-engine -q` (all green, new tests for ±1R math, timeout R, threshold gating) |
| **L2 engine/online** | `src/crypto_signal_engine/**`, `scripts/self_learning_loop.py` | serving contract + fast calibration + gate reject/restore | `pytest tests/ml-engine -q`, `python scripts/self_learning_loop.py --dry-run` prints gate verdict and a simulated REJECT restores files (file hash proof) |
| **L3 universe scanner** | `Application/Trading/Execution/MarketScannerService.cs`, `MarketData/*`, `ScannerOptions`, scanner DTO/controller | tiered universe + token bucket + points ranking | `dotnet build`; scanner pass logs `scanned=N/522`, DB rows for promoted signals |
| **L4 surface** | `src/frontend/src/pages/ScannerPage.tsx`, i18n, bot detail | points/RR/model columns, universe counters | `npx tsc --noEmit && npm run build` |
| **L5 verify/ops** | `scripts/` E2E harness, docs | one-cycle E2E + HANDOFF evidence | scanner pass at 522 symbols < 90 s; bot lifecycle on Binance testnet with a real fill/close |

Ordering: L1 → L2 (contract depends on the target), L3 independent of L1 (can start in parallel),
L4 after L3 contract, L5 last. No lane writes another lane's files.

## 5. Risks / open decisions

1. **Serving bundle invalidation:** a new objective requires a full retrain (~9 min for 1h/7 symbols,
   ~30–60 min for a wider universe). Until then the old bundle keeps serving; the engine must answer
   `points=null` and fall back to EV-in-ATR.
2. **Every existing bot's thresholds are confidence-based.** Introducing `min_expected_points` needs a
   default that does not silently change behaviour: default 0.0 keeps current decisions; 0.10 is the
   proposed production value.
3. **Binance weight** is shared with the bot's own candle fetches; the governor must reserve ~400 weight
   for bots and charts.
4. **Data honesty:** a 522-symbol model has far more samples but also many thin markets; the gate must
   stratify by symbol liquidity, and the backtest must include fees + slippage (already implemented).
5. **Scope:** the "all symbols" pass is ~1,044 weight; scanning 522 symbols every 5 minutes is at 43 % of
   the venue budget. That is acceptable but leaves little room for a second scanner instance — keep one.

## 6. Definition of done

- A scanner pass covers all 522 USDT perps (207 above the liquidity floor get full model evaluation).
- A signal carries `expected_points`, and a bot only opens when points clear the threshold.
- A REJECT is provably non-destructive (hash proof), and a PROMOTE writes a baseline.
- One full testnet lifecycle is observed: signal → claim → order → fill → close → sample stored →
  calibration updated.
- `docs/HANDOFF.md` §2/§3 updated with observed evidence.
