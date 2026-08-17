# Research basis and design decisions

Sources were checked on 16 August 2026. Primary documentation and original research are
preferred below.

## Market data

1. [Binance Spot REST — Kline/Candlestick data](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/market)
   documents `/api/v3/klines`, its OHLCV fields, a maximum of 1,000 bars per request,
   supported intervals, UTC behavior, and request weight. The downloader paginates this
   public endpoint and discards an unfinished last candle.
2. [Binance Public Data repository](https://github.com/binance/binance-public-data)
   provides daily/monthly archives and checksums. It also warns that spot archive
   timestamps from 1 January 2025 onward are in microseconds. The current implementation
   uses the REST endpoint; bulk archives are the recommended scale-up path.
3. [Coinbase Exchange candle documentation](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles)
   is useful for a future second source. It warns that historical candles can be incomplete,
   intervals without ticks may be absent, and one request is limited to 300 candles. This
   reinforces the need for explicit gap validation rather than assuming every venue is a
   perfect regular grid.

## Validation and leakage

4. [scikit-learn `TimeSeriesSplit`](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)
   states that ordinary cross-validation can train on future data and evaluate on past data.
   Its `gap` parameter excludes samples from the end of each training fold. This project
   sets the gap equal to the future-return label horizon.
5. [scikit-learn common pitfalls](https://scikit-learn.org/stable/common_pitfalls.html)
   defines leakage as using information unavailable at prediction time and says test data
   must not be used for model choices or fitted preprocessing. The project uses causal
   rolling features, no fitted preprocessing, a development-only walk-forward stage, and an
   untouched chronological holdout.
6. Bailey, Borwein, López de Prado and Zhu,
   [“The Probability of Backtest Overfitting”](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253),
   develops a framework for estimating the risk that selecting strategies on historical
   simulations produces an overfit winner. The roadmap therefore requires an experiment
   ledger, a small predeclared test matrix, and forward paper trading.

## Model choice

7. [scikit-learn `HistGradientBoostingClassifier`](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html)
   is a nonlinear tabular classifier with native missing-value support and efficient training
   for larger datasets. It is a sensible baseline for mixed momentum, volatility, volume and
   calendar features. Automatic early stopping is disabled because its internal validation
   split is not designed as a chronological market split.

The first model is intentionally not an LSTM, Transformer, or reinforcement-learning agent.
With only OHLCV features, complex models make it easier to fit noise and harder to diagnose
timing errors. They are roadmap experiments, not starting assumptions.

## Risk

8. The [U.S. CFTC customer advisory on virtual-currency trading](https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/understand_risks_of_virtual_currency.html)
   highlights volatility, flash crashes, manipulation, cyber/platform risks, and the way
   leverage amplifies losses. It also states that no trading strategy is guaranteed and that
   speculation should use only money one can afford to lose. Accordingly, v0.2 is long-only,
   signal-only, and contains no exchange credentials or execution path.

## Remaining limitations

- OHLCV does not contain the spread, queue position, order-book depth, or actual fills.
- The backtest uses configured fee/slippage rates; real costs vary by venue, account and time.
- Crypto regimes change, so historical correlations and calibrated probabilities decay.
- The neutral threshold and probability threshold are research choices, not universal values.
- A single strict holdout is still finite evidence. Forward paper trading is mandatory.
- The final production model is retrained on all labeled rows only after evaluation. Its future
  signals are not part of the historical holdout score.
