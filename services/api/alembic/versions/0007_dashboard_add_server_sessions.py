"""Server-managed OAuth state and encrypted dashboard sessions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_dashboard"
down_revision: str | Sequence[str] | None = "0006_publication"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oauth_states",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("verifier", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_oauth_states_expires_at", "oauth_states", ["expires_at"])
    op.create_table(
        "dashboard_sessions",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("user_github_id", sa.BigInteger(), nullable=False),
        sa.Column("login", sa.String(100), nullable=False),
        sa.Column("encrypted_token", sa.Text()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("user_github_id > 0", name="user_id"),
    )
    op.create_index("ix_dashboard_sessions_expires_at", "dashboard_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_table("dashboard_sessions")
    op.drop_table("oauth_states")
