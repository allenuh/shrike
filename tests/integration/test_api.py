import io
import json
import logging
from collections.abc import Iterator
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.demo import demo_id
from shrike.config import Settings
from shrike.ports.history import HistoryReader
from shrike_api.dependencies import get_reader
from shrike_api.logging import SafeJsonFormatter
from shrike_api.main import create_app

pytestmark = pytest.mark.integration


def test_read_health_and_repository_schema(client: TestClient) -> None:
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ready"}
    result = client.get("/v1/repositories")
    assert result.status_code == 200
    assert result.json()["next_cursor"] is None
    assert len(result.json()["items"]) == 1
    repo = result.json()["items"][0]
    assert repo["github_id"] == 810001
    assert repo["installation_github_id"] == 710001
    assert set(repo) == {
        "id",
        "github_id",
        "installation_id",
        "installation_github_id",
        "owner",
        "name",
        "private",
        "created_at",
    }
    assert client.get(f"/v1/repositories/{repo['id']}").json() == repo


@pytest.mark.parametrize("sort", ["name", "created_at"])
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_repository_pagination_uses_only_explicit_grants(
    seeded_database: Database, settings: Settings, sort: str, order: str
) -> None:
    config = settings.model_copy(
        update={"dev_repository_grants": "710001:810001,710001:810002,710002:810003"}
    )
    with TestClient(create_app(config, seeded_database)) as client:
        client.headers["Authorization"] = f"Bearer {config.dev_auth_token.get_secret_value()}"
        items = all_pages(client, "/v1/repositories", {"limit": 1, "sort": sort, "order": order})
    assert len(items) == len({item["id"] for item in items}) == 3
    keys = [(item[sort], item["id"]) for item in items]
    assert keys == sorted(keys, reverse=order == "desc")


@pytest.mark.parametrize("grants", ["", "710002:810001"])
def test_empty_or_mismatched_installation_grants_deny_access(
    seeded_database: Database, settings: Settings, grants: str
) -> None:
    config = settings.model_copy(update={"dev_repository_grants": grants})
    with TestClient(create_app(config, seeded_database)) as client:
        client.headers["Authorization"] = f"Bearer {config.dev_auth_token.get_secret_value()}"
        assert client.get("/v1/repositories").json()["items"] == []
        assert client.get("/v1/review-jobs").json()["items"] == []
        assert client.get(f"/v1/review-jobs/{demo_id('completed')}").status_code == 404


@pytest.mark.parametrize("authorization", [None, "Bearer wrong", "Basic wrong"])
def test_authentication_is_required(client: TestClient, authorization: str | None) -> None:
    client.headers.pop("Authorization")
    headers = {"Authorization": authorization} if authorization is not None else {}
    result = client.get("/v1/review-jobs", headers=headers)
    assert result.status_code == 401
    assert result.headers["WWW-Authenticate"] == "Bearer"
    assert result.json()["error"]["code"] == "authentication_required"


def test_production_api_denies_requests_without_real_auth_adapter(
    seeded_database: Database,
) -> None:
    settings = Settings(
        database_url=SecretStr(seeded_database.engine.url.render_as_string(hide_password=False)),
        app_env="production",
        enable_dev_auth=False,
    )
    with TestClient(create_app(settings, seeded_database)) as client:
        assert (
            client.get(
                "/v1/repositories", headers={"Authorization": "Bearer arbitrary"}
            ).status_code
            == 401
        )
        assert client.get("/openapi.json").status_code == 404


@pytest.mark.parametrize("key", ["sibling-repository", "other-repository"])
def test_repository_grants_are_not_installation_wide(client: TestClient, key: str) -> None:
    result = client.get(f"/v1/repositories/{demo_id(key)}")
    assert result.status_code == 404
    unknown = client.get(f"/v1/repositories/{uuid4()}")
    assert result.json()["error"]["message"] == unknown.json()["error"]["message"]
    jobs = client.get("/v1/review-jobs", params={"repository_id": str(demo_id(key))})
    assert jobs.json() == {"items": [], "next_cursor": None}


@pytest.mark.parametrize("key", ["other-job", "canceled"])
def test_review_detail_and_findings_cannot_cross_grants(client: TestClient, key: str) -> None:
    assert client.get(f"/v1/review-jobs/{demo_id(key)}").status_code == 404
    assert client.get(f"/v1/review-jobs/{demo_id(key)}/findings").status_code == 404


def test_changing_filters_or_identity_headers_cannot_expand_access(client: TestClient) -> None:
    result = client.get(
        "/v1/repositories",
        params={"installation_id": str(demo_id("other-installation"))},
        headers={"X-Installation-ID": "710002", "X-User-ID": "admin"},
    )
    assert result.json() == {"items": [], "next_cursor": None}


def test_detail_contains_findings_and_allowlisted_execution_metadata(client: TestClient) -> None:
    result = client.get(f"/v1/review-jobs/{demo_id('completed')}")
    assert result.status_code == 200
    detail = result.json()
    assert detail["job"]["state"] == "completed"
    assert detail["job"]["finding_count"] == 3
    assert detail["job"]["pull_request_number"] == 42
    assert [item["severity"] for item in detail["findings"]["items"]] == ["high", "medium", "low"]
    execution = detail["executions"][0]
    assert execution["provider"] == "mock"
    assert set(execution) == {
        "id",
        "attempt",
        "state",
        "started_at",
        "finished_at",
        "duration_ms",
        "input_tokens",
        "output_tokens",
        "analyzer_version",
        "ruleset_version",
        "prompt_version",
        "provider",
        "model",
        "error_code",
    }
    assert "worker_identifier" not in result.text
    assert "internal-demo-worker-not-public" not in result.text
    assert "policy_digest" not in result.text
    assert "fingerprint" not in result.text


def test_history_filters_and_time_range(client: TestClient) -> None:
    params = {
        "state": "completed",
        "pull_request_number": "42",
        "repository_id": str(demo_id("repository")),
        "installation_id": str(demo_id("installation")),
        "created_after": "2026-01-01T11:59:59Z",
        "created_before": "2026-01-01T12:00:01Z",
    }
    result = client.get("/v1/review-jobs", params=params)
    assert result.status_code == 200
    assert [item["id"] for item in result.json()["items"]] == [str(demo_id("completed"))]
    assert client.get("/v1/repositories", params={"private": False}).json()["items"] == []
    assert len(client.get("/v1/repositories", params={"search": "PAYMENTS"}).json()["items"]) == 1
    assert client.get("/v1/repositories", params={"search": "%"}).json()["items"] == []


def all_pages(client: TestClient, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cursor = None
    while True:
        query = dict(params)
        if cursor:
            query["cursor"] = cursor
        response = client.get(path, params=query)
        assert response.status_code == 200, response.text
        items.extend(response.json()["items"])
        cursor = response.json()["next_cursor"]
        if cursor is None:
            return items
        assert len(items) < 100


@pytest.mark.parametrize("sort", ["created_at", "state"])
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_history_keyset_pagination_is_stable(
    client: TestClient, seeded_database: Database, sort: str, order: str
) -> None:
    # Tied timestamps exercise UUID tie-breakers instead of relying on insertion order.
    with seeded_database.engine.begin() as connection:
        connection.execute(text("UPDATE review_jobs SET created_at='2026-01-01T12:00:00Z'"))
    items = all_pages(client, "/v1/review-jobs", {"limit": 1, "sort": sort, "order": order})
    assert len(items) == len({item["id"] for item in items}) == 4
    keys = [(item[sort], item["id"]) for item in items]
    assert keys == sorted(keys, reverse=order == "desc")


@pytest.mark.parametrize("sort", ["severity", "path"])
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_findings_filter_sort_and_pagination(client: TestClient, sort: str, order: str) -> None:
    path = f"/v1/review-jobs/{demo_id('completed')}/findings"
    items = all_pages(client, path, {"limit": 1, "sort": sort, "order": order})
    assert len(items) == len({item["id"] for item in items}) == 3
    ranks = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    keys = [(ranks[item[sort]] if sort == "severity" else item[sort], item["id"]) for item in items]
    assert keys == sorted(keys, reverse=order == "desc")
    result = client.get(path, params={"severity": "high", "source": "semgrep"})
    assert len(result.json()["items"]) == 1


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"sort": "secret_column"},
        {"state": "unknown"},
        {"repository_id": "not-a-uuid"},
        {"order": "drop table"},
        {"cursor": "bad!"},
        {"created_after": "2026-01-01T00:00:00"},
        {"created_after": "2026-02-01T00:00:00Z", "created_before": "2026-01-01T00:00:00Z"},
        {"arbitrary_column": "SYNTHETIC_SECRET_SENTINEL"},
    ],
)
def test_validation_errors_do_not_echo_inputs(client: TestClient, params: dict[str, Any]) -> None:
    result = client.get("/v1/review-jobs", params=params)
    assert result.status_code == 422
    assert "SYNTHETIC_SECRET_SENTINEL" not in result.text
    assert result.json()["error"]["request_id"] == result.headers["X-Request-ID"]


def test_cursor_cannot_be_reused_with_different_filters(client: TestClient) -> None:
    result = client.get("/v1/review-jobs", params={"limit": 1})
    cursor = result.json()["next_cursor"]
    assert cursor
    changed = client.get("/v1/review-jobs", params={"cursor": cursor, "state": "failed"})
    assert changed.status_code == 422
    assert changed.json()["error"]["code"] == "invalid_cursor"


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE installations SET status='suspended' WHERE github_id=710001",
        "UPDATE installations SET status='deleted' WHERE github_id=710001",
        "UPDATE repositories SET status='removed' WHERE github_id=810001",
    ],
)
def test_revoked_or_suspended_access_is_immediately_denied(
    client: TestClient, seeded_database: Database, statement: str
) -> None:
    with seeded_database.engine.begin() as connection:
        connection.execute(text(statement))
    assert client.get("/v1/repositories").json()["items"] == []
    assert client.get("/v1/review-jobs").json()["items"] == []
    assert client.get(f"/v1/review-jobs/{demo_id('completed')}").status_code == 404


def test_structured_logs_exclude_headers_queries_paths_and_findings(client: TestClient) -> None:
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(SafeJsonFormatter())
    logger = logging.getLogger("shrike.http")
    logger.addHandler(handler)
    try:
        response = client.get(
            f"/v1/review-jobs/{demo_id('completed')}", headers={"X-Request-ID": "SECRET_SENTINEL"}
        )
        client.get("/v1/repositories", params={"search": "SOURCE_SENTINEL"})
    finally:
        logger.removeHandler(handler)
    logs = output.getvalue()
    assert "SENTINEL" not in logs
    assert "payments" not in logs
    assert "src/" not in logs
    assert "Bearer" not in logs
    record = json.loads(logs.splitlines()[0])
    assert record["status"] == 200
    assert record["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.parametrize("kind", ["database", "unexpected"])
def test_errors_are_sanitized_and_have_request_ids(client: TestClient, kind: str) -> None:
    def failed_reader() -> Iterator[HistoryReader]:
        if kind == "database":
            raise SQLAlchemyError("SYNTHETIC_SECRET_DATABASE_BODY")
        raise RuntimeError("SYNTHETIC_SOURCE_EXCEPTION")
        yield  # pragma: no cover

    cast(FastAPI, client.app).dependency_overrides[get_reader] = failed_reader
    response = client.get("/v1/repositories")
    assert response.status_code == (503 if kind == "database" else 500)
    assert "SYNTHETIC" not in response.text
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
    assert client.get("/health/live").status_code == 200
