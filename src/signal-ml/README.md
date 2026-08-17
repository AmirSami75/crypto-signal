# Python ML engine

This private engine provides typed gRPC inference over the existing research package in
`src/crypto_signal`. The transport accepts completed OHLCV candles, validates the final
feature warm-up window, executes the loaded model, and returns an auditable result with
model and input SHA-256 digests.

It must not receive exchange API secrets or place orders. The .NET orchestrator owns all
wallet, risk, approval, and exchange execution decisions.

## Structure

```text
src/crypto_signal/                     Research, training, features, and backtesting
src/crypto_signal_engine/application/  Inference use case, validation, domain DTOs
src/crypto_signal_engine/infrastructure/ Model artifact repository
src/crypto_signal_engine/transport/grpc/ gRPC mapping and error handling
src/crypto_signal_engine/contracts/v1/ Generated Python protobuf bindings
../../contracts/.../ml_engine.proto     Canonical cross-language contract
```

## Run locally

From `src/signal-ml`, install the runtime and generation dependencies:

```bash
python -m pip install -e '.[grpc,dev]'
python scripts/generate_grpc.py
ML_MODEL_PATH=artifacts/model.joblib python -m crypto_signal_engine
```

The server listens on `0.0.0.0:50051` by default and exposes:

- `crypto_signal.ml.v1.MlEngineService/GetCapabilities`
- `crypto_signal.ml.v1.MlEngineService/GetModelInfo`
- `crypto_signal.ml.v1.MlEngineService/PredictSignal`
- standard `grpc.health.v1.Health`
- gRPC reflection in development only

## Runtime configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `ML_MODEL_PATH` | `artifacts/model.joblib` | Model artifact loaded at startup |
| `ML_MINIMUM_CANDLES` | `169` | Minimum completed candles accepted |
| `ML_MAXIMUM_CANDLES` | `2000` | Maximum candles accepted per RPC |
| `ML_GRPC_WORKERS` | `8` | gRPC worker threads |
| `ML_MAX_RECEIVE_MESSAGE_MB` | `16` | Maximum inbound message size |
| `ML_MAX_SEND_MESSAGE_MB` | `4` | Maximum outbound message size |
| `ML_ENABLE_REFLECTION` | environment-dependent | Enable reflection for development only |
| `ML_LOG_FORMAT` | `json` | `json` or `text` structured logging |

The engine validates chronological timestamps, finite positive OHLCV values, candle
geometry, symbol and interval compatibility, minimum feature warm-up, and optional model
version pinning. Invalid input maps to typed gRPC errors rather than partial predictions.

Inference is deterministic from caller-provided candles. The engine does not fetch live
exchange data during an RPC, and it never receives wallet, credential, risk, or order data.
The .NET orchestrator remains responsible for market adapters and every execution decision.

The Python tests are shared at the repository root. Run them from there with:

```bash
PYTHONPATH=src/signal-ml/src python -m unittest discover -s tests/ml-engine -v
```

Production can enable TLS or mTLS using `ML_TLS_CERTIFICATE_PATH`,
`ML_TLS_PRIVATE_KEY_PATH`, and `ML_TLS_CLIENT_CA_PATH`. Keep reflection disabled and set an
explicit deadline on every client call.

## Contract changes

Edit only the canonical file at
`../../contracts/crypto_signal_engine/contracts/v1/ml_engine.proto`, then regenerate the
Python bindings with `python scripts/generate_grpc.py`. The .NET project generates its
typed client during build. Commit the contract and generated Python bindings together, and
keep backward-compatible field numbers within `crypto_signal.ml.v1`.

The current bundled artifact may emit a joblib compatibility warning under NumPy 2.5.
Retrain and resave the artifact with the production dependency set before promoting a new
model version.
