from dataclasses import dataclass


@dataclass(frozen=True)
class RepositoryGrant:
    installation_github_id: int
    repository_github_id: int


@dataclass(frozen=True)
class ReadScope:
    """Verified server-side grants, never derived from a request's resource filters."""

    grants: tuple[RepositoryGrant, ...]
