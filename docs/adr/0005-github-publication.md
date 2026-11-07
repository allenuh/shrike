# ADR 0005: Phase 6 advisory GitHub publication

Date: 2026-11-07. Status: accepted under the user's Phase 6 publication request.

Phase 6 now means publication (previously planned as 5B); dashboard work moves to
6B. Use the canonical Shrike name; RepoPilot in the request refers to the same
analysis pipeline, not a second product or a runtime rename.

Publication is an independent operator-invoked use case over completed persisted
reports. Analysis workers never publish or request write credentials. Default
report-only operation uses PostgreSQL only. Writes require both a process setting
and an explicit CLI flag, plus paired installation/repository grants. No new
public mutation endpoint, broker task, hosted AI, dashboard, or cloud service is
introduced. This trades automatic feedback for deliberate, reviewable opt-in.

One PostgreSQL publication row per existing immutable job identity persists a
bounded payload/digest, lease, attempt count, state, safe reason and external IDs.
Preparation has a bounded lease; the committed write intent is never reclaimed
as unsent. At most three explicit definite-rejection attempts are allowed, with
server retry hints. A timeout/crash/5xx/invalid success response is uncertain.
Reconciliation reads complete bounded pages and matches the authenticated App's
bot, hidden identity marker and commit. An absent match never authorizes retrying
an ambiguous write. A confirmed review with missing comment IDs is partial and
can be read again without posting. No automatic edits/deletions hide history.

Only medium-or-higher correctness/security/reliability findings with confidence
at least 0.85 and validated evidence are published; maintainability and minor
findings remain internal. Cap total published findings at ten. Fresh complete
diff additions map to new-side line coordinates; deletions, context, unavailable
or ambiguous mappings become summary findings. A definite 422 permits a later
explicit summary-only attempt after reconciliation, rather than guessing positions.
Escape untrusted prose and omit raw evidence/source/diffs from outbound payloads.

Revalidate local ownership/access generation and canonical GitHub installation,
repository and PR identities before every operation and immediately before the
single advisory COMMENT write. Attach the exact head SHA and check afterward;
GitHub offers no atomic compare-and-publish. A detected late write is stored as
stale with its IDs. Never approve, request changes, merge, or modify code.

Reuse the App client with isolated repo-scoped write-token caching. Publication
tokens request Metadata read and Pull requests write only; analysis tokens retain
Contents read and Pull requests read. Migration 0006 adds a table, preserves
existing jobs, and updates readiness. No identity backfill or real-data edits are
needed. Publication rows must survive content retention as identity tombstones;
retention automation remains deferred. Downgrade removes publication history and
must never be used as a retry mechanism.
