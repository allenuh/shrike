# Shrike

Canonical repository: [allenuh/shrike](https://github.com/allenuh/shrike).

Shrike is an AI-assisted GitHub code review platform under development. The planned workflow will validate GitHub App webhooks, queue Python-focused reviews, combine Ruff and Semgrep findings with validated LLM suggestions, and publish feedback to GitHub. A dashboard will show history, findings, and metrics.

**Current status: Phase 8 system evaluation, verified to local synthetic/mocked scope.** The authenticated Next.js dashboard and existing webhook/Redis/Celery/Ruff/publication pipeline now have a repeatable CI-ready verification command, labeled quality corpus and bounded HTTP/queue benchmarks. Measurements expose security/data-flow misses, unreachable-code false positives and throttle-related attempt exhaustion. See the evaluation/performance documents below for evidence and limits. The dashboard defaults to a credential-free read-only demo; explicit live mode uses server-owned OAuth sessions and repository authorization. No real model request, live GitHub login/smoke test, actual published feedback, hosted CI run or cloud deployment is claimed.

## Project documents

- [System evaluation](docs/EVALUATION.md): mock-only CI entry point, labeled precision/recall, security/failure coverage and measured weaknesses.
- [Performance](docs/PERFORMANCE.md): reproducible loopback API/Redis/Celery load workloads, measurements, environment and limits.
- [Product requirements](docs/PRD.md): requirements, MVP limits, non-goals, risks, and costs.
- [Architecture](docs/ARCHITECTURE.md): repository layout, interfaces, lifecycle, schema, decisions, and threat model.
- [AI cost controls](docs/AI_COST_CONTROLS.md): mock-only development, the approximate $10 API budget, and future paid-request safeguards.
- [Analysis and evaluation commands](docs/runbooks/analysis-local.md): offline fixtures, reports, dry runs, restricted scanner, and separately opted-in live evaluation.
- [Dashboard setup and validation](docs/runbooks/dashboard-local.md): credential-free seeded demo, frontend checks, GitHub App user OAuth/session setup and manual end-to-end validation.
- [GitHub publication](docs/runbooks/github-publication.md): report-only preview, explicit repository-scoped publishing, test-repository setup, manual end-to-end validation and uncertainty recovery.
- [Asynchronous processing](docs/runbooks/async-processing.md): Redis/Celery setup, offline end-to-end tests, worker/dispatcher commands, recovery and guarded job inspection/retry.
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

The backend uses Python 3.12 and uv; tested tool versions and commands are in the backend runbook. Python dependencies are pinned in the workspace manifests and `uv.lock`; the PostgreSQL 17 image is pinned by digest. Docker Desktop must use Linux containers. The dashboard uses Node.js 22.12+ and npm with exact versions in `apps/web/package-lock.json`; Node 26.3.0/npm 11.2.0 were tested. Use a supported Node LTS for deployment. Frontend dependencies are trusted Shrike tooling, installed with lifecycle scripts disabled under the explicit user exception; fetched PR dependencies are never installed.

Every value in [.env.example](.env.example) is a placeholder. The backend deliberately does not load `.env` automatically. Follow the runbook to export only the settings this phase uses, create the local demo database, migrate, seed, and start the API. No GitHub or model credential is needed. Preserve any existing local `.env`. Never commit credentials, private code fixtures, or production data.

From the repository root, after installing the prerequisites:

```powershell
uv --cache-dir .cache/uv sync --locked
uv --cache-dir .cache/uv run --locked ruff check .
uv --cache-dir .cache/uv run --locked ruff format --check .
uv --cache-dir .cache/uv run --locked mypy
uv --cache-dir .cache/uv run --locked python scripts/test_backend.py -q
```

The test runner creates unique temporary PostgreSQL and authenticated Redis containers, a disposable database per integration test, and random broker namespaces, then cleans them up. It does not use the demo database or existing `.env`. Initial dependency/image downloads need registry access; GitHub/AI test integrations are mocked. The real Celery transport/Ruff tests use local Docker only. See the runbook for running unit tests without Docker.

Protected history APIs deny access by default. Development authentication requires an explicit opt-in, generated bearer token, and server-side installation/repository grants. Webhooks are disabled by default and use independent HMAC authentication when configured. Installing the App never grants all dashboard users access. GitHub App user OAuth is implemented behind explicit server-side configuration; live account setup remains manual and unverified. The authenticated dashboard is a local MVP, with production hardening still deferred.

A real GitHub App and publicly reachable HTTPS webhook URL are needed only when you deliberately configure live integration. Follow the separate manual runbook; no account setup or real App API calls were performed by Codex. Fork PRs and deleted fork heads are excluded. Reinstallation/transfers with existing ownership history are quarantined until a migration design supports them.

## Implementation order

AI development uses deterministic mocks exclusively (`AI_PROVIDER=mock`). The guarded hosted adapter requires explicit opt-in, verified model/pricing/token bounds, and a reconciled PostgreSQL budget. It reserves cost before sending, warns at $7.50, and stops new spending at $9.00; uncertain charges stay reserved. CI/tests use fake responses. The example price profile deliberately does not approve token bounds, so it cannot enable live requests. See the cost-control document for verification and billing limitations.

The user requested persistence/read APIs as Phase 2, GitHub ingestion as Phase 3, standalone analysis as Phase 4, and asynchronous processing as Phase 5. [ADR 0004](docs/adr/0004-asynchronous-processing.md) brings broker/fenced execution into Phase 5 and moved publication to Phase 5B. [ADR 0005](docs/adr/0005-github-publication.md) rebaselines publication as the user-requested Phase 6; dashboard work initially became Phase 6B. [ADR 0006](docs/adr/0006-saas-dashboard.md) brings the requested dashboard into Phase 7 and moves hardening to 7B. Remaining foundations, optional Semgrep, retention/production hardening and cloud remain separate work. The trusted host runs worker/scanner orchestration; do not mount a Docker socket into an API/worker container. Complete local hardening before cloud work. Verified tasks are committed automatically; completed phases are pushed under `AGENTS.md`.

Shrike will not run repository code, install repository dependencies, apply automatic fixes, or treat LLM output as trusted instructions. Reviews are advisory and will not gate merges in the MVP.

## Dashboard demo

From the repository root, use the explicitly authorized frontend tooling exception:

```powershell
Set-Location apps/web
npm ci --ignore-scripts --cache ../../.cache/npm
$env:NEXT_TELEMETRY_DISABLED = '1'
$env:SHRIKE_WEB_MODE = 'demo'
npm run dev
```

Open [Shrike locally](http://127.0.0.1:3000). The read-only demo contains only synthetic data and never contacts GitHub or the backend. For checks, production builds and the separate live OAuth configuration, follow the [dashboard runbook](docs/runbooks/dashboard-local.md). Applying migration `0007_dashboard` is required before restarting a persistent API; no existing user database was migrated during implementation.
