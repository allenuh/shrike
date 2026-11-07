# Shrike AI cost controls

Status: architecture requirements, 2026-11-06. The current backend has no AI provider, tokenizer, pricing catalog, spending ledger, or live evaluation command. This document specifies future implementation; the example settings below are not consumed by today's runtime. See [ARCHITECTURE.md](ARCHITECTURE.md) and [ROADMAP.md](ROADMAP.md) for phase boundaries.

## Budget and execution policy

The approximate total OpenAI API development budget is **$10 USD**. Initial cumulative warning and hard-stop thresholds are **$7.50** and **$9.00**. The remaining $1 buffer accommodates billing uncertainty; it does not authorize extra requests. Validate `0 <= warning < hard_stop <= total_budget`; raising limits or resetting accounting requires an explicit user decision. Never reset limits daily, on deploy, restart, seed, migration, or review purge.

Ordinary local development, CI/CD, unit/integration tests, and automated evaluation use the deterministic mock exclusively, with no model credentials or AI network access. Mock mode ignores any ambient API key and cannot fall back to a real provider. Inject fake transports for hosted-adapter contract tests. Keep mock usage/cost clearly labeled and outside the real spending total.

Real calls require a separately authorized Phase 8 implementation, `LLM_PROVIDER=openai`, `LLM_LIVE_ENABLED=true`, a verified allowlisted model/price profile, configured secret, valid ledger, and private-code consent when applicable. A key alone is insufficient. Live mode is rejected in test/CI processes; do not add paid calls to deployment hooks or ordinary startup checks. No automatic model upgrades, provider fallback, agents/tools, batch jobs, or prompt-repair calls.

## Provider and configuration contracts

The planned `LLMProvider` port accepts immutable bounded `ReviewContext` and `GenerationLimits`, returning typed candidates, provider/model identity, optional provider request ID, and nullable reported usage (including relevant billable subcategories). It owns no database or budget state. A `TokenCounter` port bounds the fully serialized request, including instructions/schema/framing. A `PricingCatalog` supplies verified versioned rates. Application orchestration applies a `SpendingLedger` port before invoking any hosted adapter. Infrastructure composition selects adapters from configuration; review business logic never imports a provider SDK or model name.

Initial proposed settings are mirrored as placeholders in [.env.example](../.env.example):

| Setting | Proposed default / meaning |
| --- | --- |
| `LLM_PROVIDER`, `LLM_MODEL` | `mock`, `mock-v1`; no paid model implicitly selected. |
| `LLM_LIVE_ENABLED`, `LLM_ALLOW_PRIVATE_CODE` | Both `false`; separate execution and sensitive-code egress consent. |
| `LLM_OPENAI_MODEL` | `gpt-6-luna` candidate for a future explicit live development profile; verify again before use. |
| `LLM_MODEL_ALLOWLIST` | Empty in mock mode; live mode requires the exact approved model identity. |
| `LLM_API_BASE_URL`, `LLM_API_KEY` | Unset in mock mode; live adapter restricts HTTPS endpoints to reviewed provider hosts. Secrets stay server-side. |
| `REVIEW_MAX_LLM_INPUT_TOKENS` | 12,000 including instructions, schema, framing, and code. |
| `REVIEW_MAX_LLM_OUTPUT_TOKENS` | 2,000 maximum billed output including reasoning where applicable; set provider-enforced cap. |
| `REVIEW_MAX_LLM_DIFF_BYTES` | 65,536 selected diff bytes, within the existing 524,288-byte fetched-diff ceiling. |
| `REVIEW_MAX_LLM_CONTEXT_BYTES` | 131,072 total serialized request bytes; token ceiling also applies. |
| `REVIEW_MAX_CONCURRENCY`, `REVIEW_MAX_PER_REPOSITORY` | Existing target: 2 active jobs per worker, 1 per repository; database claims. |
| `LLM_MAX_LIVE_CONCURRENCY` | 1 application-wide across all workers and evaluation processes, backed by durable claims. |
| `LLM_REQUEST_TIMEOUT_SECONDS`, `LLM_MAX_REQUEST_ATTEMPTS` | 30 seconds, 1 attempt (zero automatic retries) per logical call. |
| `AI_BUDGET_TOTAL_USD`, `AI_BUDGET_WARNING_USD`, `AI_BUDGET_HARD_STOP_USD` | `10.00`, `7.50`, `9.00`; cumulative application-wide USD. |
| `AI_MAX_REVIEW_COST_USD` | `0.02` cap across all paid attempts for one review; global budget also applies. |
| `LLM_PRICING_PROFILE_PATH`, `LLM_PRICING_MAX_AGE_HOURS` | Reviewed non-secret profile path, maximum 24 hours since verification for live dispatch. No rate default. |
| `LLM_LIVE_EVAL_ENABLED`, `LLM_LIVE_EVAL_MAX_REQUESTS` | `false`, `0`; an explicit live evaluation needs both opt-in and a positive finite cap. |

For future live mode, the composition root selects `LLM_OPENAI_MODEL`; the mock continues to use `LLM_MODEL=mock-v1`. Reject inconsistent/unknown provider settings rather than guess. Increasing output/context/concurrency cannot bypass budget or provider ceilings. Trim only at deterministic file/hunk boundaries, disclose omitted coverage, and avoid a paid call when no eligible context remains. Context sent to a real provider must be explicitly authorized; never treat redaction as a guarantee that source is no longer sensitive.

## Model and verified pricing

On 2026-11-06, the official [GPT-6 Luna model page](https://developers.openai.com/api/docs/models/gpt-6-luna) lists a low-cost text model with structured-output support. It is a development candidate, not a code-review quality claim or proof of account access. Revalidate support, account availability, token limits, and suitability when implementing/enabling Phase 8. Model selection remains environment-configured.

Use the then-current [official OpenAI API pricing](https://developers.openai.com/api/docs/pricing) to create a reviewed immutable price snapshot for the exact model, endpoint, processing tier, and region. Record source URL, UTC verification/expiry times, USD currency, rates/units, tokenizer/version, and all applicable billable categories. Do not embed guessed or timeless rates in code or this template. Reverify after expiry or any model/tier change; ordinary development never fetches pricing or calls model discovery automatically.

For a supported plain-text profile, reserve:

```text
upper_cost = ceil_to_micro_USD(
  input_token_upper_bound * verified_input_USD_per_million / 1_000_000
  + max_billable_output_tokens * verified_output_USD_per_million / 1_000_000
  + any_other_verified_maximum_charges
)
```

Use decimal arithmetic or integer micro-USD, never binary floating point, and round reservations upward. Use uncached input rates; do not depend on discounts. Disable optional cache writes, tools, premium modes, and other charged features unless their maximum charges are explicitly supported and reserved. Count all billable reasoning/output and applicable regional/tier surcharges. Enforce provider caps corresponding to those bounds.

If accurate counts/rates are unavailable, use a demonstrably safe model-specific upper bound with verified rates; otherwise **fail closed**. Character-count heuristics and a safety percentage alone do not establish a bound. This design provides no pricing/token uncertainty override. An unsupported billable category, stale profile, or unbounded provider behavior prevents real dispatch.

## Persistent ledger and request lifecycle

PostgreSQL holds one content-free budget for the entire Shrike application, shared by installations, workers, and live evaluations. It includes imported known prior/external development spend; the first initialization requires operator reconciliation rather than assuming the entire $10 remains. A new database or stale backup is not permission to recreate unused allowance. All live processes must use the same reconciled ledger.

Planned migrations add `ai_budgets`, immutable `ai_price_snapshots`, and `ai_spend_entries`. Use nonnegative exact monetary amounts, valid state checks, unique logical-call/attempt IDs, immutable dispatch/pricing identities, nullable reported usage, and UTC timestamps. Entries contain safe numeric usage/cost metadata only, never source, prompts, responses, keys, or sensitive payloads. Associate reviews/executions with nullable foreign keys that detach on purge; do not cascade-delete accounting. Existing execution token fields default to zero, so add explicit usage-availability/provenance fields rather than interpreting zero as provider-reported usage.

1. Verify live/evaluation/egress opt-ins, authorization/current revision, limits, model/price profile, complete token bounds, and remaining per-review/request-count allowance. A refused call makes no outbound request.
2. In a short transaction, lock the singleton budget row, compute committed exposure, and atomically reserve `upper_cost` plus a live slot. Exposure is imported prior spend + settled charges + uncertain held charges + all outstanding reservations, with each entry counted once. Admit only when `exposure + upper_cost <= hard_stop` and the per-review cap permits it. Equality is allowed; no positive request fits when exposure is already at the hard stop. Emit a safe warning when projected exposure reaches $7.50. Multiple workers cannot spend the same allowance. An unavailable/inconsistent ledger blocks dispatch.
3. Commit a unique dispatch intent before sending. The SDK/transport performs at most one request by default; disable hidden SDK/HTTP/queue retries. Commit does not make the provider operation atomic. A crash between dispatch intent and send is deliberately treated as potentially billable, even if it wastes allowance.
4. On a response, persist actual reported input/output/billable subcategory usage with the captured price snapshot, separately from estimates; calculate the local settled cost. Usage is recorded even for invalid findings. Do not describe calculated cost as an invoice. Atomically replace the reservation with settled exposure, releasing only a verified unused amount. Duplicate settlement is idempotent.
5. On timeout, lost response, crash, ambiguous cancellation, or missing usage, retain the full reservation as uncertain exposure. A worker lease expiry never refunds it or initiates a second paid call. Only a provably unsent request can release its reservation automatically. Return a safe reason and disclosed static-only result when possible. If reported costs exceed the reserved bound, retain the full actual charge, block further live work, and investigate the pricing/count discrepancy.
6. Reconcile uncertain entries against provider billing/usage evidence through an operator-controlled, auditable action. Record corrections as ledger adjustments, not destructive edits. A separate unique attempt may run only under an explicitly enabled retry policy, within its cap, with a fresh reservation; earlier uncertain charges still count. Review-attempt retries and GitHub retries do not confer paid-request retry permission.

Never hold database locks during network calls. Money reservations and potentially active requests cannot be released merely because a concurrency lease expires. An uncertain in-flight request retains its live slot until provider completion or conservative bounded reconciliation is established; fail closed rather than overrun concurrency. Retain accounting across restarts and review retention; mock fixtures cannot initialize, clear, or top up real accounting.

## Evaluation, evidence, and limitations

Live evaluation is a separate operator command, never a test or CI job. Require explicit `LLM_LIVE_EVAL_ENABLED=true` and a mandatory finite request maximum (for example, at most five for one invocation), a synthetic/public corpus, the normal global/per-review budgets, and persistent evaluation-session IDs/consumed counts. Count dispatch attempts before sending; retries consume the cap. Restarts resume the same session/counter; starting a new session requires another explicit operator action. Stop at the first limit reached. No live evaluation is performed by this task.

Before Phase 8 is verified, mocked and disposable-database tests must prove threshold equality/overflow, parallel reservations, per-review and evaluation caps, restart/restore behavior, stale pricing and unavailable ledger refusal, model/token bound failures, malformed results with usage, missing usage, dispatch/settlement crashes, duplicate settlement, uncertain-slot handling, retention independence, and disabled hidden retries. Capture logs for synthetic credential/source sentinels. All test responses remain mocked.

This ledger can control only requests routed through it. It cannot observe this coding agent's billing, other tools/API keys/projects, unrelated account charges, taxes, exchange rates, or unreported prior spend. Import known outside costs before claiming remaining development allowance, use a dedicated provider project/key where possible, and reconcile provider billing before live batches. A provider-side budget alert is supplemental; do not assume it is an immediate hard cap. Price changes, provider accounting errors, compromised keys, stale restores, and administrator tampering can defeat local estimates. Fail-closed reservations trade availability for budget safety and may exhaust allowance without a completed review. No present documentation proves that $10 remains or guarantees an account invoice ceiling.

Keep credentials outside the checkout and web bundle; never commit `.env` or real credentials. Log only safe IDs, reason codes, aggregate counts, and monetary/token metadata. Do not log private source, prompts, payloads, API keys, or raw provider errors. No cloud resources, paid calls, or provider credentials are required for the local MVP.
