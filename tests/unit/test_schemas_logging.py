import json
import logging
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from shrike_api.logging import SafeJsonFormatter
from shrike_api.schemas import JobQuery, RepositoryQuery


@pytest.mark.parametrize("limit", [0, 101, -1])
def test_page_bounds(limit: int) -> None:
    with pytest.raises(ValidationError):
        RepositoryQuery(limit=limit)


def test_date_filters_require_timezones_and_order() -> None:
    with pytest.raises(ValidationError):
        JobQuery.model_validate({"created_after": "2026-01-01T12:00:00"})
    with pytest.raises(ValidationError):
        JobQuery(
            created_after=datetime(2026, 2, 1, tzinfo=UTC),
            created_before=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_json_formatter_ignores_sensitive_message_and_arbitrary_extras() -> None:
    record = logging.LogRecord("shrike.http", logging.INFO, "", 0, "SECRET_SENTINEL", (), None)
    record.request_id = "safe-generated-id"
    record.private_code = "SOURCE_SENTINEL"
    record.authorization = "TOKEN_SENTINEL"
    formatted = SafeJsonFormatter().format(record)
    assert "SENTINEL" not in formatted
    assert json.loads(formatted)["request_id"] == "safe-generated-id"
