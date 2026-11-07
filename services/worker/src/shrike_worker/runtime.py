import threading
from datetime import UTC, datetime

from shrike.adapters.analysis.ruff import RuffAnalyzer
from shrike.adapters.github.client import GitHubAppClient
from shrike.adapters.llm.mock import MockProvider
from shrike.adapters.persistence.analysis import SqlAnalysisStore
from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.execution import SqlExecutionStore, SqlProviderAdmission
from shrike.adapters.persistence.ingestion import SqlIngestionStore
from shrike.analysis_config import AnalysisSettings
from shrike.application.execution import execute_review
from shrike.application.ingestion import process_one
from shrike.application.review import ReviewEngine
from shrike.config import Settings
from shrike.domain.access import ReadScope, RepositoryGrant
from shrike.domain.queue import Envelope, ReviewClaim
from shrike.domain.review import Candidate, Report, ReviewError, ReviewInput, SelectedFile
from shrike.ports.github import GitHubGateway
from shrike.ports.review import Analyzer

from .config import QueueSettings
from .logging import configure_logging


class FencedAnalysisStore(SqlAnalysisStore):
    def __init__(
        self, database: Database, executions: SqlExecutionStore, claim: ReviewClaim
    ) -> None:
        super().__init__(
            database, ReadScope((RepositoryGrant(claim.installation_id, claim.repository_id),))
        )
        self.executions, self.claim = executions, claim

    def authorize(self, request: ReviewInput) -> None:
        self.executions.checkpoint(self.claim)
        super().authorize(request)

    def cached(self, request: ReviewInput, digest: str) -> Report | None:
        self.authorize(request)
        return super().cached(request, digest)

    def save(self, request: ReviewInput, digest: str, report: Report) -> None:
        self.authorize(request)
        super().save(request, digest, report)


class GuardedAnalyzer:
    def __init__(self, store: SqlExecutionStore, claim: ReviewClaim, analyzer: Analyzer) -> None:
        self.store, self.claim, self.analyzer = store, claim, analyzer
        self.version = analyzer.version

    def analyze(self, file: SelectedFile) -> tuple[Candidate, ...]:
        self.store.checkpoint(self.claim)
        remaining = (self.claim.deadline - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            raise ReviewError("review_deadline")
        analyzer = (
            RuffAnalyzer(timeout=min(30, remaining))
            if isinstance(self.analyzer, RuffAnalyzer)
            else self.analyzer
        )
        result = analyzer.analyze(file)
        self.store.checkpoint(self.claim)
        return result


class Runtime:
    def __init__(
        self,
        database: Database,
        github: GitHubGateway,
        app_id: int,
        settings: QueueSettings,
        analysis: AnalysisSettings | None = None,
        analyzer: Analyzer | None = None,
    ) -> None:
        self.database, self.github, self.app_id, self.settings = database, github, app_id, settings
        self.analysis = analysis or AnalysisSettings()
        if self.analysis.provider != "mock":
            raise ReviewError("queued_provider_must_be_mock")
        self.analyzer = analyzer or RuffAnalyzer()
        self.executions = SqlExecutionStore(
            database,
            lease_seconds=settings.lease_seconds,
            deadline_seconds=settings.deadline_seconds,
            retry_base_seconds=settings.retry_base_seconds,
            repository_limit=settings.repository_limit,
        )
        self.logger = configure_logging()

    def consume(self, envelope: Envelope) -> None:
        if envelope.kind == "ingestion":
            from sqlalchemy import select

            from shrike.adapters.persistence.models import QueueMessage, WebhookDelivery

            with self.database.session() as session:
                row = session.scalar(
                    select(QueueMessage).where(
                        QueueMessage.kind == "ingestion",
                        QueueMessage.record_id == envelope.record_id,
                    )
                )
                if row is None or row.generation != envelope.generation:
                    return
                request_id = row.request_id
            process_one(
                SqlIngestionStore(
                    self.database, envelope.record_id, lease_seconds=self.settings.lease_seconds
                ),
                self.github,
                self.app_id,
            )
            with self.database.session() as session:
                receipt = session.get(WebhookDelivery, envelope.record_id)
                outcome = receipt.state if receipt else "unavailable"
                code = receipt.reason if receipt else None
            self.logger.info(
                "processed",
                extra={
                    "kind": "ingestion",
                    "record_id": str(envelope.record_id),
                    "request_id": str(request_id),
                    "outcome": outcome,
                    "error_code": code,
                },
            )
            return

        done = threading.Event()
        heartbeats: list[threading.Thread] = []

        def engine_factory(claim: ReviewClaim) -> ReviewEngine:
            def heartbeat() -> None:
                while not done.wait(min(5, self.settings.lease_seconds / 3)):
                    try:
                        self.executions.checkpoint(claim)
                    except Exception:
                        return

            thread = threading.Thread(target=heartbeat, daemon=True)
            thread.start()
            heartbeats.append(thread)
            return ReviewEngine(
                GuardedAnalyzer(self.executions, claim, self.analyzer),
                MockProvider(),
                FencedAnalysisStore(self.database, self.executions, claim),
                self.analysis.limits(),
                admission=SqlProviderAdmission(
                    self.database, "mock:mock-v1", self.settings.provider_rpm
                ),
            )

        try:
            claim = execute_review(
                envelope, self.executions, self.github, self.app_id, engine_factory
            )
            if claim is not None:
                from shrike.adapters.persistence.models import ReviewJob

                with self.database.session() as session:
                    job = session.get(ReviewJob, claim.id)
                    outcome = job.state.value if job else "unavailable"
                    code = job.error_code if job else None
                self.logger.info(
                    "processed",
                    extra={
                        "kind": "review",
                        "job_id": str(claim.id),
                        "request_id": str(claim.request_id),
                        "attempt": claim.attempt,
                        "outcome": outcome,
                        "error_code": code,
                    },
                )
        finally:
            done.set()
            for thread in heartbeats:
                thread.join(timeout=6)


def consume_default(envelope: Envelope) -> None:
    settings, queue = Settings(), QueueSettings()
    if settings.github_mode != "live" or settings.github_app_private_key_path is None:
        raise ReviewError("github_not_configured")
    with settings.github_app_private_key_path.open("rb") as handle:
        key = handle.read(65537)
    if len(key) > 65536:
        raise ReviewError("invalid_github_key")
    database = Database(settings.database_url.get_secret_value())
    github = GitHubAppClient(
        settings.github_app_id,
        key,
        client_id=settings.github_app_client_id,
        max_files=settings.review_max_files,
        max_file_bytes=settings.review_max_file_bytes,
        max_diff_bytes=settings.review_max_diff_bytes,
    )
    try:
        Runtime(database, github, settings.github_app_id, queue).consume(envelope)
    finally:
        github.close()
        database.dispose()
