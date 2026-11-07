from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.models import QueueMessage, ReviewJob, WebhookDelivery
from shrike.domain.queue import DispatchClaim, Envelope
from shrike.domain.states import JobState


def enqueue(session: Session, kind: str, record_id: UUID, request_id: UUID | None = None) -> None:
    session.execute(
        insert(QueueMessage)
        .values(kind=kind, record_id=record_id, request_id=request_id or uuid4())
        .on_conflict_do_nothing(constraint="uq_queue_record")
    )


def reschedule(session: Session, kind: str, record_id: UUID, due: datetime) -> None:
    enqueue(session, kind, record_id)
    row = session.scalar(
        select(QueueMessage)
        .where(QueueMessage.kind == kind, QueueMessage.record_id == record_id)
        .with_for_update()
    )
    assert row is not None
    row.generation += 1
    row.available_at, row.published_at = due, None
    row.lease_token, row.lease_expires_at, row.failures = None, None, 0


class SqlDispatchStore:
    def __init__(self, database: Database, *, redelivery_seconds: float = 30) -> None:
        self.database, self.redelivery_seconds = database, redelivery_seconds

    def claim(self) -> DispatchClaim | None:
        now = datetime.now(UTC)
        ingestion = exists(
            select(WebhookDelivery.id).where(
                WebhookDelivery.id == QueueMessage.record_id,
                or_(
                    and_(WebhookDelivery.state == "pending", WebhookDelivery.available_at <= now),
                    and_(
                        WebhookDelivery.state == "processing",
                        WebhookDelivery.lease_expires_at <= now,
                    ),
                ),
            )
        )
        review = exists(
            select(ReviewJob.id).where(
                ReviewJob.id == QueueMessage.record_id, ReviewJob.state == JobState.PENDING
            )
        )
        with self.database.session() as session, session.begin():
            row = session.scalar(
                select(QueueMessage)
                .where(
                    QueueMessage.available_at <= now,
                    or_(QueueMessage.lease_token.is_(None), QueueMessage.lease_expires_at <= now),
                    or_(
                        QueueMessage.published_at.is_(None),
                        QueueMessage.published_at
                        <= now - timedelta(seconds=self.redelivery_seconds),
                    ),
                    or_(
                        and_(QueueMessage.kind == "ingestion", ingestion),
                        and_(QueueMessage.kind == "review", review),
                    ),
                )
                .order_by(QueueMessage.available_at, QueueMessage.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if row is None:
                return None
            row.lease_token, row.lease_expires_at = uuid4(), now + timedelta(seconds=15)
            return DispatchClaim(
                row.id,
                row.lease_token,
                row.request_id,
                Envelope(kind=row.kind, record_id=row.record_id, generation=row.generation),
            )

    def _finish(self, claim: DispatchClaim, *, failed: bool) -> None:
        with self.database.session() as session, session.begin():
            row = session.scalar(
                select(QueueMessage).where(QueueMessage.id == claim.id).with_for_update()
            )
            if (
                row is None
                or row.lease_token != claim.fence
                or row.generation != claim.envelope.generation
            ):
                return
            now = datetime.now(UTC)
            if failed:
                row.failures = min(row.failures + 1, 20)
                row.available_at = now + timedelta(seconds=min(300, 2**row.failures))
            else:
                row.published_at, row.failures = now, 0
            row.lease_token, row.lease_expires_at = None, None

    def sent(self, claim: DispatchClaim) -> None:
        self._finish(claim, failed=False)

    def failed(self, claim: DispatchClaim) -> None:
        self._finish(claim, failed=True)
