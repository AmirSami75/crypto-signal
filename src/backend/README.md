# .NET 10 API and orchestrator

This is the active public backend. It owns the HTTP API, authentication, users, wallets,
orders, exchange adapters, risk gates, audit events, persistence, and orchestration of
Python ML workloads.

The Python service is an internal compute boundary. It does not receive exchange secrets
and cannot place orders directly.

## Projects

| Project | Role |
| --- | --- |
| `src/CryptoSignal.Infra` | Cross-cutting infrastructure: base entities, generic repository, `ApiResult` envelope, exception middleware, Serilog/Mapster/Swagger composition, rules engine. No domain knowledge. |
| `src/CryptoSignal.Auth` | Users, roles, permissions, login history, JWT issuance, permission-based authorization. |
| `src/CryptoSignal.Api` | Composition root. Owns `CryptoSignalDbContext`, the concrete `User` entity, the ML gRPC client, and the thin controllers. |

Dependencies point inward only: `Api → Auth → Infra`.

Run the API locally:

```bash
dotnet run --project src/backend/src/CryptoSignal.Api
```

Or bring up the whole stack — API, PostgreSQL and the Python ML service — with
`docker compose` from `devops/` (see `devops/compose.dev.yml`).

## Endpoints

Anonymous:

- `GET /health/live` — process liveness.
- `GET /health/ready` — aggregate readiness including PostgreSQL and the Python ML service.
- `GET /api/v1` — versioned API discovery.
- `GET /api/v1/platform` — current service boundaries and safe operating mode.
- `POST /api/v1/auth/login` — issues a JWT and records a login-history row.

Authenticated:

- `POST /api/v1/auth/logout`, `PUT /api/v1/auth/change-password`, `GET /api/v1/auth/session-validate`
- `GET|POST /api/v1/user`, `GET|PUT|DELETE /api/v1/user/{id}`, plus `PUT account-activation`,
  `PUT account-de-activation` and `PUT reset-password`.
- `GET|POST /api/v1/role`, `GET|PUT|DELETE /api/v1/role/{id}` — roles and their permission
  assignments.
- `GET /api/v1/permission` — permission catalogue; `POST /api/v1/permission/resolve` for a role set;
  `GET /api/v1/permission/get-document` for the catalogue PDF.
- `GET /api/v1/login-history/{page}/{pageSize}/{desc}` — read-only audit trail. This controller
  exposes the paged route only; writes and the unpaged list are suppressed.
- `GET /api/v1/ml/capabilities` — orchestrated ML capability discovery.
- `GET /api/v1/ml/model` — loaded model identity, version, and inference settings.
- `POST /api/v1/ml/predictions` — validated REST-to-gRPC prediction orchestration.

Paged listing is a path-segment route, not a query string: every CRUD controller also answers
`GET /api/v1/{controller}/{page}/{pageSize}/{desc}`, returning `PagedResult<T>`.

Controller and action names are slugified on the way into the route table, so
`LoginHistoryController` is reached at `login-history` and `AccountDeActivation` at
`account-de-activation`. Every response is wrapped in the `ApiResult<T>` envelope.

Swagger UI is served at `/swagger` and includes the inherited base-controller documentation from
all three assemblies.

The backend compiles its typed gRPC client from the canonical contract under `contracts/`.
React continues to use JSON/HTTP and never calls the Python service directly.

## Configuration

Infrastructure settings bind from the `API_Settings` section; ML and CORS settings are top-level.
Both follow standard ASP.NET Core environment variable mapping (`__` for `:`).

| Variable | Development value | Purpose |
| --- | --- | --- |
| `API_Settings__Db__Type` | `PostgreSql` | Only supported provider — Oracle and SQL Server were removed |
| `API_Settings__Db__PostgreSqlCnnStr` | `Host=db;…` | Npgsql connection string. Required |
| `API_Settings__Db__MaxRetryCount` | `0` | Leave at 0 — see the warning below |
| `API_Settings__Jwt__SecretKey` | dev key in `appsettings.Development.json` | Required, ≥ 32 bytes: HMAC-SHA256 signing |
| `API_Settings__Bootstrap__SuperAdminPassword` | dev fallback | Required outside Development |
| `Cors__AllowedOrigins__0` | `http://localhost:5173` | Blank means no cross-origin access, not a wildcard |
| `MlService__Address` | `http://signal-ml:50051` | Private Python gRPC endpoint |
| `MlService__DeadlineSeconds` | `10` | Per-call deadline propagated by the client |
| `MlService__MaxReceiveMessageMb` | `4` | Maximum gRPC response size |
| `OperatingMode` | `PAPER` | Platform execution mode |

Every secret in `appsettings.json` is blank on purpose. `appsettings.Development.json` carries
development-only values; production supplies them through `devops/env/prod/api.env` and secret
management. A missing required key fails startup with a message naming the key.

> **Do not raise `API_Settings__Db__MaxRetryCount` without further work.** A non-zero value installs
> `NpgsqlRetryingExecutionStrategy`, which refuses to run inside a transaction the caller opened
> itself — and the user seeder plus the user and role controllers all use `BeginTransactionAsync`.
> With retries on, superadmin seeding and every user/role write throw
> `InvalidOperationException: … does not support user-initiated transactions`. Enabling it means
> wrapping each of those transactions in `Database.CreateExecutionStrategy()` first. The seeder is
> already wrapped; the controllers are not.

## Database and bootstrap

`EnsureCreatedAsync` runs on start, followed by the ordered seeders: permissions, then roles, then
the `cs-admin` superadmin — created from `API_Settings__Bootstrap__SuperAdminPassword` and flagged
for a mandatory password change at first login. Outside Development the seeder throws rather than
create a full-privilege account with a password published in the source tree. In Development, with
that key blank, it falls back to the built-in default in `AuthGlobalVariables.DefaultPassword` and
logs a warning, so `cs-admin` can log in on a fresh database with no extra setup.

Concurrency uses the PostgreSQL `xmin` system column, so no `RowVersion` column is mapped.

`POST /api/v1/ml/predictions` accepts a symbol, interval, optional request ID and expected
model version, plus a chronological array of completed OHLCV candles. Candle-count limits
are discoverable from `GET /api/v1/ml/capabilities`. The response includes the signal,
probabilities, confidence, model version, model training time, input digest, and processing
time. These fields support traceability and do not authorize an order.

## Next backend milestone

Authentication, roles, permissions and the superadmin bootstrap are in place. Still outstanding:
authorization tests, then the order, wallet, audit, risk, and exchange APIs — which must remain
unavailable until their domain and safety tasks are complete.
