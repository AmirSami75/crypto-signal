# DevOps

All Compose commands run from this directory. The base file defines the service graph;
the development and production overlays provide environment-specific ports, volumes,
commands, and environment files.

```bash
docker compose -f compose.yml -f compose.dev.yml up --build
docker compose -f compose.yml -f compose.prod.yml config --quiet
```

The active services are PostgreSQL, the internal Python ML service, the .NET 10 API and
orchestrator, and the React dashboard. Production secrets are intentionally blank.

The ML engine uses gRPC on container port `50051`. Development binds it only to
`127.0.0.1:50051`; production keeps it private on the Compose application network. Its
health check uses the standard gRPC health protocol, and the .NET readiness endpoint also
verifies that a production model is loaded.

## Compose layout

| File | Responsibility |
| --- | --- |
| `compose.yml` | Shared service graph, images, dependencies, networks, and health checks |
| `compose.dev.yml` | Local ports, source mounts, development targets, and `env/dev/*` |
| `compose.prod.yml` | Runtime-only services, restart policies, persistent data, and `env/prod/*` |

Development binds PostgreSQL to `127.0.0.1:5432`, gRPC to `127.0.0.1:50051`, the .NET API
to `127.0.0.1:8000`, and Vite to `127.0.0.1:5173`. Production exposes only the dashboard
and API on loopback by default; PostgreSQL and the ML engine remain private.

## Common operations

```bash
# Validate the fully merged configurations
docker compose -f compose.yml -f compose.dev.yml config --quiet
docker compose -f compose.yml -f compose.prod.yml config --quiet

# Start or inspect development
docker compose -f compose.yml -f compose.dev.yml up --build -d
docker compose -f compose.yml -f compose.dev.yml ps

# Stop development without deleting PostgreSQL data
docker compose -f compose.yml -f compose.dev.yml down
```

Before production startup, populate `env/prod/db.env` and `env/prod/api.env`, mount the
approved model artifact, configure TLS or a trusted private network for gRPC, and replace
all blank secret placeholders. Do not commit real credentials. `OPERATING_MODE` remains
`PAPER` until the tracker’s safety gates and live-readiness review are complete.
