from typing import Protocol
from uuid import UUID

from shrike.application.queries import FindingFilters, JobFilters, Pagination, RepositoryFilters
from shrike.application.views import Page
from shrike.domain.access import ReadScope
from shrike.domain.dashboard import (
    AttemptView,
    CoverageView,
    FindingDetail,
    MetricsView,
    OperationalView,
    PublicationView,
    RepositoryCard,
    ReviewRow,
)


class DashboardReader(Protocol):
    def repositories(
        self, scope: ReadScope, filters: RepositoryFilters, page: Pagination
    ) -> Page[RepositoryCard]: ...
    def reviews(
        self, scope: ReadScope, filters: JobFilters, page: Pagination
    ) -> Page[ReviewRow]: ...
    def review(self, scope: ReadScope, job_id: UUID) -> ReviewRow | None: ...
    def finding_details(
        self, scope: ReadScope, job_id: UUID, filters: FindingFilters, page: Pagination
    ) -> Page[FindingDetail] | None: ...
    def publication(self, scope: ReadScope, job_id: UUID) -> PublicationView | None: ...
    def coverage(
        self, scope: ReadScope, job_id: UUID
    ) -> tuple[CoverageView | None, str | None]: ...
    def attempts(self, scope: ReadScope, job_id: UUID) -> tuple[AttemptView, ...]: ...
    def metrics(self, scope: ReadScope, window: int) -> MetricsView: ...
    def operations(self, scope: ReadScope) -> OperationalView: ...
