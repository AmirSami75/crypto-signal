# Code walkthrough: how the whole project works

This guide assumes you understand a little about crypto candles, but are new to machine
learning and time-series prediction. Read it once from top to bottom, then keep the function
reference near you while using VS Code.

## The project in one simple sentence

The program studies old, completed crypto candles, learns patterns that were sometimes
followed by price going up, sideways, or down, tests those patterns only on later candles,
and produces a research signal: `BUY`, `HOLD`, or `SELL`.

It does not know the future. It finds statistical patterns in history, and those patterns can
stop working. It also never sends an order to an exchange.

## First: this model is not an LSTM

Version 0.2 uses scikit-learn's `HistGradientBoostingClassifier`. Think of it as a team of
small decision trees. One tree may learn a rule like "momentum is positive and volatility is
not too high." Later trees concentrate on examples the earlier trees got wrong. Their votes
are combined into three probabilities:

```text
SELL  21%
HOLD  33%
BUY   46%
```

With the default 50% confidence requirement, that example becomes `HOLD`, because no
direction has at least 50% probability.

Why begin here instead of with an LSTM?

- it trains quickly on a normal computer;
- it works naturally with a table of indicators;
- it can handle some missing feature values;
- it is easier to debug and provides a strong baseline to beat;
- an LSTM introduces sequences, scaling, more tuning, and more ways to leak future data.

An LSTM can be added later, but it should compete against this exact baseline using the same
chronological test periods and trading costs.

## Six words you need to know

**Candle:** one time bucket containing open, high, low, close, and volume (OHLCV). With a
`1h` interval, every row represents one hour.

**Feature:** a number calculated from the current and earlier candles that the model can see.
Examples are 24-hour momentum, RSI, and recent volatility.

**Label or target:** the answer used while teaching. This project uses `-1` for `SELL`, `0`
for `HOLD`, and `1` for `BUY`.

**Training:** showing the model features together with their known historical labels so that
it can learn rules.

**Prediction:** giving a trained model features without the future answer. It returns the
probability of each class.

**Backtest:** a simulation that converts historical signals into positions and returns while
charging the configured fees and slippage.

## The end-to-end flow

```text
1. Download completed candles through V2RayN
                 |
2. Validate and save a CSV
                 |
3. Calculate 38 past-only features
                 |
4. Look 6 candles ahead to create historical labels
                 |
5. Split old development data -> purge gap -> newest holdout
                 |
6. Walk forward through development data and measure each fold
                 |
7. Test once on the untouched holdout and run the backtest
                 |
8. Train a production model on every labeled row and save it
                 |
9. Calculate features for the newest completed candle and emit a signal
```

The most important rule is that time always moves from left to right. Randomly shuffling
financial time series would let the model learn from tomorrow while pretending to predict
tomorrow.

## What the default target means

The default configuration has:

```toml
prediction_horizon = 6
label_threshold = 0.0035
```

On one-hour candles, the program compares the current close with the close six hours later:

- future return greater than `+0.35%` becomes `BUY` (`1`);
- future return below `-0.35%` becomes `SELL` (`-1`);
- anything from `-0.35%` through `+0.35%` becomes `HOLD` (`0`).

The last six rows do not have a known six-hour future yet, so they are not training examples.
This is correct; assigning `HOLD` to those rows would teach the model a made-up answer.

## The 38 features

`features.py` turns raw candles into a table the model can understand. Every calculation is
causal: it uses the current row and rows before it, never rows after it.

| Group | Examples | What it describes |
|---|---|---|
| Returns and momentum | 1, 3, 6, 12, 24, 72 candles | Recent direction and speed |
| Trend | SMA and EMA ratios, normalized MACD | Price relative to slow/fast trends |
| Risk | rolling volatility, ATR | How violently price is moving |
| Oscillators | RSI, Bollinger z-score, stochastic | Whether price is stretched in its recent range |
| Volume | log change, 24/168-candle ratios | Unusual or changing activity |
| Candle shape | body, range, upper/lower shadows | Buying/selling behavior inside the candle |
| Calendar | sine/cosine of hour and weekday | Repeating time-of-day and weekly behavior |

The 168-candle calculations require a warm-up period. Those early rows cannot yet have all
long-window features, so `make_supervised` removes them.

## How training avoids seeing the future

Assume the supervised data is drawn as one long timeline:

```text
oldest                                                     newest
[----------- development -----------][purge][--- holdout ---]
                                       6 rows      final 20%
```

The last 20% is the strict holdout. It is kept away from training. The six-row purge gap is
the same size as the target horizon; it prevents a development label from using a future
price that belongs to the holdout period.

Inside the development section, five walk-forward folds are used by default:

```text
Fold 1: [train][gap][validate]
Fold 2: [------ train][gap][validate]
Fold 3: [------------- train][gap][validate]
```

Training grows forward in time and validation is always later. The fold results show whether
performance is reasonably stable across different periods instead of coming from one lucky
window.

After cross-validation:

1. an **evaluation model** trains only on development rows;
2. it predicts the untouched holdout exactly once;
3. holdout predictions are backtested with costs;
4. a separate **production model** trains on every labeled row and is saved for new signals.

The scores in the report belong to the evaluation model, not the final production fit. A
model cannot honestly score itself on rows it already learned.

## What the model actually learns

Each historical training row looks conceptually like this:

| momentum_6 | rsi_14 | volatility_24 | ... | correct label six hours later |
|---:|---:|---:|---|---:|
| +0.008 | 0.64 | 0.012 | ... | BUY |
| -0.003 | 0.49 | 0.018 | ... | HOLD |
| -0.012 | 0.29 | 0.026 | ... | SELL |

The gradient-boosted trees repeatedly split feature values to separate the three labels.
Class-balanced sample weights give rare labels more importance, so a common `HOLD` class
does not automatically dominate learning.

For a new candle, `predict_proba` returns a probability for each class. The project aligns
those columns in a fixed `SELL, HOLD, BUY` order, then applies the confidence rule. A `BUY`
or `SELL` is emitted only when that direction reaches `probability_threshold` and beats the
opposite direction. Otherwise the output is `HOLD`.

## Read the metrics like a human

No single metric proves a trading system works.

| Metric | Plain-English meaning |
|---|---|
| Ordinary accuracy | Percentage of all labels predicted correctly. Can look good if one class is very common. |
| Balanced accuracy | Accuracy calculated equally across SELL, HOLD, and BUY. Usually more useful when classes are uneven. |
| Precision | Of all times the model said a class, how often was it right? |
| Recall | Of all real examples of a class, how many did the model find? |
| Macro F1 | Precision/recall score giving each class equal importance. `100%` is perfect. |
| Log loss | Punishes bad probabilities, especially confident wrong answers. Lower is better. |
| Total return | Change in simulated equity over the holdout after configured costs. |
| CAGR | Return expressed as a yearly rate. It is unreliable on short test periods. |
| Sharpe | Annualized return divided by volatility, assuming a zero risk-free rate here. Higher is better, but it can be unstable. |
| Maximum drawdown | Worst peak-to-trough fall. A value of `-25%` means losing one quarter from a prior peak. |
| Exposure | Fraction of time the strategy held a long or short position. |
| Position changes / turnover | How often and how much the position changed. More turnover means more cost sensitivity. |

Compare the ML strategy with buy-and-hold, inspect every validation fold, and remember that
historical success can disappear in live markets.

## Proxy and network path

`config.toml` contains:

```toml
[network]
proxy_url = "http://127.0.0.1:10808"
timeout_seconds = 30
```

`data._get_json` URL-encodes the Binance parameters, creates a request with a user-agent,
builds a `ProxyHandler` that sends both HTTP and HTTPS traffic to that address, and decodes
the JSON response. Start V2RayN before `download`, `run-all`, or an online `signal`.

If your V2RayN HTTP port is different, change the number in both config files you use. A
SOCKS-only listener is not the same thing as an HTTP proxy. If direct access works, use
`proxy_url = "off"`. No API keys or passwords are used by this project.

## Logs: how to watch the program think

The terminal and rotating log file show the same progress. Real-data logs go to
`artifacts/logs/crypto_signal.log`; demo logs go to
`artifacts/demo/logs/crypto_signal.log`.

An ordinary run at `INFO` level shows download pages, row counts, each training stage, every
fold, readable percentages, backtest results, saved files, and total time. `WARNING` calls
attention to issues such as timestamp gaps. `ERROR` includes a full traceback. Change the
level to `DEBUG` to also see individual HTTP request details and internal counts.

Log rotation is controlled by:

```toml
[logging]
level = "INFO"
log_file = "artifacts/logs/crypto_signal.log"
max_bytes = 5000000
backup_count = 3
```

When asking for help, copy the last relevant block from this log, beginning a little before
the first `ERROR` line. Do not paste credentials if you later add private APIs.

## Commands and when to use them

Run these inside the activated virtual environment:

| Command | What it does |
|---|---|
| `crypto-signal --config config.toml download` | Downloads all configured historical closed candles and saves the CSV. |
| `crypto-signal --config config.toml train` | Reuses the CSV, trains, evaluates, backtests, and saves artifacts. |
| `crypto-signal --config config.toml train --refresh` | Downloads fresh history first, then trains. |
| `crypto-signal --config config.toml signal` | Downloads recent candles through the proxy and scores the newest completed candle. |
| `crypto-signal --config config.toml signal --offline` | Uses the local CSV rather than the network. |
| `crypto-signal --config config.toml run-all` | Download, train, and signal in one command. |
| `crypto-signal --config config.demo.toml demo` | Runs the bundled synthetic example without the network. |

Human-readable output is the default. Put `--json` before the command when a program, rather
than a person, will read the output:

```bash
crypto-signal --config config.toml --json train
```

## Configuration classes

`config.py` uses frozen data classes. "Frozen" means settings cannot quietly change halfway
through a run.

| Class | Owns |
|---|---|
| `MarketConfig` | symbol, candle interval, start/end timestamps, CSV path |
| `FeatureConfig` | prediction horizon and label threshold |
| `ModelConfig` | holdout size, folds, confidence threshold, tree hyperparameters |
| `BacktestConfig` | fee, slippage, and long-only/short setting |
| `OutputConfig` | artifact directory |
| `NetworkConfig` | proxy address and HTTP timeout |
| `LoggingConfig` | level, file, rotation size, backup count |
| `AppConfig` | one container holding all sections plus the source TOML path |

`load_config` reads TOML, converts values to the correct Python types, resolves relative
paths from the config file's folder, builds those classes, and calls `validate_config`.

## File and function reference

### `src/crypto_signal/config.py`

- `_resolve`: converts a relative config path into an absolute path.
- `load_config`: reads the TOML file and builds `AppConfig`.
- `validate_config`: stops early when thresholds, splits, timeouts, or logging values are
  impossible.

### `src/crypto_signal/log_setup.py`

- `get_logger`: gives each module a named child logger.
- `configure_logging`: installs the terminal handler and size-rotating file handler.

### `src/crypto_signal/data.py`

- `interval_milliseconds` / `interval_periods_per_year`: convert candle intervals for API
  pagination and annualized metrics.
- `iso_to_milliseconds`: converts an ISO-8601 config timestamp for Binance.
- `_get_json`: performs a JSON GET through the configured V2RayN proxy.
- `_rows_to_frame`: turns Binance arrays into typed, sorted pandas rows and removes an
  unfinished candle.
- `fetch_historical_ohlcv`: requests up to 1,000 candles per page until history is complete.
- `fetch_recent_ohlcv`: requests the newest candles used for a signal.
- `save_ohlcv` / `load_ohlcv`: cache and restore CSV data. Loading accepts mixed ISO-8601
  timestamps with or without fractional seconds.
- `validate_ohlcv`: checks columns, order, duplicates, positive prices, OHLC relationships,
  volume, and missing time buckets.

### `src/crypto_signal/features.py`

- `_rsi` and `_atr`: implement two common technical indicators.
- `make_features`: calculates the 38 causal feature columns.
- `make_target`: looks forward only to create historical teaching labels.
- `make_supervised`: combines candles, features, labels, and removes warm-up/unknown rows.

### `src/crypto_signal/model.py`

- `build_model`: creates the gradient-boosting classifier with chronological early stopping
  disabled.
- `fit_model`: computes class-balanced weights and trains one model.
- `aligned_probabilities`: guarantees probability columns are ordered SELL/HOLD/BUY even if
  a model was trained without one class.
- `probabilities_to_signals`: applies the minimum-confidence rule.
- `classification_metrics`: calculates the classification report, balanced accuracy, macro
  F1, and log loss.
- `walk_forward_validation`: builds chronological folds, trains each model, logs metrics, and
  combines later-period predictions.

### `src/crypto_signal/backtest.py`

- `signals_to_positions`: turns signals into remembered positions. In long-only mode, BUY
  means `1`, SELL means `0`, and HOLD keeps the previous position.
- `performance_metrics`: calculates return, CAGR, volatility, Sharpe, drawdown, hit rate,
  exposure, position changes, and turnover.
- `run_backtest`: applies a signal to the following close-to-close return, charges costs on
  changes and final liquidation, and builds ML and buy-and-hold equity curves.

### `src/crypto_signal/pipeline.py`

- `_json_default` / `write_json`: safely save paths, timestamps, and NumPy values as JSON.
- `download_data`: runs the historical download, cache, validation, and summary.
- `_load_or_download`: chooses between the existing CSV and a refreshed download.
- `_prediction_frame`: joins the true class, probabilities, and chosen signal.
- `_plot_equity`: saves the holdout equity chart.
- `_config_snapshot`: records the exact run settings in metadata.
- `_report_markdown`: creates the short result report.
- `train_and_backtest`: coordinates all seven training stages and saves every artifact.
- `latest_signal`: loads the production model, obtains recent/local candles, calculates the
  latest features, predicts probabilities, and writes `latest_signal.json`.

### `src/crypto_signal/human_output.py`

- `number`, `percent`, and `duration`: convert raw computer values into readable text.
- `format_download_summary`: explains a completed download.
- `format_training_summary`: formats rows, class balance, folds, test metrics, and backtest.
- `format_signal_summary`: displays the signal, price, probabilities, confidence, and source.

### `src/crypto_signal/cli.py`

- `build_parser`: defines every terminal command and option.
- `main`: loads config, starts logging, calls the selected pipeline, chooses human/JSON
  output, and logs a traceback before returning an error.

`__main__.py` allows `python -m crypto_signal`. `__init__.py` stores the project version.

### Scripts, tests, and VS Code files

- `scripts/generate_demo_data.py`: creates deterministic synthetic candles for offline use.
- `tests/ml-engine/`: checks timestamps, the proxy, causal features, inference, model
  versioning, unknown labels, purge gaps, class
  order, position behavior, costs, and output formatting.
- `.vscode/tasks.json`: repeatable setup/test/run commands.
- `.vscode/launch.json`: the choices shown in VS Code's Run and Debug menu.
- `.vscode/settings.json`: tells VS Code to use `.venv` and the source directory.

## Training artifacts

| Artifact | What is inside |
|---|---|
| `model.joblib` | Production model, ordered feature names, and training metadata |
| `metadata.json` | Exact config, data range, class counts, folds, holdout and backtest metrics |
| `REPORT.md` | Short human-readable holdout report |
| `holdout_predictions.csv` | Timestamp, true/predicted class, probabilities, and signal |
| `holdout_backtest.csv` | Position, next return, turnover, cost, strategy return, and equity |
| `equity_curve.png` | ML strategy and buy-and-hold equity on the holdout |
| `latest_signal.json` | Newest signal, probabilities, price, source, and model date |

## A sensible LSTM roadmap

Do not replace the baseline immediately. Add an LSTM as a second model and compare them.

1. Keep this downloader, labels, chronological holdout, costs, and reports unchanged.
2. Turn feature rows into rolling sequences such as the previous 48 or 168 candles.
3. Fit every scaler on training rows only, then apply it to later rows. Fitting a scaler on
   all history leaks information.
4. Create one small LSTM layer, dropout, and a three-unit softmax output.
5. Train each walk-forward fold independently with early stopping based only on that fold's
   later validation segment.
6. Record the same balanced accuracy, macro F1, log loss, and cost-aware backtest metrics.
7. Keep the LSTM only if it is consistently better across folds, the untouched holdout, and
   a new forward paper-trading period after considering its extra complexity.

The sequence must end at the candle whose signal is being decided. The label may look ahead
to teach the past, but no feature or scaler is allowed to look ahead.

## Safe research habits

- Start with the offline demo, then use one-hour or four-hour real candles.
- Never interpret synthetic demo returns as evidence.
- Do not change settings repeatedly until the holdout looks profitable; that indirectly
  trains on the holdout.
- Record each experiment and keep a fresh future paper-trading window.
- Test larger fees and slippage than you expect.
- Check logs for data gaps and failed network fallbacks.
- Treat a signal as uncertain research output, never as guaranteed financial advice.

For installation buttons and screenshots-to-expect in VS Code, continue with
[RUN_IN_VSCODE.md](../RUN_IN_VSCODE.md). For research stages, see
[ROADMAP.md](../ROADMAP.md).
