# ADR 0006: Phase 7 authenticated Shrike dashboard

Date: 2026-11-07. Status: accepted under the requested Phase 7 dashboard scope.

The user moves the previously deferred 6B dashboard to Phase 7. The old Phase 7
hardening work becomes 7B and remains unrequested. Keep the FastAPI modular backend,
worker, PostgreSQL, mock AI and independent publication boundaries. There is no
existing frontend to preserve; add Next.js/TypeScript/Tailwind in `apps/web` with
pinned npm dependencies and a lockfile. No hosted Site/cloud service is introduced.

Use a restrained engineering workspace: dark navigation, warm neutral canvas,
compact tables, semantic state badges and a muted green accent. Six read-oriented
pages share navigation, filters, pagination, empty/error/loading states and a
typed validated API contract. React text rendering protects findings; source
snippets use only already-persisted bounded finding evidence, never a new source
fetch. GitHub links are constructed from authorized repository identities and SHAs.

Next.js is a same-origin backend-for-frontend, proxying only allowlisted dashboard
and authentication routes to a fixed server-configured backend. Cookies are opaque;
GitHub/provider credentials never enter browser responses or NEXT_PUBLIC settings.
The default read-only demo serves synthetic seeded fixtures locally and never
contacts the backend; live mode is explicit and never falls back to demo data.

FastAPI owns GitHub App OAuth with S256 PKCE, expiring single-use database state
bound to an HttpOnly browser cookie, fixed callback/origin allowlists, opaque
server-managed sessions and encrypted access tokens. Sessions expire within one
hour (or the provider expiry, if sooner). Discard refresh tokens and require login
again instead of adding a refresh-token rotation subsystem in this phase. Validate
GitHub user identity and paired installation/repository membership on every live
request, with no authorization cache. Intersect these grants with active local
ownership/access predicates for lists, individual resources, snippets and metrics.
Logout requires same-origin POST and clears the encrypted credential; reads have
no mutation effects. Existing opt-in development bearer authentication remains
development/test-only and cannot bypass cookie sessions in production.

Migration 0007 adds only OAuth-state/session tables. Readiness advances; existing
review/accounting data is unchanged. Metrics aggregate authorized jobs before
computing totals: selected 7/30/90-day creation window, completed/(completed+failed)
success rate, failed/(completed+failed) failure rate, and mean completed processing
duration. Canceled/pending/running jobs are excluded from those denominators.
Queue/worker views disclose only repository-scoped outbox/lease evidence; heartbeat,
Redis reachability and global infrastructure telemetry stay explicitly unavailable.

Settings expose the fixed analysis/publication policy and integration status plus
local display preferences. They cannot enable publishing, AI spend, reruns or
change operational policy. Dependency installation concerns trusted Shrike frontend
tooling only, with lifecycle scripts disabled; fetched PR code/dependencies remain
untrusted and are never installed or executed. Automated verification uses seeded
fixtures, mocked GitHub OAuth/API, ephemeral PostgreSQL and browser/component tests;
no live App authorization, private code egress or model request is authorized.

The automatic approval reviewer initially rejected `npm install` under the literal
AGENTS.md dependency-installation prohibition. The user then explicitly authorized
an exception for the pinned Shrike frontend/test packages with lifecycle scripts
disabled. That exception applies to this dashboard tooling, not analyzed PRs.
