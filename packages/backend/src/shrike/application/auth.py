import base64
import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from shrike.domain.auth import AuthenticatedUser, AuthenticationError
from shrike.ports.auth import SessionStore, UserAuthorizationGateway


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class DashboardAuth:
    def __init__(
        self, store: SessionStore, github: UserAuthorizationGateway, client_id: str, callback: str
    ) -> None:
        self.store, self.github, self.client_id, self.callback = store, github, client_id, callback

    def start(self) -> tuple[str, str]:
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        self.store.save_state(digest(state), verifier, datetime.now(UTC) + timedelta(minutes=5))
        return "https://github.com/login/oauth/authorize?" + urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": self.callback,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        ), state

    def complete(
        self, code: str, state: str, browser_state: str | None, old_session: str | None = None
    ) -> str:
        if (
            not re.fullmatch(r"[A-Za-z0-9_-]{43}", state)
            or browser_state is None
            or not secrets.compare_digest(state.encode(), browser_state.encode())
            or not 1 <= len(code) <= 512
        ):
            raise AuthenticationError("invalid_oauth_state")
        verifier = self.store.consume_state(digest(state))
        if verifier is None:
            raise AuthenticationError("invalid_oauth_state")
        credential = self.github.exchange(code, verifier)
        identity = self.github.identity(credential.token)
        session = secrets.token_urlsafe(32)
        self.store.create(
            digest(session),
            identity,
            credential.token,
            datetime.now(UTC) + timedelta(seconds=min(3600, credential.expires_in)),
        )
        if old_session:
            self.store.revoke(digest(old_session))
        return session

    def authenticate(self, cookie: str | None) -> AuthenticatedUser:
        if cookie is None or not re.fullmatch(r"[A-Za-z0-9_-]{43}", cookie):
            raise AuthenticationError()
        session = self.store.read(digest(cookie))
        if session is None:
            raise AuthenticationError()
        identity = self.github.identity(session.token)
        if identity.id != session.identity.id:
            raise AuthenticationError()
        grants = self.github.grants(session.token)
        if self.store.read(digest(cookie)) is None:
            raise AuthenticationError()
        return AuthenticatedUser(identity, grants)

    def logout(self, cookie: str | None) -> None:
        if cookie:
            self.store.revoke(digest(cookie))
