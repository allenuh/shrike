from datetime import UTC, datetime

from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import delete, update

from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.models import DashboardSession, OAuthState
from shrike.domain.auth import AuthenticationError, SavedSession, UserIdentity


class SqlSessionStore:
    def __init__(self, database: Database, key: SecretStr) -> None:
        self.database, self.cipher = database, Fernet(key.get_secret_value().encode())

    def save_state(self, digest: str, verifier: str, expiry: datetime) -> None:
        with self.database.session() as session, session.begin():
            session.execute(delete(OAuthState).where(OAuthState.expires_at <= datetime.now(UTC)))
            session.add(
                OAuthState(
                    digest=digest,
                    verifier=self.cipher.encrypt(verifier.encode()).decode(),
                    expires_at=expiry,
                )
            )

    def consume_state(self, digest: str) -> str | None:
        with self.database.session() as session, session.begin():
            row = session.scalar(
                delete(OAuthState)
                .where(OAuthState.digest == digest, OAuthState.expires_at > datetime.now(UTC))
                .returning(OAuthState.verifier)
            )
        if row is None:
            return None
        try:
            return self.cipher.decrypt(row.encode()).decode()
        except Exception:
            raise AuthenticationError() from None

    def create(
        self, digest: str, identity: UserIdentity, token: SecretStr, expiry: datetime
    ) -> None:
        with self.database.session() as session, session.begin():
            session.add(
                DashboardSession(
                    digest=digest,
                    user_github_id=identity.id,
                    login=identity.login,
                    encrypted_token=self.cipher.encrypt(token.get_secret_value().encode()).decode(),
                    expires_at=expiry,
                )
            )

    def read(self, digest: str) -> SavedSession | None:
        with self.database.session() as session:
            row = session.get(DashboardSession, digest)
            if row is None or row.expires_at <= datetime.now(UTC) or row.encrypted_token is None:
                return None
            try:
                token = SecretStr(self.cipher.decrypt(row.encrypted_token.encode()).decode())
            except Exception:
                raise AuthenticationError() from None
            return SavedSession(UserIdentity(row.user_github_id, row.login), token, row.expires_at)

    def revoke(self, digest: str) -> None:
        with self.database.session() as session, session.begin():
            session.execute(
                update(DashboardSession)
                .where(DashboardSession.digest == digest)
                .values(encrypted_token=None, expires_at=datetime.now(UTC))
            )
