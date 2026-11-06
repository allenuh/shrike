# Shrike product requirements

Status: proposed design; planning baseline dated 2026-11-06. This document specifies intended behavior, not implemented capabilities.

## Problem and outcome

Pull request authors need timely, actionable review feedback without surrendering control of their code. Maintainers need a record of what ran, what was skipped, and why a finding appeared. Shrike will demonstrate authenticated GitHub ingestion, durable asynchronous work, static and AI-assisted analysis, validated publication, and an authorized dashboard.

Primary users are Python repository maintainers and PR authors. The initial operating model is one self-hosted deployment with multiple GitHub App installations and repository-level authorization. Commercial tenant management is outside the MVP.

## Functional requirements

| ID | Requirement | Verification target |
| --- | --- | --- |
| F1 | Track GitHub App installations and selected repositories; reconcile installation changes and revocation. | Mock add/remove/delete events update access; removed repositories stop new analysis and publication. |
| F2 | Verify webhook signatures, bound payload size, validate schemas, deduplicate delivery IDs, and durably accept events. | Invalid/missing signatures never enqueue; replaying one delivery creates one receipt and one intended run. |
| F3 | Handle PR `opened`, `synchronize`, `reopened`, `ready_for_review`, base-changing `edited`, and `closed` events. | Drafts/closed PRs skip new reviews; unchanged edits do not trigger analysis; close events cancel pending work. |
| F4 | Queue work with bounded retries, durable status, failure reasons, and recovery from broker/process failure. | Duplicate delivery and crash tests do not duplicate findings or knowingly duplicate publication. |
| F5 | Fetch canonical PR metadata, diff, and eligible file content at immutable SHAs using installation tokens. | Fork PR fixtures use PR-authoritative content; inaccessible/truncated/over-limit data is explicitly skipped. |
| F6 | Analyze changed Python source with Ruff and curated Semgrep rules, without executing repository code. | Synthetic positive/negative fixtures yield expected findings; unsafe paths/configs are rejected. |
| F7 | Invoke a provider-agnostic LLM interface with a deterministic, offline mock as the default. | Mock supplies stable valid/malformed responses; no external service is needed. |
| F8 | Normalize and validate findings; deduplicate overlaps and constrain comments to changed lines. | Invalid paths, lines, severities, oversized messages, and malformed model output are rejected with safe reason codes. |
| F9 | Publish a capped, advisory GitHub review for the current revision, disclosing skipped/degraded status. | Stale runs do not post; ambiguous writes enter reconciliation; failed analysis never appears as a clean pass. |
| F10 | Provide GitHub App user login, authorized history/detail views, findings, and basic metrics. | Unauthenticated requests fail; users without repository access cannot read runs, findings, or aggregates. |
| F11 | Record safe operational metadata and support retention/purge. | Correlation IDs and timings exist without code/token logging; expired records and revoked credentials are removed. |

Supported events beyond PR actions are `ping`, `installation`, and `installation_repositories`. Unknown signed events are acknowledged without scheduling reviews. Lifecycle events reconcile canonical state asynchronously; out-of-order delivery must not restore revoked access.

## MVP scope

- A GitHub.com App installed on selected repositories, including private repositories and fork PRs when the installation can access required content. GitHub Enterprise Server is deferred.
- Python-only changed-file analysis. Non-Python, binary, generated, vendor, symlink, submodule, oversized, deleted, and unavailable files are counted as skipped with reasons.
- Current PR base/head revision snapshots; historical results remain until retention expires. Reviews are advisory: no required checks, auto-approval, or merge blocking.
- Ruff and a small checked-in Semgrep rule set. Repository configs, custom rules, plugins, hooks, dependency installation, builds, tests, and import execution are excluded.
- A mock LLM and stable provider interface. A hosted-provider adapter requires a separately requested follow-up, explicit private-code egress configuration, and budget controls.
- One summary plus at most ten inline comments in one GitHub review. Findings on unchanged lines remain internal or are excluded with a reason; no invented line mappings.
- Read-only dashboard: repository list, paginated history, run/attempt details, finding filters, severity counts, success/failure rates, queue wait, and review duration. No manual rerun control.
- English output, one deployment, one fixed analysis policy, no billing or organization settings UI.

## Explicit non-goals

No arbitrary repository execution, dependency installation, automatic code changes, agent tool use, autonomous fixes, full-repository analysis, semantic guarantees, or vulnerability certification. No additional language analyzers, chat UI, IDE extension, Slack/email notifications, policy editor, vector database, fine-tuning, or review-memory system. No commercial billing, SSO/RBAC product, high-availability guarantee, multi-region deployment, or cloud provisioning in the local MVP. AWS ECS, Terraform, and OpenTelemetry are later phases.

## Initial operating limits

These are proposed configurable defaults, to be measured during implementation. Limit breaches must be visible; they must never silently produce a successful clean review.

| Limit | Proposed default and behavior |
| --- | --- |
| Webhook body | 1 MiB; reject before unbounded buffering. |
| Diff | 512 KiB and 2,000 changed lines; skip the review if the bounded snapshot cannot be established. |
| Python files | First 20 eligible paths in deterministic lexical order; disclose additional skipped files. |
| Individual file | 200 KiB decoded content; skip the file if exceeded. |
| Analyzer execution | 30 seconds per analyzer per run; bounded CPU, memory, process count, input, and output. |
| LLM | 12,000 input tokens, 2,000 output tokens, 30-second request timeout; omit only at file/hunk boundaries and disclose coverage. |
| Review | 180-second attempt deadline, at most 3 processing attempts, bounded exponential backoff with jitter. |
| Concurrency | Initially 2 active jobs per worker and 1 per repository; enforce using database claims. |
| Publication | At most 10 inline comments and 100 stored normalized findings; bounded messages/summary. |
| Retention | Review content 30 days, webhook receipt metadata 7 days, operational logs 14 days. Keep content-free run/publication identity tombstones for deployment lifetime to prevent replay after content expiry; document any explicit full erasure/reset. Raw webhook bodies, diffs, prompts, and model responses are not persisted. |

The provider adapter owns token accounting; uncertain estimates use conservative bounds. A paid adapter cannot be enabled until token and monetary ceilings are enforceable. The mock does not imply a real model has assessed code quality.

## Nonfunctional requirements

| Area | Requirement and measurable target |
| --- | --- |
| Durability | No acknowledged supported event is lost after its database transaction commits. Broker outages leave durable outbox work pending. Crash tests prove eventual recovery or visible terminal failure. |
| Consistency | At-least-once delivery, one run per analysis identity, idempotent persistence, fenced leases. GitHub network ambiguity is explicit; no exactly-once claim. |
| Responsiveness | Webhook acknowledgement p95 under 500 ms for 100 sequential synthetic events on a documented local reference machine with healthy PostgreSQL; no GitHub/LLM call in this path. |
| Review latency | At concurrency 2, ten bounded synthetic PR jobs complete p95 within 60 seconds with mock adapters; every attempt respects the 180-second deadline. Record machine/fixture details. Real provider latency is outside this target. |
| Reliability | Required static-analysis failures prevent normal publication. Optional LLM failure permits a clearly labeled static-only result. Permanent failures and exhausted retries remain inspectable. |
| Privacy | No raw source, diff, prompt, response, tokens, or credentials in logs/traces. Findings can contain sensitive text and require repository access/retention controls. |
| Isolation | Scanners receive eligible source, trusted rules, and minimal environment; no repository execution, network, service credentials, or unrestricted filesystem access. Isolation failure stops analysis. |
| Authorization | Every resource and aggregate query is repository-scoped server-side. Access validation fails closed. Enforce expiry, logout, and installation revocation. |
| Reproducibility | Pin runtimes/containers, commit lockfiles/migrations, use deterministic mocks, and record analyzer/prompt versions per run. |
| Operability | Safe structured logs, health checks, stage timings, backlog age, failure/retry counters, and recovery/purge runbooks before local MVP acceptance. |
| Usability | Keyboard navigation, loading/error/empty states, explicit partial/skipped/degraded labels, and core pages usable at desktop/mobile widths. |

## Success measures

The MVP succeeds when an offline synthetic PR event traverses ingestion, durable dispatch, analysis, mock-assisted validation, mock publication, and the authorized dashboard; recovery/authorization tests pass; and a fresh checkout reproduces the workflow with documented commands. A separately authorized real GitHub smoke test validates external integration before claiming real-world compatibility. Mock results do not constitute that smoke test.

Maintain a synthetic corpus with at least ten seeded actionable issues and ten clean/unsupported cases. Record expected hits and false positives separately for Ruff, Semgrep, and mock findings. This tests pipeline behavior, not LLM intelligence or general vulnerability recall.

## Risks, costs, and scope control

| Risk or cost | Mitigation / decision |
| --- | --- |
| Duplicate work and ambiguous GitHub writes | Unique identities, outbox, fenced leases, review markers, and reconciliation. Accept explicit uncertainty if GitHub cannot confirm an outcome. |
| Malicious code and prompt injection | Data-only analysis, trusted configs, isolated scanner processes, structured output, and no model tools. Review text cannot choose URLs, commands, or credentials. |
| Sandbox portability | Prove Linux-container isolation early. Native Windows workers are excluded. Never weaken isolation silently for a demo. |
| GitHub limits and unavailable fork content | Bounded pagination, retry windows, canonical metadata checks, explicit skipped/failed states. Incomplete data is not a clean result. |
| Noisy suggestions | Small rule set, provenance, diff validation, deduplication, caps, advisory feedback. Real model quality needs separate evaluation. |
| Private-code egress | Mock default; hosted adapter disabled until enabled explicitly with a documented provider data policy and operator opt-in. |
| Dashboard authorization | GitHub App user authorization, short access-cache lifetime, revocation handling, cross-repository tests. Defer custom organizations/roles. |
| Local resources | PostgreSQL, Redis, Node, and analysis containers consume memory/CPU. Start with 4 CPUs and 8 GiB available to Docker as an estimate, then measure. No paid service is required. |
| Hosted model charges | Zero in mock mode. Future cost equals input/output token usage at the selected provider rates, bounded by per-run/day caps; no assumed market prices. |
| Cloud expense | ECS, database, Redis, logs, backups, networking/NAT, and secrets incur recurring costs. Estimate current regional prices only when cloud work is authorized. |
| Scope creep | Extra languages, reruns, cloud, and paid adapters require separate phases. Defer features that do not improve the end-to-end MVP. |

## Decisions requiring implementation evidence

Phase 1 pins versions, dependency tooling, authentication library, and token key format. Phase 3 proves Linux scanner isolation before analyzer implementation. A hosted LLM vendor, cloud region/topology, spending ceiling, and production retention policy require separate decisions. None is needed for this planning task.
