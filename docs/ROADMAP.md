# Shrike implementation roadmap

Planning baseline: 2026-11-06. Only Phase 0 is in scope for the current task. All application phases below are proposed and require a subsequent user request. Complete only the requested phase; do not treat this roadmap as authorization to implement the entire product.

## Status and evidence rules

Use `not started`, `in progress`, `blocked`, or `verified`. A phase is `verified` only when its exit criteria have recorded evidence. Code written, tests proposed, and manual steps documented are not equivalent to verification. If part of a phase passes, record that evidence while leaving the phase incomplete. Record command/date/environment details in the task report or a committed validation note; never invent output.

| Phase | Outcome | Status |
| --- | --- | --- |
| 0 | Repository inspection and implementation plan | Verified: documentation and repository-hygiene checks passed |
| 1 | Reproducible monorepo and local foundations | Not started |
| 2 | Durable signed webhook ingestion and dispatch | Not started |
| 3 | Safe immutable snapshots and static analysis | Not started |
| 4 | Mock LLM, validated findings, persisted results | Not started |
| 5 | GitHub publication and recovery | Not started |
| 6 | Authenticated dashboard and metrics | Not started |
| 7 | Local MVP hardening and portfolio evidence | Not started |
| 8 | Optional hosted LLM adapter and evaluation | Not started; separate scope |
| 9 | AWS ECS, Terraform, OpenTelemetry | Not started; deferred |

Dependencies: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7. Scanner-isolation feasibility may be investigated within Phase 3 before its other work. Phases 8 and 9 depend on a verified local MVP and can be requested independently; cloud does not require a paid model.

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
- CI runs Python lint/format/type checks, meaningful foundation tests, TypeScript/lint/build checks, and Compose configuration validation using synthetic local configuration.
- Record exact setup/check commands, tool versions, service health, and remaining manual prerequisites. Do not claim a live GitHub integration.

## Phase 2: webhook durability and job orchestration

Implement signature verification, supported-event validation, receipt/outbox persistence, canonical reconciliation through a fake GitHub adapter, Celery dispatch, run identities, leases, retries, and broker-loss recovery. Real adapter connectivity is deferred to Phase 5.

Acceptance criteria:

- Missing/wrong signatures, malformed payloads, and oversize/chunked bodies return documented errors without scheduling work. Valid signatures are tested over exact bytes.
- Replaying the same event 100 times creates one delivery receipt and one intended review run; different deliveries for the same base/head/policy still create one run.
- Kill dispatch after publish but before marking; duplicate work is harmless. Stop Redis during ingestion; accepted events remain in PostgreSQL and dispatch after recovery.
- Simulate Redis data loss and a worker crash after claim; reconciliation recovers work, fences old owners, and records attempts. No stale attempt can overwrite a newer result.
- Synthetic draft/close/base-change/removal/reordered lifecycle events yield correct skip/cancel/supersede state. A stale installation event cannot restore access.
- Demonstrate p95 acknowledgement under 500 ms for 100 sequential events on a documented local machine. Record actual results even if the target is missed.

## Phase 3: safe snapshots and static analysis

First prove the sandbox, then implement bounded GitHub snapshot contracts, diff mapping, Ruff, and Semgrep. Use fake GitHub responses and actual pinned scanner tools in tests. No repository execution or live private code is permitted.

Acceptance criteria:

- A sandbox probe demonstrates no network, no service credential/host filesystem access, non-root execution, and enforced resource/time/output limits in the supported Linux worker container. No privileged container or Docker socket is used. If infeasible, mark the phase blocked and document a justified alternative before proceeding.
- Positive Ruff/Semgrep fixtures trigger expected rules; negative/clean fixtures do not. Repository analyzer configs and malicious hooks are ignored and never executed.
- Correctly handle fork SHAs, base changes, renames, deletions, duplicate paths, traversal, symlink/submodule/binary entries, missing patches, pagination, and truncation using synthetic fixtures.
- Enforce every PRD byte/file/line limit. Show explicit partial/skip reasons; incomplete input never produces a clean result.
- Map new-side findings to exact changed lines. Unchanged-line findings cannot become inline comments.
- Kill a scanner and worker; verify safe failure state, lease recovery, temporary-source cleanup, and janitor removal of crash leftovers. Analyzer failure cannot be recorded as zero issues.

## Phase 4: mock-assisted review and result persistence

Implement the LLM port, deterministic mock, bounded context construction, strict response schemas, normalized findings, deduplication, provenance, and durable coverage/results. Do not add a hosted provider yet.

Acceptance criteria:

- Repeated fixtures produce identical mock results and recorded policy/tool/prompt/model versions. No network or API key is needed by the mock.
- Reject malformed JSON/schema, unknown severity, invalid path/line, oversized response, dangerous Markdown/links, and embedded tool instructions. No candidate can change a publication target or invoke a tool.
- Optional model timeout/invalid response yields labeled static-only results. Required scanner failure does not yield a normal review.
- Equivalent issues deduplicate with retained provenance; non-equivalent findings remain distinct. Enforce finding/comment caps and deterministic ordering.
- Persist run/attempt state and findings transactionally under a fence. Replayed jobs do not duplicate rows.
- Maintain at least ten seeded actionable and ten clean/unsupported synthetic cases, with expected static hits and mock behavior documented separately.
- Capture logs during adversarial tests; synthetic secret/source/prompt sentinels are absent. Raw prompts/responses/diffs are not persisted.

## Phase 5: GitHub REST adapter and publication

Implement the real GitHub adapter with mocked HTTP contract tests, short-lived installation credentials, least-privilege access, bounded pagination/rate-limit handling, advisory reviews, and publication reconciliation. Use the same contracts for fake and real adapters.

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

Separate follow-up after Phase 7. Choose one provider, use the existing interface, require explicit private-code egress opt-in, and document data retention/processing terms. Enforce model allowlists, per-run/day token and monetary budgets, timeouts, redaction, and a disabled-by-default configuration. Evaluate against a synthetic/public corpus with recorded actionable/false-positive results and actual usage; do not claim quality based on mock tests. Local tests must remain offline and free. Do not add agent tools or autonomous fixes.

## Phase 9: cloud and telemetry

Separate follow-up after Phase 7; no real infrastructure is configured by this plan. Prepare a reviewed costed design before provisioning: AWS ECS/Fargate web/API/worker/dispatcher, managed PostgreSQL/Redis options, private networking, TLS ingress, secret management, IAM, image registry, state storage, and log retention. Validate that the selected scanner isolation works on the target runtime before choosing it; restricted Fargate capabilities may require a justified runner change.

Acceptance criteria for a future authorized cloud phase:

- Record region, topology, minimum idle/monthly cost assumptions, budgets, and teardown plan using then-current pricing; account for NAT, load balancer, database, Redis, logs, and backups.
- Terraform formatting/validation and reviewed plans pass; state is remote/locked/encrypted, secrets are excluded, IAM is scoped, and provisioning is separately authorized.
- GitHub Actions builds immutable images, uses short-lived cloud federation, runs required checks, and documents deployment/migration/rollback procedures. No long-lived cloud keys.
- Deploy only when requested; verify HTTPS, private storage/broker, secret rotation, backup restore, alarms, and a synthetic end-to-end review in the actual environment.
- Add OpenTelemetry correlation across webhook/outbox/task stages and sanitized traces/metrics without source or credential attributes. Demonstrate dashboard/alert evidence and record actual costs/limitations.

## Current manual steps and remaining work

All application phases remain unimplemented. Tool installation/version pinning, Compose startup, migrations, tests, GitHub App registration, OAuth setup, webhook connectivity, provider selection, and cloud configuration are future work. Finding executable tools on the current machine does not verify versions, Docker daemon availability, or a working development stack.
