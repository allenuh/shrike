# ADR 0007: bounded production-readiness evaluation

Status: accepted for the requested Phase 8 testing scope, 2026-11-07.

The user requested system evaluation as Phase 8. The earlier roadmap used that
number for hosted-provider operations. Rebaseline Phase 8 to deterministic
regression, quality and load measurement; retain hosted operations as Phase 8B.
Retention, backup automation, cloud deployment and live account verification remain
separate work. Passing local tests does not establish production readiness.

Preserve the modular backend, worker and existing ports. Use installed locked
tools: pytest, httpx, real disposable PostgreSQL/Redis, Celery and isolated Ruff.
A bounded Python load harness avoids adding Locust or installing dependencies.
The API harness uses actual loopback HTTP; the queue harness uses real Redis with
two Celery threads. This portable development pool cannot prove Linux prefork
kill semantics or production capacity. A separate spawned-process termination
test proves durable lease recovery without executing repository code.

The labeled synthetic corpus is independent of provider output. Match findings
one-to-one on rule, path and exact new-side line. Wrong lines count as both a
false positive and a missed label. Clean means no labeled issue within the stated
correctness/security scope, not a security certification. Include known misses
and false positives rather than tuning labels to the implementation.

The new machine-readable evaluator is mock-only and creates a cold in-memory
cache for each case. It never initializes a hosted adapter or reads credentials.
Existing hosted evaluation remains separately opted in, cumulatively budgeted
and request-capped; add a persistent admission limit to that operator path.
No live request is authorized or required. Mock model cost is exactly zero;
unpriced infrastructure and hosted cost are unknown, never guessed.

Write generated measurements to ignored `.cache/phase8`, with no source, prompts,
credentials, URLs or machine/user identity. Commit methodology, labeled fixtures,
scripts and manually recorded measured evidence. No persistence migration or
application architecture change is needed.
