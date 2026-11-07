import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fakes import ReviewGitHub, github_fixture
from sqlalchemy import func, select

from shrike.adapters.github.webhooks import parse_webhook
from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.execution import SqlExecutionStore, SqlProviderAdmission
from shrike.adapters.persistence.ingestion import SqlIngestionStore, accept_delivery
from shrike.adapters.persistence.models import (
    Installation,
    ProviderWindow,
    QueueMessage,
    ReviewExecution,
    ReviewFinding,
    ReviewJob,
)
from shrike.application.ingestion import process_one
from shrike.domain.github import GitHubError
from shrike.domain.queue import Envelope
from shrike.domain.review import Candidate, ReviewError, SelectedFile
from shrike.domain.states import InstallationStatus, JobState
from shrike_worker.config import QueueSettings
from shrike_worker.runtime import Runtime

pytestmark = pytest.mark.integration


class NoopAnalyzer:
    version = "fake-static-v1"

    def analyze(self, file: SelectedFile) -> tuple[Candidate, ...]:
        return ()


def prepare(
    database: Database, github: ReviewGitHub | None = None
) -> tuple[ReviewGitHub, Envelope]:
    github = github or ReviewGitHub()
    raw = json.dumps(github_fixture("pull_request_opened.json")).encode()
    with database.session() as session, session.begin():
        accept_delivery(
            session,
            str(uuid4()),
            hashlib.sha256(raw).hexdigest(),
            parse_webhook("pull_request", raw, 12345),
        )
    assert process_one(SqlIngestionStore(database), github, 12345)
    with database.session() as session:
        row = session.scalar(select(QueueMessage).where(QueueMessage.kind == "review"))
        assert row is not None
        return github, Envelope(kind="review", record_id=row.record_id, generation=row.generation)


def due(database: Database, job_id: Any) -> Envelope:
    with database.session() as session, session.begin():
        job = session.get(ReviewJob, job_id)
        assert job is not None
        job.available_at = datetime.now(UTC) - timedelta(seconds=1)
        row = session.scalar(
            select(QueueMessage).where(
                QueueMessage.kind == "review", QueueMessage.record_id == job_id
            )
        )
        assert row is not None
        row.available_at = job.available_at
        return Envelope(kind="review", record_id=job_id, generation=row.generation)


def test_review_result_and_duplicate_claims(
    database: Database, queue_settings: QueueSettings
) -> None:
    github, envelope = prepare(database)
    runtime = Runtime(database, github, 12345, queue_settings, analyzer=NoopAnalyzer())
    runtime.consume(envelope)
    runtime.consume(envelope)
    with database.session() as session:
        job = session.get(ReviewJob, envelope.record_id)
        assert job is not None and job.state == JobState.COMPLETED and job.attempt_count == 1
        assert (
            job.first_started_at is not None
            and job.started_at is not None
            and job.finished_at is not None
        )
        assert job.result is not None and len(job.result["findings"]) == 1
        assert session.scalar(select(func.count()).select_from(ReviewFinding)) == 1
        execution = session.scalar(select(ReviewExecution))
        assert (
            execution is not None and execution.provider == "mock" and not execution.usage_reported
        )
        assert execution.input_tokens == 0 and execution.output_tokens == 0
    assert runtime.executions.publication_candidate(envelope.record_id)


def test_same_job_concurrent_consumers_one_winner(database: Database) -> None:
    _, envelope = prepare(database)
    store = SqlExecutionStore(database)
    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(lambda _: store.claim(envelope), range(2)))
    assert sum(claim is not None for claim in claims) == 1


def test_repository_limit_blocks_other_work_in_the_same_repository(database: Database) -> None:
    _, envelope = prepare(database)
    with database.session() as session, session.begin():
        original = session.get(ReviewJob, envelope.record_id)
        assert original is not None
        other = ReviewJob(
            installation_id=original.installation_id,
            repository_id=original.repository_id,
            pull_request_id=original.pull_request_id,
            base_sha=original.base_sha,
            head_sha=original.head_sha,
            policy_digest="e" * 64,
        )
        session.add(other)
        session.flush()
        from shrike.adapters.persistence.dispatch import enqueue

        enqueue(session, "review", other.id)
        second = Envelope(kind="review", record_id=other.id, generation=0)
    store = SqlExecutionStore(database, repository_limit=1)
    assert store.claim(envelope) is not None
    assert store.claim(second) is None


def test_transient_retries_bounded_and_exponential(
    database: Database, queue_settings: QueueSettings
) -> None:
    github, envelope = prepare(database)
    github.error = GitHubError("github_transient", retry_at=datetime.now(UTC))
    runtime = Runtime(database, github, 12345, queue_settings, analyzer=NoopAnalyzer())
    delays = []
    for attempt in range(1, 4):
        runtime.consume(envelope)
        with database.session() as session:
            job = session.get(ReviewJob, envelope.record_id)
            assert job is not None and job.attempt_count == attempt
            if attempt < 3:
                assert job.state == JobState.PENDING and job.started_at is None
                delays.append((job.available_at - datetime.now(UTC)).total_seconds())
            else:
                assert job.state == JobState.FAILED and job.error_code == "github_transient"
        envelope = due(database, envelope.record_id)
    assert delays[1] > delays[0] > 3
    runtime.consume(envelope)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ReviewExecution)) == 3


def test_permanent_validation_not_retried(
    database: Database, queue_settings: QueueSettings
) -> None:
    github, envelope = prepare(database)
    github.source = b"not-matching-snapshot\n+extra-line\n"
    Runtime(database, github, 12345, queue_settings, analyzer=NoopAnalyzer()).consume(envelope)
    with database.session() as session:
        job = session.get(ReviewJob, envelope.record_id)
        assert job is not None and job.state == JobState.FAILED and job.attempt_count == 1
        assert not job.publication_eligible and job.result is None


def test_canonical_head_change_after_analysis_discards_findings(
    database: Database, queue_settings: QueueSettings
) -> None:
    github, envelope = prepare(database)

    class UpdatingAnalyzer(NoopAnalyzer):
        def analyze(self, file: SelectedFile) -> tuple[Candidate, ...]:
            github.pr_data = replace(github.pr_data, head_sha="d" * 40)
            return ()

    runtime = Runtime(database, github, 12345, queue_settings, analyzer=UpdatingAnalyzer())
    runtime.consume(envelope)
    with database.session() as session:
        job = session.get(ReviewJob, envelope.record_id)
        assert job is not None and job.state == JobState.CANCELED and job.result is None
        assert session.scalar(select(func.count()).select_from(ReviewFinding)) == 0
    assert not runtime.executions.publication_candidate(envelope.record_id)


def test_revocation_during_snapshot_prevents_analysis(
    database: Database, queue_settings: QueueSettings
) -> None:
    github, envelope = prepare(database)

    def revoke() -> None:
        with database.session() as session, session.begin():
            installation = session.scalar(select(Installation))
            assert installation is not None
            installation.status = InstallationStatus.SUSPENDED
            installation.access_generation += 1

    github.on_blob = revoke
    runtime = Runtime(database, github, 12345, queue_settings, analyzer=NoopAnalyzer())
    runtime.consume(envelope)
    assert not runtime.executions.publication_candidate(envelope.record_id)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ReviewFinding)) == 0


def test_expired_worker_recovery_fences_old_owner(
    database: Database, queue_settings: QueueSettings
) -> None:
    github, envelope = prepare(database)
    store = SqlExecutionStore(database)
    abandoned = store.claim(envelope)
    assert abandoned is not None
    with database.session() as session, session.begin():
        job = session.get(ReviewJob, abandoned.id)
        assert job is not None
        job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert SqlExecutionStore(database).recover() == 1
    with pytest.raises(ReviewError, match="stale_execution"):
        store.checkpoint(abandoned)
    next_envelope = due(database, abandoned.id)
    runtime = Runtime(database, github, 12345, queue_settings, analyzer=NoopAnalyzer())
    runtime.consume(next_envelope)
    store.fail(abandoned, "late_failure", transient=True)
    with database.session() as session:
        job = session.get(ReviewJob, abandoned.id)
        assert job is not None and job.state == JobState.COMPLETED and job.attempt_count == 2
        executions = list(
            session.scalars(select(ReviewExecution).order_by(ReviewExecution.attempt))
        )
        assert [row.state for row in executions] == [JobState.FAILED, JobState.COMPLETED]


def test_provider_rate_is_shared_across_instances(database: Database) -> None:
    admission = SqlProviderAdmission(database, "mock:mock-v1", 1)
    admission.acquire()
    with pytest.raises(ReviewError, match="provider_throttled") as error:
        SqlProviderAdmission(database, "mock:mock-v1", 1).acquire()
    assert error.value.retry_at is not None
    with database.session() as session:
        row = session.get(ProviderWindow, "mock:mock-v1")
        assert row is not None and row.next_at > datetime.now(UTC) + timedelta(seconds=55)


def test_provider_throttle_schedules_retry_at_shared_window(
    database: Database, queue_settings: QueueSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    github, envelope = prepare(database)
    SqlProviderAdmission(database, "mock:mock-v1", 1).acquire()

    def forbidden(*args: object) -> None:
        pytest.fail("Throttled review must not invoke its model")

    monkeypatch.setattr("shrike.adapters.llm.mock.MockProvider.review", forbidden)
    Runtime(database, github, 12345, queue_settings, analyzer=NoopAnalyzer()).consume(envelope)
    with database.session() as session:
        job = session.get(ReviewJob, envelope.record_id)
        window = session.get(ProviderWindow, "mock:mock-v1")
        assert job is not None and window is not None and job.state == JobState.PENDING
        assert job.error_code == "provider_throttled" and job.available_at >= window.next_at
        assert job.attempt_count == 1 and not job.publication_eligible


def test_completed_old_head_becomes_ineligible_after_new_ingestion(
    database: Database, queue_settings: QueueSettings
) -> None:
    github, envelope = prepare(database)
    runtime = Runtime(database, github, 12345, queue_settings, analyzer=NoopAnalyzer())
    runtime.consume(envelope)
    assert runtime.executions.publication_candidate(envelope.record_id)
    github.pr_data = replace(github.pr_data, head_sha="d" * 40)
    raw = json.dumps(github_fixture("pull_request_opened.json")).encode()
    with database.session() as session, session.begin():
        accept_delivery(
            session,
            str(uuid4()),
            hashlib.sha256(raw).hexdigest(),
            parse_webhook("pull_request", raw, 12345),
        )
    assert process_one(SqlIngestionStore(database), github, 12345)
    assert not runtime.executions.publication_candidate(envelope.record_id)
    with database.session() as session:
        old = session.get(ReviewJob, envelope.record_id)
        assert old is not None and old.state == JobState.COMPLETED and not old.publication_eligible
        assert session.scalar(select(func.count()).select_from(ReviewJob)) == 2
