import base64
import hashlib
import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any, cast

import httpx2 as httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fakes import github_fixture

from shrike.adapters.github.client import API_VERSION, READ_PERMISSIONS, GitHubAppClient
from shrike.domain.github import GitHubError, GitHubRepository

NOW = 1794000000.0
REPOSITORY = GitHubRepository(810001, 610001, "shrike-demo", "payments-api", True)


@pytest.fixture(scope="module")
def key() -> bytes:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


@pytest.fixture
def factory(key: bytes) -> Iterator[Callable[..., GitHubAppClient]]:
    clients: list[GitHubAppClient] = []

    def create(
        handler: Callable[[httpx.Request], httpx.Response], **kwargs: Any
    ) -> GitHubAppClient:
        client = GitHubAppClient(
            12345, key, transport=httpx.MockTransport(handler), sleep=lambda _: None, **kwargs
        )
        clients.append(client)
        return client

    yield create
    for client in clients:
        client.close()


def token_response(clock: float = NOW) -> httpx.Response:
    return httpx.Response(
        201,
        json={
            "token": "synthetic-installation-token-value",
            "expires_at": datetime.fromtimestamp(clock + 3600, UTC).isoformat(),
        },
    )


def test_jwt_claims_read_only_scopes_cache_and_expiry(
    factory: Callable[..., GitHubAppClient],
    key: bytes,
) -> None:
    clock = [NOW]
    tokens: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.github.com"
        assert request.headers["X-GitHub-Api-Version"] == API_VERSION
        if request.method == "POST":
            claims = jwt.decode(
                request.headers["Authorization"][7:],
                cast(rsa.RSAPrivateKey, serialization.load_pem_private_key(key, None)).public_key(),
                algorithms=["RS256"],
                options={"verify_exp": False, "verify_iat": False},
            )
            assert claims == {"iat": int(clock[0]) - 60, "exp": int(clock[0]) + 540, "iss": "12345"}
            tokens.append(json.loads(request.content))
            return token_response(clock[0])
        return httpx.Response(200, json=github_fixture("pull_request_opened.json")["repository"])

    client = factory(handler, clock=lambda: clock[0])
    assert client.repository(710001, 810001, "shrike-demo", "payments-api").id == 810001
    client.repository(710001, 810001, "shrike-demo", "payments-api")
    assert tokens == [{"permissions": READ_PERMISSIONS, "repository_ids": [810001]}]
    clock[0] += 3550
    client.repository(710001, 810001, "shrike-demo", "payments-api")
    assert len(tokens) == 2


def test_expired_server_token_refreshes_once(factory: Callable[..., GitHubAppClient]) -> None:
    calls = {"token": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            calls["token"] += 1
            return token_response()
        calls["get"] += 1
        return (
            httpx.Response(401)
            if calls["get"] == 1
            else httpx.Response(200, json=github_fixture("pull_request_opened.json")["repository"])
        )

    factory(handler, clock=lambda: NOW).repository(710001, 810001, "shrike-demo", "payments-api")
    assert calls == {"token": 2, "get": 2}


@pytest.mark.parametrize(
    "headers,status",
    [
        ({"Retry-After": "120"}, 429),
        ({"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(int(NOW) + 300)}, 403),
        ({}, 403),
    ],
)
def test_rate_limits_are_deferred_without_sleeping(
    factory: Callable[..., GitHubAppClient],
    headers: dict[str, str],
    status: int,
) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            status, headers=headers, json={"message": "secondary rate limit SYNTHETIC_SECRET"}
        )

    with pytest.raises(GitHubError) as result:
        factory(handler, clock=lambda: NOW).installation(710001)
    assert result.value.code == "github_rate_limited"
    assert result.value.retry_at is not None and result.value.retry_at.timestamp() > NOW
    assert "SYNTHETIC" not in str(result.value)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "status,code",
    [
        (404, "github_not_found"),
        (403, "github_access_denied"),
        (302, "unexpected_github_status"),
        (401, "github_authentication_failed"),
    ],
)
def test_error_bodies_and_redirects_are_not_exposed(
    factory: Callable[..., GitHubAppClient],
    status: int,
    code: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={"message": "PRIVATE_SENTINEL"},
            headers={"Location": "http://127.0.0.1/secret"},
        )

    with pytest.raises(GitHubError, match=code) as result:
        factory(handler).installation(710001)
    assert "PRIVATE_SENTINEL" not in str(result.value)


def test_transient_failures_retry_boundedly(factory: Callable[..., GitHubAppClient]) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(True)
        if len(calls) < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=github_fixture("installation_created.json")["installation"])

    assert factory(handler).installation(710001).id == 710001
    assert len(calls) == 3


def test_transport_failure_is_sanitized_and_bounded(
    factory: Callable[..., GitHubAppClient],
) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(True)
        raise httpx.ConnectError("TOKEN_PRIVATE_SENTINEL", request=request)

    with pytest.raises(GitHubError) as result:
        factory(handler).installation(710001)
    assert result.value.code == "github_transient" and len(calls) == 3
    assert "SENTINEL" not in str(result.value)


@pytest.mark.parametrize("bad_link", [False, True])
def test_inventory_pagination_stays_on_trusted_endpoint(
    factory: Callable[..., GitHubAppClient],
    bad_link: bool,
) -> None:
    calls = []
    repo = github_fixture("pull_request_opened.json")["repository"]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.method == "POST":
            assert json.loads(request.content) == {"permissions": {"metadata": "read"}}
            return token_response()
        if request.url.params["page"] == "1":
            next_url = (
                "https://evil.example/steal"
                if bad_link
                else "https://api.github.com/installation/repositories?per_page=100&page=2"
            )
            return httpx.Response(
                200,
                json={"total_count": 1, "repositories": []},
                headers={"Link": f'<{next_url}>; rel="next"'},
            )
        return httpx.Response(200, json={"total_count": 1, "repositories": [repo]})

    client = factory(handler, clock=lambda: NOW)
    if bad_link:
        with pytest.raises(GitHubError, match="pagination"):
            client.repositories(710001)
        assert len(calls) == 2
    else:
        assert len(client.repositories(710001)) == 1
        assert len(calls) == 3


def test_diff_and_blob_byte_limits(factory: Callable[..., GitHubAppClient]) -> None:
    payload = github_fixture("pull_request_opened.json")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return token_response()
        if request.headers["Accept"] == "application/vnd.github.diff":
            return httpx.Response(200, content=b"x" * 101)
        return httpx.Response(200, json=payload["pull_request"])

    client = factory(handler, clock=lambda: NOW, max_diff_bytes=100)
    with pytest.raises(GitHubError, match="too_large"):
        client.diff(710001, REPOSITORY, 101)
    content = b"synthetic source bytes"
    sha = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()

    def blob_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return token_response()
        return httpx.Response(
            200,
            json={
                "sha": sha,
                "size": len(content),
                "encoding": "base64",
                "content": base64.b64encode(content).decode(),
            },
        )

    assert factory(blob_handler, clock=lambda: NOW).blob(710001, REPOSITORY, sha) == content
    with pytest.raises(GitHubError, match="oversized"):
        factory(blob_handler, clock=lambda: NOW, max_file_bytes=1).blob(710001, REPOSITORY, sha)


def test_files_commit_and_diff_read_contracts(factory: Callable[..., GitHubAppClient]) -> None:
    payload = github_fixture("pull_request_opened.json")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return token_response()
        if "/commits/" in request.url.path:
            return httpx.Response(200, json={"sha": "b" * 40})
        if request.url.path.endswith("/files"):
            return httpx.Response(
                200,
                json=[
                    {
                        "sha": "c" * 40,
                        "filename": "src/payments.py",
                        "status": "modified",
                        "additions": 2,
                        "deletions": 1,
                    }
                ],
            )
        if request.headers["Accept"] == "application/vnd.github.diff":
            return httpx.Response(200, content=b"diff --git a/src/payments.py b/src/payments.py\n")
        return httpx.Response(200, json=payload["pull_request"])

    client = factory(handler, clock=lambda: NOW)
    assert client.files(710001, REPOSITORY, 101)[0].path == "src/payments.py"
    assert client.head_commit(710001, REPOSITORY, "b" * 40) == "b" * 40
    assert client.diff(710001, REPOSITORY, 101).startswith(b"diff")
