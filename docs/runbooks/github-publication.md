# Independent advisory GitHub publication

Phase 6 publishes completed Shrike reports (RepoPilot in the request is the same
pipeline). [ADR 0005](../adr/0005-github-publication.md) records the phase rebaseline,
quality threshold, independent execution and uncertainty tradeoffs. Dashboard work
is Phase 6B. No live GitHub review or paid AI call was performed during implementation. The subsequent [Phase 7 dashboard](dashboard-local.md) advances current API readiness to `0007_dashboard`; migrate to head before restarting current services.

## Offline verification

Use the existing Python 3.12/uv workspace and Docker Desktop in Linux-container
mode. These commands use installed, locked dependencies and local container images;
they do not contact GitHub or a model provider:

```powershell
uv --cache-dir .cache/uv run --locked --offline --no-sync ruff check .
uv --cache-dir .cache/uv run --locked --offline --no-sync ruff format --check .
uv --cache-dir .cache/uv run --locked --offline --no-sync mypy
uv --cache-dir .cache/uv run --locked --offline --no-sync python scripts/test_backend.py -q
```

The runner creates and removes unique ephemeral PostgreSQL/Redis containers and a
UUID database per test. Migration upgrade/downgrade/upgrade and Alembic metadata
comparison run there, never against demo/user data. The extended
`tests/integration/test_celery_pipeline.py` exercises signed webhook ingestion,
real transport, isolated Ruff, mock AI, persistence and independent fake publication.
It proves analysis creates no publication intent until the publisher is invoked.
`test_publication.py` covers concurrency, recovery, stale/access boundaries and
idempotency; unit tests use an HTTP mock transport, including no-retry writes.

For Docker-free tests, use a fresh temp directory each time:

```powershell
uv --cache-dir .cache/uv run --locked --offline --no-sync pytest tests/unit -q -p no:cacheprovider --basetemp .cache/publication-unit-unique
```

## Test repository and App setup (manual, unperformed)

1. Create a disposable GitHub repository containing only synthetic/public Python
   code, with branches inside that repository. Forks are unsupported. Install your
   test App on **only this selected repository**. Do not use private production code.
2. Follow [github-app-manual.md](github-app-manual.md) for the separate integration
   database, App registration, generated webhook secret, outside-checkout PEM with
   restricted file access, HTTPS tunnel and `/webhooks/github` URL. There is no OAuth
   callback requirement for publication. Keep TLS verification and HMAC enabled.
3. To publish, change the App's **Pull requests** permission to **Read and write**
   and accept the permission update for the selected installation. Keep Metadata
   read and Contents read for analysis. All other permissions remain disabled:
   Issues write, Checks write, Actions write and Contents write are unnecessary.
   A key alone or App permission upgrade alone never enables the publisher.
4. Stop old API/worker processes, back up the integration database deliberately,
   then run `uv --cache-dir .cache/uv run --locked alembic upgrade head` and
   `uv --cache-dir .cache/uv run --locked alembic check`. Readiness now requires
   `0006_publication`. Do not downgrade publication history to retry a write.
5. Follow [async-processing.md](async-processing.md) to start the API, PostgreSQL,
   Redis, dispatcher and trusted host worker with `AI_PROVIDER=mock`. Do not mount a
   Docker socket into API/worker containers. Publish from a separate operator shell.

The client pins REST API `2026-03-10`. Documentation checked 2026-11-07:
[create/list reviews](https://docs.github.com/en/rest/pulls/reviews),
[review comments and line/side](https://docs.github.com/en/rest/pulls/comments),
[installation token scoping](https://docs.github.com/en/rest/apps/apps#create-an-installation-access-token-for-an-app).
The publisher requests repository-ID-scoped Metadata read/Pull requests read
tokens for its reads, and separate Metadata read/Pull requests write tokens only
for a write. Analysis clients retain Contents read/Pull requests read. Caches are
separate by scope, bounded and in-memory; no personal access tokens are supported.

## Manual end-to-end smoke test (unperformed)

Create a same-repository PR adding `demo.py` with invented content:

```python
value = 10 / 0
```

Wait for the signed event and queued job to finish. Obtain the job UUID through the
scoped read API or the guarded job-inspection CLI in the asynchronous runbook.
The deterministic mock should produce a high-confidence correctness finding.
Worker completion alone must leave the PR without Shrike feedback.

In the separate publisher shell, export the same integration `DATABASE_URL`, App
ID, optional client ID and outside-checkout key path. Export public installation
and repository IDs as an explicit paired grant. These IDs are not user names or
internal UUIDs. No grants means no access, including report-only reads.

```powershell
$env:GITHUB_PUBLISH_REPOSITORY_GRANTS = '<installation-github-id>:<repository-github-id>'
$env:GITHUB_PUBLISHING_ENABLED = 'false'
$env:GITHUB_MODE = 'disabled'
uv --cache-dir .cache/uv run --locked --offline python -m shrike.publication_cli --job-id <job-uuid>
uv --cache-dir .cache/uv run --locked --offline python -m shrike.publication_cli --job-id <job-uuid> --output <new-private-path-outside-checkout.json>
```

Default report-only mode reads the completed persisted report, makes **zero GitHub
requests**, does not read a key, and creates no publication row. The optional new
JSON file is a bounded summary-only preview; inspect it privately. It can contain
sensitive finding prose and paths, so keep it outside Git and remove it when done.
The preview uses summary locations because it deliberately does not fetch a fresh
diff. Console output contains only status/UUID/counts, never finding prose.

When deliberately ready to post to this test PR:

```powershell
$env:GITHUB_MODE = 'live'
$env:GITHUB_PUBLISHING_ENABLED = 'true'
uv --cache-dir .cache/uv run --locked --offline python -m shrike.publication_cli --job-id <job-uuid> --publish
```

`--offline` applies to uv dependency resolution; the explicitly enabled publisher
contacts GitHub. Both environment opt-ins and `--publish` are required. The command
publishes exactly one advisory `COMMENT` review with the immutable head SHA; it
never approves, requests changes, merges, or edits code. Up to ten medium-or-higher
correctness/security/reliability findings at confidence >= 0.85 are selected, sorted
by severity and deduplicated. Low/minor/maintainability suggestions remain internal.
Raw evidence, diffs, file contents, and model responses are omitted. Only current
new-side added lines get inline comments; deleted/context/invalid mappings become
actionable summary findings. The summary labels mock/partial/static-only coverage.

Verify manually:

1. GitHub shows one summary and the zero-division inline comment on the added line.
   The review is advisory and labeled deterministic mock-assisted. No approval or
   change request is submitted. Inspect only synthetic content in screenshots.
2. Repeat the exact `--publish` command. It returns `no_action` for a locally
   published identity and creates no additional review or comments.
3. Push a new commit to the PR, let ingestion record the new revision, and try the
   old job UUID. It must not create new feedback. A new completed job is a distinct
   immutable identity and requires its own explicit publishing command.
4. Remove App repository selection or suspend/uninstall the test App. Existing
   grants must not bypass active local/canonical access checks. Do not run paid AI.
5. Confirm publication metadata using the integration database command below.
   Do not select `payload`, job results or finding messages in operational logs.

```powershell
docker compose -p shrike-github --env-file .env.example exec postgres psql -U shrike -d shrike_demo -c 'SELECT job_id,state,attempts,review_id,comment_ids,reason,available_at FROM review_publications ORDER BY updated_at DESC LIMIT 10;'
```

No live failure injection is necessary: stale-before/after-write, 422 summary
fallback, API rate limits, deleted/context lines, timeout/lost response, partial
ID retrieval and duplicate claims are deterministically tested offline.

## Failure handling and investigation

`preparing` has a two-minute bounded ownership lease. The payload/digest and write
intent commit as `inflight` before the one HTTP attempt. A crashed inflight lease
becomes `uncertain`, never an unsent task. No database transaction spans HTTP.
Repeated explicit invocations reconcile with complete bounded review pages,
authenticated App bot identity, exact head SHA and hidden per-job marker. Analysis
never reruns because publication failed. A pending matching review or conflicting
reviews require investigation; no automatic submit/edit/delete occurs.

A definite 401/403/404/422/rate-limit response is `failed` with bounded backoff
and at most three write attempts per identity. Respect `available_at` (including
GitHub retry/reset hints) before explicitly rerunning the same command. A definite
422 enables summary-only fallback on the next attempt after reconciliation. Do
not guess diff positions, increase counters, or delete identities to force success.

Timeouts, 5xx, invalid write responses and crashes are `uncertain`. Run the same
`--publish` command only to **read/reconcile**, never to send a replacement review.
If the marker is found, persist the external review/comment IDs. If absent, retain
uncertainty indefinitely, including after 24 hours; absence alone is not proof
that the POST never happened. Investigate the PR and GitHub incident history
manually. There is intentionally no force-repost/reset command.

`partial` preserves a confirmed review ID when comment enumeration fails or IDs
are incomplete; another invocation only reads IDs, with no second review POST.
`suppressed` means stale/inaccessible work was refused before a known write.
`stale` preserves a review ID when a post-write revision/access check detects the
unavoidable GitHub race. Revocation prevents further repository reads, including
reconciliation; keep the uncertain record for an authorized operator to investigate.
The API offers no atomic compare-and-post, so exactly-once or perfect cancellation
is not promised. Never hide this by automatically deleting historical reviews.

Exit codes: 0 for report-only/published/no action; 1 for a visible non-success
publication outcome; 2 for refused configuration/access or unavailable resources.
`no_action` can also mean an active lease, future retry time or exhausted attempts;
inspect metadata before inferring success. No publication watch process or queue
is enabled. Set `GITHUB_PUBLISHING_ENABLED=false` and `GITHUB_MODE=disabled` in
the operator shell afterward; revoke/remove the test installation and stop the
tunnel/processes when finished. Keep publication identities/IDs across restarts
and content retention. Automated retention/reconciliation scheduling is deferred.
