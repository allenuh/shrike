from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import FastAPI, Query, Request
from fastapi.responses import Response
from sqlalchemy import text
from starlette.middleware.base import RequestResponseEndpoint

from shrike.adapters.persistence.database import Database
from shrike.application.queries import FindingFilters, JobFilters, Pagination, RepositoryFilters
from shrike.application.views import JobDetail
from shrike.config import Settings

from .dependencies import Reader, Scope
from .errors import ApiError, error_response, register_errors
from .logging import configure_logging
from .schemas import (
    ErrorResponse,
    FindingQuery,
    FindingResponse,
    JobDetailResponse,
    JobQuery,
    JobResponse,
    PageResponse,
    RepositoryQuery,
    RepositoryResponse,
)
from .webhooks import router as webhook_router


def create_app(settings: Settings | None = None, database: Database | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()
    db = database if database is not None else Database(config.database_url.get_secret_value())
    logger = configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if database is None:
                db.dispose()

    app = FastAPI(
        title="Shrike backend",
        version="0.1.0",
        description="Read API. Development authentication is opt-in; real user login is deferred.",
        docs_url="/docs" if config.app_env != "production" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if config.app_env != "production" else None,
        lifespan=lifespan,
        responses={status: {"model": ErrorResponse} for status in (401, 404, 422, 500, 503)},
    )
    app.state.settings, app.state.database = config, db
    register_errors(app)
    app.include_router(webhook_router)

    @app.middleware("http")
    async def request_metadata(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.request_id = str(uuid4())
        start = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            response = error_response(request, 500, "internal_error", "An internal error occurred")
        response.headers["X-Request-ID"] = request.state.request_id
        logger.info(
            "request",
            extra={
                "request_id": request.state.request_id,
                "method": request.method if request.method in {"GET", "HEAD"} else "OTHER",
                "status": response.status_code,
                "duration_ms": round((perf_counter() - start) * 1000, 2),
            },
        )
        return response

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready() -> dict[str, str]:
        with db.session() as session:
            revision = session.scalar(text("SELECT version_num FROM alembic_version"))
        if revision != "0004_outbox":
            raise ApiError(503, "schema_not_ready", "Database schema is not ready")
        return {"status": "ready"}

    @app.get("/v1/repositories", response_model=PageResponse[RepositoryResponse])
    def repositories(
        scope: Scope, reader: Reader, query: Annotated[RepositoryQuery, Query()]
    ) -> PageResponse[RepositoryResponse]:
        result = reader.repositories(
            scope,
            RepositoryFilters(query.installation_id, query.private, query.search, query.sort),
            Pagination(query.limit, query.cursor, query.order),
        )
        return PageResponse[RepositoryResponse].model_validate(result)

    @app.get("/v1/repositories/{repository_id}", response_model=RepositoryResponse)
    def repository(repository_id: UUID, scope: Scope, reader: Reader) -> RepositoryResponse:
        result = reader.repository(scope, repository_id)
        if result is None:
            raise ApiError(404, "not_found", "Resource not found")
        return RepositoryResponse.model_validate(result)

    @app.get("/v1/review-jobs", response_model=PageResponse[JobResponse])
    def jobs(
        scope: Scope, reader: Reader, query: Annotated[JobQuery, Query()]
    ) -> PageResponse[JobResponse]:
        result = reader.jobs(
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
        return PageResponse[JobResponse].model_validate(result)

    @app.get("/v1/review-jobs/{job_id}", response_model=JobDetailResponse)
    def job(job_id: UUID, scope: Scope, reader: Reader) -> JobDetailResponse:
        result = reader.job(scope, job_id)
        findings = reader.findings(scope, job_id, FindingFilters(), Pagination())
        if result is None or findings is None:
            raise ApiError(404, "not_found", "Resource not found")
        detail = JobDetail(result, findings, reader.executions(scope, job_id))
        return JobDetailResponse.model_validate(detail)

    @app.get("/v1/review-jobs/{job_id}/findings", response_model=PageResponse[FindingResponse])
    def findings(
        job_id: UUID, scope: Scope, reader: Reader, query: Annotated[FindingQuery, Query()]
    ) -> PageResponse[FindingResponse]:
        result = reader.findings(
            scope,
            job_id,
            FindingFilters(query.severity, query.source, query.sort),
            Pagination(query.limit, query.cursor, query.order),
        )
        if result is None:
            raise ApiError(404, "not_found", "Resource not found")
        return PageResponse[FindingResponse].model_validate(result)

    return app
