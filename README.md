# Shrike

Canonical repository: [allenuh/shrike](https://github.com/allenuh/shrike).

Shrike is an AI-assisted GitHub code review platform under development. The planned workflow will validate GitHub App webhooks, queue Python-focused reviews, combine Ruff and Semgrep findings with validated LLM suggestions, and publish feedback to GitHub. A dashboard will show history, findings, and metrics.

**Current status: Phase 3 GitHub App integration and PR ingestion, verified with mocks.** The backend has scoped read APIs, SQLAlchemy/Alembic persistence, raw-byte webhook authentication, a durable inbox, a metadata ingestion worker, and a read-only GitHub App client. Live account setup and a real GitHub smoke test remain manual and unperformed. There is no frontend, review executor, analyzer/LLM integration, publishing, Redis/Celery transport, CI workflow, or cloud deployment yet. Compose provides the development database.

## Project documents

- [Product requirements](docs/PRD.md): requirements, MVP limits, non-goals, risks, and costs.
- [Architecture](docs/ARCHITECTURE.md): repository layout, interfaces, lifecycle, schema, decisions, and threat model.
- [AI cost controls](docs/AI_COST_CONTROLS.md): mock-only development, the approximate $10 API budget, and future paid-request safeguards.
- [Roadmap](docs/ROADMAP.md): phases, measurable acceptance criteria, and validation status.
- [Agent instructions](AGENTS.md): rules for future implementation tasks.
- [Backend setup and manual verification](docs/runbooks/backend-local.md): exact local commands.
- [Phase scope decision](docs/adr/0001-persistence-phase-scope.md): the user-requested Phase 2 rebaseline.
- [GitHub App manual setup](docs/runbooks/github-app-manual.md): registration, read permissions, keys, tunnel, selected installation, and optional real smoke test.
- [Ingestion design decision](docs/adr/0002-github-ingestion.md): durable acceptance, canonical verification, and deferred broker/fork support.

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

Protected history APIs deny access by default. Development authentication requires an explicit opt-in, generated bearer token, and server-side installation/repository grants. Webhooks are disabled by default and use independent HMAC authentication when configured. Installing the App never grants all dashboard users access. Real GitHub user login remains deferred; this is not a production user-facing service.

A real GitHub App and publicly reachable HTTPS webhook URL are needed only when you deliberately configure live integration. Follow the separate manual runbook; no account setup or real App API calls were performed by Codex. Fork PRs and deleted fork heads are excluded. Reinstallation/transfers with existing ownership history are quarantined until a migration design supports them.

## Implementation order

AI development uses deterministic mocks exclusively. The planned hosted integration requires explicit opt-in, model configuration, conservative per-request cost reservations, and a persistent application-wide ledger that warns at $7.50 and stops new spending at $9.00. These controls and the provider interface are design requirements awaiting Phases 4/8; no live model or spending ledger is implemented. CI/tests remain mock-only. The buffer within the approximate $10 budget is not permission to spend. See the cost-control document for pricing verification and accounting limitations.

The user requested persistence/read APIs as Phase 2 and GitHub App ingestion as Phase 3. Remaining foundations, Redis/Celery dispatch, safe static analysis (Phase 3B), mock-assisted review, publishing, and the authenticated dashboard remain separate work. Complete local hardening before cloud work. See the [roadmap](docs/ROADMAP.md) for evidence. Meaningful verified tasks are committed automatically; completed verified phases are pushed under the standing policy in `AGENTS.md`.

Shrike will not run repository code, install repository dependencies, apply automatic fixes, or treat LLM output as trusted instructions. Reviews are advisory and will not gate merges in the MVP.
