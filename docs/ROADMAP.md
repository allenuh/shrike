# Shrike implementation roadmap

Planning baseline: 2026-11-06. The user redefined Phase 2 as persistence/read APIs and Phase 3 as secure GitHub App integration/PR ingestion. [ADR 0001](adr/0001-persistence-phase-scope.md) and [ADR 0002](adr/0002-github-ingestion.md) record the scope changes. Implement only requested phases. The user's standing authorization in `AGENTS.md` permits commits after meaningful verified tasks and pushes after completed verified phases; this does not authorize starting future phases.

## Status and evidence rules

Use `not started`, `in progress`, `blocked`, or `verified`. A phase is `verified` only when its exit criteria have recorded evidence. Code written, tests proposed, and manual steps documented are not equivalent to verification. If part of a phase passes, record that evidence while leaving the phase incomplete. Record command/date/environment details in the task report or a committed validation note; never invent output.

| Phase | Outcome | Status |
| --- | --- | --- |
| 0 | Repository inspection and implementation plan | Verified: documentation and repository-hygiene checks passed |
| 1 | Reproducible monorepo and full local foundations | Not complete: only Python/API/database prerequisites supplied by Phase 2 |
| 2 | Persistence and core backend read APIs | Verified: 124 tests, migrations/constraints/API isolation, lint/types, and loopback HTTP smoke passed |
| 2B | Full Redis/Celery dispatch and recovery | Required local portions delivered and verified in Phase 5; deployed runner/retention remain future hardening |
| 3 | Secure GitHub App integration and PR ingestion | Verified: 185 tests, migrations/security/CLI checks, lint/types, configuration and documentation validation passed |
| 3B | Safe immutable snapshots and static analysis | Partly absorbed into Phase 4: restricted Ruff/snapshot parser; queue integration and Semgrep remain deferred |
| 4 | Standalone AI-assisted analysis, guarded provider, reports and cost ledger | Verified to offline/mocked scope: 267 tests, isolated Ruff, migrations, budget/cache/security checks, lint/types and evaluation passed |
| 5 | Asynchronous ingestion/review processing through Redis/Celery | Verified locally: real transport/storage/scanner, mocked GitHub/AI; fenced retries/concurrency/recovery and guarded operations pass |
| 6 | Independent GitHub advisory publication and recovery (formerly 5B) | Verified locally: 349 tests, 91% coverage, mocked GitHub publication and real PostgreSQL/Redis/Celery/Ruff; evidence below |
| 7 | Authenticated Shrike dashboard (formerly 6B) | In progress: backend auth/scoped metrics verified; frontend verification underway |
| 7B | Local MVP hardening and portfolio evidence | Not started; deferred by the Phase 7 dashboard request |
| 8 | Live model evaluation and operational accounting hardening | Separate follow-up; guarded adapter/ledger brought forward into Phase 4 |
| 9 | AWS ECS, Terraform, OpenTelemetry | Not started; deferred |

Phase 2 supplies backend prerequisites; Phase 3 adds the inbox; Phase 4 adds standalone analysis; Phase 5 connects asynchronous processing. The user-requested Phase 6 publication supersedes 5B under [ADR 0005](adr/0005-github-publication.md); dashboard work initially became 6B. [ADR 0006](adr/0006-saas-dashboard.md) moves the user-requested dashboard into Phase 7 and defers hardening to 7B. Remaining local foundations, optional Semgrep/deployed-runner validation, publication, dashboard and hardening remain separately requested work. Phases 8/9 require a verified local MVP; cloud does not require a paid model. Historical phase records retain their original validation snapshots.

## Project identity and AI budget update

This section records the earlier documentation-only planning update. ADR 0003 and the Phase 4 implementation below subsequently bring its provider/accounting gates forward; historical validation counts are not current source counts.

Shrike is the canonical name and `https://github.com/allenuh/shrike.git` is the canonical repository. The 2026-11-06 naming audit found the existing application/configuration already uses Shrike; no package, service, schema, or data rename is needed. Planned portfolio deliverables and future services must use Shrike.

The approximate total OpenAI API development budget is $10 USD, with cumulative warning at $7.50 and hard stop at $9.00. [AI_COST_CONTROLS.md](AI_COST_CONTROLS.md) is the planned enforcement contract. Phase 4 supplies a deterministic mock and provider contracts; Phase 8 supplies the verified pricing, persistent ledger, atomic reservation gate, and opt-in hosted/evaluation adapters. All ordinary development, CI/CD, unit/integration tests, and automated evaluation remain mock-only. No real AI API call or cloud action is authorized by this update. Existing phase order/status remains unchanged; the new controls are future acceptance gates, not completed features.

Validation record for this documentation/configuration task (2026-11-06, Windows/PowerShell):

- An inline Python standard-library validator run through `.venv/Scripts/python.exe -` passed: all 79 tracked/new project files have no stale project names or private-key blocks; ten Markdown documents have balanced fences and 34 resolving local links; all 60 example settings are unique placeholders with consistent mock/limit/budget values. The validator also checked final newlines, whitespace, conflict markers, canonical origin, secret/cache ignore rules, the exact seven-file change scope, and preservation of every pre-existing `AGENTS.md` instruction. The existing `.env` was not read or edited.
- `docker compose --env-file .env.example config --quiet` passed with a generated password supplied only to the child process. No services, tunnel, model requests, or cloud resources were started. Official model/pricing documentation was read; no authenticated OpenAI API call was made and no token rates were added as runtime defaults.
- `git -c core.excludesFile= diff --check` passed; Git emitted only LF/CRLF conversion notices. Application lint/type/test/migration checks were not rerun because no source, dependency, schema, or application behavior changed. Existing Phase 2/3 test records remain historical evidence; Phases 4/8 and all cost-control enforcement remain unimplemented.

## Phase 0: inspect and plan

Deliver exactly the requested planning/configuration files, with no application scaffolding or external API calls.

Acceptance criteria:

- Inspect tracked/untracked repository state and applicable contributor guidance without exposing existing secrets.
- Present the design and significant decisions before writing files.
- Create `AGENTS.md`, `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `README.md`, `.gitignore`, and placeholder-only `.env.example`.
- Cover requirements/non-goals, proposed structure, architecture/lifecycle, schema, decisions/tradeoffs, security/threats, phases, local tooling, risks/costs/scope creep.
- Check relative documentation links, placeholder-only environment values, ignore rules, diff whitespace, and absence of application scaffolding.
- Preserve the local `.env`; report validation performed and all unperformed application/integration checks honestly.

Validation record (2026-11-06, Windows/PowerShell, Python 3.12 interpreter):

- Repository inspection and pre-write design presentation completed; all seven requested files exist. The existing `.env` was neither read nor edited.
- An inline Python documentation/hygiene validator passed: eight relative Markdown links resolve, all 36 environment settings have unique names and placeholder-only values, 13 Git ignore cases behave correctly (including example files and lockfiles), and all seven files pass final-newline/trailing-whitespace/conflict-marker checks. Markdown code fences are balanced. Workspace inventory contains only these seven files plus the pre-existing `.env`, excluding Git internals.
- `git -c core.excludesFile= diff --check` passed (exit 0); Git emitted only its LF-to-CRLF working-copy conversion notice. Untracked files were covered by the explicit Python whitespace checks. `git -c core.excludesFile= status --short` confirmed the expected changes. The per-command override bypasses an unreadable global ignore configuration without changing repository/user settings.
- A manual consistency review confirmed requirements, lifecycle/schema, security, phase boundaries, limits, and deferred work agree across documents.
- No application tests/builds, Docker startup, migrations, real GitHub/LLM calls, tool-version compatibility checks, or cloud actions were performed. All implementation phases remain not started.

## Phase 1: local foundations

Create only the minimal monorepo foundation: shared backend package, FastAPI health routes, worker entry point, dispatcher command, Next.js shell, PostgreSQL/Redis Compose services, configuration validation, initial migration tooling, and CI. Do not implement webhook/review features yet.

Acceptance criteria:

- Pin supported Python/Node/container/dependency versions and commit package lockfiles. Document package-manager and environment-key format decisions.
- A fresh checkout starts using documented Compose commands; web/API health respond; database and broker remain on private networks; required migration/schema readiness is checked.
- Migrate an empty ephemeral PostgreSQL database to head; verify schema state. Document migration rollback/recovery policy, including any deliberately irreversible future migrations.
- Mock mode starts without GitHub/provider credentials; required placeholders fail startup with safe messages. No credentials appear in frontend bundles or config logs.
- Keep AI configuration mock-only in development/CI profiles; missing keys never trigger credential discovery or paid fallback. Label future example settings until implemented.
- CI runs Python lint/format/type checks, meaningful foundation tests, TypeScript/lint/build checks, and Compose configuration validation using synthetic local configuration.
- Record exact setup/check commands, tool versions, service health, and remaining manual prerequisites. Do not claim a live GitHub integration.

## Phase 2: persistence and core backend APIs

Current authorized scope: six SQLAlchemy models, initial Alembic migration, connection/session management, scoped repositories/history/detail/findings reads, filtering/keyset pagination/sorting, Pydantic schemas, a guarded synthetic development seed, safe errors/logging, and disposable PostgreSQL unit/integration verification. Do not add live GitHub webhooks, AI calls, frontend product features, or automatic commits.

Acceptance criteria:

- Use unique stable GitHub IDs for installations, repositories, and PRs; enforce PR number uniqueness within a repository, analysis identity uniqueness across base/head/policy, finding fingerprint uniqueness per job, and execution attempt uniqueness per job.
- Enforce explicit `pending`, `running`, `completed`, `failed`, and `canceled` job states, valid timestamps, bounded findings, valid line/path values, and nonnegative execution usage. Represent cancellation without pretending a worker/cancel endpoint exists.
- Enforce job installation/repository/PR ownership using composite foreign keys. Keep framework-independent read contracts separate from SQLAlchemy and HTTP implementations.
- Provide connection pooling and request-owned sessions with cleanup/rollback. No automatic migration or seed on API startup.
- Expose authorized repositories, review history, detail including findings/executions, and paginated findings. Support documented filters, allowlisted sorts, bounded limits, cursor validation, and deterministic tie-breakers.
- Deny protected reads by default. Development-only bearer access uses explicit server-side installation/repository grant pairs and active-status checks; production cannot enable it. Inaccessible objects return generic `404`; lists and filters cannot expand access.
- Use explicit Pydantic response allowlists that omit credentials and internal worker/policy/fingerprint columns. Structured logs and error envelopes never echo headers, raw exceptions, database values, private paths, or query input.
- Provide an explicit, idempotent synthetic seed CLI guarded by environment, loopback host, database name, and confirmation flag. Do not expose a seed endpoint or mutate unrelated data.
- Verify real PostgreSQL migration up/down/up and metadata agreement, uniqueness/check/FK behavior, scoped API responses, pagination, revocation, secret redaction, seed repeat/refusal, rollback, and database-per-test isolation. Unit tests must run without Docker; full integration tests must use disposable PostgreSQL, not SQLite.
- Pass locked dependency checks, Ruff lint/format, strict mypy, Compose validation, and relevant tests. Document manual setup/migration/API commands and distinguish them from actually executed checks.

Verification record (2026-11-06; Windows/PowerShell, Python 3.12.6, uv 0.13.7, Docker Server 29.9.2, digest-pinned PostgreSQL 17):

- `uv --cache-dir .cache/uv run --locked python scripts/test_backend.py -q --cov=shrike --cov=shrike_api --cov-report=term-missing`: **124 passed in 14.61 seconds; 98% statement coverage** across shared/backend API modules. This includes real PostgreSQL upgrade/down/upgrade and Alembic metadata checks, uniqueness/FK/check violations, base-revision identity, seed repeat/refusal, per-test database isolation, rollback, scoped reads, stable pagination, paired/empty grants, revocation, safe responses, and redaction. Temporary test containers were removed by the runner; an explicit Docker inventory check confirmed no `shrike-tests-*` containers remained.
- Unit-only execution without Docker: **38 passed** using `uv --cache-dir .cache/uv run --locked --offline pytest tests/unit -q -p no:cacheprovider --basetemp <unique-workspace-cache-directory>`. The ordinary sandboxed unit command initially hit permissions on pytest cache/temp directories created by an elevated run; the successful rerun used a fresh workspace temp directory and disabled that shared cache. No application change was needed for this environment restriction.
- `uv --cache-dir .cache/uv run --locked --offline ruff check .`: passed. `uv --cache-dir .cache/uv run --locked --offline ruff format --check .`: 42 files already formatted. `uv --cache-dir .cache/uv run --locked --offline mypy`: passed for 35 source files, including migrations and tests. Initial formatting/type issues were corrected before these successful checks.
- `uv --cache-dir .cache/uv lock --check --offline`: passed; 44 locked packages. Direct imports are explicitly pinned; editable package rebuilds succeeded. Initial dependency installation needed approved registry access because the sandbox blocks network access; the runtime tests used no external GitHub/LLM services. The pinned Starlette test client required `httpx2`; its deprecated `httpx` fallback was replaced before the successful suite.
- `docker compose --env-file .env.example config --quiet` with a generated exported local password: passed. This validates the database-only Compose configuration without reading the existing `.env`; the persistent Compose demo stack was not started.
- A temporary loopback Uvicorn process against a separate synthetic `shrike_demo` database passed real HTTP liveness/readiness, authorized repository/history/detail/findings reads, request IDs, and anonymous `401` checks. Programmatic Alembic upgrade/head consistency and the guarded seed CLI (insert, then no-op) passed. The token was generated in memory; captured server output contained neither token nor request URL paths. The API process and task-owned temporary migration/demo database container were stopped/removed afterward.
- Documentation/source hygiene checks passed for seven Markdown documents, 16 relative links, 40 placeholder-only environment values, synchronized PostgreSQL image pins, exact dependency pins, and all 53 tracked/new source/document files. Existing `AGENTS.md` is unchanged. `git -c core.excludesFile= diff --check` passed with only Git's LF/CRLF conversion notices. The pre-existing `.env` was neither read nor edited and remains ignored.

Manual steps still required: follow [backend-local.md](runbooks/backend-local.md) to create/reuse your persistent local demo database/password, export a generated development token and grants, migrate/seed, and start the API. The persistent Compose recipe is documented, not claimed as performed. Phase 2 was subsequently committed and pushed as `9fc377e` before Phase 3. Real user login, full Phase 1 services/CI, broker dispatch, AI/static execution, frontend, retention automation, and cloud remain deferred.

## Phase 2B: webhook durability and job orchestration (deferred)

Implement signature verification, supported-event validation, receipt/outbox persistence, canonical reconciliation through a fake GitHub adapter, Celery dispatch, run identities, leases, retries, and broker-loss recovery. Real adapter connectivity is deferred to Phase 5.

Acceptance criteria:

- Missing/wrong signatures, malformed payloads, and oversize/chunked bodies return documented errors without scheduling work. Valid signatures are tested over exact bytes.
- Replaying the same event 100 times creates one delivery receipt and one intended review run; different deliveries for the same base/head/policy still create one run.
- Kill dispatch after publish but before marking; duplicate work is harmless. Stop Redis during ingestion; accepted events remain in PostgreSQL and dispatch after recovery.
- Simulate Redis data loss and a worker crash after claim; reconciliation recovers work, fences old owners, and records attempts. No stale attempt can overwrite a newer result.
- Synthetic draft/close/base-change/removal/reordered lifecycle events yield correct skip/cancel/supersede state. A stale installation event cannot restore access.
- Demonstrate p95 acknowledgement under 500 ms for 100 sequential events on a documented local machine. Record actual results even if the target is missed.

## Phase 3: secure GitHub App integration and PR ingestion

Authorized scope: read-only App authentication/client; signed webhook acceptance; canonical installation/repository/PR metadata; durable deduplication and job creation; bounded file/diff/commit/blob reads; mocked tests; and separate manual App/tunnel instructions. No LLM, analyzer execution, publishing, frontend, or real account/repository modifications are part of the implementation. Git source commits/pushes follow the separately authorized development policy.

Acceptance criteria:

- Verify current GitHub permission documentation and request Metadata, Contents, and Pull requests read only. Keep tokens short-lived, scoped and in memory; keep private keys outside the checkout and secrets out of logs/responses.
- Verify exact bounded raw bytes with HMAC-SHA256/constant-time comparison before parsing. Enforce header/schema/App/installation/repository/PR/SHA consistency, JSON encoding/content-type, and body limits even without Content-Length.
- Receive opened/reopened/synchronize plus relevant lifecycle actions. Persist minimal receipts and metadata; deduplicate delivery IDs and logical job identity. Create pending jobs only after canonical verification, cancel obsolete work, and quarantine fork/draft/closed/archived PRs appropriately.
- Disable/quarantine revoked installation/repository access immediately. Fence stale workers and serialize per-installation snapshots; preserve deleted tombstones. Handle inaccessible resources without leaking provider response bodies or rewriting ownership history.
- Keep every GitHub call behind a typed port. Bound JSON, pagination, file count, diff and blob bytes; reject external URLs/redirects/unsafe paths; verify immutable identities; refresh expired tokens and honor durable rate-limit/transient retry schedules.
- Test the API, client, worker CLI, migration up/down/up and data preservation, deduplication, stale leases/revocation races, scopes/identity errors, forks, invalid signatures, chunked oversize input, HTTP retry behavior, and log/response privacy using synthetic data and disposable PostgreSQL. No real GitHub API call is required.
- Pass lint, formatting, strict types, locked dependency and Compose checks. Document account actions separately and distinguish mocked verification from a future operator-performed live smoke test. Commit verified tasks and push only once this phase is verified complete.

Verification record (2026-11-06, Windows/PowerShell, Python 3.12.6, uv 0.13.7, disposable digest-pinned PostgreSQL 17):

- `uv --cache-dir .cache/uv run --locked --offline python scripts/test_backend.py -q --cov=shrike --cov=shrike_api --cov=shrike_worker --cov-report=term-missing`: **185 passed in 22.87 seconds; 93% statement coverage**. This includes the old read API, initial and ingestion migrations up/down/up, retention of Phase 2 data when downgrading ingestion, real constraint behavior, signed/chunked requests, canonical identity checks, duplicate deliveries/jobs, fork exclusion, revocation races, per-installation snapshot serialization, expired leases, retry exhaustion, JWT/read-only token scope/cache/refresh, pagination/redirect bounds, diff/blob limits, and the worker CLI with a fake GitHub adapter.
- Unit-only execution without Docker: **68 passed in 1.18 seconds**, using `uv --cache-dir .cache/uv run --locked --offline pytest tests/unit -q -p no:cacheprovider --basetemp <unique-workspace-cache-directory>`. The isolated workspace temp/cache approach avoids the previously documented sandbox cache permissions issue.
- Ruff lint passed; `ruff format --check .` reported 62 files already formatted; strict mypy passed for 54 files including worker, migrations and tests; `uv lock --check --offline` resolved the locked 49 packages. Commands used `uv --cache-dir .cache/uv run --locked --offline`. Initial schema regex compatibility, formatting and typing issues were corrected before the successful final checks. Worker coverage is included in the final run.
- `docker compose --env-file .env.example config --quiet` passed with a generated exported password; the isolated `shrike-github` configuration also passed with port 55433. No persistent demo stack or tunnel was started. The task-owned temporary migration container was inspected and removed; test-runner container inventory was empty after completion.
- Final documentation/source hygiene passed: 78 tracked/new source/document files, nine Markdown documents, 24 relative links, 42 placeholder-only example settings, valid synthetic JSON fixtures, and no credential-bearing dependency URLs, committed private-key blocks, local `.env`, caches, or generated artifacts. `git diff --check` passed with only Git's LF/CRLF notices. The existing `.env` was not read or edited.
- Current GitHub permission/JWT/token/webhook/retry documentation was checked, and the separate manual runbook links the official sources. The standing automatic-commit/phase-push policy is recorded in `AGENTS.md` and committed as `5ca78d6`. The feature commit and completed-phase push are authorized after validation; Git history and the task report record their actual outcomes.

Manual account steps are in [github-app-manual.md](runbooks/github-app-manual.md). App registration, private-key creation, installation, tunnel startup, live PR creation, and real GitHub smoke testing remain **unperformed**. The full feature is not production hosting/authentication: user OAuth, Redis/Celery transport, retention automation, and analyzer/publishing runtimes remain deferred. Forks and reinstallation/transfer with existing history are quarantined by design.

## Phase 3B: safe snapshots and static analysis (deferred)

First prove the sandbox, then implement bounded GitHub snapshot contracts, diff mapping, Ruff, and Semgrep. Use fake GitHub responses and actual pinned scanner tools in tests. No repository execution or live private code is permitted.

Acceptance criteria:

- A sandbox probe demonstrates no network, no service credential/host filesystem access, non-root execution, and enforced resource/time/output limits in the supported Linux worker container. No privileged container or Docker socket is used. If infeasible, mark the phase blocked and document a justified alternative before proceeding.
- Positive Ruff/Semgrep fixtures trigger expected rules; negative/clean fixtures do not. Repository analyzer configs and malicious hooks are ignored and never executed.
- Correctly handle fork SHAs, base changes, renames, deletions, duplicate paths, traversal, symlink/submodule/binary entries, missing patches, pagination, and truncation using synthetic fixtures.
- Enforce every PRD byte/file/line limit. Show explicit partial/skip reasons; incomplete input never produces a clean result.
- Map new-side findings to exact changed lines. Unchanged-line findings cannot become inline comments.
- Kill a scanner and worker; verify safe failure state, lease recovery, temporary-source cleanup, and janitor removal of crash leftovers. Analyzer failure cannot be recorded as zero issues.

## Phase 4: mock-assisted review and result persistence

The user's expanded Phase 4 request supersedes the original mock-only scope under [ADR 0003](adr/0003-analysis-engine-scope.md). Implement a queue/HTTP-independent snapshot engine, strict diff/file/context selection, required isolated Ruff (optional Semgrep deferred), deterministic mock and guarded OpenAI adapter, versioned prompts, normalized validated findings, reports/cache, persistent budget reservations, dry-run and evaluation commands. No real API calls, publishing, dashboard, queue wiring, or cloud work is authorized. Fenced job-state integration remains Phase 2B work; report persistence is verified independently.

Acceptance criteria:

- Parse bounded unified diffs and verify actual head-file line evidence. Reject incomplete/duplicate/unsafe/mismatched input; disclose unsupported/deleted/oversized/excluded files. Changed Python content is parsed as data and never imported/executed.
- Run digest-pinned Ruff in a non-root read-only networkless container without mounts, repository configs, inline policy suppression, credentials, Docker socket, or privileged execution. Bound CPU/memory/process/time/output and clean exact task-owned containers. Probe isolation and force scanner timeout; failure is never a clean review. Document host-operated runner limits before future worker integration.
- Keep `AI_PROVIDER=mock` as default, legacy alias lower priority, and all ordinary development/CI/tests offline. Unknown providers fail safely. Real adapter contracts use fake HTTP transports only and one structured model request, no tools, no automatic retries/fallback.
- Bound full serialized input/output token estimates, relevant changed-code windows, total context/diff/files/lines, and concurrency. Version prompts/model/analyzer/schema/policy. No supplied text can select tools or change application policy.
- Independently validate Pydantic output, real selected paths/changed lines/exact evidence, severity/confidence, message size/text, and supported security evidence. Reject invented or unsupported claims. Deduplicate known rule/path/line identities with retained provenance, deterministic ordering and capped findings. Optional model failures yield disclosed static-only reports.
- Report findings, summaries, coverage, model/prompt/analyzer metadata, content hash, latency, estimated tokens/cost, nullable actual usage/calculated cost, and cache hits. Authorize every cache access; include repository/installation/SHAs/content/model/prompt/policy in hash and check current access generation. Report persistence is transactional and replay-safe; raw prompts/diffs/model responses are not stored.
- Persist a shared reconciled spending ledger with integer micro-USD, $7.50 warning/$9.00 hard stop, per-review cap, global live slots and unique dispatch identities. Reserve before sending, keep uncertain charges/slots across restart, record available usage even for invalid findings, freeze on overruns, and prevent duplicate dispatch/settlement or retention resets. Test threshold races, budget denial with zero transport calls, migration up/down/up and prior-data preservation.
- Verify current official model/pricing docs and store a dated expiring example profile without implicitly enabling real calls. Missing/stale pricing, missing explicit bounded token-policy approval, missing credentials/opt-ins/access, unavailable ledger, and insufficient allowance fail safely. Dry-run sends no request or monetary reservation. Token upper bounds are disclosed as estimates, not exact tokenizer counts.
- Provide ten known-bug and ten clean synthetic cases, a runnable mock evaluation command, optional explicitly capped/session-bound live evaluation commands, and log/error privacy tests. No real live evaluation is required or claimed; mock results test orchestration only.

Verification record (2026-11-06 client date, Windows/PowerShell, Python 3.12.6, uv 0.13.7; UTC pricing verification falls on 2026-11-07):

- `uv --cache-dir .cache/uv run --locked --offline python scripts/test_backend.py -q --cov=shrike --cov=shrike_api --cov=shrike_worker --cov-report=term-missing`: **267 passed in 32.24 seconds, 91% statement coverage** after the final partial-usage accounting refinement. Includes all prior API/GitHub tests, real PostgreSQL upgrade/down/upgrade and Alembic metadata agreement, Phase 2/3 data preservation, scoped cache/revocation and retention independence, pricing/opt-in/credential/usage failures, parallel budget reservations and hard-stop equality, persistent uncertainty/slots/evaluation caps, duplicate settlement/dispatch, partial reported usage, overrun freeze, unavailable ledger, mocked Responses HTTP/timeout/rate-limit behavior, scanner policy/noqa/timeout, CLI privacy/dry-run, and malformed diff/model evidence checks.
- `uv --cache-dir .cache/uv run --locked --offline pytest tests/unit -q -p no:cacheprovider --basetemp .cache/phase4-unit-final-04`: **132 passed in 1.30 seconds**, without Docker. Earlier evaluation expected F823 for one unbound-name fixture; direct Ruff 0.17.4 verification established F821 and the fixture was corrected. One new outage test initially omitted budget initialization and exercised the unreconciled-budget guard instead; its setup was corrected before the final passing suite. Initial lint/format issues were corrected.
- `uv --cache-dir .cache/uv run --locked --offline ruff check .`: passed; `ruff format --check .`: **87 files already formatted**; strict `mypy`: **75 files passed**; `uv --cache-dir .cache/uv lock --check --offline`: **49 locked packages**. No dependency changes were required. Domain/application import checks prohibit HTTP/queue/SQL/provider-adapter dependencies.
- `uv --cache-dir .cache/uv run --locked --offline python -m shrike.review_cli evaluate`: **20 cases, 10 hits, 0 misses, 0 false-positive cases; 9 static hits and 1 deterministic mock hit**. Actual digest-pinned Ruff ran; no provider request was made. A synthetic snapshot produced one valid mock finding at changed line 1. Mock dry-run reported zero model cost; hosted dry-run, without key/database/live opt-in, estimated **6,345 input-token upper bound and $0.001635 reserved-cost ceiling** from the dated profile without sending a request or reserving money. The explicit ignored synthetic report artifact was inspected.
- Restricted Ruff 0.17.4 version/execution and trusted BusyBox isolation probe passed: UID 65534, no host mounts/secrets paths, read-only filesystem, blocked network, 128 MiB memory and 32-process cgroup limits. CPU/output/time bounds are set by the runner; forced scanner timeout/cleanup passed. Only trusted digest-pinned images were downloaded; no repository dependencies/configs/hooks/code were executed. Host Docker access is not a deployed worker architecture.
- Documentation/source hygiene passed for **107 tracked/new files, 12 Markdown documents, 46 resolving local links, and 58 unique placeholder settings**; JSON fixtures/profile parse, Ruff image pin agreement, preserved original AGENTS instructions, no stale project names/private-key blocks, safe ignore rules, and clean whitespace/conflict-marker checks. `docker compose --env-file .env.example config --quiet` passed with a child-process-only generated password. `git -c core.excludesFile= diff --check` passed with only LF/CRLF notices. The existing `.env` was never read or edited. Final Docker inventory contained no task-owned test/scanner/probe containers.

Remaining manual/deferred steps: [analysis-local.md](runbooks/analysis-local.md) documents offline commands and separately opted-in live setup/evaluation. No real OpenAI request, real model quality/encoding compatibility, billing reconciliation, account balance, or invoice ceiling is verified. The shipped price profile leaves bounded-token approval false. Semgrep, deployed runner/queue leases and 180-second queued attempt deadlines, billing recovery/audit workflows, retention automation, publishing, dashboard, and cloud remain deferred. The feature commit/push are authorized after final staged review; Git history and the task report record their actual results.

## Phase 5: asynchronous pull request processing

The user's current request supersedes the earlier publication scope. [ADR 0004](adr/0004-asynchronous-processing.md) brings the necessary Phase 2B outbox/broker/job lifecycle work into Phase 5. Do not implement publication, a dashboard, new infrastructure services, or real external integration calls. Use PostgreSQL as the durable authority, Redis/Celery as ID-only transport, existing isolated analysis, bounded/fenced retries, repository concurrency, provider admission, safe correlation logs and guarded development operations.

Milestone 1 verified (2026-11-06 client date): migration `0004_outbox` adds/backfills ID-only dispatch records. Webhook receipt acceptance and canonical review-job creation enqueue transactionally; broker calls never occur in the webhook handler. Dispatcher leases and scheduling survive publish failure, lost confirmation and lost broker messages; generations fence old confirmations. Scoped ingestion claims process only the addressed receipt. `uv --cache-dir .cache/uv run --locked --offline python scripts/test_backend.py -q`: **272 passed in 25.63 seconds**; Ruff lint passed, formatting checked **94 files**, strict mypy passed **81 files**. Migration up/down/up and metadata agreement passed. The phase remains incomplete pending the real Celery/Redis worker, fenced execution, operations and end-to-end failure verification.

Milestone 1 was committed as `6a567e4` (`feat(worker): add transactional ingestion and review outbox`). The later verification below completes the current asynchronous scope, not Phase 5B publishing.

Acceptance criteria for the completed local Phase 5 scope:

- Atomic receipt/job/outbox commits; no broker or review call in webhook acknowledgement. Versioned JSON ID-only messages; authenticated Redis; safe redelivery after ambiguous publish or broker loss. No result backend, remote control, pickle or task autoretry.
- Canonical access/identity/revision validation before gathering immutable bounded content and after analysis. Persist job states, attempts, first/current start/finish, due time, safe errors, result/findings and usage provenance under expiring fences. Duplicate messages/restarts cannot duplicate rows or let old workers overwrite results.
- At most three lifetime attempts with database-owned bounded exponential backoff/jitter and provider retry hints. Permanent validation errors fail; stale/closed/revoked work cancels. Repository claims enforce configured limits across processes; provider admission is shared and survives broker/worker restarts. Expired-worker recovery closes old attempts and schedules a fresh generation.
- New canonical heads disable prior completed results and cancel obsolete unfinished work. Future publication eligibility checks current local state; no actual publication is implemented, and a future writer must recheck GitHub before writing.
- Correlate API request UUID through outbox and worker job/attempt logs using allowlisted metadata only. Development-only inspection/retry requires explicit opt-in, development environment and paired grants, preserves execution history and remaining attempts, and rejects inaccessible/stale/completed/exhausted jobs.
- Prove signed event → actual Redis → actual Celery consumer → isolated Ruff/mock engine → PostgreSQL, including duplicate deliveries, broker-data loss/connection failure, concurrency, stale results, revocation, worker-loss simulation, throttling, manual retry and migration/metadata agreement. No real GitHub/model request, cloud resource or unrequested service.

Final verification record (2026-11-07 client date; Windows/PowerShell, Python 3.12.6, uv 0.13.7, digest-pinned PostgreSQL 17/Redis 8.2.3/Ruff 0.17.4):

- `uv --cache-dir .cache/uv run --locked --offline python scripts/test_backend.py -q --cov=shrike --cov=shrike_api --cov=shrike_worker --cov-report=term --tb=short`: **307 passed in 55.43 seconds, 91% statement coverage**. Includes prior phases and new outbox/queue, PostgreSQL migration up/down/up/metadata, canonical snapshot processing, explicit attempts/results, repository collision/duplicate claims, stale canonical heads and eligibility invalidation, revocation, exponential retries/exhaustion, expired-worker recovery/fencing, provider window scheduling, guarded actual CLI retry/inspection, and log/privacy tests.
- Real transport tests use authenticated disposable Redis and an actual in-process Celery solo consumer, not eager mode. Signed ASGI webhook acceptance, raw-byte HMAC, real isolated Ruff and deterministic mock review produce one stored finding and one execution. Duplicate deliveries/identities are harmless; deleting only the random test broker namespace recovers from PostgreSQL. An actual loopback connection refusal leaves the HTTP receipt accepted and outbox pending. Focused real transport checks: **3 passed in 17.08 seconds**. Linux prefork deployment remains manual/unperformed.
- Initial tests exposed a too-long test namespace and shared Celery task registration leaking callbacks between app instances. Namespace bounds were respected and task registration made app-local; regressions cover isolation. Logging capture also exposed stale streams; safe dynamic stderr emission now prevents closed-stream fallback from echoing raw messages/exceptions. Initial lint/type issues were corrected before passing checks.
- `ruff check .` and `ruff format --check .` passed (**110 files**); strict `mypy` passed (**96 source files**); `uv lock --check --offline` passed (**62 packages**). All were run through `uv --cache-dir .cache/uv run --locked --offline` except the lock command. Hygiene validated **131 tracked/nonignored files, 14 Markdown documents, 60 local links and 63 placeholder-only example settings**; original AGENTS instructions are preserved, domain/application import boundaries hold, and no stale branding, conflict markers or private-key blocks were found. `git diff --check` and default/queue `docker compose --env-file .env.example ... config --quiet` passed; `.env`, caches and the separate WSL environment are ignored. Disposable test/scanner containers remaining: **zero**. Celery **5.6.3** and redis-py **6.4.0** are directly pinned; dependency installation used approved registry access, never analyzed-repository dependencies. Celery's official Redis/configuration documentation informed JSON-only/late-ack/visibility settings; PostgreSQL recovery is authoritative beyond broker behavior.
- The hardened Compose queue profile was actually started in a uniquely named temporary project with generated process-only passwords/random loopback port: authenticated ping and AOF passed under non-root/read-only restrictions. Its exact container/network/volume were removed. The first verifier expected byte keys from `config_get`; it was corrected to accept the client's decoded keys before the successful check. No persistent user stack or GitHub account was configured. The existing `.env` was never read/edited.

Commands and remaining manual steps: [async-processing.md](runbooks/async-processing.md). Start a persistent database/Redis only deliberately, migrate to `0005_execution`, configure the selected test App separately, then run dispatcher and host worker. Automatic queued AI is mock-only. Native Windows threads are development-only; Linux prefork/process-kill deployment and cloud runner compatibility are unperformed. Automatic orphan-container cleanup/retention, hosted queue spending, publishing (5B), dashboard, CI and cloud remain deferred. Git history/task report record the feature commits and completed-phase push after staged validation.

## Phase 6: GitHub REST adapter and independent publication (formerly 5B)

The user requested Phase 6 publication on 2026-11-07; [ADR 0005](adr/0005-github-publication.md) records the naming/scope rebaseline and independent operator execution. Extend the Phase 3 read-only GitHub adapter with advisory reviews and publication reconciliation. Add Pull requests write permission only when this publishing phase is implemented and explicitly configured; retain scoped short-lived credentials and mocked contracts. No write permission or publishing endpoint is present in Phase 3.

Acceptance criteria:

- Mocked HTTP tests cover token expiry, authorization denial/revocation, API pagination, fork-content access, rate limits, transient failure, invalid inline locations, and current-revision checks.
- One eligible current run produces one advisory summary with no more than ten valid inline comments. No-comment/partial/static-only/mock-assisted results are labeled accurately.
- Superseded/closed/revoked work cannot knowingly publish. Test revision changes before and during publication, and document the unavoidable external-write race.
- A lost response after a simulated successful write reconciles by App identity/marker to the existing review. An unresolved outcome remains `uncertain`; it is never blindly reposted or represented as success.
- Posting retries use a separate bounded publication policy and do not rerun completed analysis. Duplicate tasks cannot initiate concurrent writes.
- Document GitHub App registration, exact permissions/events, private-key mounting, callback/webhook URLs, secret generation, optional HTTPS tunnel, and removal/revocation cleanup as manual steps.
- A real smoke test is optional and requires separate authorization and credentials. Record it as unperformed until an actual test App/repository event succeeds; mock contract tests alone do not establish real compatibility.

Implementation and verification (2026-11-07 client date):

- Implemented a report-only CLI over completed persisted reports; publishing additionally requires explicit live/enabled settings, paired repository grants and `--publish`. Worker completion never publishes; no hosted model, public mutation API, dashboard or cloud work is added.
- Added a bounded quality-filtered advisory summary, up to ten new-side inline comments and actionable summary fallback for deleted/context/invalid locations. Only medium-or-higher correctness/security/reliability findings with confidence >= 0.85 are selected. Mock/partial/static-only coverage is disclosed; evidence/source is omitted and untrusted prose is escaped.
- Added minimal repository-scoped App read/write token scopes and no-retry COMMENT-only writes. Full bounded pagination and authenticated App-bot/marker/SHA checks prevent known duplicate reviews. Durable write intents, separate publication attempts/leases, external IDs and uncertain/partial/stale states preserve failure history independently from analysis.
- Migration `0006_publication` preserves previous jobs and adds `review_publications`; API readiness requires the new revision. Disposable upgrade/downgrade/upgrade and metadata comparison are included in verification.
- Initial targeted publication/migration run: **20 passed, 4 failed**; corrected a newly inserted due-time race and stale-outcome precedence. Initial full run: **343 passed, 1 failed**, 91% statement coverage; the pre-existing ingestion test put `available_at` exactly at the container clock's now while polling with the host clock. Its synthetic due time now uses one second in the past. No runtime ingestion retry semantics or counters were changed. Initial formatting/type issues and duplicate test-module naming were corrected before final validation.
- Final executed checks on Windows, Python 3.12.6 and Docker Desktop Linux engine 29.9.2:
  - `uv --cache-dir .cache/uv run --locked --offline --no-sync python scripts/test_backend.py -q --cov=shrike --cov=shrike_api --cov=shrike_worker --cov-report=term --tb=short`: **349 passed in 67.03 seconds, 91% statement coverage**. Includes upgrade/downgrade/upgrade/metadata agreement, real signed-event/Redis/Celery/isolated-Ruff/mock-AI-to-independent-publication, CLI opt-ins/report-only privacy, API failure/partial ID recovery, stale heads/base/closed/draft/fork checks, revocation/generation changes, concurrent leases, before/after-intent crash recovery, uncertain absent/pending/confirmed reconciliation and idempotency.
  - `uv --cache-dir .cache/uv run --locked --offline --no-sync ruff check .`: **passed**.
  - `uv --cache-dir .cache/uv run --locked --offline --no-sync ruff format --check .`: **122 files already formatted**.
  - `uv --cache-dir .cache/uv run --locked --offline --no-sync mypy`: **106 source files passed**.
  - `uv --cache-dir .cache/uv lock --check --offline`: **passed, 62 packages resolved**; no dependency changes or installations.
  - `docker compose --env-file .env.example config --quiet`: **passed**, without starting persistent services.
  - Docker was initially stopped and then required sandbox-external engine access; the first attempted integration setup did not run tests. After starting Docker, all test databases/containers were disposable and cleaned by the runner.

The [publication runbook](runbooks/github-publication.md) includes test repository/App permission-upgrade instructions, private local preview, explicit publish commands, duplicate/stale/revocation checks, metadata inspection, migration precautions and uncertainty investigation. Real App registration/permission consent, tunnel, live PR creation, actual GitHub publication and manual end-to-end smoke validation remain **unperformed**; live verification is optional and separate from this local/mocked phase gate. Automated publication scheduling, retention and production deployment remain deferred. Git history and the task report record feature commits and any completed-phase push after staged validation.

## Phase 7: authenticated SaaS dashboard (formerly 6B)

Implement backend GitHub App user authorization, opaque sessions, server-side access checks, typed frontend API access, and the read-only dashboard. Use mock identities only in local/test mode.

Acceptance criteria:

- Test OAuth state expiry/replay, callback allowlisting, credential expiry and required reauthorization (refresh tokens are deliberately discarded), logout/session revocation, cookie flags, CSRF/Origin enforcement, and production rejection of mock-auth bypass.
- Test two users with different repository access; cross-repository list/detail/finding/metrics requests leak no data. Revocation invalidates known grants immediately; unobserved permission changes expire within the 60-second access-cache bound.
- List repositories/runs, paginate history, filter findings, inspect attempts/coverage/publication uncertainty, and display severity counts, success/failure rates, queue wait, and duration. Define metric denominators/window explicitly and scope them before aggregation.
- Render untrusted finding text safely; no raw HTML, scriptable links, tokens, or private source in client logs. Backend tokens never enter the browser bundle/storage.
- Component/E2E checks cover loading/empty/error/unauthorized/partial/degraded states, keyboard interaction, and desktop/mobile layouts. Type checks and production build pass.

Implementation progress (2026-11-07 client date):

- [ADR 0006](adr/0006-saas-dashboard.md) records the requested phase rebaseline, fixed review policy, encrypted server sessions, one-hour reauthentication tradeoff, Next.js BFF boundary, synthetic demo separation and migration implications. No architecture replacement, hosted service, paid model or unrequested hardening work is added.
- Backend checkpoint: GitHub App OAuth with S256 PKCE and fixed callbacks, single-use five-minute cookie-bound state, opaque HttpOnly/SameSite sessions, encrypted credentials, session rotation/expiry/logout, same-origin POST enforcement and fresh GitHub membership on every read. SQL-scoped history/metrics/detail/evidence/operations respect paired grants and local revocation/access blocking. Migration `0007_dashboard` adds state/session tables and readiness gating.
- `uv --cache-dir .cache/uv run --locked --offline --no-sync python scripts/test_backend.py -q --cov=shrike --cov=shrike_api --cov=shrike_worker --cov-report=term --tb=short`: **378 passed in 81.75 seconds, 92% statement coverage**, Windows/Python 3.12.6. Includes migration up/down/up/metadata, mocked OAuth/token exchange, state expiry/replay/cookie binding, encrypted session persistence/rotation/expiry/logout, Origin denial, two-user isolation, inaccessible UUIDs/snippets/metrics, membership/local revocation and authorization outages. Earlier targeted auth/dashboard/migration run: **27 passed in 7.11 seconds**. Backend unit-only run: **175 passed in 2.71 seconds**.
- Backend lint/format/type/lock checks passed: `uv --cache-dir .cache/uv run --locked --offline --no-sync ruff check .`; `uv --cache-dir .cache/uv run --locked --offline --no-sync ruff format --check .` (**137 files**); `uv --cache-dir .cache/uv run --locked --offline --no-sync mypy` (**120 files**); `uv --cache-dir .cache/uv lock --check --offline` (**62 packages**).
- Frontend source covers all six requested pages, typed validated API data, URL filters/pagination, loading/error/retry/empty states, mobile navigation and seeded read-only demo. Final browser verification is still underway; the phase is not yet complete. Dependency installation was initially rejected by automatic review under AGENTS.md; the user explicitly authorized the pinned dashboard/test tooling exception with lifecycle scripts disabled. ESLint 9 is retained for current Next plugin peer compatibility; an ESLint 10 trial produced invalid peers and was reverted.
- [dashboard-local.md](runbooks/dashboard-local.md) documents exact demo/live setup, test commands, repository-scoped metrics, operational telemetry limits and manual validation. Real GitHub OAuth/App setup and live end-to-end verification remain **unperformed**. No paid AI call, private-code fetch, cloud deployment, global worker heartbeat or broker health claim is made.

## Phase 7B: local MVP hardening and demonstration

Complete the reproducible offline workflow, failure drills, privacy checks, operational metrics, and honest portfolio evidence. This is the local MVP release gate, not a production-hosting claim.

Acceptance criteria:

- From a clean checkout, documented commands run migrations and a signed synthetic event through the full pipeline into mock GitHub publication and an authorized dashboard view.
- Ten bounded synthetic jobs at concurrency 2 meet the p95 60-second mock target; attempts respect the 180-second deadline. Record hardware, fixture sizes, measured timings, and misses.
- Repeat duplicate-delivery, DB/broker outage, lost-broker-message, worker-kill, stale-lease, revocation, malformed-model, scanner-timeout, and ambiguous-publication drills with recorded outcomes.
- Liveness/readiness and internal backlog/retry/duration/uncertainty metrics work. Log capture confirms no source, prompts, credentials, repository names/paths, or raw webhook bodies.
- Test retention boundaries: 30-day review-content purge with content-free identity tombstones still preventing replay, 7-day terminal delivery purge, active-work protection, 24-hour removed-repository content purge, and abandoned-temp cleanup. Document full-erasure/reset implications and 14-day log rotation; verify the selected local mechanism.
- Document setup, restart/recovery, retry exhaustion, publication investigation, retention, database backup/restore, and migrations. Demonstrate restore into an ephemeral database using synthetic data.
- CI runs all relevant unit/integration/E2E/security/build checks without paid services or real secrets. Document any intentionally manual checks as unperformed until executed.
- Publish a local demo script, architecture explanation, screenshots using synthetic data, and measured limitations. Clearly distinguish offline demonstration from separately verified real GitHub behavior.

## Phase 8: optional hosted LLM provider

Separate requested follow-up after Phase 7 for real model quality evaluation and operational billing reconciliation/audit/restore workflows. Phase 4 now implements the guarded OpenAI adapter, model configuration, spending gate and capped evaluation command under ADR 0003. The original gates below remain the target for mature hosted operation; mocked contracts are not evidence of real account/model compatibility. Reverify current `gpt-6-luna` support/pricing and all egress/billing assumptions before any separately authorized live batch. No tools or autonomous fixes.

Acceptance criteria (all automated checks use fake model transports/responses and disposable PostgreSQL):

- Live mode defaults off, mock mode never reads/requires a key or calls a provider, and CI/test processes refuse live mode. A key/model name alone cannot enable paid dispatch. All ordinary development and automated evaluations remain mock-only.
- Implement and test provider/token-counter/pricing/ledger ports without model-specific business logic. Verify configurable input/output/context/diff/concurrency/timeout and per-review cost limits; enforce one global live call and one paid attempt by default. Disable SDK/HTTP/queue hidden retries; any separately enabled bounded retry requires a fresh reservation and consumes review/evaluation allowances.
- Import/reconcile known prior/external development spend, then enforce cumulative $7.50 warning and $9.00 hard stop within the approximate $10 total budget. Validate threshold order and prevent implicit resets/top-ups. Test exact threshold equality, over-budget refusal with zero outbound calls, and parallel workers competing for the last allowance.
- Create versioned official-pricing snapshots with exact model/tier/region/currency, all billable categories, verification/expiry times, and safe complete-request token bounds. Recheck current official prices when implemented/enabled; no guessed rates, assumed cache discounts, or timeless hardcoded prices. Missing/stale prices, unknown token bounds, unavailable ledger, or unsupported charges fail closed.
- Add ledger migrations and verify upgrade/down/upgrade against disposable PostgreSQL. Use exact monetary arithmetic, unique call/attempt identities, atomic reservation/settlement, durable dispatch intent and global slots, and nullable actual reported usage distinct from estimates. Keep content-free spending records independent of job deletion and retention; test restart, duplicate settlement, restore/reconciliation guards, and purge behavior.
- Inject crashes before/after dispatch and before settlement, timeouts, missing usage, malformed output with valid usage, and unexpected actual cost overruns. Potentially billed requests retain full uncertain reservations and appropriate live slots; lease expiry cannot refund or replay them. Stop live work on accounting discrepancies. Test bounded explicit retry accounting without a real request.
- Add an operator-only live evaluation command with separate explicit opt-in, mandatory finite request cap (default 0), persistent session/counter across restart, synthetic/public corpus, and the same global/per-review budget. Count each dispatch attempt including retries; never run it in CI. A future live batch requires explicit task authorization and reports observed quality/usage honestly; mock results prove only orchestration.
- Capture synthetic secret/source sentinels to prove logs/errors contain no keys, prompts, source, sensitive payloads, or raw provider bodies. Provide manual pricing/usage reconciliation, budget-warning, uncertain-charge, backup/restore, and opt-in setup steps. Document external-account billing limitations and do not claim an invoice ceiling or account balance.

Phase 8 remains a **separate future operational follow-up**. The Phase 4 adapter/ledger/evaluation command does not establish model quality, exact tokenizer compatibility, automatic billing reconciliation, stale-backup detection, an invoice ceiling, or live production readiness. No real OpenAI call has been performed.

## Phase 9: cloud and telemetry

Separate follow-up after Phase 7; no real infrastructure is configured by this plan. Prepare a reviewed costed design before provisioning: AWS ECS/Fargate web/API/worker/dispatcher, managed PostgreSQL/Redis options, private networking, TLS ingress, secret management, IAM, image registry, state storage, and log retention. Validate that the selected scanner isolation works on the target runtime before choosing it; restricted Fargate capabilities may require a justified runner change.

Acceptance criteria for a future authorized cloud phase:

- Record region, topology, minimum idle/monthly cost assumptions, budgets, and teardown plan using then-current pricing; account for NAT, load balancer, database, Redis, logs, and backups.
- Terraform formatting/validation and reviewed plans pass; state is remote/locked/encrypted, secrets are excluded, IAM is scoped, and provisioning is separately authorized.
- GitHub Actions builds immutable images, uses short-lived cloud federation, runs required checks, and documents deployment/migration/rollback procedures. No long-lived cloud keys.
- Deploy only when requested; verify HTTPS, private storage/broker, secret rotation, backup restore, alarms, and a synthetic end-to-end review in the actual environment.
- Add OpenTelemetry correlation across webhook/outbox/task stages and sanitized traces/metrics without source or credential attributes. Demonstrate dashboard/alert evidence and record actual costs/limitations.

## Current manual steps and remaining work

Phases 2-5 are verified to their documented local/mocked scope, including real Redis/Celery transport and PostgreSQL-backed execution. Phase 6 adds independent publication with mocked GitHub verification; see its evidence above. Follow the backend/analysis/async runbooks; no persistent user stack, live App/model setup, Linux deployment or published feedback is claimed. Remaining foundations, optional Semgrep, live publication smoke verification, OAuth/dashboard, automatic accounting/retention/orphan cleanup, CI and cloud remain deferred. Account/tunnel/live evaluation require separate manual opt-ins. Mocked cost tests do not establish an API balance or invoice ceiling.
