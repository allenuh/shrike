"""Synthetic development data only. Never runs on API startup or through an HTTP endpoint."""

from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shrike.domain.states import FindingSource, JobState, Severity

from .models import Installation, PullRequest, Repository, ReviewExecution, ReviewFinding, ReviewJob

DEMO_INSTALLATION_GITHUB_ID = 710001
DEMO_REPOSITORY_GITHUB_ID = 810001
DEMO_TIME = datetime(2026, 1, 1, 12, tzinfo=UTC)


def demo_id(key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"shrike-synthetic-demo:{key}")


def seed_demo(session: Session) -> bool:
    """Seed an empty database in the caller's transaction; repeated seed is a no-op."""
    tables = (Installation, Repository, PullRequest, ReviewJob, ReviewFinding, ReviewExecution)
    counts = tuple(session.scalar(select(func.count()).select_from(table)) for table in tables)
    if any(counts):
        if (
            counts == (2, 3, 3, 6, 3, 4)
            and session.get(ReviewJob, demo_id("completed")) is not None
        ):
            return False
        raise ValueError("Demo seed requires an empty database or the unchanged demo dataset")
    primary = Installation(
        id=demo_id("installation"),
        github_id=DEMO_INSTALLATION_GITHUB_ID,
        account_github_id=610001,
        account_type="Organization",
        created_at=DEMO_TIME,
    )
    other = Installation(
        id=demo_id("other-installation"),
        github_id=710002,
        account_github_id=610002,
        account_type="Organization",
        created_at=DEMO_TIME,
    )
    session.add_all([primary, other])
    session.flush()
    repositories = [
        Repository(
            id=demo_id("repository"),
            installation_id=primary.id,
            github_id=DEMO_REPOSITORY_GITHUB_ID,
            owner="shrike-demo",
            name="payments-api",
            created_at=DEMO_TIME,
        ),
        Repository(
            id=demo_id("sibling-repository"),
            installation_id=primary.id,
            github_id=810002,
            owner="shrike-demo",
            name="developer-cli",
            private=False,
            created_at=DEMO_TIME,
        ),
        Repository(
            id=demo_id("other-repository"),
            installation_id=other.id,
            github_id=810003,
            owner="other-demo",
            name="private-service",
            created_at=DEMO_TIME,
        ),
    ]
    session.add_all(repositories)
    session.flush()
    prs = [
        PullRequest(
            id=demo_id(f"pr-{index}"),
            repository_id=repo.id,
            github_id=910001 + index,
            number=42 + index,
            base_sha="a" * 40,
            head_sha="b" * 40,
            created_at=DEMO_TIME,
        )
        for index, repo in enumerate(repositories)
    ]
    session.add_all(prs)
    session.flush()
    states = [
        ("completed", JobState.COMPLETED, 0),
        ("pending", JobState.PENDING, 0),
        ("running", JobState.RUNNING, 0),
        ("failed", JobState.FAILED, 0),
        ("canceled", JobState.CANCELED, 1),
        ("other-job", JobState.COMPLETED, 2),
    ]
    jobs = []
    for index, (key, state, repo_index) in enumerate(states):
        created = DEMO_TIME + timedelta(hours=index)
        started = (
            created + timedelta(seconds=2)
            if state not in {JobState.PENDING, JobState.CANCELED}
            else None
        )
        finished = (
            created + timedelta(seconds=12)
            if state in {JobState.COMPLETED, JobState.FAILED, JobState.CANCELED}
            else None
        )
        job = ReviewJob(
            id=demo_id(key),
            installation_id=repositories[repo_index].installation_id,
            repository_id=repositories[repo_index].id,
            pull_request_id=prs[repo_index].id,
            base_sha="a" * 40,
            head_sha=f"{index + 1:040x}",
            policy_digest="d" * 64,
            state=state,
            created_at=created,
            started_at=started,
            finished_at=finished,
            attempt_count=1 if started else 0,
            first_started_at=started,
        )
        jobs.append(job)
    session.add_all(jobs)
    session.flush()
    for index, job in enumerate(jobs):
        if job.started_at:
            session.add(
                ReviewExecution(
                    id=demo_id(f"execution-{index}"),
                    job_id=job.id,
                    attempt=1,
                    state=job.state,
                    created_at=job.started_at,
                    started_at=job.started_at,
                    finished_at=job.finished_at,
                    duration_ms=10000 if job.finished_at else 0,
                    input_tokens=0,
                    output_tokens=0,
                    analyzer_version="demo-static-v1",
                    ruleset_version="demo-rules-v1",
                    provider="mock",
                    model="mock-v1",
                    prompt_version="demo-prompt-v1",
                    error_code="analyzer_timeout" if job.state == JobState.FAILED else None,
                    worker_identifier="internal-demo-worker-not-public",
                )
            )
    for index, (source, severity, rule, path, line, message) in enumerate(
        [
            (
                FindingSource.RUFF,
                Severity.LOW,
                "F401",
                "src/payments.py",
                3,
                "Remove the unused import to keep dependencies clear",
            ),
            (
                FindingSource.SEMGREP,
                Severity.HIGH,
                "demo.parameterized-query",
                "src/storage.py",
                18,
                "Use bound parameters for this synthetic query example",
            ),
            (
                FindingSource.LLM,
                Severity.MEDIUM,
                "demo.mock-review",
                "src/payments.py",
                31,
                "Synthetic mock suggestion: validate the amount before processing",
            ),
        ]
    ):
        session.add(
            ReviewFinding(
                id=demo_id(f"finding-{index}"),
                job_id=jobs[0].id,
                fingerprint=f"{index + 1:064x}",
                source=source,
                severity=severity,
                rule_id=rule,
                path=path,
                line_start=line,
                line_end=line,
                message=message,
                created_at=DEMO_TIME,
            )
        )
    session.flush()
    return True
