"""create core persistence

Revision ID: 0001_core
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_core"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "installations",
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("account_github_id", sa.BigInteger(), nullable=False),
        sa.Column("account_type", sa.String(length=12), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "suspended",
                "deleted",
                name="installation_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "account_type IN ('User', 'Organization')", name=op.f("ck_installations_account_type")
        ),
        sa.CheckConstraint(
            "github_id > 0 AND account_github_id > 0",
            name=op.f("ck_installations_positive_github_ids"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_installations")),
        sa.UniqueConstraint("github_id", name=op.f("uq_installations_github_id")),
    )
    op.create_table(
        "repositories",
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("owner", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("private", sa.Boolean(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "removed",
                name="repository_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("github_id > 0", name=op.f("ck_repositories_positive_github_id")),
        sa.CheckConstraint(
            "length(owner) > 0 AND length(name) > 0", name=op.f("ck_repositories_nonempty_names")
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["installations.id"],
            name=op.f("fk_repositories_installation_id_installations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_repositories")),
        sa.UniqueConstraint("github_id", name=op.f("uq_repositories_github_id")),
        sa.UniqueConstraint("id", "installation_id", name="uq_repository_ownership"),
    )
    op.create_index(
        "ix_repositories_installation_status",
        "repositories",
        ["installation_id", "status"],
        unique=False,
    )
    op.create_table(
        "pull_requests",
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                "open",
                "closed",
                "merged",
                name="pull_request_state",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("draft", sa.Boolean(), nullable=False),
        sa.Column("base_sha", sa.String(length=64), nullable=False),
        sa.Column("head_sha", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "base_sha ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'", name=op.f("ck_pull_requests_base_sha")
        ),
        sa.CheckConstraint(
            "head_sha ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'", name=op.f("ck_pull_requests_head_sha")
        ),
        sa.CheckConstraint(
            "github_id > 0 AND number > 0", name=op.f("ck_pull_requests_positive_identifiers")
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            name=op.f("fk_pull_requests_repository_id_repositories"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pull_requests")),
        sa.UniqueConstraint("github_id", name=op.f("uq_pull_requests_github_id")),
        sa.UniqueConstraint("id", "repository_id", name="uq_pr_ownership"),
        sa.UniqueConstraint("repository_id", "number", name="uq_pr_repository_number"),
    )
    op.create_table(
        "review_jobs",
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("pull_request_id", sa.Uuid(), nullable=False),
        sa.Column("base_sha", sa.String(length=64), nullable=False),
        sa.Column("head_sha", sa.String(length=64), nullable=False),
        sa.Column("policy_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                "pending",
                "running",
                "completed",
                "failed",
                "canceled",
                name="job_state",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(state = 'pending' AND started_at IS NULL AND finished_at IS NULL) OR "
            "(state = 'running' AND started_at IS NOT NULL AND finished_at IS NULL) OR "
            "(state IN ('completed', 'failed') AND started_at IS NOT NULL "
            "AND finished_at IS NOT NULL) OR (state = 'canceled' AND finished_at IS NOT NULL)",
            name=op.f("ck_review_jobs_state_timestamps"),
        ),
        sa.CheckConstraint(
            "base_sha ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'", name=op.f("ck_review_jobs_base_sha")
        ),
        sa.CheckConstraint(
            "head_sha ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'", name=op.f("ck_review_jobs_head_sha")
        ),
        sa.CheckConstraint(
            "policy_digest ~ '^[0-9a-f]{64}$'", name=op.f("ck_review_jobs_policy_digest")
        ),
        sa.CheckConstraint(
            "(started_at IS NULL OR started_at >= created_at) AND "
            "(finished_at IS NULL OR finished_at >= coalesce(started_at, created_at))",
            name=op.f("ck_review_jobs_time_order"),
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["installations.id"],
            name=op.f("fk_review_jobs_installation_id_installations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pull_request_id", "repository_id"],
            ["pull_requests.id", "pull_requests.repository_id"],
            name="fk_job_pr_ownership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["repository_id", "installation_id"],
            ["repositories.id", "repositories.installation_id"],
            name="fk_job_repository_ownership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_jobs")),
        sa.UniqueConstraint(
            "repository_id",
            "pull_request_id",
            "base_sha",
            "head_sha",
            "policy_digest",
            name="uq_job_analysis_identity",
        ),
    )
    op.create_index(
        "ix_jobs_repository_created",
        "review_jobs",
        ["repository_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_jobs_state_created", "review_jobs", ["state", "created_at", "id"], unique=False
    )
    op.create_table(
        "review_executions",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                "pending",
                "running",
                "completed",
                "failed",
                "canceled",
                name="execution_state",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("analyzer_version", sa.String(length=64), nullable=True),
        sa.Column("ruleset_version", sa.String(length=64), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("worker_identifier", sa.String(length=128), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(state = 'running' AND finished_at IS NULL) OR "
            "(state IN ('completed', 'failed', 'canceled') AND finished_at IS NOT NULL "
            "AND finished_at >= started_at)",
            name=op.f("ck_review_executions_state_timestamps"),
        ),
        sa.CheckConstraint(
            "state <> 'pending'", name=op.f("ck_review_executions_execution_started")
        ),
        sa.CheckConstraint(
            "attempt BETWEEN 1 AND 3", name=op.f("ck_review_executions_attempt_bounds")
        ),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND duration_ms >= 0",
            name=op.f("ck_review_executions_nonnegative_usage"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["review_jobs.id"],
            name=op.f("fk_review_executions_job_id_review_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_executions")),
        sa.UniqueConstraint("job_id", "attempt", name="uq_execution_job_attempt"),
    )
    op.create_table(
        "review_findings",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "ruff",
                "semgrep",
                "llm",
                name="finding_source",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum(
                "info",
                "low",
                "medium",
                "high",
                "critical",
                name="finding_severity",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("rule_id", sa.String(length=100), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("line_start", sa.Integer(), nullable=False),
        sa.Column("line_end", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "fingerprint ~ '^[0-9a-f]{64}$'", name=op.f("ck_review_findings_fingerprint")
        ),
        sa.CheckConstraint(
            "length(path) > 0 AND path !~ '(^/|(^|/)\\.\\.(/|$)|:|\\\\)'",
            name=op.f("ck_review_findings_safe_relative_path"),
        ),
        sa.CheckConstraint(
            "length(message) BETWEEN 1 AND 4000", name=op.f("ck_review_findings_message_length")
        ),
        sa.CheckConstraint(
            "line_start > 0 AND line_end >= line_start", name=op.f("ck_review_findings_line_range")
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["review_jobs.id"],
            name=op.f("fk_review_findings_job_id_review_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_findings")),
        sa.UniqueConstraint("job_id", "fingerprint", name="uq_finding_job_fingerprint"),
    )
    op.create_index(
        "ix_findings_job_severity", "review_findings", ["job_id", "severity"], unique=False
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index("ix_findings_job_severity", table_name="review_findings")
    op.drop_table("review_findings")
    op.drop_table("review_executions")
    op.drop_index("ix_jobs_state_created", table_name="review_jobs")
    op.drop_index("ix_jobs_repository_created", table_name="review_jobs")
    op.drop_table("review_jobs")
    op.drop_table("pull_requests")
    op.drop_index("ix_repositories_installation_status", table_name="repositories")
    op.drop_table("repositories")
    op.drop_table("installations")
    # ### end Alembic commands ###
