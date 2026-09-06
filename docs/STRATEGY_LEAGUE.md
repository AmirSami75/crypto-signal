# Strategy League — walk-forward ranking of the Strategy Zoo

**Run:** 2026-09-05T12:08:31Z · **Artifact:** `src/signal-ml/artifacts/league/20260905T120831Z.json`
**Universe:** BTCUSDT, ETHUSDT, SOLUSDT × 1h, 15m (9 strategies × 3 symbols × 2 intervals = 54 rows)
**Costs:** fee 0.10% + slippage 0.05% per side · **Validation:** purged walk-forward, 3 test eras, overfitting verdict per (strategy, symbol, interval)

## Verdict scale

- **ROBUST** — test return ≥ 0.5 × train return
- **MODERATE** — test return ≥ 0 (some edge survives out-of-sample)
- **WEAK / OVERFIT** — test return < 0 (edge dies out-of-sample)

**All numbers below are TEST-split, net of fees and slippage.** Train-split numbers stay in the JSON artifact for audit.

## Result: 50 of 54 combinations are WEAK. The zoo has no real edge at these costs.

The pattern is mechanical, not strategic: every high-frequency strategy bleeds out almost exactly at
the rate fees accumulate. `triple_ema` 15m traded ~16,000 times and returned −100.00% on all three
symbols; `macd`, `donchian`, `bollinger` all sit at −99%+. On 1h the same strategies lose "only"
40–65% — still WEAK. This independently reproduces the bracket-sweep conclusion
(`docs/ml-improvement-plan.md`): indicator entries alone do not carry costs; edge must come from
selectivity (fewer, better trades), not from indicator choice.

## Top of the table (only positive TEST returns)

| Rank | Strategy | Symbol | TF | Trades | Win% | Net return | PF | Sharpe | Max DD | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | rsi_pullback | SOLUSDT | 15m | 6 | 83.3% | **+0.94%** | 2.42 | 0.64 | −0.68% | MODERATE |
| 2 | rsi_pullback | ETHUSDT | 15m | 8 | 62.5% | **+0.71%** | 0.95 | 0.30 | −1.00% | MODERATE |
| 3 | rsi_pullback | BTCUSDT | 15m | 5 | 20.0% | −1.57% | 0.00 | −0.29 | −2.44% | WEAK |

## Why the winner is still not adoptable — read before starting a scanner bot on it

1. **Sample size is 5–8 trades.** One lucky era dominates. The 95% CI on a 6-trade 83% win rate
   spans roughly 36–100% — statistically indistinguishable from a coin with fees.
2. **Train/test inconsistency.** SOLUSDT rsi_pullback *lost* −1.45% in-sample and made +0.94%
   out-of-sample (ratio −0.65). A real edge earns in both; sign-flipping across splits is noise.
3. **The third era took 0 trades.** Selectivity is the point, but 0 trades in an era means we
   cannot yet tell "rare and good" from "stopped firing".
4. **Verdict MODERATE, not ROBUST.** Nothing in the zoo reached ROBUST.

**Adoption gate (standing):** a strategy is adoptable only when it shows positive net TEST return
with ≥ 30 test trades AND a ROBUST walk-forward verdict. No strategy currently passes. The
bracket-sweep conclusion applies unchanged: the scanner and zoo are *infrastructure* — they are the
delivery mechanism for an edge that the models must still find. A Scanner-kind bot running
`rsi_pullback` on 15m Sandbox is a legitimate *observation* experiment (does the claim path work
end-to-end?), not an edge bet — and it must stay behind the Sandbox gate.

## Repeat the run

```bash
cd src/signal-ml
.venv/bin/python -m crypto_signal run-league --config config.toml \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT --intervals 1h,15m --refresh
```

Add `--resume <partial.json>` to continue an interrupted run. Update this doc with each new run's
date stamp; keep TEST-split numbers only in the tables.
