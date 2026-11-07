from collections.abc import Callable
from typing import Any

from celery import Celery
from celery.signals import setup_logging
from pydantic import ValidationError

from shrike.domain.queue import Envelope, QueueUnavailable

from .config import QueueSettings
from .logging import configure_logging

TASK_NAME = "shrike.process"


def _safe_logging(**kwargs: Any) -> None:
    configure_logging()


# Prevent worker bootstrap from replacing sanitizing handlers with traceback/argument formatters.
setup_logging.connect(_safe_logging, weak=False)


def create_app(
    settings: QueueSettings, consumer: Callable[[Envelope], None] | None = None
) -> Celery:
    app = Celery("shrike", broker=settings.broker_url.get_secret_value())
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        result_backend=None,
        task_ignore_result=True,
        task_store_errors_even_if_ignored=False,
        task_default_queue=settings.namespace,
        task_default_exchange=settings.namespace,
        task_default_routing_key=settings.namespace,
        task_create_missing_queues=False,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        task_acks_on_failure_or_timeout=False,
        worker_prefetch_multiplier=1,
        worker_enable_remote_control=False,
        task_send_sent_event=False,
        worker_send_task_events=False,
        worker_hijack_root_logger=False,
        worker_redirect_stdouts=False,
        task_soft_time_limit=190,
        task_time_limit=210,
        broker_connection_timeout=3,
        broker_connection_retry_on_startup=True,
        broker_connection_max_retries=3,
        task_publish_retry=False,
        broker_transport_options={
            "visibility_timeout": 300,
            "socket_connect_timeout": 3,
            "socket_timeout": 3,
            "global_keyprefix": settings.namespace + ":",
        },
    )

    def consume(message: dict[str, Any]) -> None:
        logger = configure_logging()
        if (
            not isinstance(message, dict)
            or type(message.get("version")) is not int
            or message.get("version") != 1
        ):
            logger.warning("ignored")
            return
        try:
            envelope = Envelope.model_validate(message)
        except ValidationError:
            logger.warning("ignored")
            return
        try:
            if consumer is not None:
                consumer(envelope)
            else:
                from .runtime import consume_default

                consume_default(envelope)
        except Exception:
            # PostgreSQL redelivery/recovery owns retries. Never let Celery store/format raw
            # dependency exceptions or hot-loop an unbounded broker autoretry.
            logger.error(
                "failed",
                extra={
                    "kind": envelope.kind,
                    "record_id": str(envelope.record_id),
                    "outcome": "infrastructure_unavailable",
                },
            )

    app.task(
        name=TASK_NAME,
        ignore_result=True,
        autoretry_for=(),
        max_retries=0,
        shared=False,
        lazy=False,
    )(consume)
    configure_logging()
    return app


class CeleryPublisher:
    def __init__(self, app: Celery) -> None:
        self.app = app

    def publish(self, envelope: Envelope) -> None:
        try:
            self.app.send_task(
                TASK_NAME,
                args=[envelope.model_dump(mode="json")],
                argsrepr="[opaque identifiers]",
                kwargsrepr="{}",
                retry=False,
                ignore_result=True,
            )
        except Exception:
            raise QueueUnavailable from None
