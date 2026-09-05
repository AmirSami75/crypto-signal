# Strategy League

First ranked run of the Strategy Zoo (Phase 1, T1.4). Honest numbers: the ranking is decided on
**walk-forward TEST-split returns only** — training-era figures stay in the JSON artifact for audit.
A strategy is a candidate for adoption only if it shows positive net return on the TEST split.

## Run metadata

- **Date:** 2026-09-05
- **Command:** `cd src/signal-ml && .venv/bin/python -m crypto_signal --config config.toml run-league --symbols BTCUSDT,ETHUSDT,SOLUSDT --intervals 1h,15m`
- **Artifact:** `src/signal-ml/artifacts/league/20260905T120831Z.json` (54 rows = 9 strategies × 3 symbols × 2 intervals)
- **Data:** Binance spot candles, 2020-01-01 → present (1h ≈ 58k candles, 15m ≈ 210–234k candles per symbol)
- **Walk-forward:** 40% train era + 3 test eras, purged by `max_horizon = 24` candles
- **Brackets:** ATR-native 1.5 / 1.0 (TP/SL), fees 0.10% + slippage 0.05%, one position at a time
- **Verdicts:** ROBUST (test ≥ ½ train) / MODERATE (test ≥ 0) / WEAK (test ≤ 0) / OVERFITTED (train ≫ test)

## Top-5 (TEST split)

| Rank | Strategy | Symbol | TF | Verdict | Trades | Win % | Return % | Profit factor | Sharpe | Max DD % |
|-----:|----------|--------|----|---------|-------:|------:|---------:|--------------:|-------:|---------:|
| 1 | rsi_pullback | SOLUSDT | 15m | MODERATE | 6 | 83.3 | +0.94 | 2.42 | 0.64 | -0.68 |
| 2 | rsi_pullback | ETHUSDT | 15m | MODERATE | 8 | 62.5 | +0.71 | 0.95 | 0.30 | -1.00 |
| 3 | rsi_pullback | ETHUSDT | 1h | MODERATE | 1 | 100.0 | +0.40 | n/a | 0.29 | 0.00 |
| 4 | rsi_pullback | SOLUSDT | 1h | MODERATE | 1 | 100.0 | +0.37 | n/a | 0.30 | 0.00 |
| 5 | rsi_pullback | BTCUSDT | 1h | WEAK | 2 | 50.0 | -0.12 | 0.00 | -0.00 | -1.11 |

## Full table (TEST split)

| Rank | Strategy | Symbol | TF | Verdict | Trades | Win % | Return % | Profit factor | Sharpe | Max DD % |
|-----:|----------|--------|----|---------|-------:|------:|---------:|--------------:|-------:|---------:|
| 6 | rsi_pullback | BTCUSDT | 15m | WEAK | 5 | 20.0 | -1.57 | 0.00 | -0.29 | -2.44 |
| 7 | ema_cross | SOLUSDT | 1h | WEAK | 1037 | 44.6 | -39.31 | 0.84 | -1.39 | -49.57 |
| 8 | supertrend | SOLUSDT | 1h | WEAK | 739 | 41.0 | -49.92 | 0.72 | -2.15 | -57.21 |
| 9 | supertrend | ETHUSDT | 1h | WEAK | 813 | 39.4 | -57.01 | 0.59 | -3.41 | -64.93 |
| 10 | supertrend | BTCUSDT | 1h | WEAK | 802 | 38.0 | -57.44 | 0.47 | -4.72 | -62.60 |
| 11 | keltner_breakout | ETHUSDT | 1h | WEAK | 1151 | 40.1 | -63.27 | 0.64 | -3.41 | -70.97 |
| 12 | keltner_breakout | BTCUSDT | 1h | WEAK | 1209 | 41.4 | -64.36 | 0.57 | -4.49 | -69.67 |
| 13 | rsi | BTCUSDT | 1h | WEAK | 940 | 37.0 | -64.43 | 0.47 | -5.14 | -69.87 |
| 14 | rsi | SOLUSDT | 1h | WEAK | 802 | 36.4 | -65.22 | 0.63 | -3.26 | -78.14 |
| 15 | rsi | ETHUSDT | 1h | WEAK | 957 | 38.0 | -65.85 | 0.57 | -3.95 | -76.69 |
| 16 | ema_cross | BTCUSDT | 1h | WEAK | 1173 | 38.6 | -67.78 | 0.47 | -5.77 | -75.87 |
| 17 | ema_cross | ETHUSDT | 1h | WEAK | 1220 | 40.3 | -67.86 | 0.60 | -4.07 | -70.89 |
| 18 | keltner_breakout | SOLUSDT | 1h | WEAK | 1087 | 38.2 | -75.88 | 0.63 | -3.74 | -85.58 |
| 19 | macd | ETHUSDT | 1h | WEAK | 2324 | 42.0 | -81.97 | 0.67 | -4.42 | -90.08 |
| 20 | bollinger | SOLUSDT | 1h | WEAK | 1738 | 38.4 | -82.69 | 0.69 | -3.77 | -86.50 |
| 21 | bollinger | BTCUSDT | 1h | WEAK | 1889 | 38.3 | -85.71 | 0.47 | -7.26 | -86.90 |
| 22 | donchian | ETHUSDT | 1h | WEAK | 2020 | 39.8 | -85.86 | 0.59 | -5.39 | -92.07 |
| 23 | macd | SOLUSDT | 1h | WEAK | 2119 | 40.5 | -86.29 | 0.71 | -3.83 | -92.61 |
| 24 | donchian | BTCUSDT | 1h | WEAK | 2002 | 38.3 | -87.88 | 0.47 | -7.38 | -90.98 |
| 25 | bollinger | ETHUSDT | 1h | WEAK | 1931 | 37.9 | -88.32 | 0.55 | -5.95 | -91.23 |
| 26 | macd | BTCUSDT | 1h | WEAK | 2307 | 38.4 | -89.53 | 0.49 | -7.65 | -91.77 |
| 27 | donchian | SOLUSDT | 1h | WEAK | 1970 | 39.5 | -90.29 | 0.65 | -4.64 | -94.25 |
| 28 | rsi | SOLUSDT | 15m | WEAK | 2971 | 40.5 | -91.17 | 0.56 | -7.41 | -94.19 |
| 29 | supertrend | SOLUSDT | 15m | WEAK | 2917 | 41.2 | -92.95 | 0.50 | -8.43 | -94.91 |
| 30 | supertrend | ETHUSDT | 15m | WEAK | 3206 | 37.2 | -94.71 | 0.36 | -11.81 | -96.18 |
| 31 | supertrend | BTCUSDT | 15m | WEAK | 3331 | 32.1 | -95.60 | 0.24 | -15.39 | -97.25 |
| 32 | rsi | BTCUSDT | 15m | WEAK | 3131 | 33.2 | -95.66 | 0.27 | -14.10 | -96.12 |
| 33 | rsi | ETHUSDT | 15m | WEAK | 3163 | 36.6 | -97.11 | 0.35 | -11.44 | -97.31 |
| 34 | macd | SOLUSDT | 15m | WEAK | 6018 | 38.7 | -97.54 | 0.38 | -14.59 | -97.83 |
| 35 | keltner_breakout | SOLUSDT | 15m | WEAK | 2729 | 39.5 | -98.55 | 0.34 | -14.83 | -98.72 |
| 36 | bollinger | SOLUSDT | 15m | WEAK | 5629 | 38.4 | -98.62 | 0.38 | -14.83 | -98.80 |
| 37 | keltner_breakout | ETHUSDT | 15m | WEAK | 3172 | 42.1 | -98.85 | 0.32 | -14.53 | -99.05 |
| 38 | bollinger | ETHUSDT | 15m | WEAK | 5912 | 37.9 | -99.03 | 0.34 | -14.84 | -99.16 |
| 39 | keltner_breakout | BTCUSDT | 15m | WEAK | 2838 | 39.4 | -99.17 | 0.30 | -15.62 | -99.31 |
| 40 | bollinger | BTCUSDT | 15m | WEAK | 6307 | 38.7 | -99.19 | 0.35 | -15.09 | -99.31 |
| 41 | donchian | SOLUSDT | 15m | WEAK | 5125 | 38.8 | -99.55 | 0.36 | -14.16 | -99.63 |
| 42 | donchian | ETHUSDT | 15m | WEAK | 5917 | 39.9 | -99.76 | 0.33 | -15.68 | -99.82 |
| 43 | donchian | BTCUSDT | 15m | WEAK | 5942 | 38.0 | -99.78 | 0.27 | -16.35 | -99.87 |
| 44 | ema_cross | SOLUSDT | 15m | WEAK | 5105 | 41.3 | -99.80 | 0.31 | -16.04 | -99.87 |
| 45 | ema_cross | ETHUSDT | 15m | WEAK | 5541 | 40.0 | -99.83 | 0.30 | -17.78 | -99.89 |
| 46 | ema_cross | BTCUSDT | 15m | WEAK | 5760 | 38.7 | -99.84 | 0.27 | -18.32 | -99.89 |
| 47 | macd | BTCUSDT | 15m | WEAK | 9582 | 32.8 | -99.99 | 0.19 | -19.19 | -99.99 |
| 48 | macd | ETHUSDT | 15m | WEAK | 9672 | 36.3 | -99.99 | 0.23 | -18.41 | -99.99 |
| 49 | macd | SOLUSDT | 15m | WEAK | 6307 | 38.7 | -99.99 | 0.27 | -16.60 | -99.98 |
| 50 | triple_ema | SOLUSDT | 15m | WEAK | 15162 | 39.7 | -100.00 | 0.30 | -16.13 | -100.00 |
| 51 | triple_ema | BTCUSDT | 15m | WEAK | 16391 | 32.3 | -100.00 | 0.22 | -18.24 | -100.00 |
| 52 | triple_ema | ETHUSDT | 15m | WEAK | 16408 | 36.8 | -100.00 | 0.26 | -17.10 | -100.00 |

## Honest reading

- **No strategy is adoptable.** The only positive TEST-split rows are `rsi_pullback` with 1–8 trades
  — statistically nothing. 48 of 54 rows are deeply negative after fees + slippage.
- **The zoo confirms the bracket sweep.** Just as the ML model had no profitable bracket config
  (2026-09-01), none of the 9 indicator strategies clears costs out of sample. Fees + slippage
  (~0.25–0.35% round trip) against 1.5/1.0 ATR brackets need a resolved win rate ≈ 45–55%; these
  rules run 32–44%.
- **15m is a fee grinder.** The same strategies lose 2–5× more on 15m than 1h: more trades, same
  per-trade cost, thinner edge. Trend followers (supertrend, triple_ema, ema_cross, donchian)
  whipsaw themselves to -100% (equity ruin) on 15m.
- **rsi_pullback's positive verdicts are a sample-size warning, not an edge.** 6–8 trades cannot
  support adoption; its train-era returns are also ≈ 0, so even MODERATE means "unproven".

## Gate

Nothing here graduates to a bot. Per the plan's honesty gate: a strategy must show positive net
TEST-split return before it can be wired to `StrategyKey` — and even then, only with enough trades
to make the number meaningful. Next lever if this is revisited: wider bracket grid and
per-strategy parameter selection *inside* the train era only, so the test eras stay untouched.
