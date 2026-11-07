import json
import logging

from shrike.telemetry import SafeStderrHandler


class SafeWorkerFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        result: dict[str, object] = {"event": "worker_event", "level": record.levelname}
        for name in (
            "job_id",
            "request_id",
            "attempt",
            "outcome",
            "kind",
            "record_id",
            "error_code",
        ):
            value = getattr(record, name, None)
            if value is not None:
                result[name] = value
        # Never format arbitrary library messages, task arguments, exceptions or URLs.
        return json.dumps(result)


def configure_logging() -> logging.Logger:
    handler = SafeStderrHandler()
    handler.setFormatter(SafeWorkerFormatter())
    for name in ("celery", "kombu", "amqp", "redis"):
        logger = logging.getLogger(name)
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.WARNING)
    logger = logging.getLogger("shrike.worker")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    return logger
