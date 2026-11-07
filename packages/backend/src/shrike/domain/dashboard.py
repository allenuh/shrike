from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DashboardModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class RepositoryCard(DashboardModel):
    id: UUID
    owner: str
    name: str
    private: bool
    installation_github_id: int
    latest_state: str | None
    review_count: int


class ReviewRow(DashboardModel):
    id: UUID
    repository_id: UUID
    repository_owner: str
    repository_name: str
    pr_number: int
    head_sha: str
    state: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    finding_count: int


class FindingDetail(DashboardModel):
    id: UUID
    severity: str
    source: str
    rule_id: str
    path: str
    line: int
    explanation: str
    suggestion: str | None
    snippet: str | None
    github_url: str


class PublicationView(DashboardModel):
    state: str
    review_id: int | None
    comment_ids: list[int]
    reason: str | None


class CoverageView(DashboardModel):
    selected_files: int
    skipped_files: int
    changed_lines: int


class AttemptView(DashboardModel):
    attempt: int
    state: str
    duration_ms: int
    provider: str | None
    error_code: str | None


class MetricsView(DashboardModel):
    window_days: int
    as_of: datetime
    repositories: int
    reviews: int
    findings: int
    completed: int
    failed: int
    success_rate: float | None
    failure_rate: float | None
    average_processing_seconds: float | None
    severity_counts: dict[str, int]
    daily_reviews: list[dict[str, str | int]]


class OperationalView(DashboardModel):
    as_of: datetime
    database: str
    pending: int
    running: int
    active_leases: int
    expired_leases: int
    retry_wait: int
    undispatched: int
    uncertain_publications: int
    oldest_pending_seconds: float | None
    worker_heartbeat: str = "unavailable"
    broker_reachability: str = "unavailable"


class PolicyView(DashboardModel):
    authentication: str
    ai_provider: str
    publishing: str
    minimum_confidence: float = 0.85
    maximum_published_findings: int = 10
    supported_language: str = "Python"
