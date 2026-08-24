# Python ML engine

A stateless advisor over gRPC. It answers two questions and takes no action on either:

1. **"What is the trade here?"** — given a market, a candle window and a take-profit / stop-loss
   pair, it returns a direction, entry / TP / SL prices, and a calibrated probability that the
   take-profit is reached before the stop.
2. **"What now?"** — given the same plus an open position, it returns HOLD / OPEN / CLOSE /
   ADJUST_BRACKET with a reason code.

It must not receive exchange API secrets and it never places an order. The .NET orchestrator owns
the bot loop, all state, and every execution decision; everything this service returns is advisory
data, and the second RPC is an advisor precisely so that the decision to act stays on the side of
the system that can be held to a risk policy.

## The bet is an input, not a hard-coded assumption

The predecessor answered one question — "is BTCUSDT going up over the next six candles by more than
0.35%" — which meant a bot targeting 2% profit against a 1% stop was acting on a model that had
never been asked about that trade. Here the barrier distances are **features**: each training row
carries its own `(take_profit_atr, stop_loss_atr)` pair and a triple-barrier label saying which
barrier the price path actually reached first. One model therefore answers any requested pair.

Distances are in **ATR units** rather than percent because 2% is a routine move on one pair and a
rare one on another; "1.5 ATR" is comparable across both, which is what lets one pooled model serve
markets it was never trained on.

The short side needs no second model either, but not by swapping the barriers. Each candle is
emitted once per *(barrier pair, direction)*, with the direction carried as a feature
(`direction_sign`) and the label stated from that bet's own point of view: **`+1` means
"take-profit came first"** whichever way the bet points, so both sides read `P(+1)` and both are
handed the same, unswapped distances — `levels_for` is what puts the prices on the correct side of
the entry. Mirroring the barriers instead would be actively wrong: a candle whose range straddles
both barriers is a loss for *both* directions under the adverse-wins rule, but mirrored inputs would
score it as a short **win**.

## Structure

```text
src/crypto_signal/domain/          Barrier resolution, levels, direction, decimal money — shared by
                                   the labeller, the backtester and the server so they cannot
                                   disagree about what "take-profit first" means
src/crypto_signal/features/        Scale-free feature construction
src/crypto_signal/labeling/        Triple-barrier labelling and barrier augmentation
src/crypto_signal/modeling/        Estimator, calibration, direction selection, time-grouped splits
src/crypto_signal/evaluation/      Bracket backtest (and the legacy close-to-close one)
src/crypto_signal/training/        Training pipeline and report

src/crypto_signal_engine/application/     Candle window, evaluator, signal service, bot advisor
src/crypto_signal_engine/infrastructure/  Model registry
src/crypto_signal_engine/transport/grpc/  Servicer and proto <-> dataclass mappers
src/crypto_signal_engine/contracts/v1/    Generated Python protobuf bindings
../../contracts/.../ml_engine.proto        Canonical cross-language contract
```

## Run locally

From `src/signal-ml`:

```bash
python -m pip install -e '.[grpc,dev]'
python scripts/generate_grpc.py
ML_MODEL_DIR=artifacts/models python -m crypto_signal_engine
```

The server listens on `0.0.0.0:50051` by default and exposes:

- `crypto_signal.ml.v1.MlEngineService/GetCapabilities`
- `crypto_signal.ml.v1.MlEngineService/GetModelInfo`
- `crypto_signal.ml.v1.MlEngineService/GetSignal`
- `crypto_signal.ml.v1.MlEngineService/EvaluateBotDecision`
- standard `grpc.health.v1.Health`
- gRPC reflection in development only

Starting with no servable model is a **warning, not a failure**: the model directory is a mounted
volume, and a crash-loop would turn "the artifact has not been copied in yet" into a container that
is never up long enough for anyone to copy it in. The server comes up, reports an empty inventory,
and fails signal requests with `FAILED_PRECONDITION` naming what it skipped and why. Resolution
reads the directory per request, so a newly-arrived artifact needs no restart.

## Model registry

`ML_MODEL_DIR` holds joblib bundles named for what they serve:

| File | Serves |
| --- | --- |
| `BTCUSDT_1h.joblib` | that pair and interval only |
| `_pooled_1h.joblib` | every symbol at `1h` that has no dedicated bundle |

Resolution is exact match, then pooled, then refusal. A per-symbol bundle is an *optimisation* over
the pooled one, so a broken override is recorded in the rejection list and logged — it does not deny
a request the pooled model can answer.

## Prices cross the wire as decimal strings

Every price and percentage in the contract is a `string`, not a `double`. The .NET side holds money
as `decimal`, and the audit chain requires that the price the engine computed is the price the
database records, byte for byte. Only dimensionless quantities — probabilities, ratios, ATR
multiples, timings — are floating point.

## Runtime configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `ML_MODEL_DIR` | `artifacts/models` | Registry directory, re-read per request |
| `ML_MODEL_PATH` | unset | Single-artifact fallback for a pre-registry deployment |
| `OPERATING_MODE` | `PAPER` | `PAPER`, `SANDBOX` or `LIVE`; reported, never enforced here |
| `ML_DEFAULT_MAX_HOLDING_PERIODS` | `0` | `0` defers to the horizon each bundle was labelled at |
| `ML_MINIMUM_CONFIDENCE` | `0.0` | Floor when a request sets none; policy belongs in the orchestrator |
| `ML_BARRIER_ATR_BOUNDS` | `0.5,4.0` | Trained barrier span; outside it the answer carries a warning |
| `ML_MINIMUM_CANDLES` | `169` | Minimum completed candles accepted (the feature warm-up) |
| `ML_MAXIMUM_CANDLES` | `2000` | Maximum candles accepted per RPC |
| `ML_GRPC_WORKERS` | `8` | gRPC worker threads |
| `ML_MAX_RECEIVE_MESSAGE_MB` | `16` | Maximum inbound message size |
| `ML_MAX_SEND_MESSAGE_MB` | `4` | Maximum outbound message size |
| `ML_ENABLE_REFLECTION` | environment-dependent | Enable reflection for development only |
| `ML_LOG_FORMAT` | `json` | `json` or `text` structured logging |

A request outside the trained ATR span is answered with an extrapolation note in `warning` rather
than refused — a flagged answer is more useful than none, and the caller can see the edge of the
training set in `GetModelInfo` instead of inferring it after the fact.

The engine validates chronological timestamps, finite positive OHLCV values, candle geometry,
symbol and interval compatibility, the feature warm-up window, and optional model version pinning.
A gap **inside** the warm-up window is fatal; an earlier one is advisory, because the newest feature
row reads only the last `ML_MINIMUM_CANDLES` bars.

Inference is deterministic from caller-provided candles: the same window and parameters produce the
same `input_digest_sha256`, direction and levels. The engine does not fetch exchange data during an
RPC, and it never receives wallet, credential, risk or order data.

## Tests

Run from the repository root — `pytest.ini` lives there:

```bash
python -m pytest tests/ml-engine -q
```

Production can enable TLS or mTLS using `ML_TLS_CERTIFICATE_PATH`, `ML_TLS_PRIVATE_KEY_PATH`, and
`ML_TLS_CLIENT_CA_PATH`. Keep reflection disabled and set an explicit deadline on every client call.

## Contract changes

Edit only the canonical file at
`../../contracts/crypto_signal_engine/contracts/v1/ml_engine.proto`, then regenerate the Python
bindings with `python scripts/generate_grpc.py`. The .NET project generates its typed client during
build. Commit the contract and generated Python bindings together.

Field numbers within `crypto_signal.ml.v1` are never reused. Retired fields go into a `reserved`
clause with a note saying what they meant — `Signal`, `sell_semantics` and `probability_threshold`
are all there. Repurposing a field number is how a caller keeps reading a value that no longer means
what its name says, which is a class of bug that survives review and then loses money.

## Training

Training runs **on the host**, not in the container: only `testnet.binance.vision` is reachable from
inside the compose network, and the mainnet history the models are trained on is not. Candle CSVs
live in `data/`, one per symbol, and `download` fetches every symbol in `market.symbols`.

```bash
python -m crypto_signal.cli --config config.toml download    # one CSV per configured symbol
python -m crypto_signal.cli --config config.toml train       # pooled bundle + per-symbol overrides
python -m crypto_signal.cli --config config.toml signal --symbol ETHUSDT --take-profit 2 --stop-loss 1
```

`train` writes the whole registry directory: `_pooled_<INTERVAL>.joblib`, a per-symbol bundle for
each configured symbol, plus `metadata.json` and a human-readable `REPORT.md` beside them. The
registry globs `*.joblib`, so the two documents sit safely in the same directory.

The `-legacy` suffixed commands (`train-legacy`, `signal-legacy`, `download-legacy`) drive the
original close-to-close model into `artifacts/legacy`. They are kept as a comparison baseline only —
nothing serves from them. `demo` trains and signals on a bundled synthetic market and touches no
network at all, which is the quickest way to confirm an install works.

### Reading the bracket backtest

`REPORT.md` grades each symbol against **three break-even win rates**, and the distinction matters
because a single one cannot say *why* a strategy lost:

| Column | Charges | Read it as |
| --- | --- | --- |
| *asked* | nothing | The rate the requested bracket would need in a frictionless world — the rung the model's own `expected_value` is quoted against. **Not a grade.** |
| *before fees* | entry gap, stop slippage | The rate the bracket the strategy actually filled needed. Beating this means the model has a real **directional** edge. |
| *net* | everything | An accounting identity: the achieved rate exceeds it exactly when `expectancy_atr` is positive. |

A win rate above *before fees* and below *net* is a model that is right often enough but a bracket
too narrow to pay the venue — a bracket problem, not a model problem, and the two have opposite
remedies. `Fee (ATR)` names the size of that toll directly: on BTCUSDT it is ~0.39 of a 1-ATR stop,
because ATR is only ~0.6% of price against a 0.25% round trip. **Any caller sizing a bracket must
clear the fee in ATR units before the model's edge is worth anything.**

Win and loss magnitudes are reported in **ATR units, not percent**, for the same reason the barriers
are: averaging percentages across trades whose barriers sat at different fractions of price makes a
model that wins in quiet bars and loses in volatile ones look like it ran an inverted bracket.
