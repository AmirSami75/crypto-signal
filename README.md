# Crypto Signal Platform

Crypto Signal is an operations platform for ML-assisted cryptocurrency trading. The
active architecture has three strict application boundaries:

- **.NET 10 API and orchestrator** — public API, identity, wallets, risk, orders,
  exchange adapters, audit, persistence, and all execution authorization.
- **Python ML engine** — gRPC inference, market-data validation, features, training,
  backtesting, and versioned model artifacts. It cannot place exchange orders.
- **React dashboard** — operator-facing monitoring and control plane. It communicates
  only with the .NET API.

PostgreSQL stores operational state. The default operating mode is `PAPER`; live trading
must remain unavailable until the planned safety gates are implemented and tested.

## Current milestone

The platform foundation and synchronous ML inference path are working end to end:

- environment-specific Docker Compose starts PostgreSQL, the Python ML engine, the .NET
  API, and the React dashboard;
- the canonical Protobuf v1 contract drives generated Python and .NET clients;
- the .NET API applies deadlines and translates public REST requests into private gRPC
  calls;
- the Python engine validates completed candles, loads the model artifact, and returns an
  auditable prediction containing model and input SHA-256 digests.

The next milestone is `BE-004`: PostgreSQL-backed .NET authentication, roles,
permissions, and superadmin bootstrap. Durable job orchestration, order execution, wallet
accounting, and exchange connectivity are still planned work. Track implementation in the
[delivery plan](https://docs.google.com/spreadsheets/d/1hixfVNsWoTP4HfqasJo6EDz0AjkJeI96_0ssx-8Hn0I/edit).

## Start development

The host has .NET 10, but the complete stack is intended to run consistently through
Docker:

```bash
cd devops
docker compose -f compose.yml -f compose.dev.yml up --build
```

Then open:

- React dashboard: `http://127.0.0.1:5173`
- .NET API: `http://127.0.0.1:8000/api/v1/`
- Aggregate readiness: `http://127.0.0.1:8000/health/ready`
- Python ML gRPC endpoint (internal; development bind): `127.0.0.1:50051`
- ML model information through .NET: `http://127.0.0.1:8000/api/v1/ml/model`

## Repository map

```text
src/backend/      .NET 10 public API and orchestrator
src/signal-ml/    Python research library and production gRPC inference engine
src/frontend/     React + TypeScript operations dashboard
contracts/        Versioned cross-language protobuf contracts
devops/           Dockerfiles, Compose overlays, environment files
docs/             Architecture, safety, migration, and research documentation
tests/ml-engine/  Python ML unit and inference tests
```

See `docs/ARCHITECTURE.md` before adding a new service or integration.

## Public and private protocols

React and other external clients use the versioned JSON/HTTP API exposed by .NET. Only
.NET calls the Python ML engine, using the private gRPC contract at
`contracts/crypto_signal_engine/contracts/v1/ml_engine.proto`. A model signal is advisory;
it cannot authorize or submit an exchange order.

## Run Python tests

From the repository root, with the ML dependencies installed:

```bash
PYTHONPATH=src/signal-ml/src python -m unittest discover -s tests/ml-engine -v
```

See the service-specific READMEs under `src/` and `devops/` for configuration and run
commands.
