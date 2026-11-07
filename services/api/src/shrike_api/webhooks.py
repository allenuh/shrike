import hashlib
import re
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from shrike.adapters.github.webhooks import InvalidWebhook, parse_webhook, verify_signature
from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.ingestion import WebhookConflict, accept_delivery
from shrike.config import Settings

from .errors import ApiError

router = APIRouter()


@router.post("/webhooks/github")
async def github_webhook(request: Request) -> JSONResponse:
    settings = cast(Settings, request.app.state.settings)
    if not settings.github_webhooks_enabled:
        raise ApiError(503, "webhooks_disabled", "GitHub webhooks are disabled")
    for header in ("x-hub-signature-256", "x-github-event", "x-github-delivery", "content-length"):
        if len(request.headers.getlist(header)) > 1:
            raise ApiError(400, "invalid_webhook_headers", "Invalid webhook headers")
    if request.headers.get("content-encoding", "identity") != "identity":
        raise ApiError(415, "unsupported_encoding", "Unsupported content encoding")
    if request.headers.get("content-type", "").split(";")[0].lower() != "application/json":
        raise ApiError(415, "unsupported_content_type", "Expected application/json")
    length = request.headers.get("content-length")
    if length and not re.fullmatch(r"[0-9]{1,10}", length):
        raise ApiError(400, "invalid_content_length", "Invalid content length")
    if length and int(length) > settings.webhook_max_bytes:
        raise ApiError(413, "webhook_too_large", "Webhook payload is too large")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > settings.webhook_max_bytes:
            raise ApiError(413, "webhook_too_large", "Webhook payload is too large")
        body.extend(chunk)
    raw = bytes(body)
    if not verify_signature(
        raw,
        request.headers.get("x-hub-signature-256"),
        settings.github_webhook_secret.get_secret_value(),
    ):
        raise ApiError(401, "invalid_webhook_signature", "Invalid webhook signature")
    event = request.headers.get("x-github-event", "")
    if not re.fullmatch(r"[a-z_]{1,64}", event):
        raise ApiError(400, "invalid_webhook_headers", "Invalid webhook headers")
    try:
        delivery = str(UUID(request.headers.get("x-github-delivery", "")))
        incoming = parse_webhook(event, raw, settings.github_app_id)
    except (ValueError, InvalidWebhook):
        raise ApiError(400, "invalid_webhook_payload", "Invalid webhook payload") from None
    database = cast(Database, request.app.state.database)

    def persist() -> bool:
        try:
            with database.session() as session, session.begin():
                return accept_delivery(
                    session,
                    delivery,
                    hashlib.sha256(raw).hexdigest(),
                    incoming,
                    UUID(request.state.request_id),
                )
        except WebhookConflict:
            raise ApiError(409, "webhook_identity_conflict", "Webhook identity conflict") from None

    accepted = await run_in_threadpool(persist)
    return JSONResponse(
        status_code=202 if accepted else 200,
        content={"status": "accepted" if accepted else "duplicate"},
    )
