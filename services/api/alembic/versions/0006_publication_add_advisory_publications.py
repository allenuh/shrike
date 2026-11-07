"""Durable independent publication identities, write intents and external IDs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0006_publication"
down_revision: str | Sequence[str] | None = "0005_execution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_publications",
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("review_jobs.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("marker", sa.String(200), nullable=False, unique=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary_only", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("payload", JSONB()),
        sa.Column("payload_digest", sa.String(64)),
        sa.Column("review_id", sa.BigInteger()),
        sa.Column("comment_ids", JSONB(), nullable=False, server_default="[]"),
        sa.Column("reason", sa.String(64)),
        sa.Column("lease_token", sa.Uuid()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "state IN ('preparing','inflight','published','partial','uncertain',"
            "'failed','suppressed','stale')",
            name="state",
        ),
        sa.CheckConstraint("attempts BETWEEN 0 AND 3", name="attempts"),
        sa.CheckConstraint("(lease_token IS NULL) = (lease_expires_at IS NULL)", name="lease"),
        sa.CheckConstraint("review_id IS NULL OR review_id > 0", name="review_id"),
        sa.CheckConstraint(
            "payload_digest IS NULL OR payload_digest ~ '^[a-f0-9]{64}$'", name="payload_digest"
        ),
    )


def downgrade() -> None:
    op.drop_table("review_publications")
