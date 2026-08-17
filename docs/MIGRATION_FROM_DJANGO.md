# Django-to-.NET migration

Django is not part of the new `crypto-signal` runtime. The previous implementation is
retained only in the old `crypto-ml-signal` workspace for reference.

Reusable assets migrated into this project:

- the causal Python ML package, tests, configurations, sample data, and model artifacts;
- live-trading safety and research documentation;
- PostgreSQL and environment-specific Compose conventions.

Features that must be reimplemented in .NET rather than copied from Django:

- authentication and token/session lifecycle;
- users, roles, and capability-based authorization;
- superadmin bootstrap;
- immutable audit events;
- operational persistence and migrations;
- order, wallet, exchange, reconciliation, and risk APIs.

No Django package, settings module, migration, or container is required by the new stack.
