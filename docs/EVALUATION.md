# Shrike system evaluation

Phase 8 implements [ADR 0007](adr/0007-system-evaluation.md). These are local,
synthetic measurements and mocked integration contracts. They do not certify
production deployment, real GitHub compatibility or real-model quality.

## Repeatable verification and CI

Use a trusted Shrike checkout with the existing locked Python 3.12/uv environment,
Node/npm tooling, installed Playwright browser and preloaded digest-pinned
PostgreSQL, Redis, Ruff and probe Docker images. No dependency installation is
performed by this workflow. Provision tools separately under the repository's
installation rules; never install analyzed repository dependencies. Do not mount
the Docker socket into API/worker containers. No external test accounts, API
secrets, paid requests or cloud resources are needed.

From the repository root, choose a **new** output directory on each invocation:

```powershell
uv --cache-dir .cache/uv run --locked --offline --no-sync python scripts/verify.py --frontend --benchmarks --output-dir .cache/phase8/ci-run-001
```

This CI entry point runs lint, formatting, strict Python typing, full backend
unit/integration tests with coverage/JUnit, labeled quality evaluation, frontend
lint/format/type/component checks, production build, browser-bundle secret scan,
desktop/mobile E2E and bounded load tests. It stops on the first failing command
and writes `checks.json` with actual exit codes/durations and a `complete` flag.
Unexecuted planned steps remain identifiable. A nonzero command must fail the CI
job; never use `continue-on-error`. Omit `--frontend` or `--benchmarks` for a
smaller backend lane; run the full command for the local phase gate.

The runner forces mock/demo modes, disables live flags, replaces provider build
credentials with synthetic canaries, disables Next telemetry and sets `CI=true`.
It neither loads `.env` nor prints environment values. Use preprovisioned,
short-lived CI runners with no real service secrets, read-only checkout access,
repository hooks disabled and no deployment/publishing permissions. This phase
provides the portable entry point; no hosted CI run or cloud runner was created.

Individual commands, also suitable for preprovisioned Linux CI:

```powershell
uv --cache-dir .cache/uv run --locked --offline --no-sync pytest tests/unit -q
uv --cache-dir .cache/uv run --locked --offline --no-sync python scripts/test_backend.py -q --cov=shrike --cov=shrike_api --cov=shrike_worker --cov-report=term
uv --cache-dir .cache/uv run --locked --offline --no-sync python -m shrike.evaluation --output .cache/phase8/quality-001.json --check-baseline tests/fixtures/evaluation/baseline.json
uv --cache-dir .cache/uv run --locked --offline --no-sync python scripts/benchmark.py --output-dir .cache/phase8/load-001
```

Frontend commands in `apps/web`: `npm run lint`, `npm run format:check`,
`npm run typecheck`, `npm run test`, `npm run build`, `npm run test:e2e`.
On Windows the installed Edge browser is selected; Linux requires its matching
preinstalled Chromium. Browser downloads never occur during the checks. See
[dashboard-local.md](runbooks/dashboard-local.md) for browser provisioning and
ports. Docker, its engine access and loopback listeners must be available.

## Coverage and security matrix

| Area | Executable evidence |
| --- | --- |
| Persistence and API | `tests/integration/test_migrations.py`, `test_constraints.py`, `test_api.py`: upgrade/down/up, metadata agreement, constraints, stable pagination, sanitization and scoped reads |
| Webhook boundary | `tests/unit/test_webhook_security.py`, `tests/integration/test_webhook_ingestion.py`: exact raw HMAC, malformed/oversized input, duplicate/conflicting deliveries, reordered events and App/repository revocation |
| GitHub permissions | `test_github_client.py`, `test_publication_client.py`, `test_user_authorization_client.py`: mocked scoped tokens, expiry, pagination, permission denial, rate/transport failures; no live account calls |
| Queue and recovery | `test_dispatch.py`, `test_execution.py`, `test_celery_pipeline.py`: concurrent claims, per-repository limits, attempts/backoff, broker outage/loss, stale generations, expired leases, immutable heads and revoked access |
| Actual process loss | `test_worker_kill.py`: spawn an owned process, commit a claim, terminate it, wait for a short test lease, recover naturally, reject old fence, complete attempt two without resetting history |
| Findings and source | `test_review_engine.py`, `test_analysis.py`: strict model JSON, evidence/confidence/security validation, exact changed lines, renamed/deleted/context paths, malformed diffs, scanner isolation/config suppression/timeouts |
| Sessions and access | `test_dashboard_auth.py`, `test_dashboard_reads.py`, `test_api.py`: OAuth replay/expiry/binding, encrypted credentials, logout, Origin checks, production mock-auth rejection, two-user list/detail/evidence/aggregate isolation and permission outages |
| Publication | `test_publication.py`: independent opt-in, quality gates, stale commits, idempotency, ambiguous write and partial ID reconciliation; never approve/reject/merge |
| Privacy and injection | Source/key/log sentinels in existing backend suites; comment/string injection cases in both corpora; untrusted output paths/URLs/HTML rejected; no repository imports, hooks, dependencies, configs or model tool execution |
| Browser | Existing component tests and Playwright desktop/mobile navigation from review list to file-grouped findings/evidence; filtering, responsive keyboard behavior, read-only demo and denied mutation routes |
| Browser secrets | `scripts/check_web_secrets.py`: production static JS excludes backend credential configuration and synthetic build-secret canaries; empty/missing chunks fail the check |
| Load | `tests/benchmarks/test_load.py`: actual loopback HTTP, real Redis/Celery threads, PostgreSQL and isolated Ruff; see [PERFORMANCE.md](PERFORMANCE.md) |

Tests use synthetic public fixtures and mocked external integrations. Prompt
injection resistance here means inert input plus validated outputs and no tool
capability, not proof that a real model cannot be manipulated. Scanner isolation
depends on the trusted host kernel/Docker daemon. The kill test terminates a
claimant process, not a Linux Celery prefork child while scanning. Actual prefork
soft/hard limits, scanner orphan cleanup after host death and live GitHub/OAuth
verification remain manual and unperformed.

## Labeled quality methodology

[`tests/fixtures/evaluation`](../tests/fixtures/evaluation/README.md) contains 32
manually labeled before/after changes: 15 flawed cases with 16 issue labels and
17 clean cases. Labels/rationales are independent of engine output. A clean
change can contain an unchanged defect outside review scope. Sources are never
executed. Unit tests require every label to map to an actual changed head line.

Each run uses actual pinned isolated Ruff and the deterministic mock model, a
fresh engine/cache per case and the normal evidence/confidence/diff validators.
No hosted adapter or credential lookup is initialized, even with ambient hosted
settings. `--repeats 1..5` repeats cold runs; the default is one. Repetition changes
timing observations, not the number of independently labeled examples.

Matching is one-to-one on **path + rule + exact one-based head line**. A duplicate
or extra prediction, including on a flawed case, is FP. A wrong-line finding is
FP and leaves an FN. Report TP/(TP+FP) precision, TP/(TP+FN) recall, F1, absolute
FP/FN, wrong-line counts and clean cases with any prediction / clean cases.
Undefined denominators are JSON `null`, never a perfect score. Percentiles use
nearest rank. Latency is engine wall time including Docker startup/scanning and
mock inference, excluding dataset load. No statistical confidence or population
false-positive rate can be inferred from this small curated corpus.

The optional `--check-baseline` pins a canonical JSON SHA-256 (insensitive to
formatting/CRLF) and measured regression floors. It writes results even when the
gate fails, then exits 1; invalid configuration/scanner/output errors exit 2.
Without a baseline it is a measurement command, with exit 0 meaning the workflow
ran, not that every label was found. Baseline values are regression limits and
must not be presented as production acceptance targets.

JSON contains per-case IDs, counts, safe statuses, latency and token upper bounds,
corpus hash, analyzer/provider identity, environment, aggregate metrics and costs.
It omits source, findings/evidence, prompts, paths, credentials and host identity.
Model cost is exactly `$0.000000` for this mock run. Hosted estimates and unpriced
infrastructure cost are `null`; token upper bounds are not actual billed usage.
Coverage/JUnit/Playwright artifacts may include test source and synthetic paths;
keep them private to the trusted CI workspace. Generated artifacts stay ignored
under `.cache`; they are not committed.

## Recorded results and priority weaknesses

The initial executed corpus run on 2026-11-07 local time (32 cold observations):
**14 TP, 2 FP, 2 FN; precision/recall/F1 0.875; clean-case FP 2/17 (11.76%);
zero wrong-line findings; p50 500 ms, p95 594 ms; mock model cost $0.**
This establishes orchestration/rule behavior, not real-model performance.
Final verification evidence and timings are recorded in [ROADMAP.md](ROADMAP.md).
The final repeat reproduced every quality count, with p50 **469 ms** and p95
**532 ms**. Its machine-readable outputs are `.cache/phase8/final/quality.json`,
`checks.json`, `coverage.json`, `backend.xml` and `load/load-*.json`.
The full frontend-inclusive run also wrote `.cache/phase8/verified/browser.json`.

The three most important weaknesses exposed are:

1. **Incomplete defect coverage.** `bug-eval-input` and `bug-zero-variable` are
   missed. The mock recognizes literal division and Ruff's small correctness
   policy; it is not a general security/data-flow analyzer. The engine's ability
   to validate a security claim does not mean the mock generates that claim.
   Prioritize reviewed security/data-flow rules and an independent holdout set
   before making broader coverage claims.
2. **Reachability false positives.** `clean-unreachable-division` and
   `clean-dead-branch` are flagged despite literal-false guards. Evidence text
   and exact changed-line validation do not prove an expression executes.
   Prioritize conservative reachability analysis or suppress uncertain cases;
   retain these labels as regression evidence.
3. **Throttling can exhaust valid jobs.** The measured default-60-RPM burst with
   one-second test retry base completed 9/10 jobs; one exhausted three attempts
   on provider admission. Even the 6000-RPM local case needed 14 total attempts.
   Admission collisions consume execution attempts and can rerun scanning.
   Design a durable admission-wait state with separate bounded scheduling before
   expanding workloads. No counters, rate gates or worker semantics were bypassed
   to make this measurement pass. See load methodology and run variance in
   [PERFORMANCE.md](PERFORMANCE.md).

## Separately authorized real-model evaluation

This Phase 8 workflow is always mock-only and accepts no live flag or external
endpoint. No real evaluation was run. The older operator CLI's explicitly guarded
live path is documented in [analysis-local.md](runbooks/analysis-local.md) and
[AI_COST_CONTROLS.md](AI_COST_CONTROLS.md). Its original curated hit counters are
not interchangeable with this evaluator's exact-line precision/recall.

A separate requested live task must reconcile prior spend, verify current
official pricing/model/token-bound support, egress consent and an allowlisted
model, enable live/evaluation settings, supply a persistent session UUID and a
positive request cap (default zero, maximum five). It uses the cumulative
PostgreSQL ledger, $7.50 warning/$9 hard stop within the approximate $10 total
development budget, per-review bounds, one global live slot and no paid retries.

Phase 8 additionally rate-limits this operator evaluation to **one uncached
admission per 60 seconds**, persisted in `provider_windows` under the shared
`hosted-evaluation` key. Admission precedes reservation/dispatch; a second attempt
fails closed with `provider_throttled`, does not sleep/retry or call a model, and
stops the batch. Preserve the same ledger/session across manual resumptions;
cache hits make no request. This is a maximum admission rate, not a promise of
live throughput. Never reset clocks, budgets or session counters to unblock work.
Provider/model/private-account compatibility, real precision/recall, actual billed
usage, external-account balance and invoice ceilings remain unmeasured.
