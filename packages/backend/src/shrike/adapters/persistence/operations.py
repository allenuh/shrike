"""Explicitly development-only job metadata and bounded manual retry."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, or_, select

from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.dispatch import reschedule
from shrike.adapters.persistence.execution import SqlExecutionStore
from shrike.adapters.persistence.models import Installation, Repository, ReviewJob
from shrike.domain.access import ReadScope
from shrike.domain.review import ReviewError
from shrike.domain.states import InstallationStatus, JobState, RepositoryStatus


class DevJobOperations:
    def __init__(
        self, database: Database, scope: ReadScope, *, environment: str, enabled: bool
    ) -> None:
        if environment != "development" or not enabled:
            raise ReviewError("development_operations_disabled")
        self.database, self.scope = database, scope

    def inspect(
        self, job_id: UUID | None = None, state: JobState | None = None, limit: int = 20
    ) -> list[dict[str, object]]:
        if not 1 <= limit <= 100:
            raise ReviewError("invalid_inspection_limit")
        if not self.scope.grants:
            raise ReviewError("repository_denied")
        statement = (
            select(ReviewJob)
            .join(Repository, ReviewJob.repository_id == Repository.id)
            .join(Installation, ReviewJob.installation_id == Installation.id)
            .where(
                or_(
                    *(
                        and_(
                            Installation.github_id == grant.installation_github_id,
                            Repository.github_id == grant.repository_github_id,
                        )
                        for grant in self.scope.grants
                    )
                ),
                Repository.status == RepositoryStatus.ACTIVE,
                Repository.access_blocked.is_(False),
                Installation.status == InstallationStatus.ACTIVE,
            )
        )
        if job_id is not None:
            statement = statement.where(ReviewJob.id == job_id)
        if state is not None:
            statement = statement.where(ReviewJob.state == state)
        with self.database.session() as session:
            jobs = list(
                session.scalars(
                    statement.order_by(ReviewJob.created_at.desc(), ReviewJob.id).limit(limit)
                )
            )
            if job_id is not None and not jobs:
                raise ReviewError("job_unavailable")
            return [
                {
                    "job_id": str(job.id),
                    "state": job.state.value,
                    "attempt_count": job.attempt_count,
                    "created_at": job.created_at.isoformat(),
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                    "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                    "available_at": job.available_at.isoformat(),
                    "error_code": job.error_code,
                    "publication_eligible": job.publication_eligible,
                }
                for job in jobs
            ]

    def retry(self, job_id: UUID) -> None:
        self.inspect(job_id)
        store = SqlExecutionStore(self.database)
        with self.database.session() as session, session.begin():
            records = store._records(session, job_id)
            if records is None or not store._current(*records):
                raise ReviewError("job_unavailable")
            job = records[3]
            if job.state != JobState.FAILED or job.attempt_count >= 3:
                raise ReviewError("job_not_retryable")
            job.state, job.started_at, job.finished_at = JobState.PENDING, None, None
            job.lease_token, job.lease_expires_at, job.publication_eligible = None, None, False
            job.available_at, job.error_code = datetime.now(UTC), "manual_retry"
            reschedule(session, "review", job.id, job.available_at)
