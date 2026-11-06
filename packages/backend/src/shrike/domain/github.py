from dataclasses import dataclass
from datetime import datetime


class GitHubError(Exception):
    """Safe, fixed code only; never includes HTTP bodies, URLs, or credentials."""

    def __init__(self, code: str, *, retry_at: datetime | None = None) -> None:
        super().__init__(code)
        self.code, self.retry_at = code, retry_at


@dataclass(frozen=True)
class GitHubInstallation:
    id: int
    app_id: int
    account_id: int
    account_type: str
    suspended: bool


@dataclass(frozen=True)
class GitHubRepository:
    id: int
    owner_id: int
    owner: str
    name: str
    private: bool
    archived: bool = False


@dataclass(frozen=True)
class GitHubPullRequest:
    id: int
    number: int
    base_repository_id: int
    head_repository_id: int | None
    base_sha: str
    head_sha: str
    state: str
    draft: bool
    changed_files: int = 0


@dataclass(frozen=True)
class GitHubFile:
    sha: str
    path: str
    status: str
    additions: int
    deletions: int
