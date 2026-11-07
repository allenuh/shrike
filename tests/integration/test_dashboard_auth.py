from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import select

from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.demo import demo_id
from shrike.adapters.persistence.models import (
    DashboardSession,
    Installation,
    OAuthState,
    Repository,
)
from shrike.config import Settings
from shrike.domain.access import RepositoryGrant
from shrike.domain.auth import AuthenticationError, UserCredential, UserIdentity
from shrike_api.main import create_app

pytestmark = pytest.mark.integration
ORIGIN = "https://dashboard.example.test"


class FakeUserAuthorization:
    def __init__(self) -> None:
        self.user_id = 901
        self.authorized: tuple[RepositoryGrant, ...] = (RepositoryGrant(710001, 810001),)
        self.error: AuthenticationError | None = None
        self.exchanges = 0
        self.verifier: str | None = None

    def exchange(self, code: str, verifier: str) -> UserCredential:
        self.exchanges += 1
        self.verifier = verifier
        return UserCredential(SecretStr("synthetic-private-access-token"), 7200)

    def identity(self, token: SecretStr) -> UserIdentity:
        if self.error:
            raise self.error
        return UserIdentity(self.user_id, "synthetic-user")

    def grants(self, token: SecretStr) -> tuple[RepositoryGrant, ...]:
        return self.authorized


def config(database: Database, **values: Any) -> Settings:
    return Settings(
        database_url=SecretStr(database.engine.url.render_as_string(hide_password=False)),
        github_user_auth_enabled=True,
        github_app_id=12345,
        github_app_client_id="synthetic-client-id",
        github_oauth_client_secret=SecretStr("synthetic-client-secret"),
        dashboard_token_key=SecretStr(Fernet.generate_key().decode()),
        dashboard_origin=ORIGIN,
        **values,
    )


def begin(client: TestClient) -> str:
    response = client.get("/auth/github/start", follow_redirects=False)
    assert response.status_code == 302
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["code_challenge_method"] == ["S256"]
    assert len(query["code_challenge"][0]) == 43
    assert query["redirect_uri"] == [ORIGIN + "/api/backend/auth/github/callback"]
    return query["state"][0]


def login(client: TestClient) -> str:
    state = begin(client)
    response = client.get(
        "/auth/github/callback",
        params={"state": state, "code": "synthetic-code"},
        follow_redirects=False,
    )
    assert response.status_code == 303 and response.headers["location"] == ORIGIN + "/"
    assert (
        "HttpOnly" in response.headers["set-cookie"] and "Secure" in response.headers["set-cookie"]
    )
    assert "SameSite=lax" in response.headers["set-cookie"]
    token = client.cookies.get("__Host-shrike_session")
    assert token
    return token


def test_secure_session_pkce_encryption_repository_isolation_and_logout(
    seeded_database: Database,
) -> None:
    github = FakeUserAuthorization()
    with TestClient(
        create_app(config(seeded_database), seeded_database, auth_gateway=github), base_url=ORIGIN
    ) as client:
        token = login(client)
        assert client.get("/auth/session").json() == {"login": "synthetic-user", "mode": "live"}
        for path in (
            "/v1/repositories",
            "/v1/review-jobs",
            "/v1/dashboard/repositories",
            "/v1/dashboard/reviews",
            "/v1/dashboard/metrics",
            "/v1/dashboard/operations",
        ):
            response = client.get(path)
            assert response.status_code == 200, path
            assert "private-access-token" not in response.text
            assert "other-demo" not in response.text
            assert response.headers["cache-control"] == "no-store"
        assert client.get(f"/v1/dashboard/reviews/{demo_id('other-job')}").status_code == 404
        assert client.get(f"/v1/review-jobs/{demo_id('other-job')}/findings").status_code == 404
        with seeded_database.session() as session:
            stored = session.scalar(select(DashboardSession))
            assert stored and stored.digest != token and token not in stored.digest
            assert stored.encrypted_token and "synthetic" not in stored.encrypted_token
            assert stored.expires_at <= datetime.now(UTC) + timedelta(hours=1)
        assert (
            client.post("/auth/logout", headers={"Origin": "https://evil.test"}).status_code == 403
        )
        assert client.get("/auth/logout").status_code == 405
        response = client.post("/auth/logout", headers={"Origin": ORIGIN})
        assert response.status_code == 204
        client.cookies.set("__Host-shrike_session", token)
        assert client.get("/v1/dashboard/metrics").status_code == 401
        with seeded_database.session() as session:
            assert session.scalar(select(DashboardSession.encrypted_token)) is None


def test_state_cookie_binding_expiry_and_replay(seeded_database: Database) -> None:
    github = FakeUserAuthorization()
    with TestClient(
        create_app(config(seeded_database), seeded_database, auth_gateway=github), base_url=ORIGIN
    ) as client:
        state = begin(client)
        with seeded_database.session() as session, session.begin():
            row = session.scalar(select(OAuthState))
            assert row
            row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        response = client.get(
            "/auth/github/callback",
            params={"state": state, "code": "synthetic"},
            follow_redirects=False,
        )
        assert "/login?error=" in response.headers["location"]
        assert github.exchanges == 0
        state = begin(client)
        client.cookies.clear()
        response = client.get(
            "/auth/github/callback",
            params={"state": state, "code": "synthetic"},
            follow_redirects=False,
        )
        assert "/login?error=" in response.headers["location"] and github.exchanges == 0
        state = begin(client)
        callback = {"state": state, "code": "synthetic"}
        assert (
            client.get("/auth/github/callback", params=callback, follow_redirects=False).headers[
                "location"
            ]
            == ORIGIN + "/"
        )
        # Recreate the browser binding; the consumed database state still forbids replay.
        client.cookies.set("__Host-shrike_oauth_state", state)
        assert (
            "/login?error="
            in client.get("/auth/github/callback", params=callback, follow_redirects=False).headers[
                "location"
            ]
        )
        assert github.exchanges == 1


@pytest.mark.parametrize(
    "revocation", ["membership", "repository", "installation", "session", "identity", "outage"]
)
def test_each_request_revalidates_access_without_cached_grants(
    seeded_database: Database, revocation: str
) -> None:
    github = FakeUserAuthorization()
    with TestClient(
        create_app(config(seeded_database), seeded_database, auth_gateway=github), base_url=ORIGIN
    ) as client:
        login(client)
        assert len(client.get("/v1/dashboard/repositories").json()["items"]) == 1
        if revocation == "membership":
            github.authorized = ()
        elif revocation == "identity":
            github.user_id = 999
        elif revocation == "outage":
            github.error = AuthenticationError("authorization_unavailable")
        else:
            with seeded_database.session() as session, session.begin():
                if revocation == "repository":
                    repo = session.get(Repository, demo_id("repository"))
                    assert repo
                    repo.access_blocked = True
                elif revocation == "installation":
                    from shrike.domain.states import InstallationStatus

                    installation = session.get(Installation, demo_id("installation"))
                    assert installation
                    installation.status = InstallationStatus.SUSPENDED
                else:
                    stored = session.scalar(select(DashboardSession))
                    assert stored
                    stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        response = client.get("/v1/dashboard/repositories")
        if revocation in {"identity", "session"}:
            assert response.status_code == 401
        elif revocation == "outage":
            assert response.status_code == 503
        else:
            assert response.json()["items"] == []
            assert client.get(f"/v1/dashboard/reviews/{demo_id('completed')}").status_code == 404
            assert client.get("/v1/dashboard/operations").json()["pending"] == 0


def test_two_users_and_session_rotation(seeded_database: Database) -> None:
    github = FakeUserAuthorization()
    app = create_app(config(seeded_database), seeded_database, auth_gateway=github)
    with TestClient(app, base_url=ORIGIN) as first:
        old = login(first)
        new = login(first)
        assert old != new
        first.cookies.clear()
        first.cookies.set("__Host-shrike_session", old)
        assert first.get("/auth/session").status_code == 401
    github.user_id = 902
    github.authorized = (RepositoryGrant(710002, 810003),)
    with TestClient(app, base_url=ORIGIN) as second:
        login(second)
        items = second.get("/v1/dashboard/repositories").json()["items"]
        assert len(items) == 1 and items[0]["owner"] == "other-demo"
        assert second.get(f"/v1/dashboard/reviews/{demo_id('completed')}").status_code == 404


@pytest.mark.parametrize(
    "origin",
    [
        "http://public.test",
        "https://user:password@host.test",
        "https://host.test/extra",
        "https://host.test?next=evil",
        "https://host.test#fragment",
    ],
)
def test_production_callback_is_fixed_https_origin(seeded_database: Database, origin: str) -> None:
    with pytest.raises(ValidationError):
        config(seeded_database, app_env="production").model_validate(
            config(seeded_database).model_dump() | {"dashboard_origin": origin}
        )
