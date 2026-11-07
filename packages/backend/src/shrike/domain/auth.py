from dataclasses import dataclass
from datetime import datetime

from pydantic import SecretStr

from shrike.domain.access import RepositoryGrant


class AuthenticationError(Exception):
    def __init__(self, code: str = "authentication_required") -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class UserIdentity:
    id: int
    login: str


@dataclass(frozen=True)
class UserCredential:
    token: SecretStr
    expires_in: int


@dataclass(frozen=True)
class AuthenticatedUser:
    identity: UserIdentity
    grants: tuple[RepositoryGrant, ...]


@dataclass(frozen=True)
class SavedSession:
    identity: UserIdentity
    token: SecretStr
    expires_at: datetime
