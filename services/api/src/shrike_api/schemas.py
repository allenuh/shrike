from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from shrike.domain.states import FindingSource, JobState, Severity


class ResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PageResponse[T](ResponseModel):
    items: list[T]
    next_cursor: str | None


class RepositoryResponse(ResponseModel):
    id: UUID
    github_id: int
    installation_id: UUID
    installation_github_id: int
    owner: str
    name: str
    private: bool
    created_at: datetime


class JobResponse(ResponseModel):
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


class FindingResponse(ResponseModel):
    id: UUID
    source: FindingSource
    severity: Severity
    rule_id: str
    path: str
    line_start: int
    line_end: int
    message: str


class ExecutionResponse(ResponseModel):
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


class JobDetailResponse(ResponseModel):
    job: JobResponse
    findings: PageResponse[FindingResponse]
    executions: list[ExecutionResponse]


class PageQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=2048)
    order: Literal["asc", "desc"] = "desc"


class RepositoryQuery(PageQuery):
    installation_id: UUID | None = None
    private: bool | None = None
    search: str | None = Field(default=None, min_length=1, max_length=100)
    sort: Literal["created_at", "name"] = "created_at"


class JobQuery(PageQuery):
    installation_id: UUID | None = None
    repository_id: UUID | None = None
    pull_request_number: int | None = Field(default=None, ge=1, le=2147483647)
    state: JobState | None = None
    created_after: AwareDatetime | None = None
    created_before: AwareDatetime | None = None
    sort: Literal["created_at", "state"] = "created_at"

    @model_validator(mode="after")
    def valid_range(self) -> "JobQuery":
        if (
            self.created_after is not None
            and self.created_before is not None
            and self.created_after > self.created_before
        ):
            raise ValueError("created_after must not exceed created_before")
        return self


class FindingQuery(PageQuery):
    severity: Severity | None = None
    source: FindingSource | None = None
    sort: Literal["severity", "path"] = "severity"


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
