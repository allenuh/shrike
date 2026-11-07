import json

import httpx2 as httpx
import pytest
from pydantic import SecretStr

from shrike.adapters.github.user_auth import GitHubUserAuthorization
from shrike.domain.access import RepositoryGrant
from shrike.domain.auth import AuthenticationError


def test_oauth_exchange_pkce_and_fresh_membership_are_scoped_to_this_app() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "github.com":
            body = request.content.decode()
            assert "code_verifier=synthetic-verifier" in body
            assert (
                "redirect_uri=https%3A%2F%2Fdashboard.test%2Fapi%2Fbackend%2Fauth%2Fgithub%2Fcallback"
                in body
            )
            return httpx.Response(
                200,
                json={
                    "access_token": "synthetic-token",
                    "token_type": "bearer",
                    "expires_in": 28800,
                    "refresh_token": "discard-me",
                },
            )
        assert request.headers["Authorization"] == "Bearer synthetic-token"
        if request.url.path == "/user":
            return httpx.Response(200, json={"id": 901, "login": "synthetic-user"})
        if request.url.path == "/user/installations":
            return httpx.Response(
                200,
                json={
                    "total_count": 2,
                    "installations": [
                        {"id": 710001, "app_id": 12345, "suspended_at": None},
                        {"id": 710002, "app_id": 999, "suspended_at": None},
                    ],
                },
            )
        assert request.url.path == "/user/installations/710001/repositories"
        return httpx.Response(200, json={"total_count": 1, "repositories": [{"id": 810001}]})

    github = GitHubUserAuthorization(
        12345,
        "synthetic-id",
        SecretStr("synthetic-secret"),
        "https://dashboard.test/api/backend/auth/github/callback",
        transport=httpx.MockTransport(handler),
    )
    try:
        credential = github.exchange("synthetic-code", "synthetic-verifier")
        assert credential.expires_in == 3600
        assert github.identity(credential.token).id == 901
        assert github.grants(credential.token) == (RepositoryGrant(710001, 810001),)
        assert len(calls) == 4
    finally:
        github.close()


@pytest.mark.parametrize(
    "failure", ["timeout", "401", "500", "malformed", "foreign_link", "truncated"]
)
def test_authorization_errors_fail_closed_without_retries_or_secret_text(failure: str) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("SYNTHETIC_SECRET")
        if failure.isdigit():
            return httpx.Response(int(failure), content=b"SYNTHETIC_SECRET")
        if failure == "malformed":
            return httpx.Response(200, content=b"SYNTHETIC_SECRET")
        value = {"total_count": 1, "installations": []}
        headers = (
            {"Link": '<https://evil.test/steal>; rel="next"'} if failure == "foreign_link" else {}
        )
        return httpx.Response(200, content=json.dumps(value).encode(), headers=headers)

    github = GitHubUserAuthorization(
        12345,
        "synthetic",
        SecretStr("synthetic"),
        "https://dashboard.test/callback",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(AuthenticationError) as caught:
            github.grants(SecretStr("synthetic"))
        assert len(calls) == 1 and "SYNTHETIC_SECRET" not in str(caught.value)
    finally:
        github.close()
