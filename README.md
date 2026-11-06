# Shrike

Shrike is an AI-assisted GitHub code review platform under development. The planned workflow will validate GitHub App webhooks, queue Python-focused reviews, combine Ruff and Semgrep findings with validated LLM suggestions, and publish feedback to GitHub. A dashboard will show history, findings, and metrics.

**Current status: Phase 2 backend persistence and read APIs.** SQLAlchemy models, Alembic migrations, installation/repository-scoped FastAPI reads, synthetic demo data, and disposable PostgreSQL tests are implemented. There is no frontend, live webhook processing, worker pipeline, AI integration, CI workflow, or deployed infrastructure yet. Compose currently provides only the development database.

## Project documents

- [Product requirements](docs/PRD.md): requirements, MVP limits, non-goals, risks, and costs.
- [Architecture](docs/ARCHITECTURE.md): repository layout, interfaces, lifecycle, schema, decisions, and threat model.
- [Roadmap](docs/ROADMAP.md): phases, measurable acceptance criteria, and validation status.
- [Agent instructions](AGENTS.md): rules for future implementation tasks.
- [Backend setup and manual verification](docs/runbooks/backend-local.md): exact local commands.
- [Phase scope decision](docs/adr/0001-persistence-phase-scope.md): the user-requested Phase 2 rebaseline.

## Planned stack

| Area | Technology |
| --- | --- |
| Web | Next.js, React, TypeScript, Tailwind CSS |
| Backend | Python, FastAPI, Pydantic |
| Persistence | PostgreSQL, SQLAlchemy, Alembic |
| Jobs | Redis, Celery, database outbox and reconciliation |
| Integrations | GitHub App and REST API; provider-agnostic LLM interface |
| Analysis | Ruff, Semgrep, deterministic local mock LLM |
| Development and CI | Docker Compose, GitHub Actions |
| Later | AWS ECS, Terraform, OpenTelemetry |

The backend will be a modular monolith shared by an API process and worker processes. Redis is transport; PostgreSQL is the durable source of job and review state.

## Development preparation

The backend uses Python 3.12 and uv; tested tool versions and commands are in the backend runbook. Python dependencies are pinned in the workspace manifests and `uv.lock`; the PostgreSQL 17 image is pinned by digest. Docker Desktop must use Linux containers. Node.js is not needed for this backend-only phase; the future web application will require a supported Node.js LTS release.

Every value in [.env.example](.env.example) is a placeholder. The backend deliberately does not load `.env` automatically. Follow the runbook to export only the settings this phase uses, create the local demo database, migrate, seed, and start the API. No GitHub or model credential is needed. Preserve any existing local `.env`. Never commit credentials, private code fixtures, or production data.

From the repository root, after installing the prerequisites:

```powershell
uv --cache-dir .cache/uv sync --locked
uv --cache-dir .cache/uv run --locked ruff check .
uv --cache-dir .cache/uv run --locked ruff format --check .
uv --cache-dir .cache/uv run --locked mypy
uv --cache-dir .cache/uv run --locked python scripts/test_backend.py -q
```

The test runner creates a unique temporary PostgreSQL container and a disposable database per integration test, then removes them. It does not use the demo database or existing `.env`. Initial dependency/image downloads need registry access; test execution makes no GitHub, LLM, or paid-service calls. See the runbook for running unit tests without Docker.

The API denies access by default. Development authentication requires an explicit opt-in, generated bearer token, and server-side installation/repository grants. Real GitHub login remains deferred; this phase must not be exposed as a production user-facing service.

A real GitHub App and a publicly reachable HTTPS webhook URL will be needed only for an explicitly authorized integration smoke test. App registration, permission selection, callback URLs, secret generation, and an optional tunnel will be documented as manual steps. They have not been performed.

## Implementation order

The user requested persistence/read APIs before event processing. Remaining foundations, deferred webhook durability (Phase 2B), safe static analysis, mock-assisted review, GitHub publication, and the authenticated dashboard remain separate phases. Complete local hardening before cloud work. See the [roadmap](docs/ROADMAP.md) for phase boundaries and evidence.

Shrike will not run repository code, install repository dependencies, apply automatic fixes, or treat LLM output as trusted instructions. Reviews are advisory and will not gate merges in the MVP.
