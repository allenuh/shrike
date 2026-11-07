import hashlib

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.models import (
    AiBudget,
    AiPriceSnapshot,
    AiSpendEntry,
    AnalysisReport,
    Installation,
    Repository,
)
from shrike.domain.access import ReadScope, RepositoryGrant
from shrike.domain.ai_budget import PriceProfile
from shrike.domain.review import Report, ReviewError, ReviewInput
from shrike.domain.states import InstallationStatus, RepositoryStatus


class SqlAnalysisStore:
    def __init__(self, database: Database, scope: ReadScope) -> None:
        self.database, self.scope = database, scope

    def _repository(self, session: Session, request: ReviewInput) -> tuple[Repository, int]:
        if RepositoryGrant(request.installation_id, request.repository_id) not in self.scope.grants:
            raise ReviewError("repository_denied")
        installation = session.scalar(
            select(Installation)
            .where(
                Installation.github_id == request.installation_id,
                Installation.status == InstallationStatus.ACTIVE,
            )
            .with_for_update()
        )
        if installation is None:
            raise ReviewError("repository_denied")
        repository = session.scalar(
            select(Repository)
            .where(
                Repository.github_id == request.repository_id,
                Repository.installation_id == installation.id,
                Repository.status == RepositoryStatus.ACTIVE,
                Repository.access_blocked.is_(False),
            )
            .with_for_update()
        )
        if repository is None or (repository.private and not request.private):
            raise ReviewError("repository_denied")
        return repository, installation.access_generation

    def authorize(self, request: ReviewInput) -> None:
        with self.database.session() as session:
            self._repository(session, request)

    def cached(self, request: ReviewInput, digest: str) -> Report | None:
        with self.database.session() as session:
            repo, generation = self._repository(session, request)
            row = session.scalar(
                select(AnalysisReport).where(
                    AnalysisReport.repository_id == repo.id,
                    AnalysisReport.digest == digest,
                    AnalysisReport.access_generation == generation,
                )
            )
            return None if row is None else Report.model_validate(row.report)

    def save(self, request: ReviewInput, digest: str, report: Report) -> None:
        with self.database.session() as session, session.begin():
            repo, generation = self._repository(session, request)
            session.execute(
                insert(AnalysisReport)
                .values(
                    repository_id=repo.id,
                    digest=digest,
                    access_generation=generation,
                    report=report.model_dump(mode="json"),
                )
                .on_conflict_do_update(
                    constraint="uq_analysis_repository_digest",
                    set_={
                        "report": report.model_dump(mode="json"),
                        "access_generation": generation,
                    },
                )
            )


class SqlSpendingLedger:
    def __init__(
        self,
        database: Database,
        *,
        evaluation_session: str | None = None,
        evaluation_limit: int | None = None,
    ) -> None:
        self.database = database
        self.evaluation_session, self.evaluation_limit = evaluation_session, evaluation_limit

    def reserve(
        self,
        call_id: str,
        amount: int,
        profile: PriceProfile,
        input_bound: int,
        output_bound: int,
        review_key: str = "",
    ) -> bool:
        try:
            with self.database.session() as session, session.begin():
                budget = session.scalar(select(AiBudget).where(AiBudget.id == 1).with_for_update())
                if budget is None or budget.frozen:
                    raise ReviewError("budget_unreconciled")
                profile.check(profile.model, live=True)
                if session.get(AiSpendEntry, call_id) is not None:
                    raise ReviewError("paid_call_already_dispatched")
                if self.evaluation_session is not None:
                    entries = list(
                        session.scalars(
                            select(AiSpendEntry).where(
                                AiSpendEntry.evaluation_session == self.evaluation_session
                            )
                        )
                    )
                    if (
                        self.evaluation_limit is None
                        or not 1 <= self.evaluation_limit <= 5
                        or len(entries) >= self.evaluation_limit
                        or any(entry.evaluation_limit != self.evaluation_limit for entry in entries)
                    ):
                        raise ReviewError("evaluation_request_limit")
                if amount != profile.micro_usd(input_bound, output_bound):
                    raise ReviewError("invalid_cost_reservation")
                exposure = func.coalesce(AiSpendEntry.settled_micro, AiSpendEntry.reserved_micro)
                total = budget.prior_micro + int(
                    session.scalar(select(func.coalesce(func.sum(exposure), 0))) or 0
                )
                review_total = int(
                    session.scalar(
                        select(func.coalesce(func.sum(exposure), 0)).where(
                            AiSpendEntry.review_key == review_key
                        )
                    )
                    or 0
                )
                active = (
                    session.scalar(
                        select(func.count())
                        .select_from(AiSpendEntry)
                        .where(AiSpendEntry.state != "settled")
                    )
                    or 0
                )
                if (
                    amount <= 0
                    or total + amount > budget.hard_micro
                    or review_total + amount > budget.max_review_micro
                ):
                    raise ReviewError("budget_exceeded")
                if active >= budget.max_live:
                    raise ReviewError("live_concurrency_limit")
                encoded = profile.model_dump_json()
                price_id = hashlib.sha256(encoded.encode()).hexdigest()
                session.execute(
                    insert(AiPriceSnapshot)
                    .values(id=price_id, profile=profile.model_dump(mode="json"))
                    .on_conflict_do_nothing()
                )
                session.add(
                    AiSpendEntry(
                        id=call_id,
                        review_key=review_key,
                        price_id=price_id,
                        reserved_micro=amount,
                        input_bound=input_bound,
                        output_bound=output_bound,
                        evaluation_session=self.evaluation_session,
                        evaluation_limit=self.evaluation_limit,
                    )
                )
                return total + amount >= budget.warning_micro
        except SQLAlchemyError:
            raise ReviewError("ledger_unavailable") from None

    def settle(
        self, call_id: str, input_tokens: int | None, output_tokens: int | None
    ) -> int | None:
        try:
            with self.database.session() as session, session.begin():
                budget = session.scalar(select(AiBudget).where(AiBudget.id == 1).with_for_update())
                entry = session.get(AiSpendEntry, call_id)
                if entry is None or budget is None:
                    raise ReviewError("ledger_unavailable")
                if entry.state == "settled":
                    return entry.settled_micro
                if (input_tokens is not None and input_tokens < 0) or (
                    output_tokens is not None and output_tokens < 0
                ):
                    raise ReviewError("invalid_usage")
                entry.input_tokens, entry.output_tokens = input_tokens, output_tokens
                if (input_tokens is not None and input_tokens > entry.input_bound) or (
                    output_tokens is not None and output_tokens > entry.output_bound
                ):
                    budget.frozen = True
                if input_tokens is None or output_tokens is None:
                    entry.state = "uncertain"
                    return None
                snapshot = session.get(AiPriceSnapshot, entry.price_id)
                assert snapshot is not None
                profile = PriceProfile.model_validate(snapshot.profile)
                actual = profile.micro_usd(input_tokens, output_tokens)
                entry.state, entry.settled_micro = "settled", actual
                entry.input_tokens, entry.output_tokens = input_tokens, output_tokens
                if (
                    input_tokens > entry.input_bound
                    or output_tokens > entry.output_bound
                    or actual > entry.reserved_micro
                ):
                    budget.frozen = True
                return actual
        except SQLAlchemyError:
            raise ReviewError("ledger_unavailable") from None


def initialize_budget(
    database: Database,
    prior_micro: int,
    *,
    confirmed: bool,
    warning_micro: int = 7500000,
    hard_micro: int = 9000000,
    total_micro: int = 10000000,
    max_review_micro: int = 20000,
    max_live: int = 1,
) -> None:
    if not confirmed or not 0 <= prior_micro <= 10000000:
        raise ReviewError("budget_reconciliation_required")
    with database.session() as session, session.begin():
        if session.get(AiBudget, 1) is not None:
            raise ReviewError("budget_already_initialized")
        session.add(
            AiBudget(
                id=1,
                prior_micro=prior_micro,
                total_micro=total_micro,
                warning_micro=warning_micro,
                hard_micro=hard_micro,
                max_review_micro=max_review_micro,
                max_live=max_live,
            )
        )
