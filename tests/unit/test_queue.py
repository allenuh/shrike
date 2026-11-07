import io
import json
import logging
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError

from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.operations import DevJobOperations
from shrike.domain.access import ReadScope
from shrike.domain.queue import Envelope, QueueUnavailable
from shrike.domain.review import ReviewError
from shrike.telemetry import SafeStderrHandler
from shrike_worker.celery_app import TASK_NAME, CeleryPublisher, create_app
from shrike_worker.config import QueueSettings
from shrike_worker.logging import SafeWorkerFormatter

BROKER = "redis://:" + "synthetic-password-for-offline-tests" + "@127.0.0.1:6379/0"


@pytest.mark.parametrize(
    "url",
    [
        "redis://localhost:6379/0",
        "amqp://host/",
        "redis://:short@localhost/0",
        BROKER + "?credential_provider=untrusted",
        BROKER + "#fragment",
    ],
)
def test_broker_configuration_refuses_unsafe_or_implicit_auth(url: str) -> None:
    with pytest.raises(ValidationError):
        QueueSettings(broker_url=SecretStr(url))


def test_broker_url_is_secret_and_limits_are_bounded() -> None:
    settings = QueueSettings(broker_url=SecretStr(BROKER))
    assert BROKER not in repr(settings)
    with pytest.raises(ValidationError):
        QueueSettings(broker_url=SecretStr(BROKER), repository_limit=0)
    with pytest.raises(ValidationError):
        QueueSettings(broker_url=SecretStr(BROKER), namespace="bad:namespace")


@pytest.mark.parametrize(
    "message",
    [
        {"version": True},
        {"version": 2},
        {},
        {"version": 1, "kind": "review", "record_id": "invalid", "generation": 0},
        {"version": 1, "kind": "review", "record_id": str(uuid4()), "generation": True},
    ],
)
def test_poison_messages_never_invoke_business_logic(message: dict[str, Any]) -> None:
    calls: list[Envelope] = []
    app = create_app(QueueSettings(broker_url=SecretStr(BROKER)), calls.append)
    try:
        app.tasks[TASK_NAME].run(message)
        assert not calls
        assert app.conf.result_backend is None and app.conf.accept_content == ["json"]
        assert app.conf.task_acks_late and not app.conf.worker_enable_remote_control
    finally:
        app.close()


def test_task_registration_is_not_shared_between_app_instances() -> None:
    first: list[Envelope] = []
    second: list[Envelope] = []
    settings = QueueSettings(broker_url=SecretStr(BROKER))
    app1, app2 = create_app(settings, first.append), create_app(settings, second.append)
    message = Envelope(kind="review", record_id=uuid4(), generation=0)
    try:
        app1.tasks[TASK_NAME].run(message.model_dump(mode="json"))
        app2.tasks[TASK_NAME].run(message.model_dump(mode="json"))
        assert first == second == [message]
    finally:
        app1.close()
        app2.close()


@pytest.mark.parametrize(
    "environment,enabled", [("production", True), ("test", True), ("development", False)]
)
def test_development_operations_have_no_production_bypass(environment: str, enabled: bool) -> None:
    with pytest.raises(ReviewError, match="development_operations_disabled"):
        DevJobOperations(
            cast(Database, None), ReadScope(()), environment=environment, enabled=enabled
        )


def test_safe_logging_never_falls_back_to_raw_exception_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ClosedStream(io.StringIO):
        def write(self, text: str) -> int:
            raise ValueError("closed")

    stream = ClosedStream()
    monkeypatch.setattr("sys.stderr", stream)
    record = logging.LogRecord("celery", logging.ERROR, "", 1, "PRIVATE_SOURCE_SENTINEL", (), None)
    record.job_id = str(uuid4())
    request_id = str(uuid4())
    record.request_id = request_id
    handler = SafeStderrHandler()
    handler.setFormatter(SafeWorkerFormatter())
    assert "SENTINEL" not in handler.format(record)
    assert json.loads(handler.format(record))["request_id"] == request_id
    handler.emit(record)


def test_publisher_exception_is_sanitized() -> None:
    class Unavailable:
        def send_task(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("PRIVATE_SOURCE_SENTINEL")

    with pytest.raises(QueueUnavailable, match="^queue_unavailable$"):
        CeleryPublisher(Unavailable()).publish(
            Envelope(kind="review", record_id=uuid4(), generation=0)
        )
