import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fakes import FakeGitHub, github_fixture
from sqlalchemy import func, select

from shrike.adapters.github.webhooks import parse_webhook
from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.dispatch import SqlDispatchStore, reschedule
from shrike.adapters.persistence.ingestion import SqlIngestionStore, accept_delivery
from shrike.adapters.persistence.models import QueueMessage, ReviewJob, WebhookDelivery
from shrike.application.dispatch import dispatch_one
from shrike.application.ingestion import process_one
from shrike.domain.queue import Envelope, QueueUnavailable

pytestmark = pytest.mark.integration


def accept(database: Database) -> None:
    import json

    raw = json.dumps(github_fixture("pull_request_opened.json")).encode()
    request_id = uuid4()
    with database.session() as session, session.begin():
        accept_delivery(
            session,
            str(uuid4()),
            hashlib.sha256(raw).hexdigest(),
            parse_webhook("pull_request", raw, 12345),
            request_id,
        )


class Recorder:
    def __init__(self) -> None:
        self.messages: list[Envelope] = []
        self.fail = False

    def publish(self, envelope: Envelope) -> None:
        if self.fail:
            raise QueueUnavailable
        self.messages.append(envelope)


def test_atomic_ingestion_and_review_outbox(database: Database) -> None:
    accept(database)
    dispatcher, publisher = SqlDispatchStore(database), Recorder()
    assert dispatch_one(dispatcher, publisher)
    first = publisher.messages[0]
    assert first.kind == "ingestion"
    assert set(first.model_dump()) == {"version", "kind", "record_id", "generation"}
    assert not dispatch_one(dispatcher, publisher)
    assert process_one(SqlIngestionStore(database, first.record_id), FakeGitHub(), 12345)
    assert dispatch_one(dispatcher, publisher)
    assert publisher.messages[-1].kind == "review"
    with database.session() as session:
        rows = list(session.scalars(select(QueueMessage)))
        assert len(rows) == 2 and rows[0].request_id == rows[1].request_id
        assert session.scalar(select(func.count()).select_from(ReviewJob)) == 1


def test_broker_failure_keeps_durable_work(database: Database) -> None:
    accept(database)
    publisher, dispatcher = Recorder(), SqlDispatchStore(database)
    publisher.fail = True
    assert dispatch_one(dispatcher, publisher)
    with database.session() as session, session.begin():
        row = session.scalar(select(QueueMessage))
        assert row is not None and row.failures == 1 and row.published_at is None
        assert row.available_at > datetime.now(UTC)
        assert session.scalar(select(WebhookDelivery.state)) == "pending"
        row.available_at = datetime.now(UTC) - timedelta(seconds=1)
    publisher.fail = False
    assert dispatch_one(dispatcher, publisher) and len(publisher.messages) == 1


def test_dispatch_crash_and_lost_broker_messages_republish_safely(database: Database) -> None:
    accept(database)
    dispatcher = SqlDispatchStore(database, redelivery_seconds=0)
    abandoned = dispatcher.claim()
    assert abandoned is not None and dispatcher.claim() is None
    with database.session() as session, session.begin():
        row = session.get(QueueMessage, abandoned.id)
        assert row is not None
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    recovered = dispatcher.claim()
    assert recovered is not None and recovered.fence != abandoned.fence
    dispatcher.sent(abandoned)
    with database.session() as session:
        assert session.scalar(select(QueueMessage.published_at)) is None
    dispatcher.sent(recovered)
    repeated = dispatcher.claim()
    assert repeated is not None and repeated.envelope == abandoned.envelope


def test_outbox_rolls_back_with_webhook_receipt(database: Database) -> None:
    import json

    raw = json.dumps(github_fixture("pull_request_opened.json")).encode()
    with pytest.raises(RuntimeError), database.session() as session, session.begin():
        accept_delivery(
            session,
            str(uuid4()),
            hashlib.sha256(raw).hexdigest(),
            parse_webhook("pull_request", raw, 12345),
        )
        raise RuntimeError("synthetic-rollback")
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(QueueMessage)) == 0
        assert session.scalar(select(func.count()).select_from(WebhookDelivery)) == 0


def test_reschedule_fences_old_dispatch_confirmation(database: Database) -> None:
    accept(database)
    dispatcher = SqlDispatchStore(database)
    claim = dispatcher.claim()
    assert claim is not None
    with database.session() as session, session.begin():
        reschedule(session, "ingestion", claim.envelope.record_id, datetime.now(UTC))
    dispatcher.sent(claim)
    current = dispatcher.claim()
    assert current is not None and current.envelope.generation == 1
