import json
import logging

from shrike.telemetry import SafeStderrHandler


class SafeJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Do not serialize messages, exceptions, arbitrary extras, headers, paths, or query strings.
        return json.dumps(
            {
                "event": "http_request",
                "level": record.levelname,
                **{
                    name: getattr(record, name)
                    for name in ("request_id", "method", "status", "duration_ms")
                    if hasattr(record, name)
                },
            }
        )


def configure_logging() -> logging.Logger:
    # Uvicorn's default access logger includes URL/query strings, which may contain private input.
    logging.getLogger("uvicorn.access").disabled = True
    logger = logging.getLogger("shrike.http")
    if not logger.handlers or not any(
        isinstance(handler, SafeStderrHandler) for handler in logger.handlers
    ):
        logger.handlers = []
        handler = SafeStderrHandler()
        handler.setFormatter(SafeJsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
