# Local API and queue performance

These bounded benchmarks are repeatable local diagnostics, not production sizing
or an Internet load test. [EVALUATION.md](EVALUATION.md) describes CI and quality
measurements. [ADR 0007](adr/0007-system-evaluation.md) explains the scope.

## Reproduce

With installed locked tools and Docker/images available, from the repository root:

```powershell
uv --cache-dir .cache/uv run --locked --offline --no-sync python scripts/benchmark.py --output-dir .cache/phase8/load-001
```

The output directory must be new. Three pytest workloads write JSON and JUnit:
`load-api.json`, `load-queue-rpm-6000.json`, `load-queue-rpm-60.json` and
`load-tests.xml`. Exit nonzero on violated protocol, safety or capacity checks.
Normal backend tests deliberately skip the `benchmark` marker. The full
`scripts/verify.py --frontend --benchmarks` command runs both lanes.

No Locust installation is needed. The bounded Python/httpx thread harness is
sufficient for this small closed-loop workload and uses existing dependencies.
It accepts no target URL, persistent database URL or arbitrary concurrency/job
count. It starts unique tmpfs PostgreSQL/authenticated Redis containers on random
loopback ports; every test migrates a UUID database and drops only that database.
The runner removes its exact owned containers; Redis cleanup deletes only the
random test namespace. No application/scanner container receives a Docker socket.

## Methodology and gates

API: an actual uvicorn server on a random loopback socket, a shared persistent
httpx connection pool, eight client threads, 120 mixed requests (20 per scenario).
The readiness wait and one signed duplicate-setup request are excluded from the
timed interval. A 1,074-byte synthetic event is HMAC-signed. Scenarios are accepted
new delivery (202), exact replay (200), invalid signature (401), signed malformed
JSON (400), authorized history read (200), and unauthorized read (401). Response
body content is not recorded. Expect zero protocol mismatches and accepted-event
p95 < 500 ms, the project's local target. Authentication is scoped development
bearer authentication; no OAuth or GitHub network latency is represented. New
deliveries reference one PR identity; webhook throughput is not unique-review
throughput. Seeded reads use the small synthetic demo database.

Queue: ten canonically ingested jobs, ten independent repositories, one PR/file
per job, 15 source bytes (`value = 10 / 0` plus newline). Actual PostgreSQL outbox,
Redis transport, Celery **threads pool concurrency 2**, repository limit 1,
isolated Ruff containers, fake GitHub and deterministic mock AI. Provider
admission uses the real database clock; scenarios use 6000 RPM (capacity) and
the default 60 RPM (contention). Both use a deliberately shortened **one-second**
retry base instead of production's five seconds; 180-second attempt deadlines,
240-second leases and three lifetime attempts remain unchanged. Outbox redelivery
uses its normal 30-second interval. Dispatch polls every 50 ms with up to 20 sends
per poll. Workloads stop after all terminal states or a 60-second deadline.

End-to-end latency is persisted job creation to terminal finish, including the
small serial ingestion setup, broker startup, wait and retries. Queue-wait latency
is creation to first claim. Attempt duration includes source-port checks,
scanning/analysis and persistence. Throughput divides completed jobs by the
monotonic dispatch-to-terminal polling interval; consumer teardown is excluded.
Percentiles use nearest rank, with all ten terminal jobs in the end-to-end
denominator (including failures); state/error counts prevent misreading failures
as fast success. Peak concurrency comes from persisted attempt intervals.

Capacity requires all ten jobs completed, p95 < 60 seconds, peak running attempts
exactly two and no attempt >= 180 seconds. Both runs require all jobs terminal,
peak <= two and <= three attempts per job. The 60-RPM contention drill records
throttled job exhaustion under this synthetic burst/short backoff; it permits zero
failures when timing improves. Any terminal failure must be `provider_throttled`.
Compare run observations rather than requiring the implementation to fail.

## Measured environment and initial valid run

Executed 2026-11-07 local time (JSON timestamps cross 2026-11-08 UTC), Windows x64,
Python 3.12.6, uv 0.13.7; AMD Ryzen 5 7600X, 6 cores/12 logical processors.
Docker Desktop Linux engine 29.9.2 reported 12 CPUs and 16,285,208,576 bytes of
available VM memory. Images are digest-pinned in `infra/docker` and Ruff's adapter.
Node 26.3.0/npm 11.2.0 and installed Edge are used by the separate frontend checks.
No production host, remote network, paid provider or GitHub account was involved.

Initial valid harness invocation: `scripts/benchmark.py --output-dir
.cache/phase8/load-debug`: **3 passed in 39.88 seconds**. Machine-readable outputs
remain in that ignored directory. The final run is separately recorded in the
roadmap; timing/attempt variation is expected and is not averaged away.

| Workload | Observed result |
| --- | --- |
| 120-request mixed HTTP | First valid harness: 320.00 requests/s, accepted-event p95 47 ms, zero unexpected responses |
| 10 jobs, 6000 RPM | 10 completed, 0 failed; 14 attempts, maximum 3; 13.907 s dispatch window; end-to-end p50 6.969 s / p95 14.071 s; attempt p95 0.793 s; 0.719 completed jobs/s |
| 10 jobs, 60 RPM | 9 completed, 1 failed (`provider_throttled`); 17 attempts, maximum 3; 16.906 s window; end-to-end p50 8.788 s / p95 16.924 s; attempt p95 0.826 s; 0.532 completed jobs/s |

Final invocation via `scripts/verify.py --benchmarks --output-dir
.cache/phase8/final`: **3 passed in 40.23 seconds**:

| Workload | Final measured result |
| --- | --- |
| Mixed HTTP | 120 requests/0 mismatches in 0.281 s; 427.05 requests/s; accepted-event p95 47 ms |
| Queue 6000 RPM | 10 completed/0 failed; peak 2; 13 attempts/max 3; 13.719 s window; end-to-end p50 5.032 s/p95 13.799 s; queue-wait p95 8.284 s; attempt p95 0.726 s; 0.729 completions/s |
| Queue 60 RPM | 9 completed/1 throttled failure; peak 2; 18 attempts/max 3; 17.781 s window; end-to-end p50 8.993 s/p95 17.740 s; queue-wait p95 8.205 s; attempt p95 0.976 s; 0.506 completions/s |

Both final queue runs reached terminal states without timing out. There were
three admission-denied attempts in the capacity run and nine in the contention
run. All attempt durations stayed below the 180-second deadline. Installed
FastAPI/uvicorn/SQLAlchemy/psycopg/Redis/Celery/httpx/Ruff versions are included in
the final JSON environment. These separate runs demonstrate variance; they do
not establish confidence bounds.

The first prototype's 200-ms outbox redelivery interval created excessive duplicate
traffic and both queue checks timed out at 60 seconds. Those failed runs were not
treated as capacity success; the repeatable harness now uses the existing normal
30-second dispatcher interval. The prototype also had four temporary-directory
setup errors because its chosen parent directory did not yet exist; a fresh
owned output directory fixes this. No production retry counters or architecture
were changed. An earlier restricted pytest invocation failed to access an old
cache; final checks use task-owned output/cache directories with engine access.

## Limits and next experiments

Ten tiny jobs and a subsecond HTTP burst are not a steady-state saturation study.
There is no independent arrival rate, sustained soak, percentile confidence
interval, DB/broker CPU sample, memory/leak profile, multi-host worker or TLS
measurement. Warm local pools/images and synthetic no-latency GitHub favor these
numbers; cold image pulls and tool provisioning are deliberately excluded.
One sample cannot establish an SLA. Windows timer granularity/admission collisions
and Docker VM scheduling can affect attempts and timings.

The threads pool cannot enforce Celery prefork process kill limits. The separate
spawned-process crash test proves durable recovery/fencing, not production worker
supervision. Linux prefork smoke, larger realistic diffs/multiple files, shared
repository contention, sustained arrivals, long outages, production OAuth/GitHub
latency and an isolated-runner deployment need explicit follow-up verification.
Worker/global broker heartbeat telemetry remains unavailable in the dashboard.

The default-rate result shows the admission-attempt coupling discussed in
[EVALUATION.md](EVALUATION.md). A separate durable admission-wait design should
precede increasing traffic. Do not increase budget thresholds, disable gates,
reset counters or enable hosted queue retries to chase throughput. Model cost is
zero here; infrastructure dollars and hosted-model latency/cost are unmeasured.
