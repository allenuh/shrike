from typing import Protocol

from shrike.domain.github import GitHubFile, GitHubInstallation, GitHubPullRequest, GitHubRepository


class GitHubGateway(Protocol):
    def installation(self, installation_id: int) -> GitHubInstallation: ...

    def repositories(self, installation_id: int) -> tuple[GitHubRepository, ...]: ...

    def repository(
        self, installation_id: int, repository_id: int, owner: str, name: str
    ) -> GitHubRepository: ...

    def pull_request(
        self, installation_id: int, repository: GitHubRepository, number: int
    ) -> GitHubPullRequest: ...

    def files(
        self, installation_id: int, repository: GitHubRepository, number: int
    ) -> tuple[GitHubFile, ...]: ...

    def diff(self, installation_id: int, repository: GitHubRepository, number: int) -> bytes: ...

    def head_commit(self, installation_id: int, repository: GitHubRepository, sha: str) -> str: ...

    def blob(self, installation_id: int, repository: GitHubRepository, sha: str) -> bytes: ...
