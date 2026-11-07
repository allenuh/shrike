# Shrike dashboard: local demo and authenticated integration

Phase 7 adds the Next.js dashboard and GitHub App user sessions under
[ADR 0006](../adr/0006-saas-dashboard.md). It preserves the modular API/worker,
mock-only automatic analysis, independent publication and existing cost ledger.
No cloud hosting, real GitHub login, paid AI call or production rollout is claimed.

## Read-only seeded demo

Use Node.js 22.12+ (Node 26.3.0/npm 11.2.0 were tested), Python 3.12 for backend
checks, and Docker Desktop/Linux containers for disposable integration tests.
The user explicitly authorized installation of the pinned dashboard/test packages
with lifecycle scripts disabled after the project's general installation rule
blocked it. This exception never permits installing analyzed PR dependencies.

From the repository root:

```powershell
Set-Location apps/web
npm ci --ignore-scripts --cache ../../.cache/npm
$env:NEXT_TELEMETRY_DISABLED = '1'
$env:SHRIKE_WEB_MODE = 'demo'
npm run dev
```

Open [the local dashboard](http://127.0.0.1:3000). Demo is the default and requires
no database, GitHub App, bearer token or provider key. Three synthetic repositories,
18 reviews and deterministic finding excerpts are seeded in server-only demo code.
The fixed snapshot is 2026-11-07 15:00 UTC, so screenshots and metrics are repeatable.
All pages label demo data; no source or credentials are imported from user accounts.
Demo write routes are refused except a harmless no-session logout response. Settings
save only table density to localStorage; review policy and integrations are read-only.

Pages: overview `/`, installed repositories `/repositories`, filterable review list
`/reviews`, file-grouped detail `/reviews/{uuid}`, `/settings`, and `/status`.
`/login` starts a real OAuth flow only when live mode is explicitly configured;
in demo mode Continue returns to the synthetic workspace without contacting GitHub.

Filters and cursors are URL-backed. Repository pages and review/finding lists use
bounded pagination; changing filters clears the cursor. First page returns to the
beginning; Next advances with an opaque server cursor. The review repository selector
lists its first 100 accessible entries; use a repository card to filter any later
repository. Source snippets are bounded stored evidence, not complete source files;
legacy findings without retained evidence explicitly say it is unavailable.

## Frontend checks

From `apps/web`, with the lockfile installed and telemetry disabled:

```powershell
npm run lint
npm run format:check
npm run typecheck
npm run test
npm run build
npm run test:e2e
```

`npm run test` uses Vitest, Testing Library and synthetic mocked fetch responses.
The Playwright suite starts a production Next server on loopback port 3100 with
demo mode, navigates reviews to finding detail, filters/pages results, checks mobile
layout/navigation, persists display preferences, inspects repository/status pages,
and proves demo endpoints reject mutations. It runs desktop 1440×1000 and mobile
390×844 projects. Windows defaults to an installed Microsoft Edge; other platforms
use Playwright Chromium. Set `PLAYWRIGHT_CHANNEL` only to an installed supported
channel; on a new non-Windows machine install the matching test browser deliberately
with `npx --no-install playwright install chromium`. Do not download browsers during
ordinary test execution. Screenshots/traces stay in ignored test-output directories.
Stop an independently running server on 3100 before tests; reuse is intentionally off.

ESLint 9.39.5 matches the peer requirements of the pinned Next React/import/a11y
plugins. The registry marks ESLint 9 deprecated; ESLint 10 was tested during setup
but rejected by those plugin peers. Keep the compatible lockfile rather than forcing
invalid peers; revisit the toolchain together in a future dependency update.

From the repository root, backend checks use existing locked tooling:

```powershell
uv --cache-dir .cache/uv run --locked --offline --no-sync ruff check .
uv --cache-dir .cache/uv run --locked --offline --no-sync ruff format --check .
uv --cache-dir .cache/uv run --locked --offline --no-sync mypy
uv --cache-dir .cache/uv run --locked --offline --no-sync python scripts/test_backend.py -q
```

The runner creates only uniquely named disposable PostgreSQL/Redis containers and
test databases. It tests migration upgrade/downgrade/upgrade and metadata agreement,
mocked OAuth/token exchange, session encryption/expiry/logout/replay, two-user
resource isolation, revocation, scoped aggregates, pagination and evidence access.
It never edits an existing user database or makes a real GitHub/model request.

## Authenticated live configuration (manual, unperformed)

Use the separate integration database/App in [github-app-manual.md](github-app-manual.md)
and the [async runbook](async-processing.md). Ingest the App's selected repository
inventory before expecting dashboard data. Keep OAuth client secrets, PEMs and
provider keys outside Git; never use `NEXT_PUBLIC_*` for backend configuration.

1. In the existing GitHub App's **User authorization callback URL**, register exactly
   `https://<dashboard-origin>/api/backend/auth/github/callback`. For local-only
   testing GitHub may allow an explicitly registered loopback HTTP callback; this
   application permits it only with `APP_ENV=development` or `test`. No wildcard,
   return-to URL, request Host header or frontend-selected callback is trusted.
2. Generate an App OAuth **client secret** from the App settings. This is different
   from the installation PEM and webhook secret. The backend uses the App's public
   client ID and this secret for one PKCE-protected authorization-code exchange.
   Keep the current Metadata read/Pull requests read/Contents read permissions;
   publication's separate optional write upgrade is not required for dashboard reads.
3. Back up the integration database deliberately, stop older processing, and apply
   `uv --cache-dir .cache/uv run --locked alembic upgrade head`, followed by
   `uv --cache-dir .cache/uv run --locked alembic check`. Readiness now requires
   `0007_dashboard`. The migration adds `oauth_states` and `dashboard_sessions`
   without altering reports, findings, publication identities or AI accounting.
   Downgrading ends dashboard session support; never test destructive migrations
   against this persistent integration database.
4. Export the following only in the backend process environment. Example values are
   placeholders, not credentials; the application deliberately does not load `.env`.

```powershell
$env:APP_ENV = 'development'
$env:ENABLE_DEV_AUTH = 'false'
$env:GITHUB_USER_AUTH_ENABLED = 'true'
$env:DASHBOARD_ORIGIN = 'http://127.0.0.1:3000'
$env:GITHUB_APP_ID = '<public-app-id>'
$env:GITHUB_APP_CLIENT_ID = '<public-app-client-id>'
$env:GITHUB_OAUTH_CLIENT_SECRET = '<retrieve-from-local-secret-store>'
$env:DASHBOARD_TOKEN_KEY = '<retrieve-persistent-generated-Fernet-key-from-secret-store>'
uv --cache-dir .cache/uv run --locked uvicorn shrike_api.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

Generate the Fernet key once into an approved secret store using the installed
cryptography library; never paste it into chat or logs. Preserve it across restarts.
Losing/changing it makes existing sessions unverifiable and requires reauthorization;
it is never permission to reset review identities or the spending ledger. Deployments
must share this key and PostgreSQL session store. Automated credential rotation and
expired-session retention cleanup remain future hardening work.

5. In the frontend shell (these are server-only runtime settings):

```powershell
Set-Location apps/web
$env:NEXT_TELEMETRY_DISABLED = '1'
$env:SHRIKE_WEB_MODE = 'live'
$env:SHRIKE_API_ORIGIN = 'http://127.0.0.1:8000'
$env:SHRIKE_WEB_ORIGIN = 'http://127.0.0.1:3000'
npm run build
npm run start
```

Use exactly the same web origin in both processes, including scheme/host/port.
Production requires a fixed HTTPS dashboard origin, secure cookies and TLS between
non-loopback services. The Next proxy only accepts a configured HTTPS backend or
loopback HTTP backend, fixed allowlisted read/auth paths, and same-origin logout.
It does not forward browser Authorization headers or arbitrary cookies. No browser
CORS bypass or public backend credential is needed. Configure external reverse
proxies to avoid logging OAuth query strings, cookies, credentials or API response
bodies. Next request logging is disabled and FastAPI access logs must remain off.

## Manual live end-to-end validation (unperformed)

Sign in through `/login` using a deliberately selected test account. GitHub is the
only authorization destination. OAuth state must return to the exact registered
callback in the same browser within five minutes. State is consumed once; a missing
cookie, mismatch, expiry or replay returns a generic failure and starts no session.

Verify that the account sees only repositories accessible to both it and this App.
Inspect overview totals, filter reviews, page findings, open a detail and follow a
source link to the immutable reviewed SHA. Do not screenshot private source. Sign
out; back/reload must not restore authenticated access. Repeat with a second account
having different repository membership; guessed resource UUIDs must return 404.
Remove repository access or suspend the App and confirm the next request loses
access. A GitHub outage must show retry/error state, never demo or stale authorization.

Cookies contain random opaque values only: session and OAuth-state cookies are
HttpOnly, SameSite=Lax, Path=/, without Domain; HTTPS uses `__Host-` names and Secure.
PostgreSQL stores session/state hashes, encrypted PKCE verifiers and encrypted user
access tokens. Sessions expire within one hour or provider expiry, whichever is
earlier. Refresh tokens are discarded; an expired credential requires a new sign-in.
Logout is a same-origin POST that removes the stored credential and clears the cookie.
It revokes the local session, not the user's entire GitHub App authorization.
Every live read checks current user identity/membership at GitHub with bounded,
complete pagination and intersects paired installation/repository IDs with active
local ownership. No membership cache delays observed revocation. API errors fail
closed, so GitHub unavailability temporarily blocks dashboard reads.

## Metrics and operational limits

Overview uses the selected creation window (7/30/90 days in the UI, up to 90 via
API). Findings are stored findings on those authorized jobs. Success is
`completed / (completed + failed)`; failure uses the same denominator. Pending,
running and canceled jobs are excluded from rates. Average processing time is
`finished_at - started_at` over completed jobs only, excluding queue wait. Empty
denominators/averages are null and shown as a dash. Daily activity counts job creation
dates in UTC; the chart shows up to the last 14 days of the selected window.

System status reads only authorized job leases and review outbox/publication rows.
Pending age is creation age, not Redis latency. Active leases are not worker
heartbeats; missing/expired running leases indicate recovery may be needed. Redis
reachability and process heartbeats are explicitly unavailable. The page cannot
retry jobs, publish feedback, mutate code or change provider/spending controls.
Full operations/retention/backup drills and production SaaS hardening remain Phase
7B; this phase does not claim a production multi-tenant service or live compatibility.

## Official authentication references

Checked 2026-11-07: [GitHub App user authorization and PKCE](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app), [user installation/repository membership](https://docs.github.com/en/rest/apps/installations), and [Next request logging controls](https://nextjs.org/docs/app/api-reference/config/next-config-js/logging). No authenticated request was made to validate these documents.
