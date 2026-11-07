from datetime import UTC, datetime, timedelta
from urllib.parse import quote
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from shrike.adapters.persistence.history import SqlHistoryReader, access_predicate
from shrike.adapters.persistence.models import (
    Installation,
    QueueMessage,
    Repository,
    ReviewFinding,
    ReviewJob,
    ReviewPublication,
)
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
from shrike.domain.states import JobState, Severity


class SqlDashboardReader:
    def __init__(self, session: Session) -> None:
        self.session, self.history = session, SqlHistoryReader(session)

    def _ids(self, scope: ReadScope) -> Select[UUID]:
        return select(Repository.id).join(Installation).where(access_predicate(scope))

    def repositories(
        self, scope: ReadScope, filters: RepositoryFilters, page: Pagination
    ) -> Page[RepositoryCard]:
        result = self.history.repositories(scope, filters, page)
        items = []
        for repo in result.items:
            state = self.session.scalar(
                select(ReviewJob.state)
                .where(ReviewJob.repository_id == repo.id)
                .order_by(ReviewJob.created_at.desc(), ReviewJob.id.desc())
                .limit(1)
            )
            count = (
                self.session.scalar(
                    select(func.count())
                    .select_from(ReviewJob)
                    .where(ReviewJob.repository_id == repo.id)
                )
                or 0
            )
            items.append(
                RepositoryCard(
                    id=repo.id,
                    owner=repo.owner,
                    name=repo.name,
                    private=repo.private,
                    installation_github_id=repo.installation_github_id,
                    latest_state=state,
                    review_count=count,
                )
            )
        return Page(tuple(items), result.next_cursor)

    def review(self, scope: ReadScope, job_id: UUID) -> ReviewRow | None:
        job = self.history.job(scope, job_id)
        if job is None:
            return None
        repo = self.history.repository(scope, job.repository_id)
        if repo is None:
            return None
        return ReviewRow(
            id=job.id,
            repository_id=repo.id,
            repository_owner=repo.owner,
            repository_name=repo.name,
            pr_number=job.pull_request_number,
            head_sha=job.head_sha,
            state=job.state,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            finding_count=job.finding_count,
        )

    def reviews(self, scope: ReadScope, filters: JobFilters, page: Pagination) -> Page[ReviewRow]:
        result = self.history.jobs(scope, filters, page)
        items = tuple(
            row for job in result.items if (row := self.review(scope, job.id)) is not None
        )
        return Page(items, result.next_cursor)

    def finding_details(
        self, scope: ReadScope, job_id: UUID, filters: FindingFilters, page: Pagination
    ) -> Page[FindingDetail] | None:
        review = self.review(scope, job_id)
        findings = self.history.findings(scope, job_id, filters, page)
        if review is None or findings is None:
            return None
        job = self.session.get(ReviewJob, job_id)
        assert job
        # Only bounded evidence already validated and persisted by the analysis engine.
        reports = job.result.get("findings", []) if job.result else []
        evidence = {
            (f.get("path"), f.get("line"), f.get("rule")): f.get("evidence")
            for f in reports
            if isinstance(f, dict)
        }
        root = (
            f"https://github.com/{quote(review.repository_owner, safe='')}/"
            f"{quote(review.repository_name, safe='')}/blob/{review.head_sha}/"
        )
        items = []
        for finding in findings.items:
            explanation, _, suggestion = finding.message.partition("\nSuggestion: ")
            snippet = evidence.get((finding.path, finding.line_start, finding.rule_id))
            items.append(
                FindingDetail(
                    id=finding.id,
                    severity=finding.severity,
                    source=finding.source,
                    rule_id=finding.rule_id,
                    path=finding.path,
                    line=finding.line_start,
                    explanation=explanation,
                    suggestion=suggestion or None,
                    snippet=snippet[:500] if isinstance(snippet, str) else None,
                    github_url=root + quote(finding.path, safe="/") + f"#L{finding.line_start}",
                )
            )
        return Page(tuple(items), findings.next_cursor)

    def publication(self, scope: ReadScope, job_id: UUID) -> PublicationView | None:
        if self.review(scope, job_id) is None:
            return None
        publication = self.session.get(ReviewPublication, job_id)
        if not publication:
            return PublicationView(
                state="not_requested", review_id=None, comment_ids=[], reason=None
            )
        return PublicationView(
            state=publication.state,
            review_id=publication.review_id,
            comment_ids=publication.comment_ids,
            reason=publication.reason,
        )

    def coverage(self, scope: ReadScope, job_id: UUID) -> tuple[CoverageView | None, str | None]:
        if self.review(scope, job_id) is None:
            return None, None
        job = self.session.get(ReviewJob, job_id)
        if not job or not job.result:
            return None, None
        coverage = job.result.get("coverage", {})
        return CoverageView(
            selected_files=coverage.get("selected_files", 0),
            skipped_files=sum(coverage.get("skipped", {}).values()),
            changed_lines=coverage.get("changed_lines", 0),
        ), job.result.get("status")

    def attempts(self, scope: ReadScope, job_id: UUID) -> tuple[AttemptView, ...]:
        return tuple(
            AttemptView(
                attempt=e.attempt,
                state=e.state,
                duration_ms=e.duration_ms,
                provider=e.provider,
                error_code=e.error_code,
            )
            for e in self.history.executions(scope, job_id)
        )

    def metrics(self, scope: ReadScope, window: int, *, now: datetime | None = None) -> MetricsView:
        now = now or datetime.now(UTC)
        repo_ids = self._ids(scope)
        jobs = select(ReviewJob.id).where(
            ReviewJob.repository_id.in_(repo_ids),
            ReviewJob.created_at >= now - timedelta(days=window),
            ReviewJob.created_at <= now,
        )
        counts = dict(
            self.session.execute(
                select(ReviewJob.state, func.count())
                .where(ReviewJob.id.in_(jobs))
                .group_by(ReviewJob.state)
            ).all()
        )
        completed, failed = counts.get(JobState.COMPLETED, 0), counts.get(JobState.FAILED, 0)
        terminal = completed + failed
        seconds = self.session.scalar(
            select(
                func.avg(func.extract("epoch", ReviewJob.finished_at - ReviewJob.started_at))
            ).where(ReviewJob.id.in_(jobs), ReviewJob.state == JobState.COMPLETED)
        )
        severity = dict(
            self.session.execute(
                select(ReviewFinding.severity, func.count())
                .where(ReviewFinding.job_id.in_(jobs))
                .group_by(ReviewFinding.severity)
            ).all()
        )
        days = self.session.execute(
            select(func.date(ReviewJob.created_at), func.count())
            .where(ReviewJob.id.in_(jobs))
            .group_by(func.date(ReviewJob.created_at))
        ).all()
        return MetricsView(
            window_days=window,
            as_of=now,
            repositories=self.session.scalar(
                select(func.count()).select_from(Repository).where(Repository.id.in_(repo_ids))
            )
            or 0,
            reviews=sum(counts.values()),
            findings=sum(severity.values()),
            completed=completed,
            failed=failed,
            success_rate=100 * completed / terminal if terminal else None,
            failure_rate=100 * failed / terminal if terminal else None,
            average_processing_seconds=float(seconds) if seconds is not None else None,
            severity_counts={s.value: severity.get(s, 0) for s in Severity},
            daily_reviews=[{"date": str(day), "reviews": count} for day, count in days],
        )

    def operations(self, scope: ReadScope) -> OperationalView:
        now = datetime.now(UTC)
        ids = select(ReviewJob.id).where(ReviewJob.repository_id.in_(self._ids(scope)))
        aggregate = self.session.execute(
            select(
                func.count().filter(ReviewJob.state == JobState.PENDING).label("pending"),
                func.count().filter(ReviewJob.state == JobState.RUNNING).label("running"),
                func.count()
                .filter(ReviewJob.state == JobState.RUNNING, ReviewJob.lease_expires_at > now)
                .label("active"),
                func.count()
                .filter(
                    ReviewJob.state == JobState.RUNNING,
                    ReviewJob.lease_expires_at.is_(None) | (ReviewJob.lease_expires_at <= now),
                )
                .label("expired"),
                func.count()
                .filter(
                    ReviewJob.state == JobState.PENDING,
                    ReviewJob.available_at > now,
                    ReviewJob.attempt_count > 0,
                )
                .label("retry"),
                func.min(ReviewJob.created_at)
                .filter(ReviewJob.state == JobState.PENDING)
                .label("oldest"),
            ).where(ReviewJob.id.in_(ids))
        ).one()
        undispatched = (
            self.session.scalar(
                select(func.count())
                .select_from(QueueMessage)
                .where(
                    QueueMessage.kind == "review",
                    QueueMessage.record_id.in_(ids),
                    QueueMessage.published_at.is_(None),
                )
            )
            or 0
        )
        uncertain = (
            self.session.scalar(
                select(func.count())
                .select_from(ReviewPublication)
                .where(
                    ReviewPublication.job_id.in_(ids),
                    ReviewPublication.state.in_(["inflight", "uncertain", "partial"]),
                )
            )
            or 0
        )
        return OperationalView(
            as_of=now,
            database="reachable",
            pending=aggregate.pending,
            running=aggregate.running,
            active_leases=aggregate.active,
            expired_leases=aggregate.expired,
            retry_wait=aggregate.retry,
            undispatched=undispatched,
            uncertain_publications=uncertain,
            oldest_pending_seconds=max(0, (now - aggregate.oldest).total_seconds())
            if aggregate.oldest
            else None,
        )
