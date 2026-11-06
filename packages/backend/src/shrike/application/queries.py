from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from shrike.domain.states import FindingSource, JobState, Severity

type Order = Literal["asc", "desc"]


@dataclass(frozen=True)
class Pagination:
    limit: int = 20
    cursor: str | None = None
    order: Order = "desc"


@dataclass(frozen=True)
class RepositoryFilters:
    installation_id: UUID | None = None
    private: bool | None = None
    search: str | None = None
    sort: Literal["created_at", "name"] = "created_at"


@dataclass(frozen=True)
class JobFilters:
    installation_id: UUID | None = None
    repository_id: UUID | None = None
    pull_request_number: int | None = None
    state: JobState | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    sort: Literal["created_at", "state"] = "created_at"


@dataclass(frozen=True)
class FindingFilters:
    severity: Severity | None = None
    source: FindingSource | None = None
    sort: Literal["severity", "path"] = "severity"
