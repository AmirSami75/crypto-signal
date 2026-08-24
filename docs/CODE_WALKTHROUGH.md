# Code walkthrough: how the whole project works

This guide assumes you understand a little about crypto candles, but are new to machine
learning and time-series prediction. Read it once from top to bottom, then keep the function
reference near you while using VS Code.

> **Which pipeline this describes.** Everything below is the **barrier-conditional** pipeline — the
> one the gRPC engine serves. It answers: "if I place a bracket with take-profit `p`% and stop-loss
> `s`%, which side does the price path reach first?", returning `LONG` / `SHORT` / `FLAT` with entry,
> take-profit and stop-loss prices and a calibrated probability.
>
> A **legacy close-to-close** pipeline still exists behind the `-legacy` commands: "will the price be
> more than 0.35% higher six candles from now", answered as `BUY` / `HOLD` / `SELL`. It is kept as
> the baseline the barrier model's numbers are compared against, and it is the gentler thing to read
> first — one row per candle, one fixed question, one label. The two differ in ways that matter to a
> reader of this document:
>
> | | barrier-conditional (below) | legacy close-to-close (`-legacy`) |
> | --- | --- | --- |
> | Question | the take-profit / stop-loss pair the caller asks for | fixed ±0.35% at a fixed horizon |
> | Label | which barrier the price path touched first | sign of one future return |
> | Rows | one per candle *per barrier pair, per side* | one per candle |
> | Short side | `SHORT`, a real position with its own bracket | `SELL`, meaning exit to cash |
> | Output | a direction, a bracket, and a calibrated P(take-profit first) | a class |
> | Markets | one pooled model answers any of them | one model, one market |
>
> Where a section applies only to the legacy path, it says so. `src/crypto_signal/labeling/` and
> `src/crypto_signal/evaluation/` each hold both implementations side by side, and
> `src/signal-ml/README.md` describes the serving engine.

## The project in one simple sentence

The program studies old, completed crypto candles; learns which bracket bets — a take-profit and a
stop-loss, at distances the caller chooses — historically reached their target before their stop;
tests that only on later candles; and answers one question on demand: **which side to take, at what
prices, and how confident it is.**

It does not know the future. It finds statistical patterns in history, and those patterns can stop
working. It also never sends an order to an exchange — it returns advice, and a separate service
decides whether to act on it.

## First: this model is not an LSTM

Version 0.2 uses scikit-learn's `HistGradientBoostingClassifier`. Think of it as a team of
small decision trees. One tree may learn a rule like "momentum is positive and volatility is
not too high." Later trees concentrate on examples the earlier trees got wrong. Their votes
are combined into three probabilities:

```text
stop-loss first   21%
neither barrier   33%
take-profit first 46%
```

With the default 50% confidence requirement, that bet is declined: nothing reaches the floor, so the
answer is `FLAT`.

Why begin here instead of with an LSTM?

- it trains quickly on a normal computer;
- it works naturally with a table of indicators;
- it can handle some missing feature values;
- it is easier to debug and provides a strong baseline to beat;
- an LSTM introduces sequences, scaling, more tuning, and more ways to leak future data.

An LSTM can be added later, but it should compete against this exact baseline using the same
chronological test periods and trading costs.

## Eight words you need to know

**Candle:** one time bucket containing open, high, low, close, and volume (OHLCV). With a
`1h` interval, every row represents one hour.

**Feature:** a number calculated from the current and earlier candles that the model can see.
Examples are 24-hour momentum, RSI, and recent volatility.

**Label or target:** the answer used while teaching. For the barrier model it is the outcome of one
bracket bet: `1` the take-profit came first, `-1` the stop-loss came first, `0` neither inside the
horizon. (The legacy model reuses the same three numbers to mean `BUY` / `HOLD` / `SELL`, which is
why the barrier report renames them before writing them down.)

**Bracket:** a take-profit price and a stop-loss price placed on the same position, so the trade
closes at whichever is reached first. "Bracket-conditional" means the model is *told* those two
distances and asked about that specific bet.

**ATR:** average true range — how far this market typically moves in one candle. Barrier distances
are expressed in ATR units because "1.5 ATR" is comparable across markets, while "2%" is not.

**Training:** showing the model features together with their known historical labels so that
it can learn rules.

**Prediction:** giving a trained model features without the future answer. It returns the
probability of each class.

**Backtest:** a simulation that replays historical signals as trades — opening at the next candle's
open, closing at whichever barrier the path reached first — while charging the configured fees and
slippage.

## The end-to-end flow

```text
1. Download completed candles for every configured market
                 |
2. Validate and save one CSV per market
                 |
3. Calculate 38 past-only, scale-free features
                 |
4. Emit each candle once per (barrier pair, side) and walk its
   forward path to see which barrier it reached first
                 |
5. Split old development rows -> purge gap -> newest holdout,
   splitting on candle opens so no candle straddles the boundary
                 |
6. Walk forward through development data and measure each fold
                 |
7. Fit on one block, measure a calibration correction on the next,
   and ship the correction only if it earned its place
                 |
8. Test once on the untouched holdout, then walk a bracket backtest
   over it candle by candle
                 |
9. Write one joblib bundle per served scope into the registry
                 |
10. Ask the bundle about a requested bet on the newest closed candle
```

The most important rule is that time always moves from left to right. Randomly shuffling
financial time series would let the model learn from tomorrow while pretending to predict
tomorrow.

Step 4 is what makes step 10 answer *any* bet rather than one hard-coded one, and it is also
where the subtlest leak lives. Every barrier variant of one candle shares that candle's features
and its forward window, so a split on row positions would train on some variants of a candle and
score on the rest — the same candle on both sides of the line. That is why steps 5, 6 and 7 all
split on unique candle opens.

## What the label means

The barrier model's label is not "did price go up". It is "which of *your two* prices did the
path reach first". The default configuration has:

```toml
[barrier]
max_horizon = 24
grid_atr = [0.5, 1.0, 1.5, 2.0, 3.0]
pairs_per_candle = 3
```

For one candle, one take-profit distance, one stop-loss distance and one side, the labeller walks
forward up to `max_horizon` candles:

- the take-profit is touched first: `1`;
- the stop-loss is touched first: `-1`;
- neither is touched inside the horizon: `0`.

Three details carry real weight:

**The label speaks from the bet's own point of view.** For a short, `1` still means "the
take-profit came first" — it is just that the take-profit is *below* the entry. Both sides
therefore read the same `P(1)`, and a `direction_sign` feature tells the model which side it is
being asked about. The two sides are *not* the same question with the two distances swapped:
a candle whose high touches one barrier and whose low touches the other resolves as a loss for
both sides, and swapping distances would score it as a short win — manufacturing profit that
never existed.

**An ambiguous candle is settled as the loss.** When one candle's high reaches the target and its
low reaches the stop, the order inside that candle is unknowable from OHLC. Assuming the good
outcome is how a backtest invents profit, so the labeller and the backtester both assume the bad
one, using the same code in `domain/barriers.py` so they cannot drift apart.

**Distances are in ATR units, not percent.** A 2% move is routine on one market and rare on
another; "1.5 ATR" means the same thing on both. That is what lets one pooled model answer for a
market it never trained on. The barriers are set from the ATR at the candle being labelled, never
from a later one.

Because the barrier pair is an *input*, one candle becomes several training rows —
`pairs_per_candle` sampled pairs, each for both sides. The last `max_horizon` rows have no
resolved future yet, so they are not training examples; assigning them `0` would teach the model
a made-up answer.

The legacy close-to-close model still uses the older `prediction_horizon = 6` /
`label_threshold = 0.0035` target, where a `+0.35%` move over six candles is `BUY`. It is kept as
the baseline the barrier model is compared against.

## The 38 features

`features/builder.py` turns raw candles into a table the model can understand. Every calculation is
causal: it uses the current row and rows before it, never rows after it.

Every one of them is also **scale-free** — a ratio, a log return, a z-score or a normalized
oscillator. Not one carries an absolute price. That is the property that makes a pooled model
possible: a model that had learned "BTC trades near 60,000" would have nothing to say about a
market priced at 0.15, whereas "this candle closed 1.2 standard deviations above its 20-candle
mean" means the same thing everywhere.

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
long-window features, so the labeller drops them. This is also where the server's
`ML_MINIMUM_CANDLES` comes from: a request has to carry enough history for the newest feature row
to be real rather than half-warm.

The barrier model then adds four more columns to these 38 — `take_profit_atr`, `stop_loss_atr`,
`risk_reward_ratio` and `direction_sign` — which are the bet itself, and the reason one model can
answer any bracket. That is the 42 features the training log reports.

## How training avoids seeing the future

Assume the labelled data is drawn as one long timeline:

```text
oldest                                                       newest
[------------ development ------------][purge][--- holdout ---]
                                     24 candles     final 20%
```

The last 20% is the strict holdout, kept away from every stage of fitting. The purge gap is
`max_horizon` candles wide — the furthest a barrier label can look ahead — so a development label
cannot resolve using a price that belongs to the holdout period.

Inside development, five walk-forward folds are used by default:

```text
Fold 1: [train][gap][validate]
Fold 2: [------ train][gap][validate]
Fold 3: [------------- train][gap][validate]
```

Training grows forward in time and validation is always later. The fold results show whether
performance is reasonably stable across periods instead of coming from one lucky window.

**Every one of these splits is on unique candle opens, not on row positions.** This is the leak the
barrier model introduces and the one worth understanding. One candle becomes several rows — one per
sampled barrier pair, per side — and every one of those rows shares the same features and the same
forward window. Split by row position and the model trains on some variants of a candle and is
scored on the rest: near-duplicate rows on both sides of the line, which reports a skill that is
really memorisation. `TimeGroupedSplit` therefore splits the *timestamps* and selects rows by
timestamp membership, and `candles_between` asserts the resulting gap is real.

### The four blocks, and why the shipped model is the measured model

A raw gradient-boosting score is not a probability, and the .NET risk engine thresholds on
confidence — so calibration is not cosmetic here. Development is carved into three chronological
blocks with a purge between each:

```text
[--- fit 60% ---][purge][- calibrate 20% -][purge][- assess 20% -]
```

1. the estimator fits on the first block;
2. a monotone (isotonic) correction is measured on the second;
3. both the corrected and uncorrected candidates are assessed on the third, which neither was
   fitted to;
4. whichever wins there is the artifact that ships, and it is then scored **once** on the strict
   holdout.

The correction only ships if it actually lowers error *in the decision region* — above the
confidence floor a caller would trade on — without emptying that region. On this model it usually
loses: a monotone map cannot add resolution, only remove it, so on an already-calibrated model it
flattens the top of the range instead of fixing it. The report says which candidate shipped, and
`REPORT.md` distinguishes what was *attempted* from what was *selected*, because "isotonic" printed
alone reads as "this model is calibrated" even on the runs where the correction was measured,
judged worse, and discarded.

The order matters: the model that shipped is the model that was measured. Fitting a fresh
"production" model on every row afterwards — which the legacy pipeline does — would mean the
numbers in the report describe an artifact that no longer exists.

## What the model actually learns

Each barrier training row looks conceptually like this:

| momentum_6 | rsi_14 | volatility_24 | ... | tp_atr | sl_atr | direction | outcome |
|---:|---:|---:|---|---:|---:|---:|---:|
| +0.008 | 0.64 | 0.012 | ... | 1.5 | 1.0 | +1 (long) | `1` target first |
| +0.008 | 0.64 | 0.012 | ... | 3.0 | 1.0 | +1 (long) | `-1` stop first |
| +0.008 | 0.64 | 0.012 | ... | 1.5 | 1.0 | -1 (short) | `-1` stop first |
| -0.012 | 0.29 | 0.026 | ... | 1.0 | 2.0 | -1 (short) | `0` neither |

Note rows one and two: the same candle, the same market state, opposite outcomes — because the bet
was different. That is the whole design. The model is not learning "will price rise", it is
learning "does a bet of *this shape* on a market that looks like *this* reach its target first".

The gradient-boosted trees split on feature values to separate the three outcomes. Class-balanced
weights are used where the metric is a label decision, and deliberately **not** used when the output
is a probability — reweighting distorts the very calibration the confidence depends on.

For a new candle, the server builds two rows — one per side, with the *same* requested distances and
opposite `direction_sign` — and gets both answers from a single `predict_proba`. Each side reads
`P(1)`: the probability its own take-profit came first. `choose_direction` prices both, discards any
that fail the confidence or expected-value floor or that policy forbids, and picks the higher
expected value. If nothing qualifies, the answer is `FLAT`, and the rationale says which floor
rejected which side.

The timeout class is load-bearing rather than a nuisance. A bet that resolves neither way is not a
loss, and `expected_value` prices it at a configurable `timeout_value_atr` — `0.0` by default,
meaning "you got your capital back and paid the spread". Collapsing timeouts into losses would
understate every wide-target bracket.

## Read the metrics like a human

No single metric proves a trading system works.

| Metric | Plain-English meaning |
|---|---|
| Log loss | Punishes bad probabilities, especially confident wrong answers. Lower is better. **This is the target**, because a confidence that gets thresholded has to be a real probability. |
| Expected calibration error | Average gap between the confidence claimed and the frequency observed. `0.01` means a bucket claiming 60% won about 59–61% of the time. |
| Decision-region error | The same gap, measured only above the confidence floor a caller would actually trade on. A model can be well calibrated overall and wrong exactly where it matters. |
| Confidence ceiling | The 99th-percentile confidence this model reaches. A minimum-confidence setting above it produces no signals at all — indistinguishable from a quiet market from the outside. |
| Balanced accuracy | Accuracy calculated equally across the three outcomes. Reported for continuity, **not** as the target: it rewards predicting the scarce class more often, which is the distortion calibration exists to remove. |
| Macro F1 | Precision/recall score giving each outcome equal importance. `100%` is perfect. |
| Win rate | Share of resolved bets whose take-profit came first. |
| Break-even rate | The win rate this particular set of bets *needed*, given how its timeouts actually turned out. |
| Edge | Achieved win rate minus break-even. This is the number that says whether there was skill. |
| Expectancy (ATR) | Average result per bet in ATR units — comparable across markets, unlike percent. |
| Profit factor | Gross wins divided by gross losses. Below `1.0` the strategy lost money. |
| Bars held | Average time in a trade, in candles. Short holds with a wide target usually mean the stop is doing the work. |

A positive expectancy with a *negative* edge means the timeouts carried the result, not the model —
which is the single most common way a bracket backtest flatters a strategy that has no skill.

Inspect every validation fold, read the confidence-reach table before choosing a threshold, and
remember that historical success can disappear in live markets.

The legacy close-to-close report additionally carries total return, CAGR, Sharpe, maximum drawdown,
exposure and turnover. Those are portfolio-level figures that assume one full position at a time, so
they do not transfer to a bot trading a fixed quote notional; the per-trade statistics above are the
transferable ones.

## Proxy and network path

`config.toml` contains:

```toml
[network]
proxy_url = "http://127.0.0.1:10808"
timeout_seconds = 30
```

`data._get_json` URL-encodes the Binance parameters, creates a request with a user-agent,
builds a `ProxyHandler` that sends both HTTP and HTTPS traffic to that address, and decodes
the JSON response. Start V2RayN before `download` or an online `signal`.

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
| `crypto-signal --config config.toml download` | Downloads closed history for every symbol in `market.symbols` into `market.data_dir`, one CSV per market. |
| `crypto-signal --config config.toml train` | Reuses those CSVs, trains the barrier-conditional model, and writes the serving registry to `output.model_dir`. |
| `crypto-signal --config config.toml train --refresh` | Downloads fresh history first, then trains. |
| `crypto-signal --config config.toml signal --take-profit 2 --stop-loss 1` | Asks the trained model about one bet: which side, at what prices, with what confidence. |
| `crypto-signal --config config.toml signal --symbol ETHUSDT ...` | The same question about another market. The pooled model answers for markets it never trained on. |
| `crypto-signal --config config.toml signal --offline ...` | Uses the local CSV rather than requesting recent candles. |
| `crypto-signal --config config.demo.toml demo` | Trains and signals on the bundled synthetic market, without the network. |

The `-legacy` commands — `train-legacy`, `signal-legacy`, `download-legacy` — drive the original
close-to-close model into `output.legacy_dir`. It answers a different question ("is this market
going up over the next few candles"), which is why it is kept: it is the baseline the barrier
model's numbers are compared against, not a fallback for it.

A bet is two numbers, so `signal` requires both. `--take-profit 2 --stop-loss 1` means "2% profit
target against a 1% stop"; the engine converts each into ATR units before asking the model,
because 2% is a routine move on one market and a rare one on another.

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
| `MarketConfig` | primary symbol, the pooled `symbols` list, candle interval, start/end timestamps, CSV path and data directory |
| `BarrierConfig` | the barrier model: horizon, ATR window, barrier grid, risk:reward bounds, pairs sampled per candle, holdout and calibration splits, per-symbol overrides, and what bracket the holdout backtest measured |
| `FeatureConfig` | prediction horizon and label threshold — the *legacy* close-to-close label only |
| `ModelConfig` | holdout size, folds, confidence threshold, tree hyperparameters |
| `BacktestConfig` | fee, slippage, and the legacy long-only/short setting |
| `OutputConfig` | artifact directory, the serving `model_dir`, and the legacy directory |
| `NetworkConfig` | proxy address and HTTP timeout |
| `LoggingConfig` | level, file, rotation size, backup count |

`BarrierConfig.allow_short` and `BacktestConfig.allow_short` are two different settings and are
deliberately not shared. The first decides whether the barrier model's report measured the short
side; the second belongs to the legacy model, where "SELL" means exit to cash rather than open a
short. At serving time the short side is a per-request input, so neither field constrains a bot.
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

### `src/crypto_signal/domain/`

The vocabulary every other layer speaks. It exists so the labeller, the backtester and the gRPC
server cannot disagree about what "the take-profit came first" means — a disagreement that shows
up as a model whose live results do not resemble its report.

- `direction.py` — `Direction` (`FLAT`/`LONG`/`SHORT`) with `sign`, `opposite`, and the wire
  conversions.
- `barriers.py` — `BarrierPair`, `Outcome`, and `resolve_first_touch` / `first_touch` /
  `resolve_first_touch_scalar`: the one implementation of "walk this path and say which barrier it
  reached first", including the rule that an ambiguous candle resolves as the loss.
- `levels.py` — `atr_multiple` / `percent_from_atr` convert between the two ways of naming a
  distance; `levels_for` places entry, take-profit and stop-loss on the correct sides for a given
  direction, and `TradeLevels` reports the resulting risk:reward.
- `expectancy.py` — `OutcomeProbabilities` (which refuses to exist unless its three probabilities
  sum to one), `expected_value` in ATR units, and `break_even_win_rate`.
- `money.py` — `quantize` / `format_decimal` / `parse_money`: prices as fixed-place decimal
  strings, so the number the engine computed is the number the database records.

### `src/crypto_signal/features/`

- `indicators.py`: `relative_strength_index`, `average_true_range`, `bollinger_z_score`,
  `stochastic_position` — the four indicators worth naming separately.
- `builder.py`: `build_features` calculates the 38 causal feature columns and returns a
  `FeatureFrame` carrying the frame, the ordered column names, and the ATR series the barrier
  distances are measured in.

`FeatureFrame.frame` holds *only* feature columns — no timestamp, no OHLC — and shares the input
frame's index. Callers pair the two positionally through that index. This replaced a module-level
`FEATURE_COLUMNS` global that `make_features` rewrote as a side effect of being called, which is a
data race waiting for an eight-worker gRPC server.

### `src/crypto_signal/labeling/`

- `triple_barrier.py`: `barrier_grid` builds the sane-risk:reward pairs; `sample_barrier_pairs`
  chooses which of them a given candle is emitted for; `label_triple_barrier` resolves one
  symbol's labels; `build_barrier_dataset` assembles the `BarrierDataset` (`X`, `y`, `times`,
  class counts) across every pooled market.
- `horizon_return.py`: `label_horizon_return` / `build_horizon_dataset` — the legacy
  close-to-close target, kept as the comparison baseline.

### `src/crypto_signal/modeling/`

- `estimator.py`: `build_model` and `fit_model` (class-balanced weights for label metrics, unweighted
  for probabilities); `aligned_probabilities` guarantees the column order even if a fold never saw
  one class; `classification_metrics`; `walk_forward_validation_by_time`, which is the purged,
  candle-grouped variant the barrier model requires.
- `splitting.py`: `TimeGroupedSplit` splits on unique candle opens rather than row positions;
  `candles_between` proves a fold's purge gap is real; `chronological_blocks` carves the
  fit/calibrate/assess blocks.
- `calibration.py`: `fit_calibrated_model` fits on one block, measures a correction on the next and
  assesses both on a third, returning a `CalibrationReport` that records what was *attempted* and
  what actually *shipped*. `reliability_curve` and `measure_confidence_reach` produce the report's
  reliability table and the ceiling that tells a caller which minimum-confidence values yield no
  signals at all.
- `direction.py`: `barrier_variants` builds the two rows one bet needs; `choose_direction` scores
  both sides in a single `predict_proba`, picks the higher expected value among the candidates that
  clear the floors, and returns a `DirectionChoice` carrying a human-readable rationale for why the
  loser lost.

### `src/crypto_signal/evaluation/`

- `bracket.py`: `run_bracket_backtest` walks candles, opens at the next candle's open, exits at
  whichever barrier the intrabar path reached first, charges `BracketCosts` both ways, and reports
  win rate, expectancy in both percent and ATR, profit factor and bars held — plus **three
  break-even win rates**, which exist because one cannot say *why* a strategy lost:

  | Key | Charges | What it is |
  | --- | --- | --- |
  | `break_even_win_rate_requested` | nothing | The rate the requested bracket would need in a frictionless world. The rung `domain.expectancy` quotes to a caller, and deliberately **not** a grade. |
  | `break_even_win_rate_before_fees` | entry gap, stop slippage | The rate the bracket the strategy actually *filled* needed. Beating it means the model has a real **directional** edge. |
  | `break_even_win_rate` | everything | An accounting identity: `win_rate_resolved` exceeds it exactly when `expectancy_atr` is positive, so `edge_over_break_even` and expectancy can never disagree in sign. |

  Reporting only the first was a live defect: it graded a costed result against a cost-free bar, so
  BTCUSDT's 47.8% win rate read as a **+7.8% edge** while the account lost 0.33 ATR per trade. All
  three delegate to the unchanged `domain.break_even_win_rate` through one `_solve` helper, so they
  cannot drift apart, and the realised pair returns `None` rather than a flattering number when a side
  has no realised win to average.

  Win and loss magnitudes come in **both** percent and ATR, and the ATR pair is the one to read.
  Averaging percentages mixes bets whose barriers sat at different fractions of price, so a model that
  wins in quiet bars and loses in volatile ones reports a mean win *smaller* than its mean loss on a
  1.5:1 bracket — which reads as an inverted bracket and is not one. Note the two pairs also count
  different populations by design: the percent pair splits on the sign of the return and pairs with
  `win_rate`, the ATR pair splits on which barrier resolved and pairs with `win_rate_resolved` and the
  break-even rungs. `mean_fee_atr` states the venue's cut in the same units the barriers were
  requested in, and on BTCUSDT it is 0.385 — over a third of a 1-ATR stop, because ATR is only ~0.6%
  of price against a 0.25% round trip.
- `close_to_close.py`: `signals_to_positions`, `performance_metrics`, `run_backtest` — the legacy
  simulation. It cannot evaluate a bracket order, which is why `bracket.py` exists.

### `src/crypto_signal/training/`

- `barrier_pipeline.py`: `download_barrier_data` / `download_barrier_candles` fetch every configured
  market; `train_barrier_model` coordinates the run and writes the registry; `_train_one` labels,
  splits, validates, calibrates, scores the strict holdout and backtests a single bundle;
  `_report_markdown` writes `REPORT.md`; `latest_barrier_signal` answers one requested bet.
- `pipeline.py`: the same shape for the legacy close-to-close model, writing into
  `output.legacy_dir`.
- `artifacts.py`: `json_default`, `write_json`, `write_text` — saving paths, timestamps and NumPy
  values without a custom encoder at each call site.

### `src/crypto_signal/human_output.py`

- `number`, `percent`, and `duration`: convert raw computer values into readable text.
- `format_download_summary`: explains a completed download.
- `format_barrier_training_summary`: rows, class balance, folds, holdout metrics, what calibration
  shipped, the confidence ceiling, and the bracket backtest per market.
- `format_barrier_signal_summary`: the chosen side, entry/target/stop, confidence, expected value,
  which bundle answered, and the selector's full rationale. A `FLAT` answer prints as a refusal
  with the reason, and its prices are labelled as the bet that was considered and rejected — not as
  a recommendation.
- `format_training_summary` / `format_signal_summary`: the legacy model's equivalents.

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

`train` writes a *serving registry* into `output.model_dir` — one bundle per scope it can answer
for, plus the two documents describing the run:

| Artifact | What is inside |
|---|---|
| `_pooled_<INTERVAL>.joblib` | The cross-market model: the estimator, the ordered feature names, and the metadata the server reads. Answers for any market at that interval, including ones it never trained on. |
| `<SYMBOL>_<INTERVAL>.joblib` | An optional per-market override, trained on that market alone. Resolution prefers it over the pooled bundle. |
| `metadata.json` | Every setting, the candle range per market, class counts, walk-forward and strict-holdout metrics, the calibration report, and the bracket backtest — for every bundle in the run. |
| `REPORT.md` | The same run as prose and tables: label balance, scores, the bracket backtest, the reliability curve, and the confidence-reach table. |

The filename *is* the declaration of reach. `_pooled_1h.joblib` says "ask me about anything at
1h"; `BTCUSDT_1h.joblib` says "ask me about BTCUSDT only". The server globs `*.joblib`, so
`metadata.json` and `REPORT.md` sit safely beside the bundles, and resolution is exact match, then
pooled, then a refusal that names what *is* available.

A per-market bundle is an optimisation over the pooled one, never a prerequisite: a broken override
is logged and recorded in the rejection list rather than denying a request the pooled model could
have answered.

`train-legacy` writes the older, close-to-close artifacts into `output.legacy_dir` —
`model.joblib`, its own `metadata.json` and `REPORT.md`, plus `holdout_predictions.csv`,
`holdout_backtest.csv`, `equity_curve.png` and `latest_signal.json`.

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
