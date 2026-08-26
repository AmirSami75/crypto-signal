# Auto-Trading Bot on Bitunix — Delivery Plan

## Reality check first (important)

**Bitunix has no demo/testnet environment.** Verified July 2026: their help center documents
no demo mode, no testnet, no simulated funds. The official SDK points only at
`https://fapi.bitunix.com`. Third-party sites advertising "Bitunix demo trading" are
third-party simulators, not Bitunix.

So "auto-trading with demo functionality" is delivered as a **two-layer demo**:

1. **PAPER mode** — our own deterministic simulator (already built) driven by **real live
   Bitunix market data**. Orders, fills, fees, slippage are simulated; prices are real.
   This is the default "demo" and costs nothing.
2. **SANDBOX→LIVE progression** — when you're ready, the same bot flips to real orders on
   your key with hard caps (tiny notional, max drawdown, kill switch). Your API key has
   trade permission, so this path is wired but gated behind explicit start + limits.

Your key (`df0d9fa3…`) is stored AES-GCM sealed in the DB via the Connections page.

---

## Phase A — Wire the key & go live in PAPER against Bitunix data  *(~half day)*

| # | Task | Detail |
|---|------|--------|
| A1 | Store the connection | Connections page → venue Bitunix → paste key/secret. Sealed with AES-GCM, preview-only display |
| A2 | Create the bot | SANDBOX→PAPER bot on BTCUSDT 1h pinned to that connection; TP/SL/limits from safety policy |
| A3 | Fix credential flow for PAPER | Paper broker ignores credentials today; pass them so balance reads use real Bitunix account when available |
| A4 | Verify end-to-end | Ticks → engine consult → decision → paper fill → position → P&L on dashboard |

**Exit:** bot running autonomously on real Bitunix prices, zero financial risk.

## Phase B — Monitoring dashboard  *(~1–2 days)*

| # | Task | Detail |
|---|------|--------|
| B1 | Live position card | Unrealized P&L, mark price, TP/SL distance — auto-refreshing |
| B2 | Equity curve | Realized+unrealized over time from BotPositions snapshots |
| B3 | Tick heartbeat | Last-tick age indicator; stale >2× cadence turns amber then red |
| B4 | Decision log stream | Live-updating decisions tab (action, confidence, reason) |
| B5 | Risk & alert events panel | Kill-switch blocks, risk denials, faults surfaced as alerts |
| B6 | Bot health banner | Faulted/stale/active state prominent; one-click stop |

**Exit:** open the dashboard, see everything about the bot without touching the DB.

## Phase C — Self-learning loop  *(~3–5 days)*

| # | Task | Detail |
|---|------|--------|
| C1 | Outcome capture | Join each StrategyDecision to its position outcome (TP/SL/timeout) — table + backfill job |
| C2 | Prediction-vs-actual report | Calibration by confidence bucket, per-symbol hit rates, decay detection |
| C3 | Rolling retrain dataset | Export candles + labels including newly closed candles since last train |
| C4 | Scheduled retrain | Weekly host-side train run producing `_pooled_vN` candidates |
| C5 | Promotion gate | Candidate beats incumbent on walk-forward + bracket backtest → auto-promote; else report only |
| C6 | Version pinning UX | Bot form already pins `expectedModelVersion`; surface new-version prompt on dashboard |

**Exit:** the model retrains on what the bot actually experienced, and only improves ship.

## Phase D — Remaining backlog  *(ongoing, ordered)*

1. EX-006 circuit breaker + backoff (repeated failures disable execution)
2. RISK-003 full freshness checks (candle gaps, stale mark price)
3. TEST-001 failure-injection suite (automated, not manual probes)
4. FE-006 wallet-wide equity/drawdown view
5. PAPER-006 formal 30-day soak
6. TEST-003 alerts/incident workflow
7. ML-005 benchmark strategies, ML-006 experiment ledger
8. TEST-004 runbooks
9. Phase 8 (restricted live) — only after 4-week clean soak + your sign-off

---

## Immediate next actions (say the word)

1. I store your Bitunix key as the sealed connection (or you paste it on the Connections page yourself — safer, and rotate later since it appeared in a screenshot)
2. Create the PAPER-on-Bitunix-data bot and switch it on
3. Start Phase B monitoring build

**Safety unchanged:** signals are evidence not authorization; every intent passes the
risk engine; kill switch is one click away; nothing touches LIVE without your explicit
start plus caps.
