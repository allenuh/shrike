# Standalone analysis and evaluation

Scope: standalone operator CLI and Python engine, independent of HTTP, Celery, publishing, and dashboard code. Phase 5 reuses it through [asynchronous processing](async-processing.md), restricted to mock AI. All fixtures are invented. No real model request, live evaluation, or account/billing setup was performed. [ADR 0003](../adr/0003-analysis-engine-scope.md) explains the scanner boundary.

## Offline setup and commands

Use Python 3.12, uv, and Docker Desktop in Linux-container mode. Dependency/image downloads need registry access; analysis/tests require no paid service. From the repository root:

```powershell
uv --cache-dir .cache/uv sync --locked
docker pull ghcr.io/astral-sh/ruff@sha256:c4b7e7a87e4b07d66b569dd2e6b2ce5a25e38be91dd664dc49b9882be27acd9b
docker pull busybox@sha256:a7dbc319b1438115a207e11930dc4bb3e643dcb3ec0bdd694bb36cd8fad289ec
$env:AI_PROVIDER = 'mock'
uv --cache-dir .cache/uv run --locked --offline python -m shrike.review_cli evaluate
uv --cache-dir .cache/uv run --locked --offline python -m shrike.review_cli analyze --snapshot tests/fixtures/analysis/snapshot.json
uv --cache-dir .cache/uv run --locked --offline python -m shrike.review_cli analyze --snapshot tests/fixtures/analysis/snapshot.json --dry-run
```

For a database-free fixture demo, leave `DATABASE_URL` unset in this shell. With a database URL, follow [backend-local.md](backend-local.md), migrate to head, seed the synthetic demo, and export `DEV_REPOSITORY_GRANTS=710001:810001`; the engine uses the scoped persistent cache instead. It never auto-loads `.env` or runs migrations/seeding. Mock mode never reads `LLM_API_KEY`. Repeated calls in one engine share the bounded fixture cache; repeated CLI calls use persistent caching only when PostgreSQL is configured.

`evaluate` loads 20 bounded synthetic cases: ten defects, ten clean examples. Expected offline result is 10 hits, zero misses, zero false-positive cases, with nine static hits and one deterministic mock hit. This measures the curated rules/pipeline, not model intelligence, broad vulnerability recall, or general false-positive rates. The prompt-injection clean fixture is data only. A corpus expectation mismatch exits 1; configuration/scanner errors exit 2.

Phase 8 adds a separate 32-change labeled evaluator with exact-line precision,
recall, false positives, latency and machine-readable reports; see
[EVALUATION.md](../EVALUATION.md). Its challenging cases deliberately expose
misses/false positives and supersede the curated corpus for quality measurement.
The legacy optional live evaluator below is now additionally limited to one
uncached admission per minute, persisted across restarts. A second uncached
case inside that window stops with `provider_throttled` before reservation or
dispatch. Use `--max-requests 1` for a separately authorized one-request session;
never reset its ledger/session/rate clock to make a batch proceed.

The CLI prints only numeric/safe metadata, never finding text, source, paths, credentials, or raw provider errors. To inspect a complete report, choose a new private output path explicitly:

```powershell
New-Item -ItemType Directory -Force .cache | Out-Null
uv --cache-dir .cache/uv run --locked --offline python -m shrike.review_cli analyze --snapshot tests/fixtures/analysis/snapshot.json --report .cache/demo-report.json
```

Existing output files are never overwritten. Reports contain sensitive findings/evidence if real snapshots are supplied: restrict access, avoid screenshots/log uploads, and purge them yourself. `.cache` is ignored. Reports include validated categories/severities/confidence, real changed-line/evidence mappings, suggestions, analyzer provenance, coverage, summary, model/prompt/analyzer versions, analysis hash, latency, estimated token/cost bounds, nullable reported usage/calculated cost, and cache-hit status. A cache hit reuses original analysis usage/cost metadata and causes no additional charge.

## Scanner and pipeline boundaries

Snapshots supply immutable base/head SHAs, raw unified diff, and bounded head-file contents. The caller is responsible for obtaining them from a canonical authorized source; this CLI does not fetch GitHub content. The parser verifies hunk counts and head-line consistency. Quoted/ambiguous paths and incomplete snapshots fail closed. Deleted/binary/symlink/submodule/non-Python/missing/excluded/oversized files are skipped explicitly. File-count selection is lexical, not model-selected.

Ruff policy includes F821/F823/F601/F602/F631/B006/B012, with no formatting rules. Only changed-line findings enter reports. Repository configs and inline `noqa` cannot disable the policy. Source travels over stdin to a digest-pinned container, with no mounts, network, credentials or writable root. The container runs UID/GID 65534, drops capabilities, disables privilege escalation and Docker logging, and has 128 MiB memory, one CPU, 32 processes, file-descriptor/output bounds and a 30-second scan timeout. Exact task-owned containers are removed even on timeout. No repository code is imported/executed; Semgrep is not implemented or claimed to have run.

The Docker CLI/daemon is a trusted host/operator capability. Never give API/worker containers the Docker socket. Future queue/deployment integration needs a compatible isolated runner and fenced job leases. Kernel/daemon compromise is outside this boundary. Per-engine concurrency defaults to two, one per repository (striped locks can conservatively serialize unrelated repositories). Database live slots enforce cross-process paid concurrency. The standalone pipeline has bounded per-file/provider timeouts; the future queued 180-second attempt deadline and crash janitor remain deferred.

Context consists of changed lines and at most two adjacent supporting lines. Independent input/output/diff/context ceilings apply; an oversized complete prompt yields disclosed static-only output. No PR description or unrelated repository text is sent. Findings must refer to a selected changed line and contain evidence actually present there (and shown to the model). Unknown locations, weak confidence, unsafe text, and unsupported security hypotheses are rejected. Security normalization currently supports only directly demonstrated `eval(input(...))`; broader security coverage requires reviewed rules. Required static failure is an error; optional AI failure is labeled static-only. Advisory model claims remain fallible.

## Dry-run cost estimate without credentials

Mock dry-run reports zero model cost. To quote the hosted profile without sending a request, use a reviewed unexpired copy of [the dated price example](../openai-price-profile.example.json):

```powershell
$env:AI_PROVIDER = 'openai'
$env:LLM_OPENAI_MODEL = 'gpt-6-luna'
$env:LLM_PRICING_PROFILE_PATH = '<absolute-path-to-reviewed-unexpired-price-profile.json>'
uv --cache-dir .cache/uv run --locked --offline python -m shrike.review_cli analyze --snapshot tests/fixtures/analysis/snapshot.json --dry-run
```

This reads no API key, initializes no budget, reserves no money, and sends no model request. The scanner still runs. Stale/missing prices produce a safe refusal reason and no usable quote. Estimated input counts are conservative upper bounds, not actual tokenizer counts. Unknown prices are never treated as zero. The example intentionally leaves `byte_token_bound_approved=false`, so it cannot enable live dispatch.

## Optional live setup and evaluation (manual, unperformed)

These commands are instructions for a separately authorized operator action. Do not run them as part of ordinary development/tests. Read [AI_COST_CONTROLS.md](../AI_COST_CONTROLS.md) first. Verify current [model support](https://developers.openai.com/api/docs/models/gpt-6-luna), [official USD pricing](https://developers.openai.com/api/docs/pricing), [strict structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), and [standard service tier](https://developers.openai.com/api/reference/cli/resources/responses/methods/create). No actual tokenization/quality/account compatibility is established by mocks.

1. Use a dedicated provider project/key where possible. Reconcile all prior development/evaluation/API spending and outside charges; do not assume $10 remains. Export `DATABASE_URL` and paired grants for the synthetic demo database as in the backend runbook, migrate to `0003_analysis`, and seed only that guarded synthetic database. Live evaluation uses invented code under the demo's repository identity; it conservatively marks the snapshot private, matching that demo repository. No real GitHub source is fetched.
2. Review an exact standard non-regional text price profile, its UTC verification/expiry window (maximum 24 hours), rates, model and bounded token policy. The byte-plus-framing bound needs explicit encoding/framing evidence before setting `byte_token_bound_approved=true`; this is a bounded override, not a proven exact tokenizer. Without evidence leave it false and stay in mock/dry-run. Store the reviewed profile outside the checkout. Premium/regional/multimodal modes, custom endpoints, tools and cache-write options are unsupported.
3. Initialize the singleton ledger once after reconciling known spend. The command refuses to overwrite an existing budget. Defaults are total $10, warning $7.50, hard stop $9, $0.02 per review and one global live slot. `AI_BUDGET_*`, `AI_MAX_REVIEW_COST_USD` and `LLM_MAX_LIVE_CONCURRENCY` are read only at initialization; environment changes never top up an existing ledger. Total cannot exceed the user-authorized $10 ceiling. Enter the known spend explicitly:

```powershell
$priorSpend = Read-Host 'Reconciled prior API development spend in USD'
uv --cache-dir .cache/uv run --locked --offline python -m shrike.review_cli budget-init --prior-spend-usd $priorSpend --confirm-reconciled
```

4. Supply `LLM_API_KEY` securely from your password manager/session, never through command history, `.env` commits, logs or frontend variables. Set the approved model/allowlist/profile and live/evaluation opt-ins explicitly. The fixed provider origin ignores proxy environment variables; missing credentials, stale prices, unapproved token bounds, missing grants, CI/test execution and exhausted budgets stop dispatch. The fixture corpus is public synthetic data; the private-code flag below acknowledges its private demo repository classification, without fetching private code.

```powershell
$env:AI_PROVIDER = 'openai'
$env:LLM_OPENAI_MODEL = 'gpt-6-luna'
$env:LLM_MODEL_ALLOWLIST = 'gpt-6-luna'
$env:LLM_LIVE_ENABLED = 'true'
$env:LLM_ALLOW_PRIVATE_CODE = 'true'
$env:LLM_LIVE_EVAL_ENABLED = 'true'
$env:LLM_LIVE_EVAL_MAX_REQUESTS = '2'
$evaluationSession = [guid]::NewGuid().ToString()
uv --cache-dir .cache/uv run --locked --offline python -m shrike.review_cli evaluate --live --max-requests 2 --session $evaluationSession
```

The reviewed `LLM_PRICING_PROFILE_PATH`, secret and database/grants must already be set. Preserve the session UUID when resuming; PostgreSQL dispatch counts prevent resetting/increasing its cap. Cache hits send no request. There is at most one request per review, no retries or model escalation. Stop on the first budget/model failure. Evaluation reports corpus outcomes honestly, including misses; deterministic mock expectations do not guarantee real-model agreement. Turn live flags off and remove the session key from the environment afterward.

Reservations commit before dispatch and survive restart, timeout, missing usage, scanner/report retention, or a crash before settlement. Actual reported usage is recorded even when candidate JSON is invalid; calculated charges are not invoices. Unknown outcomes hold the full money reservation and live slot. Duplicate dispatch is refused; over-bound usage freezes spending. There is no automatic refund, retry, ledger reset, or billing reconciliation command. Investigate using safe IDs and external billing evidence; implement an auditable recovery before adjustments. Never delete accounting to unblock a demo. A stale database restore/new database requires reconciliation; automatic external detection is not provided. No application ledger can control other projects/keys, taxes, this coding session's charges, or provider billing errors.

## Verification commands

```powershell
uv --cache-dir .cache/uv run --locked --offline ruff check .
uv --cache-dir .cache/uv run --locked --offline ruff format --check .
uv --cache-dir .cache/uv run --locked --offline mypy
uv --cache-dir .cache/uv lock --check --offline
uv --cache-dir .cache/uv run --locked --offline python scripts/test_backend.py -q --cov=shrike --cov=shrike_api --cov=shrike_worker --cov-report=term-missing
```

The runner uses a unique tmpfs PostgreSQL container and database per test; hosted HTTP responses are mocked. Tests also use pre-pulled digest-pinned Ruff/probe images. No real credentials or provider requests are needed. Follow [ROADMAP.md](../ROADMAP.md) for executed evidence, remaining manual steps, and deferred criteria. Application schema downgrade destroys reports/accounting; use only disposable databases or an explicitly reconciled recovery plan.
