# CryptoSignal.Infra

Cross-cutting infrastructure shared by every backend project. It has no domain knowledge and no
dependency on `CryptoSignal.Auth` or `CryptoSignal.Api` — the arrows point inward only.

Ported from an in-house library and retargeted here to **net10.0** with **PostgreSQL as the only
database provider**. The Oracle and SQL Server paths were removed rather than left dormant, so
`DbSettings.Type` accepts `PostgreSql` and nothing else.

## What it provides

| Area | Contents |
| --- | --- |
| `Base/Entity` | `BaseEntity<TKey>`, auditing fields, soft delete, `xmin` concurrency token |
| `Base/DB` | `IRepo<T>` / `Repo<T>` generic repository, `IDbObjectInitializer`, `IEntitySeedData` |
| `Base/API` | `BaseController`, `CrudController<...>`, `ApiResult<T>`, `PagedResult<T>` |
| `Base/Auth` | `BaseUser` (TPH root), current-user abstractions |
| `Base/Markers` | Scrutor scan markers: `IInfraMarker`, `IScopedInfraMarker`, `ITransientInfraMarker`, `ISingletonInfraMarker` |
| `Attributes` | `[ControllerInfo]`, `[SearchFilter]`, `[ApiResultFilter]` |
| `Middlewares` | `UnifiedExceptionHandlerMiddleware` — maps exceptions onto the `ApiResult` envelope |
| `Exceptions` | `AppException` hierarchy carrying an HTTP status and an API status code |
| `RulesEngine` | `IRuleEngine<T>` / `ICrudRuleExecutor<TDto,TEntity,TKey>` for pre/post CRUD rules |
| `Tooling/Logging` | Serilog composition (console, rolling file, Elastic) plus `ILoggerAdapter<T>` and `EfCommandTracer` |
| `Tooling/Mapping` | Mapster `IMapperAdapter`, `ProjectTo`, assembly-scanned `IRegister` |
| `Tooling/Swagger` | `SwaggerConfigurationBuilder`, API versioning, `SlugifyParameterTransformer` |
| `Tooling/Registrations` | `InjectApiSettings`, `InjectDbContext<T>`, `AddMinimalMvc`, `AddSwagger`, health checks |
| `Extensions` | Query, type, validator, claims and file helpers |

`Tooling/Graphql` and `Tooling/Messaging` are ported but unwired: this deployment runs no GraphQL
gateway and the compose stack has no broker.

## Ported-tooling deviations

Two upstream dependencies could not be carried over as-is.

**Swagger filters target Microsoft.OpenApi 2.x.** Swashbuckle 10.x resolves Microsoft.OpenApi 2.7.5,
which moved every model type out of `Microsoft.OpenApi.Models` into the root `Microsoft.OpenApi`
namespace and replaced `OpenApiSecurityScheme.Reference` with the standalone
`OpenApiSecuritySchemeReference` type. `AuthorizationOperationFilter` therefore builds its
requirement as `[new OpenApiSecuritySchemeReference("Bearer")] = []`, pointing at the definition
`AddSwagger` registers under that id. `Operation.Summary`, `.Parameters`, `.Responses` and
`.Security` are all nullable in 2.x and are null-guarded rather than assumed populated — the 1.x
types hid those dereferences.

**`HotChocolate.Stitching` was dropped.** Stitching was removed from HotChocolate in v14 in favour of
Fusion, so its last release (13.9.16) pulled a parallel 13.x assembly graph into this v16 build and
failed with `CS7069` on `IRequestExecutorBuilder`. `GraphqlServer.AddRemoteSchema` went with it.
Nothing here serves GraphQL, so there is no gateway to stitch, and a future one would use Fusion.

## Configuration

Everything binds from the `API_Settings` configuration section. `InjectApiSettings(config)` must be
called **before** `InjectJwtAuth<T>()`, because the JWT registration resolves `IOptions<JwtSettings>`
from a temporary provider.

```
API_Settings:Db:Type                  PostgreSql
API_Settings:Db:PostgreSqlCnnStr      Npgsql connection string (required)
API_Settings:Db:MaxRetryCount         0 — see below
API_Settings:Jwt:SecretKey            ≥ 32 bytes; tokens are signed with HMAC-SHA256
API_Settings:Logging:Sinks:*          per-sink enable/level toggles
```

Missing required keys fail at startup with a message that names the key, not on first use.

`InjectDbContext` only calls `EnableRetryOnFailure` when `MaxRetryCount` is above zero, and the
default is zero. A retrying execution strategy cannot run inside a transaction the caller began
itself, and `BeginTransactionAsync` is used in the user seeder, `Repo.cs` and the user and role
controllers — so a non-zero value turns those writes into runtime failures unless each site is first
wrapped in `Database.CreateExecutionStrategy()`.

## Registration

Service discovery is assembly scanning, not hand-written registration. A type is picked up by
implementing the matching marker interface, so adding a service means adding a marker — never
editing a DI list. See `Program.cs` in `CryptoSignal.Api` for the composition order.

## Build notes

`TreatWarningsAsErrors` is set to `false` for this project only. The repository default in
`Directory.Build.props` is `true`; the ported sources still carry nullable-annotation and unused-
variable warnings, and silencing them by editing library code would make future upstream diffs
harder to read.
