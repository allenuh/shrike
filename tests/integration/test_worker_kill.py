"""Kill only an owned spawned claimant; never execute fetched code or share live data."""

import hashlib
import json
import multiprocessing
import time
from multiprocessing.connection import Connection
from uuid import uuid4

import pytest
from fakes import ReviewGitHub, github_fixture
from sqlalchemy import select

from shrike.adapters.github.webhooks import parse_webhook
from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.execution import SqlExecutionStore
from shrike.adapters.persistence.ingestion import SqlIngestionStore, accept_delivery
from shrike.adapters.persistence.models import QueueMessage, ReviewExecution, ReviewJob
from shrike.application.ingestion import process_one
from shrike.domain.queue import Envelope, ReviewClaim
from shrike.domain.review import ReviewError
from shrike.domain.states import JobState
from shrike_worker.config import QueueSettings
from shrike_worker.runtime import Runtime

pytestmark = pytest.mark.integration


def claim_and_block(url: str, envelope: Envelope, pipe: Connection) -> None:
    db = Database(url)
    try:
        # Short test lease, no heartbeat. No changes to production configuration or counters.
        claim = SqlExecutionStore(db, lease_seconds=1, deadline_seconds=0.5).claim(envelope)
        pipe.send(claim)
        pipe.recv()
    finally:
        pipe.close()
        db.dispose()


def test_killed_process_preserves_attempt_and_fences_late_writes(
    database: Database, queue_settings: QueueSettings
) -> None:
    github = ReviewGitHub()
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
        envelope = Envelope(kind="review", record_id=row.record_id, generation=row.generation)
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(
        target=claim_and_block,
        args=(database.engine.url.render_as_string(hide_password=False), envelope, child),
    )
    process.start()
    child.close()
    try:
        assert parent.poll(15), "Spawned claimant did not signal before test deadline"
        claim = parent.recv()
        assert isinstance(claim, ReviewClaim)
        process.terminate()
        process.join(timeout=10)
        assert not process.is_alive() and process.exitcode != 0
        store = SqlExecutionStore(database, retry_base_seconds=0.05)
        deadline = time.monotonic() + 10
        while not store.recover():
            assert time.monotonic() < deadline
            time.sleep(0.05)
        with pytest.raises(ReviewError):
            store.checkpoint(claim)
        while True:
            with database.session() as session:
                row = session.scalar(select(QueueMessage).where(QueueMessage.kind == "review"))
                assert row is not None
                retry = Envelope(kind="review", record_id=row.record_id, generation=row.generation)
            Runtime(database, github, 12345, queue_settings).consume(retry)
            with database.session() as session:
                job = session.get(ReviewJob, envelope.record_id)
                assert job is not None
                if job.state == JobState.COMPLETED:
                    assert job.attempt_count == 2
                    break
            assert time.monotonic() < deadline
            time.sleep(0.05)
        with database.session() as session:
            attempts = list(
                session.scalars(select(ReviewExecution).order_by(ReviewExecution.started_at))
            )
            assert len(attempts) == 2
            assert attempts[0].state == JobState.FAILED and attempts[0].error_code == "worker_lost"
            assert attempts[1].state == JobState.COMPLETED
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=10)
        parent.close()
