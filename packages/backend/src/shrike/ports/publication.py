from typing import Protocol
from uuid import UUID

from shrike.domain.access import ReadScope
from shrike.domain.github import GitHubRepository
from shrike.domain.publication import (
    PublicationClaim,
    PublicationOutcome,
    PublicationPlan,
    PublishedComment,
    PublishedReview,
)
from shrike.domain.review import Report
from shrike.ports.github import GitHubGateway


class PublicationGateway(GitHubGateway, Protocol):
    def reviews(
        self, installation_id: int, repository: GitHubRepository, number: int
    ) -> tuple[PublishedReview, ...]: ...

    def review_comments(
        self, installation_id: int, repository: GitHubRepository, number: int, review_id: int
    ) -> tuple[PublishedComment, ...]: ...

    def create_review(
        self,
        installation_id: int,
        repository: GitHubRepository,
        number: int,
        head_sha: str,
        plan: PublicationPlan,
    ) -> PublishedReview: ...


class PublicationStore(Protocol):
    def preview(self, job_id: UUID, scope: ReadScope) -> tuple[Report, str]: ...

    def claim(self, job_id: UUID, scope: ReadScope) -> PublicationClaim | None: ...

    def checkpoint(self, claim: PublicationClaim, *, current: bool = False) -> None: ...

    def begin_write(self, claim: PublicationClaim, plan: PublicationPlan) -> None: ...

    def finish(self, claim: PublicationClaim, outcome: PublicationOutcome) -> None: ...
