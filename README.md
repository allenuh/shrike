# Shrike

Shrike is a planned AI-assisted GitHub code review platform. It will validate GitHub App webhooks, queue Python-focused reviews, combine Ruff and Semgrep findings with validated LLM suggestions, and publish feedback to GitHub. A dashboard will show review history, findings, and operational metrics.

**Current status: architecture and planning only.** There is no runnable application, Compose stack, dependency manifest, CI workflow, or deployed infrastructure yet.

## Project documents

- [Product requirements](docs/PRD.md): requirements, MVP limits, non-goals, risks, and costs.
- [Architecture](docs/ARCHITECTURE.md): repository layout, interfaces, lifecycle, schema, decisions, and threat model.
- [Roadmap](docs/ROADMAP.md): phases, measurable acceptance criteria, and validation status.
- [Agent instructions](AGENTS.md): rules for future implementation tasks.

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

Install Git, Docker Desktop with Linux containers and Compose v2, Python 3.12, and a supported Node.js LTS release. Phase 1 will pin exact runtime and dependency versions and commit lockfiles. On Windows, use Linux containers for the worker and scanner isolation; WSL2 is recommended.

Copy the configuration template only if you do not already have a local environment file:

```powershell
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
```

Every value in [.env.example](.env.example) is a placeholder. Generate local credentials and keys when the corresponding phase is implemented. Keep the GitHub App PEM outside the repository and mount it read-only into the backend containers. Never commit `.env`, private keys, tokens, private code fixtures, or production data.

**No application startup or test command is available yet.** Phase 1 will add a supported `docker compose up --build` workflow, migration instructions, health checks, and exact validation commands. Later phases will add an offline synthetic webhook replay and mock GitHub integration so local tests require neither credentials nor paid services. The mock LLM requires no API key.

A real GitHub App and a publicly reachable HTTPS webhook URL will be needed only for an explicitly authorized integration smoke test. App registration, permission selection, callback URLs, secret generation, and an optional tunnel will be documented as manual steps. They have not been performed.

## Implementation order

Build foundations, webhook durability, safe static analysis, mock-assisted review, GitHub publication, and the authenticated dashboard in separate phases. Complete local hardening before cloud work. See the [roadmap](docs/ROADMAP.md) for phase boundaries and exit criteria.

Shrike will not run repository code, install repository dependencies, apply automatic fixes, or treat LLM output as trusted instructions. Reviews are advisory and will not gate merges in the MVP.
