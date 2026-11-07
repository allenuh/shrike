from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.dispatch import reschedule
from shrike.adapters.persistence.models import (
    Installation,
    ProviderWindow,
    PullRequest,
    QueueMessage,
    Repository,
    ReviewExecution,
    ReviewFinding,
    ReviewJob,
)
from shrike.domain.queue import Envelope, ReviewClaim
from shrike.domain.review import Report, ReviewError
from shrike.domain.states import (
    FindingSource,
    InstallationStatus,
    JobState,
    PullRequestState,
    RepositoryStatus,
    Severity,
)


def backoff(attempt: int, base: float, identifier: UUID) -> timedelta:
    return timedelta(
        seconds=min(300, base * 2 ** max(0, attempt - 1))
        + (identifier.int % 1000) / 1000 * base / 5
    )


class SqlExecutionStore:
    def __init__(
        self,
        database: Database,
        *,
        lease_seconds: float = 240,
        deadline_seconds: float = 180,
        retry_base_seconds: float = 5,
        repository_limit: int = 1,
    ) -> None:
        if not 0 < deadline_seconds < lease_seconds or not 1 <= repository_limit <= 2:
            raise ValueError("Invalid execution limits")
        self.database = database
        self.lease_seconds, self.deadline_seconds = lease_seconds, deadline_seconds
        self.retry_base_seconds, self.repository_limit = retry_base_seconds, repository_limit

    def _records(
        self, session: Session, job_id: UUID
    ) -> tuple[Installation, Repository, PullRequest, ReviewJob] | None:
        # Always lock in the same ownership order as ingestion, never across external work.
        identities = session.execute(
            select(
                ReviewJob.installation_id, ReviewJob.repository_id, ReviewJob.pull_request_id
            ).where(ReviewJob.id == job_id)
        ).one_or_none()
        if identities is None:
            return None
        installation = session.scalar(
            select(Installation).where(Installation.id == identities[0]).with_for_update()
        )
        repository = session.scalar(
            select(Repository).where(Repository.id == identities[1]).with_for_update()
        )
        pr = session.scalar(
            select(PullRequest).where(PullRequest.id == identities[2]).with_for_update()
        )
        job = session.scalar(select(ReviewJob).where(ReviewJob.id == job_id).with_for_update())
        assert (
            installation is not None
            and repository is not None
            and pr is not None
            and job is not None
        )
        return installation, repository, pr, job

    @staticmethod
    def _current(
        installation: Installation, repository: Repository, pr: PullRequest, job: ReviewJob
    ) -> bool:
        return (
            installation.status == InstallationStatus.ACTIVE
            and installation.github_verified
            and repository.installation_id == installation.id
            and repository.status == RepositoryStatus.ACTIVE
            and not repository.access_blocked
            and pr.repository_id == repository.id
            and pr.state == PullRequestState.OPEN
            and not pr.draft
            and pr.head_sha == job.head_sha
            and pr.base_sha == job.base_sha
        )

    def _end(
        self,
        session: Session,
        job: ReviewJob,
        code: str,
        *,
        transient: bool = False,
        retry_at: datetime | None = None,
        canceled: bool = False,
    ) -> None:
        now = datetime.now(UTC)
        execution = session.scalar(
            select(ReviewExecution).where(
                ReviewExecution.job_id == job.id, ReviewExecution.state == JobState.RUNNING
            )
        )
        if execution is not None:
            execution.state = JobState.CANCELED if canceled else JobState.FAILED
            execution.finished_at, execution.error_code = now, code
            execution.duration_ms = max(0, int((now - execution.started_at).total_seconds() * 1000))
        job.lease_token, job.lease_expires_at, job.publication_eligible = None, None, False
        job.error_code = code
        if transient and not canceled and job.attempt_count < 3:
            due = now + backoff(job.attempt_count, self.retry_base_seconds, job.id)
            job.state, job.started_at, job.finished_at = JobState.PENDING, None, None
            job.available_at = max(due, retry_at or due)
            reschedule(session, "review", job.id, job.available_at)
        else:
            job.state = JobState.CANCELED if canceled else JobState.FAILED
            job.finished_at = now
            if job.started_at is None and not canceled:
                job.started_at = now

    def claim(self, envelope: Envelope) -> ReviewClaim | None:
        now = datetime.now(UTC)
        with self.database.session() as session, session.begin():
            records = self._records(session, envelope.record_id)
            if records is None or envelope.kind != "review":
                return None
            installation, repository, pr, job = records
            message = session.scalar(
                select(QueueMessage).where(
                    QueueMessage.kind == "review", QueueMessage.record_id == job.id
                )
            )
            if message is None or message.generation != envelope.generation:
                return None
            if job.state == JobState.RUNNING and (
                job.lease_expires_at is None or job.lease_expires_at <= now
            ):
                self._end(session, job, "worker_lost", transient=True)
                return None
            if job.state != JobState.PENDING or job.available_at > now:
                return None
            if not self._current(*records):
                self._end(session, job, "stale_or_revoked", canceled=True)
                return None
            active = (
                session.scalar(
                    select(func.count())
                    .select_from(ReviewJob)
                    .where(
                        ReviewJob.repository_id == repository.id,
                        ReviewJob.state == JobState.RUNNING,
                        ReviewJob.lease_expires_at > now,
                    )
                )
                or 0
            )
            if active >= self.repository_limit:
                return None
            if job.attempt_count >= 3:
                self._end(session, job, "attempts_exhausted")
                return None
            job.attempt_count += 1
            job.state, job.started_at, job.finished_at, job.error_code = (
                JobState.RUNNING,
                now,
                None,
                None,
            )
            job.first_started_at = job.first_started_at or now
            job.lease_token, job.lease_expires_at = (
                uuid4(),
                now + timedelta(seconds=self.lease_seconds),
            )
            session.add(
                ReviewExecution(
                    job_id=job.id,
                    attempt=job.attempt_count,
                    state=JobState.RUNNING,
                    started_at=now,
                    worker_identifier=str(job.lease_token),
                )
            )
            return ReviewClaim(
                job.id,
                job.lease_token,
                message.request_id,
                message.generation,
                installation.access_generation,
                installation.github_id,
                installation.account_github_id,
                repository.github_id,
                repository.owner,
                repository.name,
                repository.private,
                pr.github_id,
                pr.number,
                job.base_sha,
                job.head_sha,
                job.attempt_count,
                now + timedelta(seconds=self.deadline_seconds),
            )

    def _owned(
        self, records: tuple[Installation, Repository, PullRequest, ReviewJob], claim: ReviewClaim
    ) -> bool:
        installation, _, _, job = records
        return (
            job.state == JobState.RUNNING
            and job.lease_token == claim.fence
            and job.lease_expires_at is not None
            and job.lease_expires_at > datetime.now(UTC)
            and installation.access_generation == claim.installation_generation
        )

    def checkpoint(self, claim: ReviewClaim) -> None:
        with self.database.session() as session, session.begin():
            records = self._records(session, claim.id)
            if records is None or not self._owned(records, claim) or not self._current(*records):
                raise ReviewError("stale_execution")
            if datetime.now(UTC) >= claim.deadline:
                raise ReviewError("review_deadline")
            records[3].lease_expires_at = datetime.now(UTC) + timedelta(seconds=self.lease_seconds)

    def complete(self, claim: ReviewClaim, report: Report) -> None:
        with self.database.session() as session, session.begin():
            records = self._records(session, claim.id)
            if records is None or not self._owned(records, claim):
                return
            job = records[3]
            if not self._current(*records) or datetime.now(UTC) >= claim.deadline:
                self._end(session, job, "stale_or_expired", canceled=True)
                return
            now = datetime.now(UTC)
            execution = session.scalar(
                select(ReviewExecution).where(
                    ReviewExecution.job_id == job.id, ReviewExecution.attempt == claim.attempt
                )
            )
            assert execution is not None
            execution.state, execution.finished_at = JobState.COMPLETED, now
            execution.duration_ms = max(0, int((now - execution.started_at).total_seconds() * 1000))
            execution.provider, execution.model, execution.prompt_version = (
                report.provider,
                report.model,
                report.prompt_version,
            )
            execution.analyzer_version = report.analyzer_version
            execution.input_tokens, execution.output_tokens = (
                report.input_tokens or 0,
                report.output_tokens or 0,
            )
            execution.usage_reported = (
                report.input_tokens is not None and report.output_tokens is not None
            )
            execution.error_code = report.reason
            session.execute(delete(ReviewFinding).where(ReviewFinding.job_id == job.id))
            for finding in report.findings:
                session.add(
                    ReviewFinding(
                        job_id=job.id,
                        fingerprint=finding.fingerprint,
                        source=FindingSource.RUFF
                        if "ruff" in finding.analyzers
                        else FindingSource.LLM,
                        severity=Severity(finding.severity),
                        rule_id=finding.rule,
                        path=finding.path,
                        line_start=finding.line,
                        line_end=finding.line,
                        message=finding.problem + "\nSuggestion: " + finding.suggestion,
                    )
                )
            job.state, job.finished_at, job.error_code = JobState.COMPLETED, now, report.reason
            job.result, job.publication_eligible = report.model_dump(mode="json"), True
            job.lease_token, job.lease_expires_at = None, None

    def fail(
        self,
        claim: ReviewClaim,
        code: str,
        *,
        transient: bool = False,
        retry_at: datetime | None = None,
        canceled: bool = False,
    ) -> None:
        with self.database.session() as session, session.begin():
            records = self._records(session, claim.id)
            if (
                records is not None
                and records[3].state == JobState.RUNNING
                and records[3].lease_token == claim.fence
                and records[3].lease_expires_at is not None
                and records[3].lease_expires_at > datetime.now(UTC)
            ):
                self._end(
                    session,
                    records[3],
                    code,
                    transient=transient,
                    retry_at=retry_at,
                    canceled=canceled or not self._current(*records),
                )

    def recover(self) -> int:
        now = datetime.now(UTC)
        with self.database.session() as session:
            ids = list(
                session.scalars(
                    select(ReviewJob.id)
                    .where(
                        ReviewJob.state == JobState.RUNNING,
                        (ReviewJob.lease_expires_at.is_(None))
                        | (ReviewJob.lease_expires_at <= now),
                    )
                    .limit(100)
                )
            )
        recovered = 0
        for job_id in ids:
            with self.database.session() as session, session.begin():
                records = self._records(session, job_id)
                if records is not None:
                    job = records[3]
                    if job.state == JobState.RUNNING and (
                        job.lease_expires_at is None or job.lease_expires_at <= now
                    ):
                        self._end(session, job, "worker_lost", transient=True)
                        recovered += 1
        return recovered

    def publication_candidate(self, job_id: UUID) -> bool:
        with self.database.session() as session:
            records = self._records(session, job_id)
            return bool(
                records
                and records[3].state == JobState.COMPLETED
                and records[3].publication_eligible
                and self._current(*records)
            )


class SqlProviderAdmission:
    def __init__(self, database: Database, key: str, requests_per_minute: int) -> None:
        if not 1 <= requests_per_minute <= 6000 or not 1 <= len(key) <= 128:
            raise ValueError("Invalid provider rate")
        self.database, self.key, self.rate = database, key, requests_per_minute

    def acquire(self) -> None:
        with self.database.session() as session, session.begin():
            now = datetime.now(UTC)
            session.execute(
                insert(ProviderWindow).values(key=self.key, next_at=now).on_conflict_do_nothing()
            )
            row = session.scalar(
                select(ProviderWindow).where(ProviderWindow.key == self.key).with_for_update()
            )
            assert row is not None
            if row.next_at > now:
                raise ReviewError("provider_throttled", retry_at=row.next_at)
            row.next_at = now + timedelta(seconds=60 / self.rate)
