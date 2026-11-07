from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import Row, Select, case, false, func, select, tuple_
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from shrike.application.cursors import (
    Cursor,
    InvalidCursor,
    context_digest,
    decode_cursor,
    encode_cursor,
)
from shrike.application.queries import FindingFilters, JobFilters, Pagination, RepositoryFilters
from shrike.application.views import (
    ExecutionView,
    FindingView,
    JobView,
    Page,
    RepositoryView,
)
from shrike.domain.access import ReadScope
from shrike.domain.states import InstallationStatus, JobState, RepositoryStatus, Severity

from .models import Installation, PullRequest, Repository, ReviewExecution, ReviewFinding, ReviewJob

type ReadRow = Row[*tuple[Any, ...]]
type ReadSelect = Select[*tuple[Any, ...]]


def access_predicate(scope: ReadScope) -> ColumnElement[bool]:
    if not scope.grants:
        return false()
    pairs = [(grant.installation_github_id, grant.repository_github_id) for grant in scope.grants]
    return (
        tuple_(Installation.github_id, Repository.github_id).in_(pairs)
        & (Installation.status == InstallationStatus.ACTIVE)
        & (Repository.status == RepositoryStatus.ACTIVE)
        & ~Repository.access_blocked
    )


def _repository_view(row: ReadRow) -> RepositoryView:
    repo, installation_github_id = row[0], row[1]
    return RepositoryView(
        repo.id,
        repo.github_id,
        repo.installation_id,
        installation_github_id,
        repo.owner,
        repo.name,
        repo.private,
        repo.created_at,
    )


def _job_view(row: ReadRow) -> JobView:
    job, number, count = row[0], row[1], row[2]
    return JobView(
        job.id,
        job.installation_id,
        job.repository_id,
        job.pull_request_id,
        number,
        job.base_sha,
        job.head_sha,
        job.state,
        job.created_at,
        job.started_at,
        job.finished_at,
        count,
    )


def _finding_view(row: ReadRow) -> FindingView:
    finding = row[0]
    return FindingView(
        finding.id,
        finding.source,
        finding.severity,
        finding.rule_id,
        finding.path,
        finding.line_start,
        finding.line_end,
        finding.message,
    )


class SqlHistoryReader:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _page[T](
        self,
        statement: ReadSelect,
        column: ColumnElement[Any],
        identity: ColumnElement[UUID],
        kind: Literal["datetime", "string", "state", "rank"],
        context: str,
        page: Pagination,
        view: Callable[[ReadRow], T],
    ) -> Page[T]:
        if not 1 <= page.limit <= 100:
            raise ValueError("Invalid page limit")
        if page.cursor:
            cursor = decode_cursor(page.cursor, context)
            value: object = cursor.value
            try:
                if kind == "datetime":
                    parsed = datetime.fromisoformat(cursor.value)
                    if parsed.utcoffset() is None:
                        raise ValueError
                    value = parsed
                elif kind == "state":
                    value = JobState(cursor.value)
                elif kind == "rank":
                    value = int(cursor.value)
                    if value not in range(5):
                        raise ValueError
            except ValueError:
                raise InvalidCursor("Invalid cursor value") from None
            key = tuple_(column, identity)
            statement = statement.where(
                key > (value, cursor.id) if page.order == "asc" else key < (value, cursor.id)
            )
        columns = (column, identity)
        statement = statement.add_columns(*columns).order_by(
            *(c.asc() if page.order == "asc" else c.desc() for c in columns)
        )
        rows = self.session.execute(statement.limit(page.limit + 1)).all()
        visible = rows[: page.limit]
        next_cursor = None
        if len(rows) > page.limit:
            last_value, last_id = visible[-1][-2:]
            serialized = (
                last_value.isoformat() if isinstance(last_value, datetime) else str(last_value)
            )
            next_cursor = encode_cursor(Cursor(serialized, last_id), context)
        return Page(tuple(view(row) for row in visible), next_cursor)

    def _repository_statement(self, scope: ReadScope) -> ReadSelect:
        return (
            select(Repository, Installation.github_id)
            .join(Installation, Repository.installation_id == Installation.id)
            .where(access_predicate(scope))
        )

    def repository(self, scope: ReadScope, repository_id: UUID) -> RepositoryView | None:
        row = self.session.execute(
            self._repository_statement(scope).where(Repository.id == repository_id)
        ).first()
        return _repository_view(row) if row else None

    def repositories(
        self, scope: ReadScope, filters: RepositoryFilters, page: Pagination
    ) -> Page[RepositoryView]:
        statement = self._repository_statement(scope)
        if filters.installation_id:
            statement = statement.where(Repository.installation_id == filters.installation_id)
        if filters.private is not None:
            statement = statement.where(Repository.private == filters.private)
        if filters.search:
            statement = statement.where(
                (Repository.owner + "/" + Repository.name).icontains(
                    filters.search, autoescape=True
                )
            )
        column = Repository.name if filters.sort == "name" else Repository.created_at
        return self._page(
            statement,
            column.expression,
            Repository.id.expression,
            "string" if filters.sort == "name" else "datetime",
            context_digest("repositories", scope, filters, page.order),
            page,
            _repository_view,
        )

    def _job_statement(self, scope: ReadScope) -> ReadSelect:
        count = (
            select(func.count(ReviewFinding.id))
            .where(ReviewFinding.job_id == ReviewJob.id)
            .correlate(ReviewJob)
            .scalar_subquery()
        )
        return (
            select(ReviewJob, PullRequest.number, count)
            .join(Repository, ReviewJob.repository_id == Repository.id)
            .join(Installation, Repository.installation_id == Installation.id)
            .join(PullRequest, ReviewJob.pull_request_id == PullRequest.id)
            .where(
                access_predicate(scope),
                ReviewJob.installation_id == Installation.id,
                PullRequest.repository_id == Repository.id,
            )
        )

    def job(self, scope: ReadScope, job_id: UUID) -> JobView | None:
        row = self.session.execute(self._job_statement(scope).where(ReviewJob.id == job_id)).first()
        return _job_view(row) if row else None

    def jobs(self, scope: ReadScope, filters: JobFilters, page: Pagination) -> Page[JobView]:
        statement = self._job_statement(scope)
        for filter_column, value in (
            (ReviewJob.installation_id, filters.installation_id),
            (ReviewJob.repository_id, filters.repository_id),
            (PullRequest.number, filters.pull_request_number),
            (ReviewJob.state, filters.state),
        ):
            if value is not None:
                statement = statement.where(filter_column == value)
        if filters.created_after:
            statement = statement.where(ReviewJob.created_at >= filters.created_after)
        if filters.created_before:
            statement = statement.where(ReviewJob.created_at <= filters.created_before)
        column = ReviewJob.state if filters.sort == "state" else ReviewJob.created_at
        return self._page(
            statement,
            column.expression,
            ReviewJob.id.expression,
            "state" if filters.sort == "state" else "datetime",
            context_digest("jobs", scope, filters, page.order),
            page,
            _job_view,
        )

    def _authorized_job_ids(self, scope: ReadScope) -> ReadSelect:
        return (
            select(ReviewJob.id)
            .join(Repository, ReviewJob.repository_id == Repository.id)
            .join(Installation, Repository.installation_id == Installation.id)
            .where(access_predicate(scope), ReviewJob.installation_id == Installation.id)
        )

    def findings(
        self, scope: ReadScope, job_id: UUID, filters: FindingFilters, page: Pagination
    ) -> Page[FindingView] | None:
        if self.job(scope, job_id) is None:
            return None
        statement = select(ReviewFinding).where(
            ReviewFinding.job_id == job_id,
            ReviewFinding.job_id.in_(self._authorized_job_ids(scope)),
        )
        if filters.severity:
            statement = statement.where(ReviewFinding.severity == filters.severity)
        if filters.source:
            statement = statement.where(ReviewFinding.source == filters.source)
        rank = case(
            *((ReviewFinding.severity == severity, rank) for rank, severity in enumerate(Severity)),
            else_=-1,
        )
        column = ReviewFinding.path.expression if filters.sort == "path" else rank
        return self._page(
            statement,
            column,
            ReviewFinding.id.expression,
            "string" if filters.sort == "path" else "rank",
            context_digest("findings", scope, job_id, filters, page.order),
            page,
            _finding_view,
        )

    def executions(self, scope: ReadScope, job_id: UUID) -> tuple[ExecutionView, ...]:
        records = self.session.scalars(
            select(ReviewExecution)
            .where(
                ReviewExecution.job_id == job_id,
                ReviewExecution.job_id.in_(self._authorized_job_ids(scope)),
            )
            .order_by(ReviewExecution.attempt)
        )
        return tuple(
            ExecutionView(
                record.id,
                record.attempt,
                record.state,
                record.started_at,
                record.finished_at,
                record.duration_ms,
                record.input_tokens,
                record.output_tokens,
                record.analyzer_version,
                record.ruleset_version,
                record.prompt_version,
                record.provider,
                record.model,
                record.error_code,
            )
            for record in records
        )
