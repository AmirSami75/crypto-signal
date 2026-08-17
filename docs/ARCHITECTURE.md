# Platform architecture

## Service boundaries

```text
Browser / operator
       |
       v
React dashboard
       |
       v
.NET 10 API and orchestrator -----> PostgreSQL
       |              |
       |              +----------> Exchange adapters (future)
       | gRPC / Protobuf v1
       v
Python ML engine -----> immutable model artifact
```

The .NET service is the only public backend and the only component allowed to authorize
or submit an exchange order. It will own users, roles, sessions, wallets, orders, fills,
risk limits, audit events, exchange credentials, reconciliation, and job state.

The Python engine is private to the application network. It owns numerical and ML work:
market-data validation, causal features, training, inference, backtesting, and artifact
generation. Its output is advisory data returned to .NET, never an execution command.

The React dashboard calls only the versioned .NET API. It must not hold exchange secrets,
call exchanges directly, or access the Python service directly.

## Initial runtime

| Component | Technology | Port in development |
| --- | --- | --- |
| Dashboard | React 19, TypeScript, Vite | 5173 |
| Public API/orchestrator | ASP.NET Core on .NET 10 | 8000 |
| Internal ML engine | Python, gRPC/Protobuf | 50051 |
| Operational database | PostgreSQL 18 | 5432 |

The canonical internal contract is `contracts/crypto_signal_engine/contracts/v1/ml_engine.proto`.
The backend sends normalized completed candles and may pin the expected model digest. The
response includes probabilities, confidence, model version, and an input digest. These
fields provide traceability; they do not authorize an order.

## Safety invariant

`PAPER` is the default mode. Adding an exchange adapter does not enable live execution.
Live mode requires explicit environment configuration, admin approval, risk checks,
idempotency, immutable audit events, reconciliation, and a tested kill switch.
