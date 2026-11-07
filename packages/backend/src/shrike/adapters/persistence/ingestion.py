import hashlib
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from shrike.domain.github import GitHubRepository
from shrike.domain.ingestion import IncomingWebhook, IngestionClaim, IngestionResult
from shrike.domain.states import InstallationStatus, JobState, PullRequestState, RepositoryStatus

from .database import Database
from .dispatch import enqueue, reschedule
from .models import (
    Installation,
    PullRequest,
    QueueMessage,
    Repository,
    ReviewExecution,
    ReviewJob,
    WebhookDelivery,
)

POLICY_DIGEST = hashlib.sha256(b"shrike-ingestion-v1:trusted-same-repository-only").hexdigest()


class WebhookConflict(ValueError):
    pass


def _cancel(
    session: Session, installation_id: UUID, repository_ids: list[UUID] | None = None
) -> None:
    statement = update(ReviewJob).where(
        ReviewJob.installation_id == installation_id,
        ReviewJob.state.in_([JobState.PENDING, JobState.RUNNING]),
    )
    if repository_ids is not None:
        statement = statement.where(ReviewJob.repository_id.in_(repository_ids))
    session.execute(
        statement.values(
            state=JobState.CANCELED,
            finished_at=datetime.now(UTC),
            publication_eligible=False,
            lease_token=None,
            lease_expires_at=None,
        )
    )
    invalid = update(ReviewJob).where(ReviewJob.installation_id == installation_id)
    if repository_ids is not None:
        invalid = invalid.where(ReviewJob.repository_id.in_(repository_ids))
    session.execute(invalid.values(publication_eligible=False))
    _close_canceled(session, installation_id)


def _close_canceled(session: Session, installation_id: UUID) -> None:
    session.execute(
        update(ReviewExecution)
        .where(
            ReviewExecution.state == JobState.RUNNING,
            ReviewExecution.job_id.in_(
                select(ReviewJob.id).where(
                    ReviewJob.installation_id == installation_id,
                    ReviewJob.state == JobState.CANCELED,
                )
            ),
        )
        .values(state=JobState.CANCELED, finished_at=datetime.now(UTC), error_code="job_canceled")
    )


def accept_delivery(
    session: Session,
    delivery_id: str,
    digest: str,
    incoming: IncomingWebhook,
    request_id: UUID | None = None,
) -> bool:
    """Caller commits receipt and revocations together. Returns False for an exact replay."""
    row_id = session.scalar(
        insert(WebhookDelivery)
        .values(
            id=uuid4(),
            delivery_id=delivery_id,
            body_digest=digest,
            event_type=incoming.event,
            routing=asdict(incoming),
            state="pending",
            attempts=0,
        )
        .on_conflict_do_nothing(index_elements=[WebhookDelivery.delivery_id])
        .returning(WebhookDelivery.id)
    )
    if row_id is None:
        previous = session.scalar(
            select(WebhookDelivery).where(WebhookDelivery.delivery_id == delivery_id)
        )
        assert previous is not None
        if previous.body_digest != digest or previous.event_type != incoming.event:
            raise WebhookConflict("Delivery identity conflict")
        return False
    receipt = session.get(WebhookDelivery, row_id)
    assert receipt is not None
    if incoming.ignored_reason and incoming.installation_id is None:
        _finish(receipt, "ignored", incoming.ignored_reason)
        return True
    assert incoming.installation_id and incoming.account_id and incoming.account_type
    session.execute(
        insert(Installation)
        .values(
            id=uuid4(),
            github_id=incoming.installation_id,
            account_github_id=incoming.account_id,
            account_type=incoming.account_type,
            status=InstallationStatus.SUSPENDED,
            github_verified=False,
            access_generation=0,
        )
        .on_conflict_do_nothing(index_elements=[Installation.github_id])
    )
    installation = session.scalar(
        select(Installation)
        .where(Installation.github_id == incoming.installation_id)
        .with_for_update()
    )
    assert installation is not None
    if (
        installation.account_github_id != incoming.account_id
        or installation.account_type != incoming.account_type
    ):
        raise WebhookConflict("Installation identity conflict")
    receipt.installation_id = installation.id
    if installation.status == InstallationStatus.DELETED:
        _finish(receipt, "ignored", "installation_deleted")
        return True
    if incoming.repository_id:
        assert incoming.owner and incoming.name
        _upsert_repository(
            session,
            installation,
            GitHubRepository(
                incoming.repository_id, incoming.account_id, incoming.owner, incoming.name, True
            ),
            activate=False,
        )
    if incoming.event == "installation" and incoming.action in {"deleted", "suspend"}:
        installation.status = (
            InstallationStatus.DELETED
            if incoming.action == "deleted"
            else InstallationStatus.SUSPENDED
        )
        installation.github_verified = True
        installation.access_generation += 1
        _cancel(session, installation.id)
        _finish(receipt, "completed", "installation_revoked")
    elif incoming.event == "installation_repositories":
        installation.access_generation += 1
        # Switching from all to selected may have an empty removed array. Quarantine until
        # complete canonical inventory is fetched; never leave stale selected-repo grants active.
        if incoming.action == "removed":
            session.execute(
                update(Repository)
                .where(Repository.installation_id == installation.id)
                .values(status=RepositoryStatus.REMOVED, access_blocked=True)
            )
            _cancel(session, installation.id)
        for github_id, name in incoming.removed_repositories:
            repository = _upsert_repository(
                session,
                installation,
                GitHubRepository(
                    github_id, incoming.account_id, incoming.owner or "unknown", name, True
                ),
                activate=False,
            )
            repository.status, repository.access_blocked = RepositoryStatus.REMOVED, True
            _cancel(session, installation.id, [repository.id])
    elif incoming.ignored_reason:
        _finish(receipt, "ignored", incoming.ignored_reason)
    if receipt.state == "pending":
        enqueue(session, "ingestion", receipt.id, request_id)
    return True


def _finish(receipt: WebhookDelivery, state: str, reason: str | None = None) -> None:
    receipt.state, receipt.reason = state, reason
    receipt.processed_at = (
        datetime.now(UTC) if state in {"completed", "ignored", "failed"} else None
    )
    receipt.lease_token, receipt.lease_expires_at = None, None


def _upsert_repository(
    session: Session, installation: Installation, repo: GitHubRepository, *, activate: bool
) -> Repository:
    session.execute(
        insert(Repository)
        .values(
            id=uuid4(),
            installation_id=installation.id,
            github_id=repo.id,
            owner=repo.owner,
            name=repo.name,
            private=repo.private,
            status=RepositoryStatus.REMOVED,
            access_blocked=False,
        )
        .on_conflict_do_nothing(index_elements=[Repository.github_id])
    )
    record = session.scalar(
        select(Repository).where(Repository.github_id == repo.id).with_for_update()
    )
    assert record is not None
    if record.installation_id != installation.id:
        raise WebhookConflict("Repository ownership conflict")
    if activate:
        record.owner, record.name, record.private = repo.owner, repo.name, repo.private
        record.status = RepositoryStatus.REMOVED if repo.archived else RepositoryStatus.ACTIVE
        record.access_blocked = False
    return record


class SqlIngestionStore:
    def __init__(
        self, database: Database, receipt_id: UUID | None = None, lease_seconds: float = 600
    ) -> None:
        self.database = database
        self.receipt_id = receipt_id
        self.lease_seconds = lease_seconds

    def claim(self) -> IngestionClaim | None:
        now = datetime.now(UTC)
        with self.database.session() as session, session.begin():
            receipt = session.scalar(
                select(WebhookDelivery)
                .where(
                    literal(True)
                    if self.receipt_id is None
                    else WebhookDelivery.id == self.receipt_id,
                    or_(
                        (WebhookDelivery.state == "pending")
                        & (WebhookDelivery.available_at <= now),
                        (WebhookDelivery.state == "processing")
                        & (WebhookDelivery.lease_expires_at <= now),
                    ),
                )
                .order_by(WebhookDelivery.created_at, WebhookDelivery.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if receipt is None:
                return None
            if receipt.attempts >= 3:
                _finish(receipt, "failed", "ingestion_attempts_exhausted")
                return None
            installation = session.scalar(
                select(Installation)
                .where(Installation.id == receipt.installation_id)
                .with_for_update()
            )
            assert installation is not None
            # Serialize control-plane snapshots per installation without holding a DB lock
            # during network calls. This prevents an older fetch overwriting a newer head.
            active = session.scalar(
                select(WebhookDelivery.id)
                .where(
                    WebhookDelivery.installation_id == installation.id,
                    WebhookDelivery.id != receipt.id,
                    WebhookDelivery.state == "processing",
                    WebhookDelivery.lease_expires_at > now,
                )
                .limit(1)
            )
            if active is not None:
                return None
            incoming = IncomingWebhook(**receipt.routing)
            blocked = None
            if installation.status == InstallationStatus.DELETED:
                blocked = "installation_deleted"
            elif (
                installation.github_verified
                and installation.status == InstallationStatus.SUSPENDED
                and incoming.action not in {"unsuspend", "created"}
            ):
                blocked = "installation_suspended"
            if incoming.repository_id:
                repository = session.scalar(
                    select(Repository).where(Repository.github_id == incoming.repository_id)
                )
                if repository is not None and repository.access_blocked:
                    blocked = "repository_removed"
            fence = uuid4()
            receipt.state, receipt.lease_token = "processing", fence
            receipt.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
            receipt.attempts += 1
            return IngestionClaim(
                receipt.id, fence, installation.access_generation, incoming, blocked
            )

    def _locked(
        self, session: Session, claim: IngestionClaim
    ) -> tuple[WebhookDelivery, Installation] | None:
        receipt = session.scalar(
            select(WebhookDelivery).where(WebhookDelivery.id == claim.id).with_for_update()
        )
        if (
            receipt is None
            or receipt.state != "processing"
            or receipt.lease_token != claim.fence
            or receipt.lease_expires_at is None
            or receipt.lease_expires_at <= datetime.now(UTC)
        ):
            return None
        installation = session.scalar(
            select(Installation).where(Installation.id == receipt.installation_id).with_for_update()
        )
        assert installation is not None
        if installation.access_generation != claim.generation:
            _finish(receipt, "pending", "installation_changed")
            receipt.available_at = datetime.now(UTC)
            reschedule(session, "ingestion", receipt.id, receipt.available_at)
            return None
        return receipt, installation

    def complete(self, claim: IngestionClaim, result: IngestionResult) -> None:
        with self.database.session() as session, session.begin():
            locked = self._locked(session, claim)
            if locked is None:
                return
            receipt, installation = locked
            if installation.status == InstallationStatus.DELETED:
                _finish(receipt, "ignored", "installation_deleted")
                return
            installation.github_verified = True
            installation.status = (
                InstallationStatus.SUSPENDED
                if result.installation.suspended
                else InstallationStatus.ACTIVE
            )
            if result.installation.suspended:
                installation.access_generation += 1
                _cancel(session, installation.id)
                _finish(receipt, "ignored", "installation_suspended")
                return
            inventory = claim.incoming.event != "pull_request"
            if inventory:
                session.execute(
                    update(Repository)
                    .where(Repository.installation_id == installation.id)
                    .values(status=RepositoryStatus.REMOVED, access_blocked=True)
                )
            records = [
                _upsert_repository(session, installation, repo, activate=True)
                for repo in result.repositories
            ]
            if inventory:
                session.flush()
                removed = list(
                    session.scalars(
                        select(Repository.id).where(
                            Repository.installation_id == installation.id,
                            Repository.status == RepositoryStatus.REMOVED,
                        )
                    )
                )
                _cancel(session, installation.id, removed)
            pr_data = result.pull_request
            if pr_data is not None:
                repository = records[0]
                session.execute(
                    insert(PullRequest)
                    .values(
                        id=uuid4(),
                        repository_id=repository.id,
                        github_id=pr_data.id,
                        number=pr_data.number,
                        state=PullRequestState.OPEN
                        if pr_data.state == "open"
                        else PullRequestState.CLOSED,
                        draft=pr_data.draft,
                        base_sha=pr_data.base_sha,
                        head_sha=pr_data.head_sha,
                    )
                    .on_conflict_do_nothing(index_elements=[PullRequest.github_id])
                )
                pr = session.scalar(
                    select(PullRequest).where(PullRequest.github_id == pr_data.id).with_for_update()
                )
                assert pr is not None
                if pr.repository_id != repository.id or pr.number != pr_data.number:
                    raise WebhookConflict("Pull request ownership conflict")
                pr.base_sha, pr.head_sha, pr.draft = (
                    pr_data.base_sha,
                    pr_data.head_sha,
                    pr_data.draft,
                )
                pr.state = (
                    PullRequestState.OPEN if pr_data.state == "open" else PullRequestState.CLOSED
                )
                session.execute(
                    update(ReviewJob)
                    .where(
                        ReviewJob.pull_request_id == pr.id,
                        ReviewJob.state.in_([JobState.PENDING, JobState.RUNNING]),
                        or_(
                            ReviewJob.head_sha != pr.head_sha,
                            ReviewJob.base_sha != pr.base_sha,
                            literal(result.reason is not None),
                        ),
                    )
                    .values(
                        state=JobState.CANCELED,
                        finished_at=datetime.now(UTC),
                        lease_token=None,
                        lease_expires_at=None,
                        publication_eligible=False,
                        error_code="superseded",
                    )
                )
                session.execute(
                    update(ReviewJob)
                    .where(
                        ReviewJob.pull_request_id == pr.id,
                        or_(
                            ReviewJob.head_sha != pr.head_sha,
                            ReviewJob.base_sha != pr.base_sha,
                            literal(result.reason is not None),
                        ),
                    )
                    .values(publication_eligible=False)
                )
                _close_canceled(session, installation.id)
                if result.reason is None:
                    job_id = session.scalar(
                        insert(ReviewJob)
                        .values(
                            id=uuid4(),
                            installation_id=installation.id,
                            repository_id=repository.id,
                            pull_request_id=pr.id,
                            base_sha=pr.base_sha,
                            head_sha=pr.head_sha,
                            policy_digest=POLICY_DIGEST,
                            state=JobState.PENDING,
                        )
                        .on_conflict_do_nothing(constraint="uq_job_analysis_identity")
                        .returning(ReviewJob.id)
                    )
                    if job_id is None:
                        job_id = session.scalar(
                            select(ReviewJob.id).where(
                                ReviewJob.pull_request_id == pr.id,
                                ReviewJob.base_sha == pr.base_sha,
                                ReviewJob.head_sha == pr.head_sha,
                                ReviewJob.policy_digest == POLICY_DIGEST,
                            )
                        )
                    assert job_id is not None
                    message = session.scalar(
                        select(QueueMessage).where(
                            QueueMessage.kind == "ingestion", QueueMessage.record_id == receipt.id
                        )
                    )
                    enqueue(
                        session, "review", job_id, message.request_id if message else receipt.id
                    )
            _finish(receipt, "ignored" if result.reason else "completed", result.reason)

    def fail(self, claim: IngestionClaim, code: str, retry_at: datetime | None = None) -> None:
        with self.database.session() as session, session.begin():
            locked = self._locked(session, claim)
            if locked is None:
                return
            receipt, installation = locked
            if retry_at is not None and receipt.attempts < 3:
                _finish(receipt, "pending", code)
                receipt.available_at = max(datetime.now(UTC), retry_at)
                reschedule(session, "ingestion", receipt.id, receipt.available_at)
            else:
                _finish(receipt, "failed", code)
                if code in {
                    "github_not_found",
                    "github_access_denied",
                    "installation_unavailable",
                    "installation_inaccessible",
                }:
                    if (
                        code in {"installation_unavailable", "installation_inaccessible"}
                        or claim.incoming.event != "pull_request"
                    ):
                        installation.status = (
                            InstallationStatus.SUSPENDED
                            if code in {"github_access_denied", "installation_inaccessible"}
                            else InstallationStatus.DELETED
                        )
                        installation.github_verified = True
                        installation.access_generation += 1
                        _cancel(session, installation.id)
                    elif claim.incoming.repository_id:
                        repo = session.scalar(
                            select(Repository).where(
                                Repository.github_id == claim.incoming.repository_id
                            )
                        )
                        if repo:
                            repo.status, repo.access_blocked = RepositoryStatus.REMOVED, True
                            _cancel(session, installation.id, [repo.id])
