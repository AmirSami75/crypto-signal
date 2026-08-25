# Database migrations

The platform uses EF Core migrations as the single schema-arrival path. `DatabaseInitializer`
calls `MigrateAsync()` on startup — never `EnsureCreatedAsync()`, which is a no-op on a database
that already exists and would let a newly added entity silently never appear in a running dev DB.

## Migrations

| Migration | Captures |
| --- | --- |
| `Baseline` | The Auth schema as it stood before migrations were introduced: `Permissions`, `Roles`, `Users`, `RolePermissions`, `UserRoles`, `LoginHistories`. |
| `Trading` | The trading domain (bots, decisions, intents, risk, orders, fills, positions, kill switches, audit, recorded candles). |

## Authoring a migration

Migrations are generated from the model, not from a database, so `migrations add` opens no
connection — the design-time connection string in `CryptoSignalDbContextFactory` need only be
well-formed. From `src/backend`:

```bash
export PATH="$PATH:$HOME/.dotnet/tools"
dotnet ef migrations add <Name> --project src/CryptoSignal.Api
```

`CryptoSignalDbContextFactory` (an `IDesignTimeDbContextFactory`) is what the tooling instantiates:
it bypasses the DI graph the running app uses (`InjectDbContext`), because the tooling never starts
the host and cannot resolve `DbSettings` or the audit/tracing interceptors. Those interceptors are
runtime behaviour and contribute nothing to the schema, so a design-time migration is identical to
one authored with them.

## A fresh database

Nothing to do. `MigrateAsync()` creates the database, applies every migration in order, and
bootstraps `__EFMigrationsHistory` itself. This is the dev-container path (`docker compose up`), and
the clean-slate reset is `docker compose down -v`.

## A database that predates migrations

A database created by the old `EnsureCreatedAsync()` path already has the Auth tables but no
`__EFMigrationsHistory`. Running `MigrateAsync()` against it would try to `CREATE TABLE "Users"` and
fail because the table is already there. Mark the Baseline as already applied so migration starts
from `Trading`:

```sql
CREATE TABLE IF NOT EXISTS "__EFMigrationsHistory" (
    "MigrationId"    character varying(150) NOT NULL,
    "ProductVersion" character varying(32)  NOT NULL,
    CONSTRAINT "PK___EFMigrationsHistory" PRIMARY KEY ("MigrationId")
);

-- MigrationId is the file-name stamp of the Baseline migration.
INSERT INTO "__EFMigrationsHistory" ("MigrationId", "ProductVersion")
VALUES ('20260824145204_Baseline', '10.0.11')
ON CONFLICT ("MigrationId") DO NOTHING;
```

In dev, `docker compose down -v` followed by `docker compose up` is simpler and leaves no chance of
a hand-typed stamp drifting from the migration file name.
