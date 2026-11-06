import secrets
from collections.abc import Iterator
from typing import Annotated, cast

from fastapi import Depends, Header, Request

from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.history import SqlHistoryReader
from shrike.config import Settings, parse_grants
from shrike.domain.access import ReadScope
from shrike.ports.history import HistoryReader

from .errors import ApiError


def get_scope(request: Request, authorization: Annotated[str | None, Header()] = None) -> ReadScope:
    settings = cast(Settings, request.app.state.settings)
    if not settings.enable_dev_auth or settings.app_env not in {"development", "test"}:
        raise ApiError(401, "authentication_required", "Authentication is required")
    if not authorization or len(authorization) > 520 or not authorization.startswith("Bearer "):
        raise ApiError(401, "authentication_required", "Authentication is required")
    supplied = authorization.removeprefix("Bearer ")
    if not secrets.compare_digest(
        supplied.encode("utf-8"), settings.dev_auth_token.get_secret_value().encode("utf-8")
    ):
        raise ApiError(401, "authentication_required", "Authentication is required")
    return ReadScope(parse_grants(settings.dev_repository_grants))


def get_reader(request: Request) -> Iterator[HistoryReader]:
    database = cast(Database, request.app.state.database)
    with database.session() as session:
        yield SqlHistoryReader(session)


Scope = Annotated[ReadScope, Depends(get_scope)]
Reader = Annotated[HistoryReader, Depends(get_reader)]
