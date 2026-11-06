import hashlib
import hmac
import json
import re

from pydantic import ValidationError

from shrike.domain.ingestion import IncomingWebhook

from .schemas import InstallationEvent, PullRequestEvent


class InvalidWebhook(ValueError):
    pass


def verify_signature(body: bytes, signature: str | None, secret: str) -> bool:
    if signature is None or not re.fullmatch(r"sha256=[0-9a-f]{64}", signature):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def parse_webhook(event: str, body: bytes, app_id: int) -> IncomingWebhook:
    try:
        raw = json.loads(body)
        if not isinstance(raw, dict):
            raise ValueError
        action = raw.get("action", "")
        if not isinstance(action, str) or len(action) > 64:
            raise ValueError
        if event == "pull_request":
            if action not in {"opened", "reopened", "synchronize", "ready_for_review", "closed"}:
                return IncomingWebhook(event, action, ignored_reason="unsupported_action")
            data = PullRequestEvent.model_validate_json(body)
            if data.installation.app_id is not None and data.installation.app_id != app_id:
                raise ValueError
            repo, pr = data.repository, data.pull_request
            reason = (
                "untrusted_fork" if pr.head.repo is None or pr.head.repo.id != repo.id else None
            )
            return IncomingWebhook(
                event,
                action,
                data.installation.id,
                repo.owner.id,
                repo.owner.type,
                repo.owner.login,
                repo.name,
                repo.id,
                pr.id,
                data.number,
                pr.base.sha,
                pr.head.sha,
                pr.head.repo.id if pr.head.repo else None,
                ignored_reason=reason,
            )
        if event in {"installation", "installation_repositories"}:
            allowed = (
                {"created", "deleted", "suspend", "unsuspend", "new_permissions_accepted"}
                if event == "installation"
                else {"added", "removed"}
            )
            if action not in allowed:
                return IncomingWebhook(event, action, ignored_reason="unsupported_action")
            data_install = InstallationEvent.model_validate_json(body)
            installation = data_install.installation
            if installation.app_id != app_id:
                raise ValueError
            if event == "installation_repositories" and not all(
                key in raw for key in ("repositories_added", "repositories_removed")
            ):
                raise ValueError
            return IncomingWebhook(
                event,
                action,
                installation.id,
                installation.account.id,
                installation.account.type,
                installation.account.login,
                removed_repositories=tuple(
                    (repo.id, repo.name) for repo in data_install.repositories_removed
                ),
            )
        return IncomingWebhook(event, action, ignored_reason="unsupported_event")
    except (ValueError, TypeError, KeyError, RecursionError, ValidationError):
        raise InvalidWebhook("Invalid webhook payload") from None
