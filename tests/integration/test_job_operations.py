from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_execution import NoopAnalyzer, due, prepare

from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.execution import SqlExecutionStore
from shrike.adapters.persistence.models import QueueMessage, ReviewExecution, ReviewJob
from shrike.adapters.persistence.operations import DevJobOperations
from shrike.domain.access import ReadScope, RepositoryGrant
from shrike.domain.review import Report, ReviewError
from shrike.domain.states import JobState
from shrike_worker.config import QueueSettings
from shrike_worker.runtime import Runtime

pytestmark = pytest.mark.integration


def operations(database: Database) -> DevJobOperations:
    return DevJobOperations(
        database,
        ReadScope((RepositoryGrant(710001, 810001),)),
        environment="development",
        enabled=True,
    )


def test_scoped_failed_inspection_and_manual_retry_preserve_attempt_history(
    database: Database, queue_settings: QueueSettings
) -> None:
    github, envelope = prepare(database)
    store = SqlExecutionStore(database)
    claim = store.claim(envelope)
    assert claim is not None
    store.fail(claim, "invalid_snapshot")
    ops = operations(database)
    rows = ops.inspect(envelope.record_id)
    assert rows[0]["state"] == "failed" and rows[0]["attempt_count"] == 1
    assert not any(
        key in rows[0] for key in ("result", "path", "private_key", "source", "database_url")
    )
    ops.retry(envelope.record_id)
    with database.session() as session:
        message = session.scalar(select(QueueMessage).where(QueueMessage.kind == "review"))
        assert message is not None and message.generation == 1
        assert session.scalar(select(ReviewExecution.state)) == JobState.FAILED
    assert store.claim(envelope) is None  # Delayed pre-retry broker messages cannot claim again.
    runtime = Runtime(database, github, 12345, queue_settings, analyzer=NoopAnalyzer())
    runtime.consume(due(database, envelope.record_id))
    with database.session() as session:
        job = session.get(ReviewJob, envelope.record_id)
        assert job is not None and job.state == JobState.COMPLETED and job.attempt_count == 2


def test_operations_refuse_ungranted_stale_completed_and_exhausted_jobs(
    database: Database, queue_settings: QueueSettings
) -> None:
    github, envelope = prepare(database)
    denied = DevJobOperations(database, ReadScope(()), environment="development", enabled=True)
    with pytest.raises(ReviewError, match="repository_denied"):
        denied.inspect(envelope.record_id)
    with pytest.raises(ReviewError, match="job_unavailable"):
        operations(database).inspect(uuid4())
    Runtime(database, github, 12345, queue_settings, analyzer=NoopAnalyzer()).consume(envelope)
    with pytest.raises(ReviewError, match="job_not_retryable"):
        operations(database).retry(envelope.record_id)
    with database.session() as session, session.begin():
        job = session.get(ReviewJob, envelope.record_id)
        assert job is not None
        job.state, job.attempt_count = JobState.FAILED, 3
    with pytest.raises(ReviewError, match="job_not_retryable"):
        operations(database).retry(envelope.record_id)


def test_deadline_prevents_late_report_commit(database: Database) -> None:
    _, envelope = prepare(database)
    store = SqlExecutionStore(database)
    claim = store.claim(envelope)
    assert claim is not None
    expired = replace(claim, deadline=datetime.now(UTC) - timedelta(seconds=1))
    with pytest.raises(ReviewError, match="review_deadline"):
        store.checkpoint(expired)
    store.complete(
        expired,
        Report.model_validate(
            {
                "analysis_hash": "a" * 64,
                "status": "completed",
                "summary": "No findings",
                "findings": [],
                "coverage": {"selected_files": 0, "skipped": {}, "changed_lines": 0},
                "provider": "mock",
                "model": "mock-v1",
                "prompt_version": "review-v1",
                "analyzer_version": "fake",
                "input_token_estimate": 0,
                "estimated_cost_usd": "0",
                "latency_ms": 0,
            }
        ),
    )
    with database.session() as session:
        job = session.get(ReviewJob, claim.id)
        assert job is not None and job.state == JobState.CANCELED and not job.publication_eligible


def test_actual_development_cli_inspection_and_retry_need_no_broker(
    database: Database, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import json
    import sys

    from shrike_worker.queue import main

    _, envelope = prepare(database)
    store = SqlExecutionStore(database)
    claim = store.claim(envelope)
    assert claim is not None
    store.fail(claim, "invalid_snapshot")
    monkeypatch.setenv("DATABASE_URL", database.engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DEV_REPOSITORY_GRANTS", "710001:810001")
    monkeypatch.setenv("ENABLE_DEV_JOB_OPERATIONS", "true")
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    monkeypatch.setattr(sys, "argv", ["queue", "inspect", "--job-id", str(claim.id)])
    main()
    assert json.loads(capsys.readouterr().out)[0]["state"] == "failed"
    monkeypatch.setattr(sys, "argv", ["queue", "retry", "--job-id", str(claim.id)])
    main()
    assert json.loads(capsys.readouterr().out)["event"] == "job_retry_scheduled"
    with database.session() as session:
        job = session.get(ReviewJob, claim.id)
        assert job is not None and job.state == JobState.PENDING and job.attempt_count == 1
