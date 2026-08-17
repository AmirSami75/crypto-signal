# React operations dashboard

The active dashboard uses React 19, TypeScript, and Vite. The development server proxies
`/api` and `/health` to the .NET orchestrator, so browser code never calls the Python ML
service directly.

Run it through Docker Compose from `devops/`, or with Node 20.19+ / 22.12+.

For a local frontend-only workflow:

```bash
npm install
npm run dev
```

Verification commands:

```bash
npm run typecheck
npm run build
```

The current screen is the foundation operations view: it shows platform mode, aggregate
readiness, service status, and the execution boundary. Authentication, reusable admin
components, model-run monitoring, signals, orders, fills, wallets, and risk views are
planned milestones. Until .NET identity is implemented, the dashboard must not add mock
authorization or expose dangerous controls.

Development requests to `/api` and `/health` are proxied to the .NET API. Browser code
must never contain exchange credentials, database credentials, model file paths, or a
direct Python gRPC endpoint.
