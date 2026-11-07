import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.execution import SqlExecutionStore
from shrike.adapters.persistence.models import ReviewPublication
from shrike.domain.access import ReadScope, RepositoryGrant
from shrike.domain.publication import PublicationClaim, PublicationOutcome, PublicationPlan
from shrike.domain.queue import ReviewClaim
from shrike.domain.review import Report, ReviewError
from shrike.domain.states import InstallationStatus, JobState, RepositoryStatus


class SqlPublicationStore:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.executions = SqlExecutionStore(database)

    def _read(self, job_id: UUID, scope: ReadScope) -> tuple[Report, ReviewClaim, str]:
        with self.database.session() as session, session.begin():
            records = self.executions.records(session, job_id)
            if not records:
                raise ReviewError("repository_denied")
            installation, repo, pr, job = records
            if (
                RepositoryGrant(installation.github_id, repo.github_id) not in scope.grants
                or installation.status != InstallationStatus.ACTIVE
                or not installation.github_verified
                or repo.status != RepositoryStatus.ACTIVE
                or repo.access_blocked
                or job.state != JobState.COMPLETED
                or job.result is None
            ):
                raise ReviewError("repository_denied")
            report = Report.model_validate(job.result)
            if report.status == "dry_run":
                raise ReviewError("publication_ineligible")
            context = ReviewClaim(
                job.id,
                uuid4(),
                uuid4(),
                0,
                installation.access_generation,
                installation.github_id,
                installation.account_github_id,
                repo.github_id,
                repo.owner,
                repo.name,
                repo.private,
                pr.github_id,
                pr.number,
                job.base_sha,
                job.head_sha,
                0,
                datetime.now(UTC) + timedelta(seconds=120),
            )
            marker = f"<!-- shrike-review:{job.id}:{job.head_sha} -->"
            return report, context, marker

    def preview(self, job_id: UUID, scope: ReadScope) -> tuple[Report, str]:
        report, _, marker = self._read(job_id, scope)
        return report, marker

    def claim(self, job_id: UUID, scope: ReadScope) -> PublicationClaim | None:
        report, context, marker = self._read(job_id, scope)
        now = datetime.now(UTC)
        with self.database.session() as session, session.begin():
            records = self.executions.records(session, job_id)
            assert records is not None
            if records[0].access_generation != context.installation_generation:
                raise ReviewError("stale_publication")
            row = session.get(ReviewPublication, job_id, with_for_update=True)
            if row is None:
                if not self.executions.current(*records) or not records[3].publication_eligible:
                    raise ReviewError("stale_publication")
                row = ReviewPublication(
                    job_id=job_id, marker=marker, state="preparing", available_at=now
                )
                session.add(row)
                session.flush()
            if row.state in {"published", "stale", "suppressed"} or row.available_at > now:
                return None
            if row.lease_expires_at is not None and row.lease_expires_at > now:
                return None
            uncertain = row.state in {"inflight", "uncertain", "partial"}
            if row.attempts >= 3 and not uncertain:
                return None
            row.state = "uncertain" if uncertain else "preparing"
            row.lease_token, row.lease_expires_at = context.fence, context.deadline
            return PublicationClaim(
                context,
                report,
                marker,
                uncertain,
                row.summary_only,
                PublicationPlan.model_validate(row.payload) if row.payload else None,
                row.review_id,
            )

    def checkpoint(self, claim: PublicationClaim, *, current: bool = False) -> None:
        c = claim.context
        with self.database.session() as session, session.begin():
            records = self.executions.records(session, c.id)
            row = session.get(ReviewPublication, c.id, with_for_update=True)
            if not records or row is None:
                raise ReviewError("stale_publication")
            installation, repo, _, job = records
            if (
                row.lease_token != c.fence
                or row.lease_expires_at is None
                or row.lease_expires_at <= datetime.now(UTC)
                or c.deadline <= datetime.now(UTC)
                or installation.access_generation != c.installation_generation
                or installation.status != InstallationStatus.ACTIVE
                or not installation.github_verified
                or repo.status != RepositoryStatus.ACTIVE
                or repo.access_blocked
                or (
                    current
                    and (not self.executions.current(*records) or not job.publication_eligible)
                )
            ):
                raise ReviewError("stale_publication")

    def begin_write(self, claim: PublicationClaim, plan: PublicationPlan) -> None:
        self.checkpoint(claim, current=True)
        with self.database.session() as session, session.begin():
            records = self.executions.records(session, claim.context.id)
            row = session.get(ReviewPublication, claim.context.id, with_for_update=True)
            if (
                not records
                or not self.executions.current(*records)
                or records[0].access_generation != claim.context.installation_generation
                or not records[3].publication_eligible
                or row is None
                or row.state != "preparing"
                or row.lease_token != claim.context.fence
                or row.lease_expires_at is None
                or row.lease_expires_at <= datetime.now(UTC)
                or row.attempts >= 3
                or claim.uncertain
            ):
                raise ReviewError("stale_publication")
            row.payload = plan.model_dump(mode="json")
            row.payload_digest = hashlib.sha256(plan.model_dump_json().encode()).hexdigest()
            row.state, row.attempts = "inflight", row.attempts + 1
            row.updated_at = datetime.now(UTC)

    def finish(self, claim: PublicationClaim, outcome: PublicationOutcome) -> None:
        with self.database.session() as session, session.begin():
            row = session.get(ReviewPublication, claim.context.id, with_for_update=True)
            if row is None or row.lease_token != claim.context.fence:
                return
            row.state, row.reason = outcome.state, outcome.reason
            row.review_id = outcome.review_id or row.review_id
            if outcome.comment_ids:
                row.comment_ids = list(outcome.comment_ids)
            row.summary_only = row.summary_only or outcome.reason == "github_invalid_review"
            row.updated_at = datetime.now(UTC)
            if outcome.state == "failed":
                row.available_at = row.updated_at + timedelta(seconds=60 * max(1, row.attempts))
                row.available_at = max(row.available_at, outcome.retry_at or row.available_at)
            row.lease_token, row.lease_expires_at = None, None
