from dataclasses import dataclass
from uuid import UUID

from shrike.domain.github import GitHubInstallation, GitHubPullRequest, GitHubRepository


@dataclass(frozen=True)
class IncomingWebhook:
    event: str
    action: str
    installation_id: int | None = None
    account_id: int | None = None
    account_type: str | None = None
    owner: str | None = None
    name: str | None = None
    repository_id: int | None = None
    pr_id: int | None = None
    number: int | None = None
    base_sha: str | None = None
    head_sha: str | None = None
    head_repository_id: int | None = None
    removed_repositories: tuple[tuple[int, str], ...] = ()
    ignored_reason: str | None = None


@dataclass(frozen=True)
class IngestionClaim:
    id: UUID
    fence: UUID
    generation: int
    incoming: IncomingWebhook
    blocked_reason: str | None = None


@dataclass(frozen=True)
class IngestionResult:
    installation: GitHubInstallation
    repositories: tuple[GitHubRepository, ...]
    pull_request: GitHubPullRequest | None = None
    reason: str | None = None
