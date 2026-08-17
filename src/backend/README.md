# .NET 10 API and orchestrator

This is the active public backend. It owns the HTTP API, authentication, users, wallets,
orders, exchange adapters, risk gates, audit events, persistence, and orchestration of
Python ML workloads.

The Python service is an internal compute boundary. It does not receive exchange secrets
and cannot place orders directly.

Run the API locally:

```bash
dotnet run --project src/backend/src/CryptoMlSignal.Api
```

Initial endpoints:

- `GET /health/live` — process liveness.
- `GET /health/ready` — aggregate readiness including the Python ML service.
- `GET /api/v1` — versioned API discovery.
- `GET /api/v1/platform` — current service boundaries and safe operating mode.
- `GET /api/v1/ml/capabilities` — orchestrated ML capability discovery.
- `GET /api/v1/ml/model` — loaded model identity, version, and inference settings.
- `POST /api/v1/ml/predictions` — validated REST-to-gRPC prediction orchestration.

The backend compiles its typed gRPC client from the canonical contract under `contracts/`.
React continues to use JSON/HTTP and never calls the Python service directly.

## ML client configuration

Configuration uses standard ASP.NET Core environment variable mapping:

| Variable | Development value | Purpose |
| --- | --- | --- |
| `MlService__Address` | `http://signal-ml:50051` | Private Python gRPC endpoint |
| `MlService__DeadlineSeconds` | `10` | Per-call deadline propagated by the client |
| `MlService__MaxReceiveMessageMb` | `4` | Maximum gRPC response size |
| `OperatingMode` | `PAPER` | Platform execution mode |

`POST /api/v1/ml/predictions` accepts a symbol, interval, optional request ID and expected
model version, plus a chronological array of completed OHLCV candles. Candle-count limits
are discoverable from `GET /api/v1/ml/capabilities`. The response includes the signal,
probabilities, confidence, model version, model training time, input digest, and processing
time. These fields support traceability and do not authorize an order.

## Next backend milestone

Authentication is not implemented in the current .NET skeleton. The next planned task is
PostgreSQL-backed ASP.NET Core Identity with `admin`, `operator`, `analyst`, and `viewer`
roles, secure token handling, authorization tests, and an idempotent superadmin bootstrap.
Order, wallet, audit, risk, and exchange APIs must remain unavailable until their domain
and safety tasks are complete.
