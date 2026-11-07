"""Transactional ID-only dispatch; backfill existing pending work."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_outbox"
down_revision: str | Sequence[str] | None = "0003_analysis"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "queue_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("generation", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("lease_token", sa.Uuid()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("kind", "record_id", name="uq_queue_record"),
        sa.CheckConstraint("kind IN ('ingestion','review')", name="kind"),
        sa.CheckConstraint("generation >= 0 AND failures BETWEEN 0 AND 20", name="counters"),
        sa.CheckConstraint("(lease_token IS NULL) = (lease_expires_at IS NULL)", name="lease"),
    )
    op.create_index("ix_queue_due", "queue_messages", ["available_at", "published_at"])
    op.execute(
        "INSERT INTO queue_messages (id, kind, record_id, request_id) "
        "SELECT gen_random_uuid(), 'ingestion', id, gen_random_uuid() FROM webhook_deliveries "
        "WHERE state IN ('pending','processing')"
    )
    op.execute(
        "INSERT INTO queue_messages (id, kind, record_id, request_id) "
        "SELECT gen_random_uuid(), 'review', id, gen_random_uuid() "
        "FROM review_jobs WHERE state = 'pending'"
    )


def downgrade() -> None:
    op.drop_index("ix_queue_due", table_name="queue_messages")
    op.drop_table("queue_messages")
