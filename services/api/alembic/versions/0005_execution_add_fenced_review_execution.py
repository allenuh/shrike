"""Fenced review attempts and provider admission; preserve existing history."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0005_execution"
down_revision: str | Sequence[str] | None = "0004_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "review_jobs", sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column("review_jobs", sa.Column("first_started_at", sa.DateTime(timezone=True)))
    op.add_column(
        "review_jobs",
        sa.Column(
            "available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.add_column("review_jobs", sa.Column("error_code", sa.String(64)))
    op.add_column("review_jobs", sa.Column("lease_token", sa.Uuid()))
    op.add_column("review_jobs", sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
    op.add_column(
        "review_jobs",
        sa.Column("publication_eligible", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column("review_jobs", sa.Column("result", JSONB()))
    op.create_check_constraint("attempt_count", "review_jobs", "attempt_count BETWEEN 0 AND 3")
    op.create_check_constraint(
        "lease", "review_jobs", "(lease_token IS NULL) = (lease_expires_at IS NULL)"
    )
    op.add_column(
        "review_executions",
        sa.Column("usage_reported", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_table(
        "provider_windows",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("next_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute(
        "UPDATE review_jobs j SET attempt_count = e.attempt, first_started_at=e.started "
        "FROM (SELECT job_id, max(attempt) AS attempt, min(started_at) AS started "
        "FROM review_executions GROUP BY job_id) e WHERE j.id=e.job_id"
    )


def downgrade() -> None:
    op.drop_table("provider_windows")
    op.drop_column("review_executions", "usage_reported")
    op.drop_constraint("lease", "review_jobs", type_="check")
    op.drop_constraint("attempt_count", "review_jobs", type_="check")
    for name in (
        "result",
        "publication_eligible",
        "lease_expires_at",
        "lease_token",
        "error_code",
        "available_at",
        "first_started_at",
        "attempt_count",
    ):
        op.drop_column("review_jobs", name)
