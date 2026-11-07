# Shrike AI cost controls

Status: implemented Phase 4 controls, 2026-11-06, with mocked hosted-provider verification and no real API calls. [ADR 0003](adr/0003-analysis-engine-scope.md) records the user's expanded scope. The standalone engine has provider contracts, deterministic mock, guarded OpenAI adapter, dry-run/evaluation commands, scoped cache, and persistent budget reservations. See [analysis-local.md](runbooks/analysis-local.md) for setup and limitations. Queue integration, automated billing reconciliation, and real model quality verification remain deferred.

## Budget and execution policy

The approximate total OpenAI API development budget is **$10 USD**. Initial cumulative warning and hard-stop thresholds are **$7.50** and **$9.00**. The remaining $1 buffer accommodates billing uncertainty; it does not authorize extra requests. Validate `0 <= warning < hard_stop <= total_budget`; raising limits or resetting accounting requires an explicit user decision. Never reset limits daily, on deploy, restart, seed, migration, or review purge.

Ordinary local development, CI/CD, unit/integration tests, and automated evaluation use the deterministic mock exclusively, with no model credentials or AI network access. Mock mode ignores any ambient API key and cannot fall back to a real provider. Inject fake transports for hosted-adapter contract tests. Keep mock usage/cost clearly labeled and outside the real spending total.

Real calls require a separately authorized live operation, `AI_PROVIDER=openai`, `LLM_LIVE_ENABLED=true`, a verified allowlisted model/price/token-bound profile, configured secret, reconciled ledger, and private-code consent when applicable. A key alone is insufficient. CLI live mode is rejected in test/CI processes; adapter tests inject fake transports explicitly. Do not add paid calls to deployment hooks or ordinary startup checks. There are no retries, tools, fallback models, batch jobs, or prompt-repair calls.

## Provider and configuration contracts

`LLMProvider.review` accepts a bounded serialized context and output cap, returning a typed `ModelReply` with model identity and nullable reported usage. It owns no database or budget state. `PriceProfile` captures verified rates and a bounded token-estimation policy; `SpendingLedger` reserves/settles through PostgreSQL. `AnalysisStore` authorizes and caches reports. Application orchestration owns these gates; composition selects adapters without provider SDKs in review business logic. A more general tokenizer/pricing port remains a future extension; the current profile fails closed unless a bounded token policy is explicitly approved.

Standalone settings are placeholders in [.env.example](../.env.example); API/ingestion processes do not enable AI from these settings:

| Setting | Proposed default / meaning |
| --- | --- |
| `AI_PROVIDER` | `mock`; lower-priority legacy alias `LLM_PROVIDER`. Mock identity is fixed at `mock-v1`. |
| `LLM_LIVE_ENABLED`, `LLM_ALLOW_PRIVATE_CODE` | Both `false`; separate execution and sensitive-code egress consent. |
| `LLM_OPENAI_MODEL` | `gpt-6-luna`; verify availability and current prices before explicit live use. |
| `LLM_MODEL_ALLOWLIST` | Empty in mock mode; live mode requires the exact approved model identity. |
| `LLM_API_KEY` | Unset/unread in mock and dry-run mode; adapter fixes the HTTPS endpoint and ignores proxy environment settings. Secrets stay server-side. |
| `REVIEW_MAX_LLM_INPUT_TOKENS` | 12,000 including instructions, schema, framing, and code. |
| `REVIEW_MAX_LLM_OUTPUT_TOKENS` | 2,000 maximum billed output including reasoning where applicable; set provider-enforced cap. |
| `REVIEW_MAX_LLM_DIFF_BYTES` | 65,536 selected diff bytes, within the existing 524,288-byte fetched-diff ceiling. |
| `REVIEW_MAX_LLM_CONTEXT_BYTES` | 131,072 total serialized request bytes; token ceiling also applies. |
| `REVIEW_MAX_CONCURRENCY` | 2 concurrent calls per engine instance; one per repository using bounded striped locks. Cross-process paid concurrency is enforced by the ledger; queue-wide review leases remain deferred. |
| `LLM_MAX_LIVE_CONCURRENCY` | 1 application-wide across all workers and evaluation processes, backed by durable claims. |
| `LLM_REQUEST_TIMEOUT_SECONDS`, `LLM_MAX_REQUEST_ATTEMPTS` | 30 seconds, 1 attempt (zero automatic retries) per logical call. |
| `AI_BUDGET_TOTAL_USD`, `AI_BUDGET_WARNING_USD`, `AI_BUDGET_HARD_STOP_USD` | `10.00`, `7.50`, `9.00`; cumulative application-wide USD. |
| `AI_MAX_REVIEW_COST_USD` | `0.02` cap across all paid attempts for one review; global budget also applies. |
| `LLM_PRICING_PROFILE_PATH` | Reviewed non-secret JSON profile; code enforces a maximum 24-hour verification window. No live rate fallback. |
| `LLM_LIVE_EVAL_ENABLED`, `LLM_LIVE_EVAL_MAX_REQUESTS` | `false`, `0`; an explicit live evaluation needs both opt-in and a positive finite cap. |

The composition root selects `LLM_OPENAI_MODEL`; the mock always uses `mock-v1`. Unknown providers fail validation. Byte/token caps apply independently; over-limit full prompts yield static-only results. Context contains changed lines and at most two adjacent supporting lines, in deterministic order; omitted lines are disclosed. No PR description or unrelated supporting file is sent. Context sent to a real provider must be explicitly authorized; redaction cannot guarantee that source is no longer sensitive.

## Model and verified pricing

On 2026-11-06, the official [GPT-6 Luna model page](https://developers.openai.com/api/docs/models/gpt-6-luna) lists a low-cost text model with structured-output support. It is a development candidate, not a code-review quality claim or proof of account access. Revalidate support, account availability, token limits, and suitability when implementing/enabling Phase 8. Model selection remains environment-configured.

Use current [official OpenAI API pricing](https://developers.openai.com/api/docs/pricing) to create a reviewed price snapshot for the exact standard, non-regional text profile. The dated [example profile](openai-price-profile.example.json) records verified USD rates and expiry, with token-bound approval deliberately false. It is a reference, not an enabled live profile. Requests explicitly select `service_tier=default`, no tools, `store=false`, and reasoning `none`. Regional/premium/multimodal/custom endpoints are unsupported. No cache discount is assumed. Reverify after expiry or model/tier changes; ordinary development never fetches pricing or model discovery automatically.

For a supported plain-text profile, reserve:

```text
upper_cost = ceil_to_micro_USD(
  input_token_upper_bound * verified_input_USD_per_million / 1_000_000
  + max_billable_output_tokens * verified_output_USD_per_million / 1_000_000
  + any_other_verified_maximum_charges
)
```

Use decimal arithmetic or integer micro-USD, never binary floating point, and round reservations upward. Use uncached input rates; do not depend on discounts. Disable optional cache writes, tools, premium modes, and other charged features unless their maximum charges are explicitly supported and reserved. Count all billable reasoning/output and applicable regional/tier surcharges. Enforce provider caps corresponding to those bounds.

The estimate counts UTF-8 bytes of the complete ASCII-escaped serialized request plus a framing ceiling (minimum 4,096), and reserves the entire provider-enforced output cap. This is deliberately conservative and is not an exact tokenizer count. Live mode fails closed unless an operator explicitly approves this bounded policy for the exact model/API via `byte_token_bound_approved=true` in a reviewed profile. This bounded override must be justified against the provider encoding/framing contract; its correctness has not been established by a live test. It never bypasses token caps, pricing expiry, budget, or request limits. Without that evidence leave approval false and use mock/dry-run only. Unsupported charges or stale/unknown rates block dispatch. General exact tokenizer integration remains future work.

## Persistent ledger and request lifecycle

PostgreSQL holds one content-free budget for the entire Shrike application, shared by installations, workers, and live evaluations. It includes imported known prior/external development spend; the first initialization requires operator reconciliation rather than assuming the entire $10 remains. A new database or stale backup is not permission to recreate unused allowance. All live processes must use the same reconciled ledger.

Migration `0003_analysis` adds `ai_budgets`, `ai_price_snapshots`, `ai_spend_entries`, and repository-scoped `analysis_reports`. Spending uses integer micro-USD, unique content/policy call identities, nullable reported usage, and UTC timestamps. Accounting contains hashes and numeric/cost metadata, never source/prompts/responses/keys; it has no cascading relationship to review content. Reports contain access-controlled findings/evidence, but no complete prompts, diffs, or model responses. Existing execution token fields remain unchanged: standalone engine metadata lives in reports/ledger until fenced queue integration is implemented.

1. Verify live/evaluation/egress opt-ins, authorization/current revision, limits, model/price profile, complete token bounds, and remaining per-review/request-count allowance. A refused call makes no outbound request.
2. In a short transaction, lock the singleton budget row, compute committed exposure, and atomically reserve `upper_cost` plus a live slot. Exposure is imported prior spend + settled charges + uncertain held charges + all outstanding reservations, with each entry counted once. Admit only when `exposure + upper_cost <= hard_stop` and the per-review cap permits it. Equality is allowed; no positive request fits when exposure is already at the hard stop. Emit a safe warning when projected exposure reaches $7.50. Multiple workers cannot spend the same allowance. An unavailable/inconsistent ledger blocks dispatch.
3. Commit a unique dispatch intent before sending. The SDK/transport performs at most one request by default; disable hidden SDK/HTTP/queue retries. Commit does not make the provider operation atomic. A crash between dispatch intent and send is deliberately treated as potentially billable, even if it wastes allowance.
4. On a response, persist actual reported input/output/billable subcategory usage with the captured price snapshot, separately from estimates; calculate the local settled cost. Usage is recorded even for invalid findings. Do not describe calculated cost as an invoice. Atomically replace the reservation with settled exposure, releasing only a verified unused amount. Duplicate settlement is idempotent.
5. On timeout, lost response, crash, ambiguous cancellation, or missing usage, retain the full reservation as uncertain exposure. A worker lease expiry never refunds it or initiates a second paid call. Only a provably unsent request can release its reservation automatically. Return a safe reason and disclosed static-only result when possible. If reported costs exceed the reserved bound, retain the full actual charge, block further live work, and investigate the pricing/count discrepancy.
6. Uncertain entries block their slot until explicit evidence-based recovery. There is no automated refund/reconciliation or retry command in this phase. Do not delete rows or change identities to retry. A future reconciliation workflow must preserve an audit trail and be separately implemented. Review/GitHub retries never confer paid-request retry permission. Duplicate settlement is idempotent; over-bound reported usage freezes further live work.

Never hold database locks during network calls. Money reservations and potentially active requests cannot be released merely because a concurrency lease expires. An uncertain in-flight request retains its live slot until provider completion or conservative bounded reconciliation is established; fail closed rather than overrun concurrency. Retain accounting across restarts and review retention; mock fixtures cannot initialize, clear, or top up real accounting.

## Evaluation, evidence, and limitations

Live evaluation is a separate operator command, never a test or CI job. It requires `LLM_LIVE_EVAL_ENABLED=true`, a configured positive maximum, an explicit `--max-requests` between 1 and 5, a `--session` UUID, the normal live opt-ins, and the shared ledger. Session dispatch counts are persisted in spend entries; restarting with the same session cannot reset or increase its cap. Use only a synthetic/public corpus. Stop at the first limit/failure reached. Mock evaluation measures pipeline expectations, not actual model quality. No live evaluation was performed by this task.

Before Phase 8 is verified, mocked and disposable-database tests must prove threshold equality/overflow, parallel reservations, per-review and evaluation caps, restart/restore behavior, stale pricing and unavailable ledger refusal, model/token bound failures, malformed results with usage, missing usage, dispatch/settlement crashes, duplicate settlement, uncertain-slot handling, retention independence, and disabled hidden retries. Capture logs for synthetic credential/source sentinels. All test responses remain mocked.

This ledger can control only requests routed through it. It cannot observe this coding agent's billing, other tools/API keys/projects, unrelated account charges, taxes, exchange rates, or unreported prior spend. Import known outside costs before claiming remaining development allowance, use a dedicated provider project/key where possible, and reconcile provider billing before live batches. A provider-side budget alert is supplemental; do not assume it is an immediate hard cap. Price changes, provider accounting errors, compromised keys, stale restores, and administrator tampering can defeat local estimates. Fail-closed reservations trade availability for budget safety and may exhaust allowance without a completed review. No present documentation proves that $10 remains or guarantees an account invoice ceiling.

Keep credentials outside the checkout and web bundle; never commit `.env` or real credentials. Log only safe IDs, reason codes, aggregate counts, and monetary/token metadata. Do not log private source, prompts, payloads, API keys, or raw provider errors. No cloud resources, paid calls, or provider credentials are required for the local MVP.
