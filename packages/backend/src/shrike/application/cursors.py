"""Bounded, filter-bound keyset cursors. A cursor never confers authorization."""

import base64
import hashlib
import json
from dataclasses import dataclass
from uuid import UUID


class InvalidCursor(ValueError):
    pass


def context_digest(*parts: object) -> str:
    return hashlib.sha256(repr(parts).encode()).hexdigest()


@dataclass(frozen=True)
class Cursor:
    value: str
    id: UUID


def encode_cursor(cursor: Cursor, context: str) -> str:
    raw = json.dumps(
        {"v": 1, "value": cursor.value, "id": str(cursor.id), "context": context},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(token: str, context: str) -> Cursor:
    try:
        if len(token) > 2048:
            raise ValueError
        raw = base64.b64decode(token, altchars=b"-_", validate=True)
        data = json.loads(raw)
        if (
            not isinstance(data, dict)
            or set(data) != {"v", "value", "id", "context"}
            or data["v"] != 1
            or type(data["v"]) is not int
            or data["context"] != context
            or not isinstance(data["id"], str)
            or not isinstance(data["value"], str)
            or len(data["value"]) > 1024
        ):
            raise ValueError
        return Cursor(data["value"], UUID(data["id"]))
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise InvalidCursor("Invalid or incompatible cursor") from None
