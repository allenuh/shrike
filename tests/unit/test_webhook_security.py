import hashlib
import hmac
import json

import pytest
from fakes import github_fixture

from shrike.adapters.github.webhooks import InvalidWebhook, parse_webhook, verify_signature


def test_hmac_uses_exact_utf8_bytes_and_constant_time_comparison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "synthetic-webhook-secret"
    body = json.dumps({"action": "test", "text": "café"}, ensure_ascii=False).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    original = hmac.compare_digest
    called = []

    def compare(left: str, right: str) -> bool:
        called.append(True)
        return original(left, right)

    monkeypatch.setattr(hmac, "compare_digest", compare)
    assert verify_signature(body, signature, secret)
    assert called
    assert not verify_signature(body + b" ", signature, secret)
    assert not verify_signature(body, signature, "wrong")


@pytest.mark.parametrize("signature", [None, "", "sha1=123", "sha256=wrong", "sha256=" + "f" * 63])
def test_rejects_invalid_signature_shapes(signature: str | None) -> None:
    assert not verify_signature(b"{}", signature, "secret")


@pytest.mark.parametrize("mutation", ["base", "number", "app", "owner", "boolean_id", "sha"])
def test_payload_identity_validation(mutation: str) -> None:
    payload = github_fixture("pull_request_opened.json")
    if mutation == "base":
        payload["pull_request"]["base"]["repo"]["id"] = 999
    elif mutation == "number":
        payload["number"] = 999
    elif mutation == "app":
        payload["installation"]["app_id"] = 999
    elif mutation == "owner":
        payload["pull_request"]["base"]["repo"]["owner"]["id"] = 999
    elif mutation == "boolean_id":
        payload["repository"]["id"] = True
    else:
        payload["pull_request"]["head"]["sha"] = "branch-name"
    with pytest.raises(InvalidWebhook):
        parse_webhook("pull_request", json.dumps(payload).encode(), 12345)


def test_fork_or_deleted_head_repository_is_not_reviewable() -> None:
    payload = github_fixture("pull_request_opened.json")
    payload["pull_request"]["head"]["repo"] = None
    result = parse_webhook("pull_request", json.dumps(payload).encode(), 12345)
    assert result.ignored_reason == "untrusted_fork"
    assert "SENTINEL" not in repr(result)
