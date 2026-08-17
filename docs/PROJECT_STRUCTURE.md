# Project structure

```text
crypto-signal/
├── contracts/         # Versioned protobuf contracts shared across runtimes
├── src/
│   ├── backend/       # .NET 10 API/orchestrator solution
│   ├── signal-ml/     # Python ML package and internal gRPC engine
│   └── frontend/      # React/TypeScript dashboard
├── devops/
│   ├── docker/        # One Dockerfile per runtime
│   ├── env/dev/       # Local-only defaults
│   ├── env/prod/      # Deployment placeholders
│   ├── compose.yml
│   ├── compose.dev.yml
│   └── compose.prod.yml
├── docs/
└── tests/
    └── ml-engine/     # Python unit and artifact-backed inference tests
```

Application code belongs under `src`. Environment and container definitions belong under
`devops`. The public backend is always `src/backend`; Python is an internal ML boundary,
not a second public backend. Tests live at the repository root so all service-level and
cross-service suites have one discoverable home.
