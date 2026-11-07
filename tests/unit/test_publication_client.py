import json
from collections.abc import Callable
from datetime import UTC, datetime

import httpx2 as httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fakes import publication_report

from shrike.adapters.github.client import (
    PUBLICATION_READ_PERMISSIONS,
    WRITE_PERMISSIONS,
    GitHubAppClient,
)
from shrike.application.publication import render_plan
from shrike.domain.github import GitHubError, GitHubRepository

REPO = GitHubRepository(810001, 610001, "shrike-demo", "payments-api", True)
PLAN = render_plan(publication_report(), "<!-- shrike-review:fixture -->")


@pytest.fixture(scope="module")
def key() -> bytes:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def review(body: str = PLAN.body, *, own: bool = True) -> dict[str, object]:
    return {
        "id": 123,
        "body": body,
        "commit_id": "b" * 40,
        "state": "COMMENTED",
        "user": {"id": 100, "login": "shrike[bot]" if own else "other[bot]", "type": "Bot"},
    }


def setup_response(request: httpx.Request) -> httpx.Response | None:
    if request.url.path.endswith("/access_tokens"):
        return httpx.Response(
            201,
            json={
                "token": "synthetic-token",
                "expires_at": datetime.fromtimestamp(1794000000 + 3600, UTC).isoformat(),
            },
        )
    if request.url.path == "/app":
        return httpx.Response(200, json={"id": 12345, "slug": "shrike"})
    return None


def client(
    key: bytes, handler: Callable[[httpx.Request], httpx.Response], *, enabled: bool = True
) -> GitHubAppClient:
    return GitHubAppClient(
        12345,
        key,
        publishing_enabled=enabled,
        transport=httpx.MockTransport(handler),
        clock=lambda: 1794000000,
        sleep=lambda _: None,
    )


def test_minimum_scoped_tokens_advisory_payload_and_bot_identity(key: bytes) -> None:
    tokens = []
    posts = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/access_tokens"):
            tokens.append(json.loads(request.content))
        if response := setup_response(request):
            return response
        if request.method == "POST":
            posts.append(json.loads(request.content))
            return httpx.Response(200, json=review())
        return httpx.Response(200, json=[review(own=False), review()])

    github = client(key, handler)
    try:
        records = github.reviews(710001, REPO, 101)
        assert [r.own for r in records] == [False, True]
        assert github.create_review(710001, REPO, 101, "b" * 40, PLAN).id == 123
        assert tokens == [
            {"permissions": PUBLICATION_READ_PERMISSIONS, "repository_ids": [810001]},
            {"permissions": WRITE_PERMISSIONS, "repository_ids": [810001]},
        ]
        assert posts == [
            {"commit_id": "b" * 40, "event": "COMMENT", "body": PLAN.body, "comments": []}
        ]
    finally:
        github.close()


@pytest.mark.parametrize(
    "failure,expected",
    [
        ("timeout", "github_write_uncertain"),
        ("500", "github_write_uncertain"),
        ("bad_json", "github_write_uncertain"),
        ("422", "github_invalid_review"),
        ("403", "github_access_denied"),
        ("401", "github_authentication_failed"),
        ("429", "github_rate_limited"),
    ],
)
def test_review_posts_never_retry_and_errors_are_safe(
    key: bytes, failure: str, expected: str
) -> None:
    posts = []

    def handler(request: httpx.Request) -> httpx.Response:
        if response := setup_response(request):
            return response
        posts.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("SYNTHETIC_SECRET_SOURCE")
        if failure == "bad_json":
            return httpx.Response(200, content=b"SYNTHETIC_SECRET_SOURCE")
        return httpx.Response(int(failure), content=b"SYNTHETIC_SECRET_SOURCE")

    github = client(key, handler)
    try:
        with pytest.raises(GitHubError) as caught:
            github.create_review(710001, REPO, 101, "b" * 40, PLAN)
        assert caught.value.code == expected and "SYNTHETIC" not in str(caught.value)
        assert len(posts) == 1
    finally:
        github.close()


def test_disabled_publishing_never_obtains_token_or_calls_api(key: bytes) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Disabled publication touched network")

    github = client(key, handler, enabled=False)
    try:
        with pytest.raises(GitHubError, match="publishing_disabled"):
            github.create_review(710001, REPO, 101, "b" * 40, PLAN)
    finally:
        github.close()


def test_review_pagination_is_complete_bounded_and_rejects_foreign_links(key: bytes) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if response := setup_response(request):
            return response
        calls.append(str(request.url))
        if request.url.params["page"] == "1":
            return httpx.Response(
                200,
                json=[review(own=False)],
                headers={
                    "Link": "<https://api.github.com/repos/shrike-demo/payments-api/"
                    'pulls/101/reviews?per_page=100&page=2>; rel="next"'
                },
            )
        return httpx.Response(200, json=[review()])

    github = client(key, handler)
    try:
        assert len(github.reviews(710001, REPO, 101)) == 2
        assert len(calls) == 2
    finally:
        github.close()

    def unsafe(request: httpx.Request) -> httpx.Response:
        return setup_response(request) or httpx.Response(
            200,
            json=[],
            headers={"Link": '<https://evil.test/steal?per_page=100&page=2>; rel="next"'},
        )

    github = client(key, unsafe)
    try:
        with pytest.raises(GitHubError, match="invalid_github_pagination"):
            github.reviews(710001, REPO, 101)
    finally:
        github.close()


def test_inline_uses_line_side_and_comment_ids_are_parsed(key: bytes) -> None:
    diff = "diff --git a/demo.py b/demo.py\n--- a/demo.py\n+++ b/demo.py\n@@ -0,0 +1 @@\n+new\n"
    plan = render_plan(publication_report(), "marker", diff)

    def handler(request: httpx.Request) -> httpx.Response:
        if response := setup_response(request):
            return response
        if request.method == "POST":
            payload = json.loads(request.content)
            assert payload["comments"][0]["line"] == 1
            assert payload["comments"][0]["side"] == "RIGHT"
            assert "position" not in payload["comments"][0]
            return httpx.Response(200, json=review(plan.body))
        return httpx.Response(
            200,
            json=[
                {
                    "id": 222,
                    "body": plan.comments[0].body,
                    "user": {"id": 100, "login": "shrike[bot]", "type": "Bot"},
                }
            ],
        )

    github = client(key, handler)
    try:
        github.create_review(710001, REPO, 101, "b" * 40, plan)
        comments = github.review_comments(710001, REPO, 101, 123)
        assert comments[0].id == 222 and comments[0].own
    finally:
        github.close()
