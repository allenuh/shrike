import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

type GitHubID = Annotated[int, Field(strict=True, gt=0, lt=2**63)]
type SHA = Annotated[str, Field(pattern=r"^[0-9a-f]{40}([0-9a-f]{24})?$", strict=True)]
type OwnerName = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,99}$")]


def valid_repo_name(value: str) -> str:
    if value in {".", ".."}:
        raise ValueError("Invalid repository name")
    return value


type RepoName = Annotated[
    str, Field(pattern=r"^[A-Za-z0-9_.-]{1,100}$"), AfterValidator(valid_repo_name)
]


class GitHubModel(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True, hide_input_in_errors=True)


class AccountData(GitHubModel):
    id: GitHubID
    login: OwnerName
    type: Literal["User", "Organization"]


class InstallationRef(GitHubModel):
    id: GitHubID
    app_id: GitHubID | None = None
    account: AccountData | None = None


class InstallationData(GitHubModel):
    id: GitHubID
    app_id: GitHubID
    account: AccountData
    suspended_at: str | None


class RepositoryData(GitHubModel):
    id: GitHubID
    name: RepoName
    owner: AccountData
    private: bool
    archived: bool = False


class Revision(GitHubModel):
    sha: SHA
    repo: RepositoryData | None


class PullRequestData(GitHubModel):
    id: GitHubID
    number: Annotated[int, Field(strict=True, gt=0, le=2147483647)]
    state: Literal["open", "closed"]
    draft: bool
    base: Revision
    head: Revision
    changed_files: Annotated[int, Field(strict=True, ge=0)] = 0


class PullRequestEvent(GitHubModel):
    action: str = Field(max_length=64)
    installation: InstallationRef
    repository: RepositoryData
    number: Annotated[int, Field(strict=True, gt=0, le=2147483647)]
    pull_request: PullRequestData

    @model_validator(mode="after")
    def consistent_identity(self) -> "PullRequestEvent":
        base = self.pull_request.base.repo
        if (
            base is None
            or base.id != self.repository.id
            or base.owner.id != self.repository.owner.id
            or self.number != self.pull_request.number
            or (
                self.installation.account is not None
                and self.installation.account.id != self.repository.owner.id
            )
        ):
            raise ValueError("Inconsistent webhook identity")
        return self


class RemovedRepository(GitHubModel):
    id: GitHubID
    name: RepoName


class InstallationEvent(GitHubModel):
    action: str = Field(max_length=64)
    installation: InstallationData
    repositories_added: list[RemovedRepository] = Field(default_factory=list, max_length=1000)
    repositories_removed: list[RemovedRepository] = Field(default_factory=list, max_length=1000)


class FileData(GitHubModel):
    sha: SHA
    filename: str = Field(min_length=1, max_length=1024)
    status: str = Field(min_length=1, max_length=32)
    additions: Annotated[int, Field(strict=True, ge=0)]
    deletions: Annotated[int, Field(strict=True, ge=0)]

    @model_validator(mode="after")
    def safe_path(self) -> "FileData":
        if re.search(r"(^/|(^|/)\.\.(/|$)|:|\\|\x00)", self.filename):
            raise ValueError("Unsafe file path")
        return self
