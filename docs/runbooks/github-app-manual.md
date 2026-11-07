# GitHub App registration and live verification: manual operator steps

These account, key, tunnel, and real-repository steps have **not** been performed by Codex. GitHub behavior is verified with synthetic fixtures/mocked responses. Follow this runbook only when intentionally configuring a test installation. Phase 5 uses the separate [Redis/Celery runbook](async-processing.md) for automatic execution with mock AI; no hosted model or publishing is enabled by those workers. [Phase 6 publication](github-publication.md) requires independent opt-ins and documents the optional write-permission upgrade. Prefer a disposable repository with invented code/data.

## Permissions verified against current documentation

Documentation checked on 2026-11-06; the adapter pins REST API version `2026-03-10`.

| Permission | Initial setting | Why |
| --- | --- | --- |
| Metadata | Read | Repository identity and installation inventory. Inventory uses a metadata-only installation token. |
| Pull requests | Read | PR metadata, diff format, and changed-file listing. |
| Contents | Read | Immutable commit and blob reads. |
| Pull requests | No write access for ingestion-only setup | Phase 6 manual publication requires Read and write plus installation consent; see the publication runbook. |
| Other repository, organization, account permissions | None | Not needed for ingestion. |

GitHub documents [PR read/file-list permissions](https://docs.github.com/en/rest/pulls/pulls), [commit read permissions](https://docs.github.com/en/rest/commits/commits), and [installation inventory access](https://docs.github.com/en/rest/apps/installations). The inventory endpoint needs an installation token and no additional permissions. Use the minimum repository permissions above; no personal access token or user OAuth grant is required by the server. See [choosing App permissions](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app).

The adapter signs App JWTs with RS256 (`iat` backdated 60 seconds, `exp` nine minutes ahead). Installation tokens expire after roughly one hour, are refreshed before expiry, and remain only in a bounded in-memory cache. Repository operations request a token narrowed to that repository ID and read permissions; inventory tokens request metadata only. The token format is treated as opaque, not fixed at 40 characters. Sources: [App JWTs](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app), [installation tokens](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app).

## 1. Prepare a separate local integration database

Install the backend dependencies as described in [backend-local.md](backend-local.md). Keep Docker Desktop in Linux-container mode. Use a fresh Compose project so synthetic seeded data and live metadata stay separate; the port override avoids the normal demo database's port.

```powershell
$env:SHRIKE_LOCAL_DB_PASSWORD = [Guid]::NewGuid().ToString('N')
$env:SHRIKE_LOCAL_DB_PORT = '55433'
$env:APP_ENV = 'development'
$env:ENABLE_DEV_AUTH = 'false'
$env:GITHUB_MODE = 'disabled'
$env:GITHUB_WEBHOOKS_ENABLED = 'false'
$env:DATABASE_URL = 'postgresql+psycopg://shrike:{0}@127.0.0.1:55433/shrike_demo' -f $env:SHRIKE_LOCAL_DB_PASSWORD
docker compose -p shrike-github --env-file .env.example up -d --wait postgres
uv --cache-dir .cache/uv run --locked alembic upgrade head
uv --cache-dir .cache/uv run --locked alembic check
```

Do not run the synthetic seed against this integration database. The seed also refuses live/webhook-enabled configuration. Reuse the original database password when restarting an existing volume; changing the environment value does not rotate PostgreSQL credentials. Do not overwrite the existing checkout `.env`; the application does not load it automatically, and Compose explicitly uses the placeholder example file above.

## 2. Register an App and generate a key

1. In GitHub, open your personal **Settings > Developer settings > GitHub Apps > New GitHub App**, or the equivalent settings for an organization you administer. Follow [GitHub's registration instructions](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app).
2. Choose a unique App name and your project's homepage URL. Restrict installation availability to your account initially if appropriate. This phase needs no user authorization callback, OAuth login, device flow, or user access token.
3. Select the repository permissions listed above and subscribe to **Pull request** events. GitHub automatically delivers `installation` and `installation_repositories` events to Apps; those are not manual subscription checkboxes. See [webhook events](https://docs.github.com/en/webhooks/webhook-events-and-payloads).
4. Create a high-entropy webhook secret in a local password manager. Use exactly the same value in the App's **Webhook secret** field and the server's `GITHUB_WEBHOOK_SECRET`. The implementation requires 32–512 characters. Never send the value in chat, place it in Git, or print it in logs.
5. Record the public App ID and optionally its public client ID. Generate a private RSA PEM key from the App settings, store it **outside the checkout**, and restrict file access to your user/service. Do not use the OAuth client secret as a signing key. No private key is committed or included in example configuration.
6. Configure the webhook URL after starting a tunnel below. If registration requires a URL first, keep webhook delivery inactive until the actual endpoint and secret are ready.

## 3. Start the API and a temporary HTTPS tunnel

Export the selected App's public IDs and the private-key file path in your local shell. Replace the placeholders locally; they are deliberately not usable values:

```powershell
$env:GITHUB_APP_ID = '<your-app-id>'
$env:GITHUB_APP_CLIENT_ID = '<optional-public-client-id>'
$env:GITHUB_APP_PRIVATE_KEY_PATH = '<absolute-path-outside-checkout-to-private-pem>'
$env:GITHUB_WEBHOOK_SECRET = '<same-generated-secret-from-your-password-manager>'
$env:GITHUB_WEBHOOKS_ENABLED = 'true'
```

Omit/remove `GITHUB_APP_CLIENT_ID` if you prefer the numeric App ID as JWT issuer; do not leave a placeholder value. The API needs the App ID and webhook secret but does not read the PEM or contact GitHub in the webhook handler.

```powershell
uv --cache-dir .cache/uv run --locked uvicorn shrike_api.main:create_app --factory --host 127.0.0.1 --port 8001 --no-access-log
```

Separately install `cloudflared` using its [official download instructions](https://developers.cloudflare.com/tunnel/downloads/) and start a development-only Quick Tunnel:

```powershell
cloudflared tunnel --url http://127.0.0.1:8001
```

Copy its generated HTTPS origin into the App webhook URL, appending `/webhooks/github`. Enable webhook delivery and keep TLS verification enabled. This tunnel forwards webhook data through a third party and exposes the local API publicly; use selected test repositories and stop it after testing. Do not enable payload inspection/body logging. Keep protected read APIs denied by default or explicitly scope development bearer access as described in the backend runbook. Quick Tunnel URLs change on restart and have no production availability guarantee. Source: [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).

## 4. Start the ingestion worker and install on a selected test repository

In another shell, export the same database URL and App configuration through your local secret store. Merely copying environment variables in one terminal does not set them in another. Then explicitly permit this worker to make read-only GitHub calls:

```powershell
$env:GITHUB_MODE = 'live'
uv --cache-dir .cache/uv run --locked python -m shrike_worker.ingest --watch
```

For a bounded one-shot drain instead, use `--once` (up to 100 currently due records). Without explicit `GITHUB_MODE=live`, App ID, and key path, the worker refuses startup. No live mode is enabled by tests or application defaults.

Install the App using its **Install App** page and select only your designated test repository. Confirm the installation delivery receives a successful response. The worker verifies the installation belongs to the configured App and reconciles its selected repository inventory before marking local access active. Existing installations can redeliver an installation event through GitHub's App **Advanced / Recent Deliveries** UI when appropriate.

## 5. Perform the optional live smoke test yourself

On that selected test repository, deliberately open a small PR from a branch **inside the same repository**, push an update, then close/reopen it if desired. These are real repository mutations and are operator actions, not actions performed by this implementation task.

Expected behavior:

- Valid new deliveries receive `202` after the receipt transaction commits; exact delivery replays return `200`. A reused delivery ID with different body/event identity returns `409`. Unsupported signed events/actions are durably ignored; their acceptance does not imply a review job was created.
- The worker fetches canonical current metadata, verifies IDs, and creates one `pending` job for the current reviewable base/head/policy identity. Repeated opened/reopened/synchronize events do not duplicate that job. Older queued revisions are canceled when a newer revision is accepted.
- Drafts, closed PRs, archived repositories, cross-repository forks, and deleted fork head repositories do not create review jobs. Canonical current state wins over delayed webhook hints. No analyzer, LLM, review execution, or GitHub comment runs in this phase.
- Removing repository selection immediately quarantines local repository access pending a complete inventory refresh. Suspension/deletion disables installation access and cancels unfinished jobs. An old worker cannot reactivate access after the generation changes.

Safely inspect only operational receipt state if needed:

```powershell
docker compose -p shrike-github --env-file .env.example exec postgres psql -U shrike -d shrike_demo -c 'SELECT delivery_id,event_type,state,reason,attempts FROM webhook_deliveries ORDER BY created_at DESC LIMIT 10;'
```

Protected repository/history reads still require the Phase 2 development token plus explicit server-side `(installation ID, repository ID)` grants; webhook installation alone does not authorize every dashboard user. Real user login remains deferred.

## Limits, failures, and recovery

The API bounds raw input even for chunked bodies (default 1 MiB), requires JSON/identity encoding, validates headers and IDs, and rejects missing/invalid HMAC-SHA256 signatures over exact bytes. See [GitHub signature validation](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries).

The read client accepts only `https://api.github.com`, rejects redirects/external pagination targets, and ignores payload URLs. JSON responses are capped at 2 MiB; inventory is capped at 1,000 repositories. File listings are capped at the configured file count (20 by default), diffs at 512 KiB, and decoded blobs at 200 KiB. Blob size/hash and immutable commit SHA are verified. File/diff reads recheck the PR revision; `head_commit` returns the verified immutable SHA and discards author/message/source fields. Ingestion itself does not fetch file contents.

Connect/read timeouts, response bounds, bounded pagination, and at most three HTTP attempts handle ordinary failures. `Retry-After` and primary reset times become durable retry schedules rather than long sleeps. The inbox permits three processing attempts, ten-minute leases, and one in-flight snapshot per installation. Expired work is reclaimed; old leases cannot finalize newer work. Redis/Celery transport is deferred, so the worker process must be running to create jobs from receipts. Source: [GitHub REST retry guidance](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api).

- `401` on the webhook: check the secret and raw-byte-preserving tunnel; do not disable signature checks.
- `400`/`409`: inspect event/installation/repository identity and payload compatibility without logging the body. Repository ownership cannot be reassigned across installations by a payload.
- `413`: input or client data exceeds a documented limit; do not interpret it as a clean review.
- Pending future `available_at`: respect the GitHub retry time. Restart a stopped worker; do not spin or bypass rate limits.
- Failed authentication: fix the App ID, issuer/key, and permission configuration locally. Tokens/private keys/response bodies are never recorded in receipt errors.
- Exhausted/failed receipts require operator diagnosis and a deliberate scoped retry after correcting the cause. GitHub redelivery of an already recorded delivery ID is deduplicated; it is not an automatic retry reset. Known suspended/deleted installations remain denied until a valid lifecycle/canonical reconciliation permits access; deletion tombstones are never blindly reset.
- Reinstallation with a new installation ID, or repository transfer with existing history, is quarantined by the current ownership constraints. Supporting that lifecycle needs a separate association/history migration. Do not rewrite ownership or drop history merely to make a test pass.

Retention cleanup, a retry administration UI, broker dispatch, production credentials/hosting, and user OAuth remain future phases. Stop the API, worker, and tunnel when finished. To stop the isolated database without deleting its data:

```powershell
docker compose -p shrike-github --env-file .env.example stop postgres
```

Record the App/test repository, delivery/job outcomes, and remaining issues privately after an actual smoke test. Do not claim live compatibility from mocked tests, and never include keys, tokens, raw payloads, or private code in screenshots/reports.
