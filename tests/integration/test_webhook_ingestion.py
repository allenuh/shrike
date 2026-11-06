import hashlib
import hmac
import json
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fakes import FakeGitHub, github_fixture
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select, text

from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.ingestion import SqlIngestionStore
from shrike.adapters.persistence.models import (
    Installation,
    PullRequest,
    Repository,
    ReviewJob,
    WebhookDelivery,
)
from shrike.application.ingestion import process_one
from shrike.config import Settings
from shrike.domain.github import GitHubError
from shrike.domain.ingestion import IngestionResult
from shrike.domain.states import InstallationStatus, JobState, RepositoryStatus
from shrike_api.main import create_app
from shrike_worker import ingest

pytestmark = pytest.mark.integration
SECRET = "synthetic-webhook-secret-only-for-offline-tests"


@pytest.fixture
def webhook_client(database: Database) -> Iterator[TestClient]:
    config = Settings(
        database_url=SecretStr(database.engine.url.render_as_string(hide_password=False)),
        app_env="test",
        github_webhooks_enabled=True,
        github_app_id=12345,
        github_webhook_secret=SecretStr(SECRET),
    )
    with TestClient(create_app(config, database)) as client:
        yield client


def post(
    client: TestClient,
    payload: dict[str, Any],
    event: str = "pull_request",
    delivery: str | None = None,
) -> int:
    raw = json.dumps(payload).encode()
    response = client.post(
        "/webhooks/github",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": event,
            "X-GitHub-Delivery": delivery or str(uuid4()),
            "X-Hub-Signature-256": "sha256="
            + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest(),
        },
    )
    return response.status_code


def count(database: Database, model: type[Any]) -> int:
    with database.session() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_signed_webhook_creates_only_durable_inbox_until_canonical_verification(
    webhook_client: TestClient,
    database: Database,
) -> None:
    payload = github_fixture("pull_request_opened.json")
    delivery = str(uuid4())
    for index in range(20):
        assert post(webhook_client, payload, delivery=delivery) == (202 if index == 0 else 200)
    assert count(database, WebhookDelivery) == 1
    assert count(database, ReviewJob) == 0
    with database.session() as session:
        receipt = session.scalar(select(WebhookDelivery))
        assert receipt is not None and "SENTINEL" not in json.dumps(receipt.routing)
        installation = session.scalar(select(Installation))
        assert installation is not None and installation.status == InstallationStatus.SUSPENDED
    github = FakeGitHub()
    assert process_one(SqlIngestionStore(database), github, 12345)
    assert count(database, ReviewJob) == count(database, PullRequest) == 1
    with database.session() as session:
        job = session.scalar(select(ReviewJob))
        assert job is not None and job.state == JobState.PENDING and job.head_sha == "b" * 40
        assert session.scalar(select(Installation.status)) == InstallationStatus.ACTIVE
    assert github.calls == ["installation", "repository", "pull_request"]


def test_logical_job_deduplication_and_new_head_cancels_old_pending_job(
    webhook_client: TestClient,
    database: Database,
) -> None:
    payload, github, store = (
        github_fixture("pull_request_opened.json"),
        FakeGitHub(),
        SqlIngestionStore(database),
    )
    for _ in range(2):
        assert post(webhook_client, payload) == 202
        assert process_one(store, github, 12345)
    assert count(database, ReviewJob) == 1
    payload["action"] = "synchronize"
    payload["pull_request"]["head"]["sha"] = "c" * 40
    github.pr_data = replace(github.pr_data, head_sha="c" * 40)
    assert post(webhook_client, payload) == 202
    assert process_one(store, github, 12345)
    with database.session() as session:
        jobs = list(session.scalars(select(ReviewJob).order_by(ReviewJob.created_at)))
        assert [job.state for job in jobs] == [JobState.CANCELED, JobState.PENDING]
        assert jobs[1].head_sha == "c" * 40


@pytest.mark.parametrize("action", ["opened", "reopened", "synchronize", "ready_for_review"])
def test_supported_pr_actions(webhook_client: TestClient, database: Database, action: str) -> None:
    payload = github_fixture("pull_request_opened.json")
    payload["action"] = action
    assert post(webhook_client, payload) == 202
    assert process_one(SqlIngestionStore(database), FakeGitHub(), 12345)
    assert count(database, ReviewJob) == 1


@pytest.mark.parametrize("kind", ["draft", "closed", "canonical_fork", "payload_fork"])
def test_nonreviewable_prs_do_not_create_jobs(
    webhook_client: TestClient,
    database: Database,
    kind: str,
) -> None:
    payload, github = github_fixture("pull_request_opened.json"), FakeGitHub()
    if kind == "draft":
        github.pr_data = replace(github.pr_data, draft=True)
    elif kind == "closed":
        github.pr_data = replace(github.pr_data, state="closed")
    elif kind == "canonical_fork":
        github.pr_data = replace(github.pr_data, head_repository_id=999)
    else:
        payload["pull_request"]["head"]["repo"]["id"] = 999
    assert post(webhook_client, payload) == 202
    process_one(SqlIngestionStore(database), github, 12345)
    assert count(database, ReviewJob) == 0
    if kind == "payload_fork":
        assert github.calls == []


@pytest.mark.parametrize("kind", ["missing", "wrong", "malformed", "mismatch"])
def test_invalid_signatures_payloads_and_identity_do_not_persist(
    webhook_client: TestClient,
    database: Database,
    kind: str,
) -> None:
    payload = github_fixture("pull_request_opened.json")
    if kind == "mismatch":
        payload["pull_request"]["base"]["repo"]["id"] = 999
    raw = b"not json" if kind == "malformed" else json.dumps(payload).encode()
    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": str(uuid4()),
    }
    if kind != "missing":
        headers["X-Hub-Signature-256"] = (
            "sha256="
            + hmac.new(
                ("wrong" if kind == "wrong" else SECRET).encode(), raw, hashlib.sha256
            ).hexdigest()
        )
    response = webhook_client.post("/webhooks/github", content=raw, headers=headers)
    assert response.status_code == (401 if kind in {"missing", "wrong"} else 400)
    assert count(database, WebhookDelivery) == 0


def test_chunked_oversize_payload_is_rejected(
    webhook_client: TestClient, database: Database
) -> None:
    response = webhook_client.post(
        "/webhooks/github",
        content=iter([b"x" * 600000, b"y" * 600000]),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert count(database, WebhookDelivery) == 0


def test_delivery_id_reuse_with_different_signed_body_is_conflict(
    webhook_client: TestClient,
) -> None:
    payload, delivery = github_fixture("pull_request_opened.json"), str(uuid4())
    assert post(webhook_client, payload, delivery=delivery) == 202
    payload["action"] = "reopened"
    assert post(webhook_client, payload, delivery=delivery) == 409


@pytest.mark.parametrize("action", ["deleted", "suspend"])
def test_installation_revocation_immediately_disables_and_cancels(
    webhook_client: TestClient,
    database: Database,
    action: str,
) -> None:
    assert post(webhook_client, github_fixture("pull_request_opened.json")) == 202
    assert process_one(SqlIngestionStore(database), FakeGitHub(), 12345)
    event = github_fixture("installation_created.json")
    event["action"] = action
    assert post(webhook_client, event, "installation") == 202
    with database.session() as session:
        assert session.scalar(select(Installation.status)) != InstallationStatus.ACTIVE
        assert session.scalar(select(ReviewJob.state)) == JobState.CANCELED


def test_revocation_during_fetch_fences_old_worker(
    webhook_client: TestClient, database: Database
) -> None:
    assert post(webhook_client, github_fixture("pull_request_opened.json")) == 202
    github, store = FakeGitHub(), SqlIngestionStore(database)

    def revoke() -> None:
        event = github_fixture("installation_created.json")
        event["action"] = "deleted"
        assert post(webhook_client, event, "installation") == 202

    github.on_pull_request = revoke
    assert process_one(store, github, 12345)
    assert count(database, ReviewJob) == 0
    process_one(store, github, 12345)
    with database.session() as session:
        assert session.scalar(select(Installation.status)) == InstallationStatus.DELETED
    assert post(webhook_client, github_fixture("installation_created.json"), "installation") == 202
    process_one(store, github, 12345)
    assert count(database, ReviewJob) == 0


def test_removed_selection_quarantines_then_reconciles_canonical_inventory(
    webhook_client: TestClient,
    database: Database,
) -> None:
    assert post(webhook_client, github_fixture("installation_created.json"), "installation") == 202
    github, store = FakeGitHub(), SqlIngestionStore(database)
    assert process_one(store, github, 12345)
    event = github_fixture("repositories_removed.json")
    event["repositories_removed"] = []
    assert post(webhook_client, event, "installation_repositories") == 202
    with database.session() as session:
        assert session.scalar(select(Repository.status)) == RepositoryStatus.REMOVED
    github.inventory = ()
    assert process_one(store, github, 12345)
    with database.session() as session:
        assert session.scalar(select(Repository.status)) == RepositoryStatus.REMOVED


def test_rate_limit_schedule_and_eventual_recovery(
    webhook_client: TestClient, database: Database
) -> None:
    post(webhook_client, github_fixture("pull_request_opened.json"))
    github, store = FakeGitHub(), SqlIngestionStore(database)
    github.error = GitHubError(
        "github_rate_limited", retry_at=datetime.now(UTC) + timedelta(hours=1)
    )
    assert process_one(store, github, 12345)
    assert not process_one(store, github, 12345)
    with database.engine.begin() as connection:
        connection.execute(text("UPDATE webhook_deliveries SET available_at=now()"))
    github.error = None
    assert process_one(store, github, 12345)
    assert count(database, ReviewJob) == 1


def test_expired_lease_and_stale_completion_cannot_duplicate_jobs(
    webhook_client: TestClient, database: Database
) -> None:
    post(webhook_client, github_fixture("pull_request_opened.json"))
    store, github = SqlIngestionStore(database), FakeGitHub()
    first = store.claim()
    assert first is not None and store.claim() is None
    with database.engine.begin() as connection:
        connection.execute(
            text("UPDATE webhook_deliveries SET lease_expires_at=now()-interval '1 second'")
        )
    second = store.claim()
    assert second is not None and first.fence != second.fence
    result = IngestionResult(github.installation_data, (github.repository_data,), github.pr_data)
    store.complete(first, result)
    assert count(database, ReviewJob) == 0
    store.complete(second, result)
    assert count(database, ReviewJob) == 1


def test_canonical_installation_identity_must_match(
    webhook_client: TestClient, database: Database
) -> None:
    post(webhook_client, github_fixture("pull_request_opened.json"))
    github = FakeGitHub()
    github.installation_data = replace(github.installation_data, app_id=999)
    process_one(SqlIngestionStore(database), github, 12345)
    assert count(database, ReviewJob) == 0
    with database.session() as session:
        assert session.scalar(select(WebhookDelivery.reason)) == "invalid_github_identity"


def test_only_one_snapshot_per_installation_can_be_in_flight(
    webhook_client: TestClient,
    database: Database,
) -> None:
    payload = github_fixture("pull_request_opened.json")
    post(webhook_client, payload)
    post(webhook_client, payload)
    store, github = SqlIngestionStore(database), FakeGitHub()
    first = store.claim()
    assert first is not None
    assert store.claim() is None
    store.complete(
        first, IngestionResult(github.installation_data, (github.repository_data,), github.pr_data)
    )
    assert process_one(store, github, 12345)
    assert count(database, ReviewJob) == 1


@pytest.mark.parametrize("kind", ["installation", "repository"])
def test_inaccessible_installation_or_repository_is_quarantined(
    webhook_client: TestClient,
    database: Database,
    kind: str,
) -> None:
    post(webhook_client, github_fixture("pull_request_opened.json"))
    github = FakeGitHub()
    if kind == "installation":
        github.error = GitHubError("github_not_found")
    else:
        github.repository_error = GitHubError("github_not_found")
    process_one(SqlIngestionStore(database), github, 12345)
    assert count(database, ReviewJob) == 0
    with database.session() as session:
        if kind == "installation":
            assert session.scalar(select(Installation.status)) == InstallationStatus.DELETED
        else:
            assert session.scalar(select(Repository.access_blocked)) is True


def test_transient_failures_exhaust_after_three_processing_attempts(
    webhook_client: TestClient,
    database: Database,
) -> None:
    post(webhook_client, github_fixture("pull_request_opened.json"))
    github, store = FakeGitHub(), SqlIngestionStore(database)
    github.error = GitHubError("github_transient", retry_at=datetime.now(UTC))
    for _ in range(3):
        assert process_one(store, github, 12345)
    assert not process_one(store, github, 12345)
    with database.session() as session:
        row = session.scalar(select(WebhookDelivery))
        assert row is not None and row.state == "failed" and row.attempts == 3


def test_ingestion_migration_downgrade_preserves_existing_phase2_data(database: Database) -> None:
    from alembic import command
    from conftest import migration_config

    from shrike.adapters.persistence.demo import seed_demo

    with database.session() as session, session.begin():
        seed_demo(session)
    with database.engine.begin() as connection:
        config = migration_config()
        config.attributes["connection"] = connection
        command.downgrade(config, "0001_core")
        assert connection.scalar(text("SELECT count(*) FROM review_jobs")) == 6
        command.upgrade(config, "head")
        command.check(config)
    assert count(database, ReviewJob) == 6


def test_repository_cannot_be_claimed_by_another_installation(
    webhook_client: TestClient,
    database: Database,
) -> None:
    payload = github_fixture("pull_request_opened.json")
    assert post(webhook_client, payload) == 202
    payload["installation"]["id"] = 710002
    assert post(webhook_client, payload) == 409
    assert count(database, Installation) == 1
    assert count(database, WebhookDelivery) == 1


def test_unknown_signed_event_is_ignored_without_job(
    webhook_client: TestClient, database: Database
) -> None:
    assert post(webhook_client, {"action": "created"}, event="unknown_event") == 202
    assert count(database, ReviewJob) == 0
    assert not process_one(SqlIngestionStore(database), FakeGitHub(), 12345)


def test_worker_cli_processes_inbox_with_mocked_github_and_closes_resources(
    webhook_client: TestClient,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    post(webhook_client, github_fixture("pull_request_opened.json"))
    closed: list[bool] = []

    class FakeCLIClient(FakeGitHub):
        def __init__(self, app_id: int, key: bytes, **kwargs: object) -> None:
            super().__init__()
            self.closed = False

        def close(self) -> None:
            self.closed = True
            closed.append(True)

    key_file = tmp_path / "synthetic.key"
    key_file.write_bytes(b"SYNTHETIC_PRIVATE_KEY_SENTINEL")
    monkeypatch.setenv("DATABASE_URL", database.engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("GITHUB_MODE", "live")
    monkeypatch.setenv("GITHUB_APP_ID", "12345")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_PATH", str(key_file))
    monkeypatch.setenv("GITHUB_WEBHOOKS_ENABLED", "false")
    monkeypatch.setattr("sys.argv", ["ingest", "--once"])
    monkeypatch.setattr(ingest, "GitHubAppClient", FakeCLIClient)
    ingest.main()
    assert count(database, ReviewJob) == 1 and closed == [True]
    output = capsys.readouterr()
    assert '"processed": 1' in output.out
    assert "SENTINEL" not in output.out + output.err
