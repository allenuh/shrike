# Local backend development and verification

Scope: the offline synthetic persistence/read-API demo. All seeded data is invented. Optional Phase 3 GitHub ingestion uses a separate integration database and is documented in [github-app-manual.md](github-app-manual.md). There is no real user login, LLM/scanner execution, publishing, or frontend. Leave GitHub modes disabled for this synthetic demo.

## Prerequisites and dependency setup

Use Python 3.12 (the checkout pins the locally tested 3.12.6 interpreter), uv 0.13.7, and Docker with Linux containers. The full Phase 1 runtime/CI hardening is still deferred. PostgreSQL 17 is pinned by image digest in `compose.yaml` and `infra/docker/postgres-image.txt`; keep these references synchronized when deliberately updating it.

The implementation was developed on Windows/PowerShell with Docker Server 29.9.2. Do not assume Docker is running merely because the CLI exists. Dependency/image installation requires registry access; no test requires GitHub, a model API, credentials for those services, or a paid provider.

From the repository root:

```powershell
uv --cache-dir .cache/uv sync --locked
```

The virtual environment and cache are ignored. Commit manifests and `uv.lock`, not `.venv`, caches, generated reports, or secrets. The API and Alembic read exported environment variables; they do not load the existing checkout `.env`. The commands below explicitly select `.env.example` for Compose so Compose does not implicitly read `.env` either. Placeholder-only templates cannot start the application without actual local settings.

## Automated verification

```powershell
uv --cache-dir .cache/uv run --locked ruff check .
uv --cache-dir .cache/uv run --locked ruff format --check .
uv --cache-dir .cache/uv run --locked mypy
uv --cache-dir .cache/uv run --locked python scripts/test_backend.py -q
```

The runner creates a unique `shrike-tests-*` PostgreSQL container with tmpfs data and a random loopback port. The passwordless test role exists only inside that disposable container. Each integration test creates its own random `shrike_test_<uuid>` database, applies the real migration, and drops only that database afterward. The runner removes only its own container in `finally`. No demo/production schema is reset. Do not supply a production URL as `SHRIKE_TEST_DATABASE_URL`; test fixtures accept only the explicit loopback `shrike_test` administration database.

Unit tests can run without Docker:

```powershell
uv --cache-dir .cache/uv run --locked pytest tests/unit -q
```

To verify migration upgrade, metadata agreement, downgrade, and re-upgrade without risking demo data:

```powershell
uv --cache-dir .cache/uv run --locked python scripts/test_backend.py -q tests/integration/test_migrations.py::test_upgrade_downgrade_upgrade_and_metadata_agreement
```

The current `downgrade base` drops all seven application tables and their content. Downgrading only to `0001_core` removes ingestion receipts/access metadata while retaining Phase 2 data. Use disposable databases for this verification. Migrations are never automatically applied on API startup.

## Start the synthetic demo

Run these commands in one PowerShell session. Generate secrets without printing them:

```powershell
$env:SHRIKE_LOCAL_DB_PASSWORD = [Guid]::NewGuid().ToString('N')
$env:DEV_AUTH_TOKEN = [Guid]::NewGuid().ToString('N')
$env:APP_ENV = 'development'
$env:GITHUB_MODE = 'disabled'
$env:GITHUB_WEBHOOKS_ENABLED = 'false'
$env:ENABLE_DEV_AUTH = 'true'
$env:DEV_REPOSITORY_GRANTS = '710001:810001'
$env:DATABASE_URL = 'postgresql+psycopg://shrike:{0}@127.0.0.1:55432/shrike_demo' -f $env:SHRIKE_LOCAL_DB_PASSWORD

docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example up -d --wait postgres
uv --cache-dir .cache/uv run --locked alembic upgrade head
uv --cache-dir .cache/uv run --locked alembic check
uv --cache-dir .cache/uv run --locked python -m shrike_api.seed --confirm-development
uv --cache-dir .cache/uv run --locked python -m shrike_api.seed --confirm-development
```

Expected seed output is `Synthetic demo data inserted` followed by `Synthetic demo data already present`. The seed requires `APP_ENV=development`, the exact database name `shrike_demo`, a loopback database host, and the flag. It refuses an unrelated nonempty database or modified/incomplete dataset. No seed HTTP endpoint exists, and normal startup never seeds.

Compose stores the demo database in its named volume. If restarting an existing volume, reuse its original password; changing the environment variable does not rotate the database user's password. Keep generated local secrets in an appropriate local secret store if needed across sessions. Do not overwrite the pre-existing `.env` or commit real environment values.

Start the API in that same session:

```powershell
uv --cache-dir .cache/uv run --locked uvicorn shrike_api.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

The API is available at `http://127.0.0.1:8000`; development OpenAPI documentation is at `/docs`. Only the synthetic payments repository is granted by the configuration above. The sibling repository and the other installation's repository are intentionally hidden. To inspect the sibling's canceled job, deliberately add `710001:810002` to the server-side grant list and restart. A resource query or `X-Installation-ID` header cannot add access.

Default configuration denies protected routes. Development auth cannot be enabled in production; real GitHub OAuth/session integration remains future work. Bind locally and do not publish this demo API to the Internet. Tokens must be 32â€“512 characters, not placeholders. There is no browser frontend in this phase.

## Manually inspect responses

Use a second PowerShell session and set its `DEV_AUTH_TOKEN` to the same generated token through your local secret store, without printing or committing it. Do not generate a different token. Then:

```powershell
$baseUrl = 'http://127.0.0.1:8000'
$demoHeaders = @{ Authorization = 'Bearer ' + $env:DEV_AUTH_TOKEN }
Invoke-RestMethod "$baseUrl/health/live"
Invoke-RestMethod "$baseUrl/health/ready"
$repositories = Invoke-RestMethod "$baseUrl/v1/repositories?sort=name&order=asc" -Headers $demoHeaders
$history = Invoke-RestMethod "$baseUrl/v1/review-jobs?state=completed&limit=2&order=asc" -Headers $demoHeaders
$completed = $history.items | Select-Object -First 1
Invoke-RestMethod "$baseUrl/v1/review-jobs/$($completed.id)" -Headers $demoHeaders
Invoke-RestMethod "$baseUrl/v1/review-jobs/$($completed.id)/findings?severity=high&source=semgrep" -Headers $demoHeaders
```

Expected: one authorized repository, a completed job with three findings and one synthetic execution record, and one high-severity Semgrep finding. No API response contains the internal worker identifier, policy digest, database URL, bearer token, or credential columns. Unauthenticated requests return `401`. Unknown and inaccessible object IDs both return a generic `404`. Filtering by an ungranted installation/repository returns an empty list.

| Route | Supported filters and sorting |
| --- | --- |
| `GET /v1/repositories` | `installation_id` (internal UUID), `private`, literal case-insensitive `search`; `sort=created_at|name` |
| `GET /v1/repositories/{id}` | Authorized repository detail |
| `GET /v1/review-jobs` | `installation_id`, `repository_id` (internal UUIDs), `pull_request_number`, `state`, timezone-aware inclusive `created_after`/`created_before`; `sort=created_at|state` |
| `GET /v1/review-jobs/{id}` | Job, finding count, first findings page, and up to three execution records |
| `GET /v1/review-jobs/{id}/findings` | `severity`, `source`; `sort=severity|path` |

Lists accept `limit=1..100` (default 20), `order=asc|desc` (default descending), and an opaque `cursor`. State ordering is alphabetical; severity ordering uses info < low < medium < high < critical. Every sort includes UUID as a tie-breaker. Detail findings use the default severity-descending order and first 20 records; follow their `next_cursor` through the findings route with the same filters/order. Encode the cursor as a query parameter, and keep filters/order/access scope unchanged; changing them returns `422`. Limit may change between pages. Pagination is a live keyset view, not an immutable multi-request snapshot.

Invalid filters, naive/reversed date ranges, malformed cursors, and unknown query parameters return sanitized `422` error envelopes. Errors have `error.code`, `error.message`, and `error.request_id`; the generated ID also appears in `X-Request-ID`. Database errors return sanitized `503`; unexpected errors return `500`. Liveness is process-only; readiness requires database connectivity and revision `0002_github`.

Structured request logs contain a generated request ID, HTTP method category, status, and duration. They omit URL/query strings, headers, repository paths, findings, raw exceptions, and database parameters. Uvicorn's default access logger is disabled by the factory as well as by the documented command. Do not enable SQL echo, request-body logging, or debug tracebacks for private data.

Stop the API with Ctrl+C and stop the database without deleting its data:

```powershell
docker compose --env-file .env.example stop postgres
```

## Verification record

See [ROADMAP.md](../ROADMAP.md) for checks actually executed and outcomes. The commands in this runbook are manual instructions unless the record explicitly says they were performed. No GitHub App, OAuth credentials, live webhook, LLM provider, frontend, or cloud resource was configured.
