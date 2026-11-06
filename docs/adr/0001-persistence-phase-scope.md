# ADR 0001: implement persistence and read APIs before event processing

Date: 2026-11-06. Status: accepted by the user's implementation request.

## Context

The planning baseline labeled Phase 2 as webhook durability. The next explicit request instead defines Phase 2 as persistence and core backend APIs, and excludes live webhooks, AI calls, and frontend features. The repository has no Phase 1 implementation. A database-backed read API needs a small amount of Python/runtime setup before it can be verified.

## Decision

Implement only the requested persistence slice plus necessary Python/API/database prerequisites. Use a uv workspace with one shared `shrike-backend` package and one `shrike-api` package, exact direct dependency pins, `uv.lock`, Python 3.12, and a PostgreSQL 17 image pinned by digest. Do not scaffold Next.js, Redis/Celery, webhook ingestion, analyzers, OAuth, or cloud infrastructure. A database-only Compose service supports manual local development.

The initial six tables are `installations`, `repositories`, `pull_requests`, `review_jobs`, `review_findings`, and `review_executions`. Jobs replace the provisional `review_runs` table name; executions replace `review_attempts`. Public states are exactly `pending`, `running`, `completed`, `failed`, and `canceled`. Cancellation is representable, but no executor or cancellation endpoint exists. Future scheduling can use a separate scheduling field or a justified migration; it must not silently change the public state contract. Webhook receipts, outbox, leases, publication records, and user-session tables remain deferred.

Use stable unique GitHub IDs plus UUID internal keys. Enforce job installation/repository/PR consistency with composite foreign keys; preserve both base/head SHA and policy digest in the analysis identity. Enforce state/timestamp, finding range/path, attempt, and usage invariants in PostgreSQL. Deleting installations, repositories, or PRs with history is restricted. Deleting a job cascades its findings and execution metadata. Future transfer/retention behavior needs an explicit migration/use case; these restrictive keys must not be bypassed.

Expose only read routes under `/v1/repositories` and `/v1/review-jobs`, with explicit Pydantic allowlists, bounded keyset pagination, filter-bound cursors, and safe error envelopes. Keep the read interface framework-independent; SQLAlchemy implements it behind a port. Cursor contents are navigation data, not signed credentials; every query independently enforces access.

Real GitHub authentication is outside this phase. The API denies protected routes by default. A development-only bearer token and explicit server-configured `(installation GitHub ID, repository GitHub ID)` grants enable the demo. No request header or resource filter may establish those grants. Active installation/repository status is checked on each query. Production rejects enabling development authentication and has no working user-login adapter yet. This is a safe incomplete production surface, not production authentication.

The synthetic seed is an explicit CLI restricted to development, a loopback host, and the `shrike_demo` database name; it requires an acknowledgement flag. It never runs on startup or through an HTTP endpoint. It refuses non-demo nonempty databases and is idempotent for the unchanged dataset. All fixtures and review results are invented; nothing was fetched from GitHub or an LLM.

Tests use a unique tmpfs PostgreSQL container per invocation and a new randomly named database per integration test, migrated through Alembic. The test container's passwordless role is confined to a random loopback port and removed afterward. The normal development Compose database instead requires a generated password. Neither tests nor application configuration reads the existing checkout `.env` automatically.

## Consequences

The original webhook Phase 2 becomes deferred Phase 2B. The broader Phase 1 remains incomplete; the current phase supplies only its minimum backend prerequisites. The modular monolith, future worker/interfaces, mock-first AI policy, and all cost/security boundaries remain in force. No migration of pre-existing application data is needed because this is the first schema. `downgrade base` is intentionally destructive and permitted only on disposable/demo databases after considering backups.

Package installation requires registry access on the first setup. Tests themselves use local PostgreSQL and in-process HTTP requests without GitHub, model, or paid-service access. Production auth, migration deployment automation, database-role hardening, retention/erasure workflows, and the full product stack remain future work.

## References

- [SQLAlchemy session lifecycle](https://docs.sqlalchemy.org/en/21/orm/session_basics.html)
- [Alembic commands and shared migration connections](https://alembic.sqlalchemy.org/en/latest/api/commands.html)
- [FastAPI dependencies with cleanup](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/)
- [uv workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/)
