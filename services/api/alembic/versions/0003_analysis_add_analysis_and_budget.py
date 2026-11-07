"""Scoped analysis reports and durable, content-free API accounting.

Downgrade destroys accounting: use only disposable databases or explicitly reconciled recovery.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0003_analysis"
down_revision: str | Sequence[str] | None = "0002_github"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analysis_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("access_generation", sa.BigInteger(), nullable=False),
        sa.Column("report", JSONB(), nullable=False),
        sa.UniqueConstraint("repository_id", "digest", name="uq_analysis_repository_digest"),
        sa.CheckConstraint("digest ~ '^[0-9a-f]{64}$'", name="digest"),
    )
    op.create_table(
        "ai_budgets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prior_micro", sa.BigInteger(), nullable=False),
        sa.Column("total_micro", sa.BigInteger(), nullable=False),
        sa.Column("warning_micro", sa.BigInteger(), nullable=False),
        sa.Column("hard_micro", sa.BigInteger(), nullable=False),
        sa.Column("max_review_micro", sa.BigInteger(), nullable=False),
        sa.Column("max_live", sa.Integer(), nullable=False),
        sa.Column("frozen", sa.Boolean(), nullable=False),
        sa.CheckConstraint("id = 1", name="singleton"),
        sa.CheckConstraint(
            "prior_micro >= 0 AND warning_micro >= 0 AND warning_micro < hard_micro "
            "AND hard_micro <= total_micro AND total_micro <= 10000000 AND max_review_micro > 0 "
            "AND max_live BETWEEN 1 AND 2",
            name="limits",
        ),
    )
    op.create_table(
        "ai_price_snapshots",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("profile", JSONB(), nullable=False),
    )
    op.create_table(
        "ai_spend_entries",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("review_key", sa.String(64), nullable=False),
        sa.Column("evaluation_session", sa.String(36)),
        sa.Column("evaluation_limit", sa.Integer()),
        sa.Column(
            "budget_id",
            sa.Integer(),
            sa.ForeignKey("ai_budgets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "price_id",
            sa.String(64),
            sa.ForeignKey("ai_price_snapshots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reserved_micro", sa.BigInteger(), nullable=False),
        sa.Column("settled_micro", sa.BigInteger()),
        sa.Column("input_bound", sa.Integer(), nullable=False),
        sa.Column("output_bound", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("state IN ('dispatched','uncertain','settled')", name="state"),
        sa.CheckConstraint(
            "reserved_micro > 0 AND settled_micro >= 0 AND input_bound > 0 "
            "AND output_bound > 0 AND input_tokens >= 0 AND output_tokens >= 0",
            name="amounts",
        ),
        sa.CheckConstraint(
            "(state = 'settled' AND settled_micro IS NOT NULL AND input_tokens IS NOT NULL "
            "AND output_tokens IS NOT NULL) OR (state <> 'settled' AND settled_micro IS NULL)",
            name="settlement",
        ),
    )
    op.create_index("ix_ai_spend_entries_review_key", "ai_spend_entries", ["review_key"])


def downgrade() -> None:
    op.drop_index("ix_ai_spend_entries_review_key", table_name="ai_spend_entries")
    op.drop_table("ai_spend_entries")
    op.drop_table("ai_price_snapshots")
    op.drop_table("ai_budgets")
    op.drop_table("analysis_reports")
