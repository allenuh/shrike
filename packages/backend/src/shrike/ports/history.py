from typing import Protocol
from uuid import UUID

from shrike.application.queries import FindingFilters, JobFilters, Pagination, RepositoryFilters
from shrike.application.views import (
    ExecutionView,
    FindingView,
    JobView,
    Page,
    RepositoryView,
)
from shrike.domain.access import ReadScope


class HistoryReader(Protocol):
    def repository(self, scope: ReadScope, repository_id: UUID) -> RepositoryView | None: ...

    def repositories(
        self, scope: ReadScope, filters: RepositoryFilters, page: Pagination
    ) -> Page[RepositoryView]: ...

    def jobs(self, scope: ReadScope, filters: JobFilters, page: Pagination) -> Page[JobView]: ...

    def job(self, scope: ReadScope, job_id: UUID) -> JobView | None: ...

    def findings(
        self, scope: ReadScope, job_id: UUID, filters: FindingFilters, page: Pagination
    ) -> Page[FindingView] | None: ...

    def executions(self, scope: ReadScope, job_id: UUID) -> tuple[ExecutionView, ...]: ...
