"""add durable GitHub ingestion

Revision ID: 0002_github
Revises: 0001_core
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_github"
down_revision: str | Sequence[str] | None = "0001_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "webhook_deliveries",
        sa.Column("delivery_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("body_digest", sa.String(length=64), nullable=False),
        sa.Column("installation_id", sa.Uuid(), nullable=True),
        sa.Column("routing", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("state", sa.String(length=12), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(state='processing' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
            "(state<>'processing' AND lease_token IS NULL AND lease_expires_at IS NULL)",
            name=op.f("ck_webhook_deliveries_lease_state"),
        ),
        sa.CheckConstraint(
            "body_digest ~ '^[0-9a-f]{64}$'", name=op.f("ck_webhook_deliveries_body_digest")
        ),
        sa.CheckConstraint(
            "state IN ('pending','processing','completed','ignored','failed')",
            name=op.f("ck_webhook_deliveries_state"),
        ),
        sa.CheckConstraint("attempts BETWEEN 0 AND 3", name=op.f("ck_webhook_deliveries_attempts")),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["installations.id"],
            name=op.f("fk_webhook_deliveries_installation_id_installations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_deliveries")),
        sa.UniqueConstraint("delivery_id", name=op.f("uq_webhook_deliveries_delivery_id")),
    )
    op.create_index(
        "ix_webhook_due",
        "webhook_deliveries",
        ["state", "available_at", "lease_expires_at"],
        unique=False,
    )
    op.add_column(
        "installations",
        sa.Column("github_verified", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "installations",
        sa.Column("access_generation", sa.BigInteger(), server_default="0", nullable=False),
    )
    op.add_column(
        "repositories",
        sa.Column("access_blocked", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("repositories", "access_blocked")
    op.drop_column("installations", "access_generation")
    op.drop_column("installations", "github_verified")
    op.drop_index("ix_webhook_due", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
