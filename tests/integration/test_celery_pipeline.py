import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import redis
from celery.contrib.testing.worker import start_worker
from fakes import ReviewGitHub, github_fixture
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select

from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.dispatch import SqlDispatchStore
from shrike.adapters.persistence.models import (
    QueueMessage,
    ReviewExecution,
    ReviewFinding,
    ReviewJob,
)
from shrike.application.dispatch import dispatch_one
from shrike.config import Settings
from shrike.domain.states import JobState
from shrike_api.main import create_app as create_api
from shrike_worker.celery_app import CeleryPublisher, create_app
from shrike_worker.config import QueueSettings
from shrike_worker.runtime import Runtime

pytestmark = pytest.mark.integration
SECRET = "synthetic-offline-webhook-secret-for-queue-tests"


def send(client: TestClient, delivery: str) -> tuple[int, str]:
    raw = json.dumps(github_fixture("pull_request_opened.json")).encode()
    response = client.post(
        "/webhooks/github",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": delivery,
            "X-Hub-Signature-256": "sha256="
            + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest(),
        },
    )
    return response.status_code, response.headers["X-Request-ID"]


def wait_complete(database: Database, publisher: CeleryPublisher) -> None:
    dispatcher = SqlDispatchStore(database, redelivery_seconds=0.1)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        dispatch_one(dispatcher, publisher)
        with database.session() as session:
            job = session.scalar(select(ReviewJob))
            if job is not None and job.state == JobState.COMPLETED:
                return
            assert job is None or job.state not in {JobState.FAILED, JobState.CANCELED}
        time.sleep(0.05)
    pytest.fail("Synthetic asynchronous review did not complete before its test deadline")


@pytest.mark.parametrize("lose_broker_data", [False, True])
def test_signed_event_real_redis_celery_ruff_to_database(
    database: Database,
    queue_settings: QueueSettings,
    lose_broker_data: bool,
    capsys: pytest.CaptureFixture[str],
) -> None:
    github = ReviewGitHub()
    # This end-to-end test uses actual isolated Ruff; GitHub and AI are deterministic fakes.
    runtime = Runtime(database, github, 12345, queue_settings)
    app = create_app(queue_settings, runtime.consume)
    publisher = CeleryPublisher(app)
    broker = redis.Redis.from_url(queue_settings.broker_url.get_secret_value())
    api_settings = Settings(
        database_url=SecretStr(database.engine.url.render_as_string(hide_password=False)),
        app_env="test",
        github_webhooks_enabled=True,
        github_app_id=12345,
        github_webhook_secret=SecretStr(SECRET),
    )
    try:
        with TestClient(create_api(api_settings, database)) as client:
            delivery = str(uuid4())
            status, request_id = send(client, delivery)
            assert status == 202
            assert send(client, delivery)[0] == 200
            if lose_broker_data:
                assert dispatch_one(SqlDispatchStore(database), publisher)
                # Remove ONLY this test's random namespace, never flush a shared Redis database.
                keys = list(broker.scan_iter(match=queue_settings.namespace + ":*"))
                if keys:
                    broker.delete(*keys)
                with database.session() as session, session.begin():
                    row = session.scalar(select(QueueMessage))
                    assert row is not None
                    row.published_at = datetime.now(UTC) - timedelta(seconds=60)
            with start_worker(
                app, pool="solo", perform_ping_check=False, loglevel="WARNING", shutdown_timeout=10
            ):
                wait_complete(database, publisher)
                assert send(client, str(uuid4()))[0] == 202
                assert dispatch_one(SqlDispatchStore(database), publisher)
                time.sleep(0.3)
            with database.session() as session:
                job = session.scalar(select(ReviewJob))
                assert job is not None and job.attempt_count == 1 and job.publication_eligible
                assert job.result is not None and job.result["provider"] == "mock"
                assert session.scalar(select(func.count()).select_from(ReviewJob)) == 1
                assert session.scalar(select(func.count()).select_from(ReviewFinding)) == 1
                assert session.scalar(select(func.count()).select_from(ReviewExecution)) == 1
                messages = list(
                    session.scalars(select(QueueMessage).where(QueueMessage.kind == "review"))
                )
                assert len(messages) == 1 and str(messages[0].request_id) == request_id
        captured = capsys.readouterr()
        assert SECRET not in captured.out + captured.err
        assert "value = 10 / 0" not in captured.out + captured.err
        assert request_id in captured.err
    finally:
        app.close()
        keys = list(broker.scan_iter(match=queue_settings.namespace + ":*"))
        if keys:
            broker.delete(*keys)
        broker.close()


def test_webhook_acceptance_during_real_broker_connection_failure(
    database: Database, queue_settings: QueueSettings
) -> None:
    # Loopback discard port: no actual external host or paid service is contacted.
    unavailable = queue_settings.model_copy(
        update={"broker_url": SecretStr("redis://" + ":" + "x" * 32 + "@127.0.0.1:1/0")}
    )
    app = create_app(unavailable)
    config = Settings(
        database_url=SecretStr(database.engine.url.render_as_string(hide_password=False)),
        app_env="test",
        github_webhooks_enabled=True,
        github_app_id=12345,
        github_webhook_secret=SecretStr(SECRET),
    )
    try:
        with TestClient(create_api(config, database)) as client:
            assert send(client, str(uuid4()))[0] == 202
        assert dispatch_one(SqlDispatchStore(database), CeleryPublisher(app))
        with database.session() as session:
            row = session.scalar(select(QueueMessage))
            assert row is not None and row.failures == 1 and row.published_at is None
    finally:
        app.close()
