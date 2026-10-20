# E13 Strategy-Mixture Stacking Ensemble — Plan

> For Hermes: implement task-by-task; honest gate decides.

**Goal:** Test whether classic TradingView-style strategy signals, stacked as meta-features into the incumbent HGB, carry direction the raw features lack.

**Architecture:** Level-0 = existing `crypto_signal/strategies/` (rsi, macd, ema_cross, bollinger, donchian, keltner_breakout, supertrend, triple_ema) emitting per-candle votes (−1/0/+1); Level-1 = HGB on [42 production features + 8 votes + vote agreement count]; same fee-aware labels, same strict holdout + purge, E8-upgrade gate.

## Why no TradingView MCP install (verified 2026-09-10)

- `ali-rajabpour/tradingview-mcp`: fetches chart **snapshot images** via Playwright, needs TV session cookies — no strategy code, no training-usable data.
- `cklose2000/pinescript-mcp-server`: Pine **authoring/validation** tooling, not a strategy library fetcher.
- There is **no legitimate bulk "fetch all strategies"**: the public Pine library has no bulk API; scraping it violates TradingView ToS and the scripts' licenses. The 8 classic strategies in-repo already cover the public-library archetypes (momentum, trend, breakout, volatility).
- Market data via TV MCP is redundant: Binance Vision bulk (already validated) is cleaner and free.

If a TV MCP is still wanted for ad-hoc chart checks: `hermes config set` a `mcp_servers.tradingview` stdio entry per `references/native-mcp.md`, restart agent. Not needed for E13.

## Tasks

1. **Audit strategy interfaces** — read `src/signal-ml/src/crypto_signal/strategies/*.py`; record each callable's signature and vote convention; normalize to {−1,0,+1} per candle with a shared adapter + unit tests (causality: vote[t] uses candles ≤ t only).
2. **Build stacked dataset** — `research_lab/experiments/run_e13.py`: production 1h universe (35 sym), fee-aware labels (TP 1.5/SL 1.0, H=24, futures costs), features = 42 production + 8 votes + agreement; strict 20% holdout, purge.
3. **Ablation gate** — HGB stacked vs HGB production-only on identical rows (this isolates the mixture's value; E6 rule). E8-upgrade gate on the difference: sequential economics, CI, concentration, 20× null.
4. **Verdict + ledger** — PASS only if stacked beats production-only on LL margin AND sequential expectancy with ≥30 trades; else REJECT (mixture adds nothing — consistent with E0–E9 if indicators share the same exhausted information).

**Prior:** ~80% REJECT — indicators are deterministic functions of the same OHLCV the HGB already sees; stacking rarely adds information, only reshapes it. The value of E13 is closing the "but classic strategies" question with a receipt.

**Files:** create `run_e13.py`, `E13_RESULT.md`, `e13_meta.json`; append LEDGER; modify nothing in serving path.
