"""Allowlisted immutable read models; persistence-only columns cannot leak by accident."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from shrike.domain.states import FindingSource, JobState, Severity


@dataclass(frozen=True)
class Page[T]:
    items: tuple[T, ...]
    next_cursor: str | None


@dataclass(frozen=True)
class RepositoryView:
    id: UUID
    github_id: int
    installation_id: UUID
    installation_github_id: int
    owner: str
    name: str
    private: bool
    created_at: datetime


@dataclass(frozen=True)
class JobView:
    id: UUID
    installation_id: UUID
    repository_id: UUID
    pull_request_id: UUID
    pull_request_number: int
    base_sha: str
    head_sha: str
    state: JobState
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    finding_count: int


@dataclass(frozen=True)
class FindingView:
    id: UUID
    source: FindingSource
    severity: Severity
    rule_id: str
    path: str
    line_start: int
    line_end: int
    message: str


@dataclass(frozen=True)
class ExecutionView:
    id: UUID
    attempt: int
    state: JobState
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int
    input_tokens: int
    output_tokens: int
    analyzer_version: str | None
    ruleset_version: str | None
    prompt_version: str | None
    provider: str | None
    model: str | None
    error_code: str | None


@dataclass(frozen=True)
class JobDetail:
    job: JobView
    findings: Page[FindingView]
    executions: tuple[ExecutionView, ...]
