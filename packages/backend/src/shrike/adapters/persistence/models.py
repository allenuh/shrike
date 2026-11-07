"""Persistence mappings. Composite foreign keys enforce repository ownership."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from shrike.domain.states import (
    FindingSource,
    InstallationStatus,
    JobState,
    PullRequestState,
    RepositoryStatus,
    Severity,
)


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def enum_column(enum: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda cls: [item.value for item in cls],
    )


class IdentityMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Installation(IdentityMixin, Base):
    __tablename__ = "installations"
    __table_args__ = (
        CheckConstraint("github_id > 0 AND account_github_id > 0", name="positive_github_ids"),
        CheckConstraint("account_type IN ('User', 'Organization')", name="account_type"),
    )

    github_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    account_github_id: Mapped[int] = mapped_column(BigInteger)
    account_type: Mapped[str] = mapped_column(String(12))
    status: Mapped[InstallationStatus] = mapped_column(
        enum_column(InstallationStatus, "installation_status"), default=InstallationStatus.ACTIVE
    )
    github_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    access_generation: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")


class Repository(IdentityMixin, Base):
    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("id", "installation_id", name="uq_repository_ownership"),
        CheckConstraint("github_id > 0", name="positive_github_id"),
        CheckConstraint("length(owner) > 0 AND length(name) > 0", name="nonempty_names"),
        Index("ix_repositories_installation_status", "installation_id", "status"),
    )

    installation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("installations.id", ondelete="RESTRICT")
    )
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    owner: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(100))
    private: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[RepositoryStatus] = mapped_column(
        enum_column(RepositoryStatus, "repository_status"), default=RepositoryStatus.ACTIVE
    )
    access_blocked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class PullRequest(IdentityMixin, Base):
    __tablename__ = "pull_requests"
    __table_args__ = (
        UniqueConstraint("repository_id", "number", name="uq_pr_repository_number"),
        UniqueConstraint("id", "repository_id", name="uq_pr_ownership"),
        CheckConstraint("github_id > 0 AND number > 0", name="positive_identifiers"),
        CheckConstraint("base_sha ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'", name="base_sha"),
        CheckConstraint("head_sha ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'", name="head_sha"),
    )

    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="RESTRICT")
    )
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    number: Mapped[int] = mapped_column(Integer)
    state: Mapped[PullRequestState] = mapped_column(
        enum_column(PullRequestState, "pull_request_state"), default=PullRequestState.OPEN
    )
    draft: Mapped[bool] = mapped_column(Boolean, default=False)
    base_sha: Mapped[str] = mapped_column(String(64))
    head_sha: Mapped[str] = mapped_column(String(64))


class ReviewJob(IdentityMixin, Base):
    __tablename__ = "review_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["repository_id", "installation_id"],
            ["repositories.id", "repositories.installation_id"],
            name="fk_job_repository_ownership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["pull_request_id", "repository_id"],
            ["pull_requests.id", "pull_requests.repository_id"],
            name="fk_job_pr_ownership",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "repository_id",
            "pull_request_id",
            "base_sha",
            "head_sha",
            "policy_digest",
            name="uq_job_analysis_identity",
        ),
        CheckConstraint("base_sha ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'", name="base_sha"),
        CheckConstraint("head_sha ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'", name="head_sha"),
        CheckConstraint("policy_digest ~ '^[0-9a-f]{64}$'", name="policy_digest"),
        CheckConstraint(
            "(state = 'pending' AND started_at IS NULL AND finished_at IS NULL) OR "
            "(state = 'running' AND started_at IS NOT NULL AND finished_at IS NULL) OR "
            "(state IN ('completed', 'failed') AND started_at IS NOT NULL "
            "AND finished_at IS NOT NULL) OR (state = 'canceled' AND finished_at IS NOT NULL)",
            name="state_timestamps",
        ),
        CheckConstraint(
            "(started_at IS NULL OR started_at >= created_at) AND "
            "(finished_at IS NULL OR finished_at >= coalesce(started_at, created_at))",
            name="time_order",
        ),
        Index("ix_jobs_repository_created", "repository_id", "created_at", "id"),
        Index("ix_jobs_state_created", "state", "created_at", "id"),
        CheckConstraint("attempt_count BETWEEN 0 AND 3", name="attempt_count"),
        CheckConstraint("(lease_token IS NULL) = (lease_expires_at IS NULL)", name="lease"),
    )

    installation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("installations.id", ondelete="RESTRICT")
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    pull_request_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    base_sha: Mapped[str] = mapped_column(String(64))
    head_sha: Mapped[str] = mapped_column(String(64))
    policy_digest: Mapped[str] = mapped_column(String(64))
    state: Mapped[JobState] = mapped_column(
        enum_column(JobState, "job_state"), default=JobState.PENDING
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    first_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    lease_token: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publication_eligible: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class ReviewFinding(IdentityMixin, Base):
    __tablename__ = "review_findings"
    __table_args__ = (
        UniqueConstraint("job_id", "fingerprint", name="uq_finding_job_fingerprint"),
        CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$'", name="fingerprint"),
        CheckConstraint("line_start > 0 AND line_end >= line_start", name="line_range"),
        CheckConstraint(
            "length(path) > 0 AND path !~ '(^/|(^|/)\\.\\.(/|$)|:|\\\\)'",
            name="safe_relative_path",
        ),
        CheckConstraint("length(message) BETWEEN 1 AND 4000", name="message_length"),
        Index("ix_findings_job_severity", "job_id", "severity"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("review_jobs.id", ondelete="CASCADE"))
    fingerprint: Mapped[str] = mapped_column(String(64))
    source: Mapped[FindingSource] = mapped_column(enum_column(FindingSource, "finding_source"))
    severity: Mapped[Severity] = mapped_column(enum_column(Severity, "finding_severity"))
    rule_id: Mapped[str] = mapped_column(String(100))
    path: Mapped[str] = mapped_column(String(1024))
    line_start: Mapped[int] = mapped_column(Integer)
    line_end: Mapped[int] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(Text)


class ReviewExecution(IdentityMixin, Base):
    __tablename__ = "review_executions"
    __table_args__ = (
        UniqueConstraint("job_id", "attempt", name="uq_execution_job_attempt"),
        CheckConstraint("attempt BETWEEN 1 AND 3", name="attempt_bounds"),
        CheckConstraint("state <> 'pending'", name="execution_started"),
        CheckConstraint(
            "(state = 'running' AND finished_at IS NULL) OR "
            "(state IN ('completed', 'failed', 'canceled') AND finished_at IS NOT NULL "
            "AND finished_at >= started_at)",
            name="state_timestamps",
        ),
        CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND duration_ms >= 0",
            name="nonnegative_usage",
        ),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("review_jobs.id", ondelete="CASCADE"))
    attempt: Mapped[int] = mapped_column(Integer)
    state: Mapped[JobState] = mapped_column(enum_column(JobState, "execution_state"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    analyzer_version: Mapped[str | None] = mapped_column(String(64))
    ruleset_version: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(64))
    # Operational identifiers are intentionally absent from public response models.
    worker_identifier: Mapped[str | None] = mapped_column(String(128))
    usage_reported: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class WebhookDelivery(IdentityMixin, Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        CheckConstraint(
            "state IN ('pending','processing','completed','ignored','failed')", name="state"
        ),
        CheckConstraint("attempts BETWEEN 0 AND 3", name="attempts"),
        CheckConstraint("body_digest ~ '^[0-9a-f]{64}$'", name="body_digest"),
        CheckConstraint(
            "(state='processing' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
            "(state<>'processing' AND lease_token IS NULL AND lease_expires_at IS NULL)",
            name="lease_state",
        ),
        Index("ix_webhook_due", "state", "available_at", "lease_expires_at"),
    )
    delivery_id: Mapped[str] = mapped_column(String(36), unique=True)
    event_type: Mapped[str] = mapped_column(String(64))
    body_digest: Mapped[str] = mapped_column(String(64))
    installation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("installations.id", ondelete="RESTRICT")
    )
    routing: Mapped[dict[str, Any]] = mapped_column(JSONB)
    state: Mapped[str] = mapped_column(String(12), default="pending")
    reason: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AnalysisReport(IdentityMixin, Base):
    __tablename__ = "analysis_reports"
    __table_args__ = (
        UniqueConstraint("repository_id", "digest", name="uq_analysis_repository_digest"),
        CheckConstraint("digest ~ '^[0-9a-f]{64}$'", name="digest"),
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE")
    )
    digest: Mapped[str] = mapped_column(String(64))
    access_generation: Mapped[int] = mapped_column(BigInteger)
    report: Mapped[dict[str, Any]] = mapped_column(JSONB)


class QueueMessage(IdentityMixin, Base):
    __tablename__ = "queue_messages"
    __table_args__ = (
        UniqueConstraint("kind", "record_id", name="uq_queue_record"),
        CheckConstraint("kind IN ('ingestion','review')", name="kind"),
        CheckConstraint("generation >= 0 AND failures BETWEEN 0 AND 20", name="counters"),
        CheckConstraint("(lease_token IS NULL) = (lease_expires_at IS NULL)", name="lease"),
        Index("ix_queue_due", "available_at", "published_at"),
    )
    kind: Mapped[str] = mapped_column(String(16))
    record_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4)
    generation: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProviderWindow(Base):
    __tablename__ = "provider_windows"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    next_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReviewPublication(Base):
    __tablename__ = "review_publications"
    __table_args__ = (
        CheckConstraint(
            "state IN ('preparing','inflight','published','partial','uncertain',"
            "'failed','suppressed','stale')",
            name="state",
        ),
        CheckConstraint("attempts BETWEEN 0 AND 3", name="attempts"),
        CheckConstraint("(lease_token IS NULL) = (lease_expires_at IS NULL)", name="lease"),
        CheckConstraint("review_id IS NULL OR review_id > 0", name="review_id"),
        CheckConstraint(
            "payload_digest IS NULL OR payload_digest ~ '^[a-f0-9]{64}$'", name="payload_digest"
        ),
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("review_jobs.id", ondelete="RESTRICT"), primary_key=True
    )
    marker: Mapped[str] = mapped_column(String(200), unique=True)
    state: Mapped[str] = mapped_column(String(16))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    summary_only: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    payload_digest: Mapped[str | None] = mapped_column(String(64))
    review_id: Mapped[int | None] = mapped_column(BigInteger)
    comment_ids: Mapped[list[int]] = mapped_column(JSONB, default=list, server_default="[]")
    reason: Mapped[str | None] = mapped_column(String(64))
    lease_token: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OAuthState(Base):
    __tablename__ = "oauth_states"
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    verifier: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class DashboardSession(Base):
    __tablename__ = "dashboard_sessions"
    __table_args__ = (CheckConstraint("user_github_id > 0", name="user_id"),)
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_github_id: Mapped[int] = mapped_column(BigInteger)
    login: Mapped[str] = mapped_column(String(100))
    encrypted_token: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AiBudget(Base):
    __tablename__ = "ai_budgets"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint(
            "prior_micro >= 0 AND warning_micro >= 0 AND warning_micro < hard_micro "
            "AND hard_micro <= total_micro AND total_micro <= 10000000 AND max_review_micro > 0 "
            "AND max_live BETWEEN 1 AND 2",
            name="limits",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prior_micro: Mapped[int] = mapped_column(BigInteger)
    total_micro: Mapped[int] = mapped_column(BigInteger, default=10000000)
    warning_micro: Mapped[int] = mapped_column(BigInteger, default=7500000)
    hard_micro: Mapped[int] = mapped_column(BigInteger, default=9000000)
    max_review_micro: Mapped[int] = mapped_column(BigInteger, default=20000)
    max_live: Mapped[int] = mapped_column(Integer, default=1)
    frozen: Mapped[bool] = mapped_column(Boolean, default=False)


class AiPriceSnapshot(Base):
    __tablename__ = "ai_price_snapshots"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    profile: Mapped[dict[str, Any]] = mapped_column(JSONB)


class AiSpendEntry(Base):
    __tablename__ = "ai_spend_entries"
    __table_args__ = (
        CheckConstraint("state IN ('dispatched','uncertain','settled')", name="state"),
        CheckConstraint(
            "reserved_micro > 0 AND settled_micro >= 0 AND input_bound > 0 "
            "AND output_bound > 0 AND input_tokens >= 0 AND output_tokens >= 0",
            name="amounts",
        ),
        CheckConstraint(
            "(state = 'settled' AND settled_micro IS NOT NULL AND input_tokens IS NOT NULL "
            "AND output_tokens IS NOT NULL) OR (state <> 'settled' AND settled_micro IS NULL)",
            name="settlement",
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    review_key: Mapped[str] = mapped_column(String(64), index=True)
    evaluation_session: Mapped[str | None] = mapped_column(String(36))
    evaluation_limit: Mapped[int | None] = mapped_column(Integer)
    budget_id: Mapped[int] = mapped_column(
        ForeignKey("ai_budgets.id", ondelete="RESTRICT"), default=1
    )
    price_id: Mapped[str] = mapped_column(ForeignKey("ai_price_snapshots.id", ondelete="RESTRICT"))
    reserved_micro: Mapped[int] = mapped_column(BigInteger)
    settled_micro: Mapped[int | None] = mapped_column(BigInteger)
    input_bound: Mapped[int] = mapped_column(Integer)
    output_bound: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(16), default="dispatched")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
