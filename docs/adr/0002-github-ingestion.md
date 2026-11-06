# ADR 0002: durable GitHub ingestion before analysis

Date: 2026-11-06. Status: accepted implementation scope.

The user defines Phase 3 as secure GitHub App integration and PR ingestion, replacing the earlier static-analysis milestone. Static execution, publishing, OAuth, Redis/Celery transport, and AI remain deferred. Existing Phase 2 persistence and read authorization stay intact.

The API authenticates bounded raw webhook bytes and writes a minimal durable PostgreSQL inbox. It never calls GitHub in the acknowledgement path. A separate polling worker claims receipts with expiring, fenced leases, verifies canonical App/installation/repository/PR identity, and atomically persists metadata plus a uniquely identified pending review job. The inbox is the temporary transport because Redis/Celery is not implemented yet; later dispatch must retain PostgreSQL authority and send record IDs only. No review execution occurs in this phase.

Only explicitly configured live workers may contact GitHub. Tests inject the GitHub port or an HTTP mock transport. App JWTs are RS256 and short-lived; installation tokens are cached in memory, restricted to read permissions and the target repository when possible, and refreshed before expiry. Only fixed GitHub.com API endpoints are supported. No payload URL or pagination link can change the destination host.

Revocation events disable local access immediately and cancel unfinished jobs. Installation access generations fence workers that fetched metadata before a removal/suspension. Deleted installation tombstones are not resurrected by old events; repository transfers with existing ownership are quarantined rather than rewriting history. New installations remain pending until canonical verification. Draft/closed PRs and all cross-repository/deleted-head forks are non-reviewable; fork support requires a separate explicit design.

Delivery IDs deduplicate receipts; base SHA, head SHA, PR identity, and policy digest deduplicate jobs. Canonical current PR state wins over reordered events. Failures carry safe codes and bounded retry schedules, never raw GitHub errors or source. Raw webhook bodies, diffs, tokens, prompts, and private keys are not persisted. The worker can fetch bounded PR files/diffs/commits/blobs through a testable interface, but ingestion itself fetches metadata only.

Manual GitHub registration, installing on selected test repositories, key generation, tunnel setup, and any real smoke test are operator steps. No such account actions or real GitHub calls are performed by this implementation task. Publishing requires a later permission upgrade; this phase requests Metadata: read, Contents: read, and Pull requests: read only.
