# Shrike implementation roadmap

Planning baseline: 2026-11-06. The user redefined Phase 2 as persistence/read APIs and Phase 3 as secure GitHub App integration/PR ingestion. [ADR 0001](adr/0001-persistence-phase-scope.md) and [ADR 0002](adr/0002-github-ingestion.md) record the scope changes. Implement only requested phases. The user's standing authorization in `AGENTS.md` permits commits after meaningful verified tasks and pushes after completed verified phases; this does not authorize starting future phases.

## Status and evidence rules

Use `not started`, `in progress`, `blocked`, or `verified`. A phase is `verified` only when its exit criteria have recorded evidence. Code written, tests proposed, and manual steps documented are not equivalent to verification. If part of a phase passes, record that evidence while leaving the phase incomplete. Record command/date/environment details in the task report or a committed validation note; never invent output.

| Phase | Outcome | Status |
| --- | --- | --- |
| 0 | Repository inspection and implementation plan | Verified: documentation and repository-hygiene checks passed |
| 1 | Reproducible monorepo and full local foundations | Not complete: only Python/API/database prerequisites supplied by Phase 2 |
| 2 | Persistence and core backend read APIs | Verified: 124 tests, migrations/constraints/API isolation, lint/types, and loopback HTTP smoke passed |
| 2B | Full Redis/Celery dispatch and recovery | Incomplete: Phase 3 supplies durable inbox ingestion; broker dispatch remains deferred |
| 3 | Secure GitHub App integration and PR ingestion | Verified: 185 tests, migrations/security/CLI checks, lint/types, configuration and documentation validation passed |
| 3B | Safe immutable snapshots and static analysis | Not started; analyzer execution deferred |
| 4 | Mock LLM, validated findings, persisted results | Not started |
| 5 | GitHub publication and recovery | Not started |
| 6 | Authenticated dashboard and metrics | Not started |
| 7 | Local MVP hardening and portfolio evidence | Not started |
| 8 | Optional hosted LLM adapter and evaluation | Not started; separate scope |
| 9 | AWS ECS, Terraform, OpenTelemetry | Not started; deferred |

Phase 2 uses minimum backend prerequisites from Phase 1; Phase 3 adds an independent ingestion runtime with a PostgreSQL inbox. Remaining foundations and broker dispatch are still required before the complete review workflow; then 3B -> 4 -> 5 -> 6 -> 7. Scanner isolation belongs to Phase 3B. Phases 8/9 require a verified local MVP and can be requested independently; cloud does not require a paid model. Phase 0/2 verification records describe their historical snapshots.

## Project identity and AI budget update

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

Implement the LLM port, deterministic mock, bounded context construction, strict response schemas, normalized findings, deduplication, provenance, and durable coverage/results. Define provider-independent request/limits/result/optional-usage contracts and composition-root model selection. Do not add a hosted provider or real requests yet. Cost controls are specified in [AI_COST_CONTROLS.md](AI_COST_CONTROLS.md).

Acceptance criteria:

- Repeated fixtures produce identical mock results and recorded policy/tool/prompt/model versions. No network or API key is needed by the mock.
- Mock is the default and exclusive AI implementation for ordinary development/CI/tests, including ambient-key and attempted-live-configuration rejection tests. Model/provider configuration does not change review business logic; unknown providers fail safely.
- Enforce configurable full-input/output token, selected-diff/context-byte, review-concurrency, and per-repository limits. Test boundaries and deterministic coverage disclosure with fake token counters; estimated/mock usage never claims to be actual billed usage.
- Reject malformed JSON/schema, unknown severity, invalid path/line, oversized response, dangerous Markdown/links, and embedded tool instructions. No candidate can change a publication target or invoke a tool.
- Optional model timeout/invalid response yields labeled static-only results. Required scanner failure does not yield a normal review.
- Equivalent issues deduplicate with retained provenance; non-equivalent findings remain distinct. Enforce finding/comment caps and deterministic ordering.
- Persist run/attempt state and findings transactionally under a fence. Replayed jobs do not duplicate rows.
- Maintain at least ten seeded actionable and ten clean/unsupported synthetic cases, with expected static hits and mock behavior documented separately.
- Capture logs during adversarial tests; synthetic secret/source/prompt sentinels are absent. Raw prompts/responses/diffs are not persisted.

## Phase 5: GitHub REST adapter and publication

Extend the Phase 3 read-only GitHub adapter with advisory reviews and publication reconciliation. Add Pull requests write permission only when this publishing phase is implemented and explicitly configured; retain scoped short-lived credentials and mocked contracts. No write permission or publishing endpoint is present in Phase 3.

Acceptance criteria:

- Mocked HTTP tests cover token expiry, authorization denial/revocation, API pagination, fork-content access, rate limits, transient failure, invalid inline locations, and current-revision checks.
- One eligible current run produces one advisory summary with no more than ten valid inline comments. No-comment/partial/static-only/mock-assisted results are labeled accurately.
- Superseded/closed/revoked work cannot knowingly publish. Test revision changes before and during publication, and document the unavoidable external-write race.
- A lost response after a simulated successful write reconciles by App identity/marker to the existing review. An unresolved outcome remains `uncertain`; it is never blindly reposted or represented as success.
- Posting retries use a separate bounded publication policy and do not rerun completed analysis. Duplicate tasks cannot initiate concurrent writes.
- Document GitHub App registration, exact permissions/events, private-key mounting, callback/webhook URLs, secret generation, optional HTTPS tunnel, and removal/revocation cleanup as manual steps.
- A real smoke test is optional and requires separate authorization and credentials. Record it as unperformed until an actual test App/repository event succeeds; mock contract tests alone do not establish real compatibility.

## Phase 6: authenticated dashboard

Implement backend GitHub App user authorization, opaque sessions, server-side access checks, typed frontend API access, and the read-only dashboard. Use mock identities only in local/test mode.

Acceptance criteria:

- Test OAuth state expiry/replay, callback allowlisting, credential expiry/refresh, logout/session revocation, cookie flags, CSRF/Origin enforcement, and production rejection of mock-auth bypass.
- Test two users with different repository access; cross-repository list/detail/finding/metrics requests leak no data. Revocation invalidates known grants immediately; unobserved permission changes expire within the 60-second access-cache bound.
- List repositories/runs, paginate history, filter findings, inspect attempts/coverage/publication uncertainty, and display severity counts, success/failure rates, queue wait, and duration. Define metric denominators/window explicitly and scope them before aggregation.
- Render untrusted finding text safely; no raw HTML, scriptable links, tokens, or private source in client logs. Backend tokens never enter the browser bundle/storage.
- Component/E2E checks cover loading/empty/error/unauthorized/partial/degraded states, keyboard interaction, and desktop/mobile layouts. Type checks and production build pass.

## Phase 7: local MVP hardening and demonstration

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

Separate requested follow-up after Phase 7. Implement OpenAI behind the Phase 4 provider port, model selection through environment configuration, and the complete [AI budget contract](AI_COST_CONTROLS.md) before enabling real requests. The documented low-cost development candidate is `gpt-6-luna`, checked against official docs on 2026-11-06; reverify then-current support/pricing and account availability at implementation. No automatic higher-cost fallback. Require explicit live and private-code egress opt-ins and document provider data handling. Do not add tools or autonomous fixes.

Acceptance criteria (all automated checks use fake model transports/responses and disposable PostgreSQL):

- Live mode defaults off, mock mode never reads/requires a key or calls a provider, and CI/test processes refuse live mode. A key/model name alone cannot enable paid dispatch. All ordinary development and automated evaluations remain mock-only.
- Implement and test provider/token-counter/pricing/ledger ports without model-specific business logic. Verify configurable input/output/context/diff/concurrency/timeout and per-review cost limits; enforce one global live call and one paid attempt by default. Disable SDK/HTTP/queue hidden retries; any separately enabled bounded retry requires a fresh reservation and consumes review/evaluation allowances.
- Import/reconcile known prior/external development spend, then enforce cumulative $7.50 warning and $9.00 hard stop within the approximate $10 total budget. Validate threshold order and prevent implicit resets/top-ups. Test exact threshold equality, over-budget refusal with zero outbound calls, and parallel workers competing for the last allowance.
- Create versioned official-pricing snapshots with exact model/tier/region/currency, all billable categories, verification/expiry times, and safe complete-request token bounds. Recheck current official prices when implemented/enabled; no guessed rates, assumed cache discounts, or timeless hardcoded prices. Missing/stale prices, unknown token bounds, unavailable ledger, or unsupported charges fail closed.
- Add ledger migrations and verify upgrade/down/upgrade against disposable PostgreSQL. Use exact monetary arithmetic, unique call/attempt identities, atomic reservation/settlement, durable dispatch intent and global slots, and nullable actual reported usage distinct from estimates. Keep content-free spending records independent of job deletion and retention; test restart, duplicate settlement, restore/reconciliation guards, and purge behavior.
- Inject crashes before/after dispatch and before settlement, timeouts, missing usage, malformed output with valid usage, and unexpected actual cost overruns. Potentially billed requests retain full uncertain reservations and appropriate live slots; lease expiry cannot refund or replay them. Stop live work on accounting discrepancies. Test bounded explicit retry accounting without a real request.
- Add an operator-only live evaluation command with separate explicit opt-in, mandatory finite request cap (default 0), persistent session/counter across restart, synthetic/public corpus, and the same global/per-review budget. Count each dispatch attempt including retries; never run it in CI. A future live batch requires explicit task authorization and reports observed quality/usage honestly; mock results prove only orchestration.
- Capture synthetic secret/source sentinels to prove logs/errors contain no keys, prompts, source, sensitive payloads, or raw provider bodies. Provide manual pricing/usage reconciliation, budget-warning, uncertain-charge, backup/restore, and opt-in setup steps. Document external-account billing limitations and do not claim an invoice ceiling or account balance.

Phase 8 remains **not started**. No provider integration, cost ledger, cost enforcement, or live evaluation has been implemented or performed by the naming/budget documentation update.

## Phase 9: cloud and telemetry

Separate follow-up after Phase 7; no real infrastructure is configured by this plan. Prepare a reviewed costed design before provisioning: AWS ECS/Fargate web/API/worker/dispatcher, managed PostgreSQL/Redis options, private networking, TLS ingress, secret management, IAM, image registry, state storage, and log retention. Validate that the selected scanner isolation works on the target runtime before choosing it; restricted Fargate capabilities may require a justified runner change.

Acceptance criteria for a future authorized cloud phase:

- Record region, topology, minimum idle/monthly cost assumptions, budgets, and teardown plan using then-current pricing; account for NAT, load balancer, database, Redis, logs, and backups.
- Terraform formatting/validation and reviewed plans pass; state is remote/locked/encrypted, secrets are excluded, IAM is scoped, and provisioning is separately authorized.
- GitHub Actions builds immutable images, uses short-lived cloud federation, runs required checks, and documents deployment/migration/rollback procedures. No long-lived cloud keys.
- Deploy only when requested; verify HTTPS, private storage/broker, secret rotation, backup restore, alarms, and a synthetic end-to-end review in the actual environment.
- Add OpenTelemetry correlation across webhook/outbox/task stages and sanitized traces/metrics without source or credential attributes. Demonstrate dashboard/alert evidence and record actual costs/limitations.

## Current manual steps and remaining work

Phase 2 persistence/read APIs and Phase 3 metadata ingestion are verified to the recorded mocked/local scope. Follow the backend runbook to start the local demo; no persistent stack or live App setup is claimed here. Remaining Phase 1 foundations, Redis/Celery dispatch, scanners, mock/hosted AI, the cost ledger, publishing, OAuth/dashboard, retention automation, and cloud are future work. GitHub account/tunnel and any eventual live evaluation remain separate manual opt-ins. Documentation of cost controls does not verify their enforcement or the remaining API balance.
