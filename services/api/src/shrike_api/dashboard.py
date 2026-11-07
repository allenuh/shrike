from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from shrike.application.queries import FindingFilters, JobFilters, Pagination, RepositoryFilters
from shrike.config import Settings
from shrike.domain.dashboard import (
    AttemptView,
    CoverageView,
    FindingDetail,
    MetricsView,
    OperationalView,
    PolicyView,
    PublicationView,
    RepositoryCard,
    ReviewRow,
)

from .dependencies import Dashboard, Scope
from .errors import ApiError
from .schemas import FindingQuery, JobQuery, PageResponse, RepositoryQuery

router = APIRouter(prefix="/v1/dashboard")


class DetailResponse(BaseModel):
    review: ReviewRow
    findings: PageResponse[FindingDetail]
    attempts: list[AttemptView]
    coverage: CoverageView | None
    analysis_status: str | None
    publication: PublicationView | None


@router.get("/repositories", response_model=PageResponse[RepositoryCard])
def repositories(
    reader: Dashboard, scope: Scope, query: Annotated[RepositoryQuery, Query()]
) -> object:
    return reader.repositories(
        scope,
        RepositoryFilters(query.installation_id, query.private, query.search, query.sort),
        Pagination(query.limit, query.cursor, query.order),
    )


@router.get("/reviews", response_model=PageResponse[ReviewRow])
def reviews(reader: Dashboard, scope: Scope, query: Annotated[JobQuery, Query()]) -> object:
    return reader.reviews(
        scope,
        JobFilters(
            query.installation_id,
            query.repository_id,
            query.pull_request_number,
            query.state,
            query.created_after,
            query.created_before,
            query.sort,
        ),
        Pagination(query.limit, query.cursor, query.order),
    )


@router.get("/reviews/{job_id}", response_model=DetailResponse)
def detail(
    job_id: UUID, reader: Dashboard, scope: Scope, query: Annotated[FindingQuery, Query()]
) -> object:
    review = reader.review(scope, job_id)
    findings = reader.finding_details(
        scope,
        job_id,
        FindingFilters(query.severity, query.source, query.sort),
        Pagination(query.limit, query.cursor, query.order),
    )
    if review is None or findings is None:
        raise ApiError(404, "not_found", "Resource not found")
    coverage, status = reader.coverage(scope, job_id)
    return {
        "review": review,
        "findings": findings,
        "attempts": reader.attempts(scope, job_id),
        "coverage": coverage,
        "analysis_status": status,
        "publication": reader.publication(scope, job_id),
    }


@router.get("/metrics", response_model=MetricsView)
def metrics(
    reader: Dashboard, scope: Scope, window_days: int = Query(default=30, ge=1, le=90)
) -> object:
    return reader.metrics(scope, window_days)


@router.get("/operations", response_model=OperationalView)
def operations(reader: Dashboard, scope: Scope) -> object:
    return reader.operations(scope)


@router.get("/settings", response_model=PolicyView)
def settings(request: Request, scope: Scope) -> PolicyView:
    config = cast(Settings, request.app.state.settings)
    return PolicyView(
        authentication="github_app" if config.github_user_auth_enabled else "development",
        ai_provider="mock",
        publishing="explicit_opt_in" if config.github_publishing_enabled else "report_only",
    )
