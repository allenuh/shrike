import base64
import json
from uuid import uuid4

import pytest

from shrike.application.cursors import Cursor, InvalidCursor, decode_cursor, encode_cursor


def test_cursor_round_trip_and_context_binding() -> None:
    cursor = Cursor("2026-01-01T12:00:00+00:00", uuid4())
    token = encode_cursor(cursor, "filter-scope-digest")
    assert decode_cursor(token, "filter-scope-digest") == cursor
    with pytest.raises(InvalidCursor):
        decode_cursor(token, "different-filter-or-scope")


@pytest.mark.parametrize("value", ["bad!", "[]", "a" * 2049, "", "e30=", "____"])
def test_malformed_cursor(value: str) -> None:
    with pytest.raises(InvalidCursor):
        decode_cursor(value, "context")


@pytest.mark.parametrize("value", [None, 1, [], "a" * 1025])
def test_cursor_values_must_be_bounded_strings(value: object) -> None:
    token = base64.urlsafe_b64encode(
        json.dumps(
            {
                "v": 1,
                "value": value,
                "id": str(uuid4()),
                "context": "context",
            }
        ).encode()
    ).decode()
    with pytest.raises(InvalidCursor):
        decode_cursor(token, "context")


@pytest.mark.parametrize("identity", [None, 123, [], {}])
def test_cursor_identity_must_be_a_uuid_string(identity: object) -> None:
    token = base64.urlsafe_b64encode(
        json.dumps(
            {
                "v": 1,
                "value": "value",
                "id": identity,
                "context": "context",
            }
        ).encode()
    ).decode()
    with pytest.raises(InvalidCursor):
        decode_cursor(token, "context")
