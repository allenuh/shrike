# Asynchronous ingestion and review operations

Scope: Phase 5 host-operated Celery worker and dispatcher, PostgreSQL durability, Redis transport, existing isolated Ruff, and deterministic mock AI. GitHub feedback publishing is separately implemented in [Phase 6](github-publication.md); workers still never publish. [ADR 0004](../adr/0004-asynchronous-processing.md) records the phase rebaseline and security boundary. All integration verification uses synthetic GitHub data; no real App operation, model request, or published review was performed.

## Offline end-to-end verification

Use Python 3.12, uv and Docker Desktop/Linux containers. Install the pinned workspace and download the Redis image once:

```powershell
uv --cache-dir .cache/uv sync --locked
docker pull redis:8.2.3@sha256:0908d9af26bf9b985e984a40a5eb82eed229b07a3317eee6843832c3cc3a9619
$env:AI_PROVIDER = 'mock'
uv --cache-dir .cache/uv run --locked --offline python scripts/test_backend.py -q tests/integration/test_celery_pipeline.py
```

The runner starts unique tmpfs PostgreSQL and authenticated Redis containers on random loopback ports, creates a separate UUID database per test, and removes them afterward. Broker tests use unique prefixes and remove only their own keys; they never flush a shared Redis database. Never point `SHRIKE_TEST_DATABASE_URL` or `SHRIKE_TEST_REDIS_URL` at persistent data. Unit tests do not need Docker; see [backend-local.md](backend-local.md) for the unique temp-directory pattern.

The end-to-end test passes a raw signed synthetic webhook through the actual ASGI route, commits the outbox, sends a JSON task through real Redis, consumes it with a real Celery worker, runs actual isolated Ruff plus mock AI, and verifies findings/attempts in PostgreSQL. It also loses the test's broker namespace and verifies replay from PostgreSQL, and confirms webhook acceptance while a broker connection fails. This is not a live GitHub or real OpenAI compatibility/quality test. The in-process Celery test consumer uses the solo pool on Windows; Linux prefork process deployment remains a separate manual check.

Full validation:

```powershell
uv --cache-dir .cache/uv run --locked --offline ruff check .
uv --cache-dir .cache/uv run --locked --offline ruff format --check .
uv --cache-dir .cache/uv run --locked --offline mypy
uv --cache-dir .cache/uv lock --check --offline
uv --cache-dir .cache/uv run --locked --offline python scripts/test_backend.py -q --cov=shrike --cov=shrike_api --cov=shrike_worker --cov-report=term-missing
```

## Optional persistent local setup (manual)

These commands are instructions, not a claim that your persistent stack or GitHub account is configured. Use [backend-local.md](backend-local.md) for PostgreSQL/exported settings and [github-app-manual.md](github-app-manual.md) for separately performed App registration, read-only permissions, key outside checkout, selected test repository, and tunnel. Do not use the synthetic seed database for real GitHub integration. No Pull requests write permission is needed in this phase.

The API, dispatcher and worker use the same database and required schema revision `0005_execution`. Stop workers/dispatcher before migration; apply explicitly, never on process startup. Source credentials are supplied only through exported settings; the backend never auto-loads `.env`. Preserve any existing local secret file.

```powershell
$env:SHRIKE_LOCAL_REDIS_PASSWORD = & uv --cache-dir .cache/uv run --locked --offline python -c "import secrets; print(secrets.token_urlsafe(32))"
$env:CELERY_BROKER_URL = "redis://:$($env:SHRIKE_LOCAL_REDIS_PASSWORD)@127.0.0.1:56379/0"
$env:QUEUE_NAMESPACE = 'shrike'
$env:AI_PROVIDER = 'mock'
docker compose --env-file .env.example --profile queue config --quiet
docker compose --env-file .env.example --profile queue up -d postgres redis
uv --cache-dir .cache/uv run --locked --offline alembic upgrade head
```

Generate/export `SHRIKE_LOCAL_DB_PASSWORD` and the matching `DATABASE_URL` first, using the appropriate separate local database/project/port in the GitHub runbook. The commands above otherwise use the default Compose project/ports; change project and port settings consistently if using that isolated integration setup. For restart, reuse the same Redis password from your secret manager/session and the existing PostgreSQL data. Do not generate a new password every shell without updating all clients. Never print expanded Compose configuration; `config --quiet` avoids rendering secrets.

The `queue` Compose profile adds only Redis: loopback port 56379 (override `SHRIKE_LOCAL_REDIS_PORT`), non-root/read-only root, data volume, AOF, password required, no-eviction memory policy. Empty, short or non-URL-safe passwords refuse startup. Redis's AOF is supplemental; PostgreSQL outbox and recovery remain authoritative. The existing database-only Compose recipe continues to work without a Redis password/profile.

## Run processing

Start the API as in the backend runbook. In another shell with the same database/broker settings:

```powershell
uv --cache-dir .cache/uv run --locked --offline python -m shrike_worker.queue dispatch --watch
```

On a Linux/WSL host with the selected GitHub App settings exported and its read-only key accessible:

```text
uv --cache-dir .cache/uv run --locked --offline python -m shrike_worker.queue worker
```

Linux uses the prefork pool, concurrency two by default, one prefetched task per process, late acknowledgements and 190/210-second soft/hard task limits. PostgreSQL review claims impose a 180-second logical deadline and 240-second lease by default; checkpoints/heartbeat renew only current claims, and Ruff receives the remaining deadline. No result can commit after its deadline or after losing its fence. The worker's broker visibility timeout is 300 seconds, and PostgreSQL scheduling recovers work even if Redis never redelivers it.

For an explicitly development-only native Windows/local transport smoke, with `APP_ENV=development`, use `worker --development-threads`. Thread pools cannot enforce prefork kill limits; checkpoints, network/scanner timeouts, database deadlines and fences still apply. This flag is not production support. The implementation tests use a real solo consumer plus separate concurrent database claims; the persistent worker commands and Linux prefork deployment have not been run against your account. In WSL, use a separate ignored environment (for example export `UV_PROJECT_ENVIRONMENT=.venv-linux` before `uv sync --locked`) rather than replacing a Windows `.venv`.

The dispatcher periodically recovers expired review leases and publishes due outbox entries. `dispatch --once` is a bounded batch of up to 100 dispatch attempts and also runs recovery; `dispatch --watch` repeats. Do not run the old `shrike_worker.ingest --watch` poller alongside this path for normal operation; it remains compatible but redundant. Missing GitHub configuration refuses worker startup; offline verification uses injected test adapters, never an automatic fake in production. Settings follow the official [Celery Redis broker guidance](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html) and [configuration reference](https://docs.celeryq.dev/en/stable/userguide/configuration.html); PostgreSQL fences/reconciliation provide durability beyond broker acknowledgement behavior.

Queued processing deliberately rejects `AI_PROVIDER=openai`. The separately opted-in standalone Phase 4 evaluator remains the only hosted path. Do not enable Celery autoretry or add paid calls to startup/health checks. Provider admission occurs before any model invocation; cache hits bypass it. A future hosted queue task must separately prove spending reservation, uncertain outcomes and restart/retry behavior without bypassing the [AI budget controls](../AI_COST_CONTROLS.md).

## States, retries and recovery

- Public job states remain `pending`, `running`, `completed`, `failed`, `canceled`. Retry wait is `pending` with `available_at` and a safe error code. `first_started_at` preserves the first start; `started_at` describes the current attempt and resets during retry wait. Every execution retains its own start/finish/error/duration. Mock usage is explicitly not provider-reported usage; legacy API zero counts do not imply a paid call.
- At most three lifetime attempts per job. Transient GitHub/network/scanner/infrastructure failures and provider throttling use PostgreSQL exponential backoff (base five seconds, cap 300, deterministic bounded jitter), respecting longer provider retry times. Validation/identity/snapshot errors fail permanently; stale/closed/revoked work is canceled. Throttling is a bounded attempt and may exhaust retries under sustained overload; tune capacity/rate and inspect failures rather than silently looping.
- One unique job identity includes installation ownership, repository, PR, base/head and policy. Duplicate webhook delivery IDs and different deliveries for the same identity cannot duplicate execution rows/findings. Outbox generations invalidate delayed messages after retry; UUID leases fence late completion/failure from dead workers. Repository claims serialize across worker processes; separate repositories remain independent.
- Dispatcher publish failure retains committed work, with bounded per-poll backoff. Ambiguous publication to the broker or unclaimed work older than 30 seconds may resend the same IDs. Redis loss is not job loss; duplicate tasks are harmless. Broker retries do not consume review attempts. Inspect backlog from PostgreSQL, not a Celery result backend.
- An expired worker is recovered on the next dispatcher cycle: its running attempt becomes failed with `worker_lost`, a fresh generation is scheduled when attempts remain, and the old token cannot write results. A live attempt checks access/current revision before source retrieval and after analysis. New canonical heads disable eligibility of prior completed reports and cancel unfinished work. No public GitHub comment is posted here; any future publisher must recheck GitHub immediately before writing, because external revision checks cannot be atomic with GitHub.
- Killing a scanner normally removes its exact generated container in `finally`. A forced host/process/daemon failure can prevent cleanup; inspect `docker ps -a --filter name=shrike-scan-` and remove only the exact abandoned Shrike container after checking that no live worker owns it. There are no source mounts or persisted source files. An automated crash-container janitor remains deferred; do not run broad Docker prune commands.

## Development-only inspection and retry

These are operator CLI commands, not public endpoints. They require `APP_ENV=development`, exact opt-in `ENABLE_DEV_JOB_OPERATIONS=true`, and server-configured paired stable GitHub IDs in `DEV_REPOSITORY_GRANTS`. Production/test mode cannot enable them. Active ownership is rechecked for every operation; no grant means no access. Metadata only is printed: job UUID, state, attempts, timestamps, safe error and eligibility; no source, raw report, private paths or credentials.

```powershell
$env:APP_ENV = 'development'
$env:ENABLE_DEV_JOB_OPERATIONS = 'true'
$env:DEV_REPOSITORY_GRANTS = '<installation-github-id>:<repository-github-id>'
uv --cache-dir .cache/uv run --locked --offline python -m shrike_worker.queue inspect --state failed --limit 20
uv --cache-dir .cache/uv run --locked --offline python -m shrike_worker.queue inspect --job-id <job-uuid>
uv --cache-dir .cache/uv run --locked --offline python -m shrike_worker.queue retry --job-id <job-uuid>
```

Inspection/retry need PostgreSQL, not broker availability. Retry accepts only failed, still-current, accessible jobs with remaining attempts. It creates a new queue generation without deleting old execution/finding history or resetting the lifetime attempt ceiling. Completed, canceled, exhausted, stale and inaccessible jobs refuse retry. Synthetic historical demo jobs are not automatically eligible for live re-execution. Fix the underlying failure first; a new revision/policy or a separately designed audited rerun is required after exhaustion. Never edit counters, clear ledgers, or delete deduplication records to unblock a demo.

Worker logs use allowlisted structured request/job/record IDs, attempt, state and safe error code. The original HTTP request ID is persisted in the outbox and follows review execution. Arbitrary Celery messages, tracebacks, broker URLs, payloads, repository paths and source are excluded; stream failure also cannot echo raw log records. Use job UUID/request ID to correlate API and worker events. Traces, dashboards, retention automation and production alerts remain later work.

Before schema rollback, stop all processing. Downgrading `0005_execution` removes scheduling/report eligibility metadata and provider-admission clocks but retains earlier history/accounting tables; downgrading `0004_outbox` removes dispatch history. Restart only after migration/reconciliation checks. Never perform destructive migration tests on the live integration or demo database. [ROADMAP.md](../ROADMAP.md) records executed tests, temporary Compose verification and remaining manual steps.
