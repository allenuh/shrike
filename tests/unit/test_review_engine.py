import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest
from pydantic import SecretStr, TypeAdapter, ValidationError

from shrike.adapters.analysis.memory import MemoryAnalysisStore
from shrike.adapters.llm.mock import MockProvider
from shrike.adapters.llm.openai import OpenAIProvider
from shrike.analysis_config import AnalysisSettings
from shrike.application.diff import select_files
from shrike.application.prompts import build_context, payload
from shrike.application.review import ReviewEngine
from shrike.domain.access import ReadScope, RepositoryGrant
from shrike.domain.ai_budget import PriceProfile
from shrike.domain.review import (
    Candidate,
    ModelOutput,
    ModelReply,
    ReviewError,
    ReviewLimits,
    SelectedFile,
)
from shrike.review_cli import EvalCase, snapshot


@dataclass
class FakeAnalyzer:
    version: str = "fake-static-v1"
    findings: tuple[Candidate, ...] = ()
    calls: int = 0

    def analyze(self, file: SelectedFile) -> tuple[Candidate, ...]:
        self.calls += 1
        return self.findings


def request(code: str = "value = 10 / 0\n") -> Any:
    return snapshot(EvalCase(id="test", code=code, expected=None))


def store() -> MemoryAnalysisStore:
    return MemoryAnalysisStore(ReadScope((RepositoryGrant(710001, 810001),)))


def price(**changes: Any) -> PriceProfile:
    values = dict(
        model="gpt-6-luna",
        source="https://developers.openai.com/api/docs/pricing",
        verified_at=datetime.now(UTC) - timedelta(minutes=5),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        input_usd_per_million="0.10",
        output_usd_per_million="0.50",
        byte_token_bound_approved=True,
    )
    return PriceProfile.model_validate(values | changes)


def candidate(**changes: Any) -> Candidate:
    values = dict(
        category="correctness",
        severity="high",
        confidence=0.9,
        path="demo.py",
        line=1,
        problem="Division by literal zero fails",
        suggestion="Use a nonzero divisor instead",
        evidence="value = 10 / 0",
        rule="division-by-zero",
    )
    return Candidate.model_validate(values | changes)


class ReplyProvider:
    name = "mock"
    model = "mock-v1"

    def __init__(self, text: str = '{"findings":[]}') -> None:
        self.text = text
        self.calls = 0

    def review(self, context: str, max_output_tokens: int) -> ModelReply:
        self.calls += 1
        return ModelReply(text=self.text, model=self.model)


def test_mock_report_cache_and_dry_run() -> None:
    analyzer = FakeAnalyzer()
    engine = ReviewEngine(analyzer, MockProvider(), store())
    first = engine.analyze(request())
    assert first.status == "completed" and len(first.findings) == 1
    assert first.findings[0].line == 1 and first.findings[0].analyzers == ("mock",)
    assert first.estimated_cost_usd == "0.000000" and first.input_tokens is None
    second = engine.analyze(request())
    assert second.cache_hit and second.findings == first.findings and analyzer.calls == 1
    assert engine.analyze(request(), dry_run=True).status == "dry_run"


def test_authorization_checked_even_for_cached_results() -> None:
    cache = store()
    engine = ReviewEngine(FakeAnalyzer(), MockProvider(), cache)
    engine.analyze(request())
    cache.scope = ReadScope(())
    with pytest.raises(ReviewError, match="repository_denied"):
        engine.analyze(request())


@pytest.mark.parametrize("field,value", [("repository_id", 810002), ("installation_id", 710002)])
def test_cross_scope_denied(field: str, value: int) -> None:
    with pytest.raises(ReviewError, match="repository_denied"):
        ReviewEngine(FakeAnalyzer(), MockProvider(), store()).analyze(
            request().model_copy(update={field: value})
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("path", "invented.py"),
        ("line", 2),
        ("evidence", "invented"),
        ("confidence", 0.2),
        ("problem", "<script>bad</script>"),
        ("suggestion", "Visit https://evil.invalid"),
        ("category", "security"),
    ],
)
def test_untrusted_candidates_rejected(field: str, value: Any) -> None:
    provider = ReplyProvider(ModelOutput(findings=[candidate(**{field: value})]).model_dump_json())
    result = ReviewEngine(FakeAnalyzer(), provider, store()).analyze(request())
    assert not result.findings and result.rejected_findings == 1 and result.status == "partial"


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        '{"findings":[],"extra":1}',
        '{"findings":[{"line":"1"}]}',
        "```json\n{}\n```",
    ],
)
def test_invalid_output_is_static_only(text: str) -> None:
    result = ReviewEngine(FakeAnalyzer(), ReplyProvider(text), store()).analyze(request())
    assert result.status == "static_only" and result.reason == "model_output_invalid"


def test_deduplicate_static_model_with_provenance() -> None:
    c = candidate(rule="F821")
    provider = ReplyProvider(
        ModelOutput(
            findings=[c.model_copy(update={"problem": "Different wording for same issue"})]
        ).model_dump_json()
    )
    result = ReviewEngine(FakeAnalyzer(findings=(c,)), provider, store()).analyze(request())
    assert len(result.findings) == 1 and result.findings[0].analyzers == ("mock", "ruff")


def test_security_requires_known_operation_and_normalizes_claim() -> None:
    provider = ReplyProvider(
        ModelOutput(
            findings=[
                candidate(
                    category="security",
                    rule="unsafe-eval-input",
                    evidence="eval(input())",
                    problem="Speculative remote kernel compromise",
                )
            ]
        ).model_dump_json()
    )
    result = ReviewEngine(FakeAnalyzer(), provider, store()).analyze(
        request("value = eval(input())\n")
    )
    assert len(result.findings) == 1
    assert "kernel" not in result.findings[0].problem


@pytest.mark.parametrize(
    "path",
    ["../bad.py", "/bad.py", "a/../b.py", "a\\b.py", "a:b.py", "a//b.py", ".git/a.py", "a\x00.py"],
)
def test_paths_rejected(path: str) -> None:
    with pytest.raises(ValidationError):
        candidate(path=path)


def test_input_limits_and_context_truncation() -> None:
    with pytest.raises(ReviewError, match="diff_size_limit"):
        select_files(request(), ReviewLimits(max_diff_bytes=1))
    with pytest.raises(ReviewError, match="changed_line_limit"):
        select_files(request("a = 1\nb = 2\n"), ReviewLimits(max_changed_lines=1))
    files, coverage = select_files(request(), ReviewLimits(max_file_bytes=1))
    assert not files and coverage.skipped == {"file_size_limit": 1}
    files, _ = select_files(request(), ReviewLimits())
    _, count, omitted = build_context(files, ReviewLimits(max_llm_diff_bytes=1))
    assert count == 0 and omitted
    provider = ReplyProvider()
    result = ReviewEngine(
        FakeAnalyzer(), provider, store(), ReviewLimits(max_input_tokens=1)
    ).analyze(request())
    assert provider.calls == 0 and result.reason == "context_token_limit"


@pytest.mark.parametrize(
    "change,code",
    [
        (lambda s: s.rsplit("\n", 2)[0] + "\n", "incomplete_diff"),
        (lambda s: s.replace("+value = 10 / 0", "+value = invented"), "snapshot_diff_mismatch"),
        (lambda s: s.replace("@@ -0,0 +1 @@", "@@ -0,0 +1,3 @@"), "incomplete_diff"),
        (lambda s: s + s, "duplicate_diff_path"),
        (lambda s: s.replace("b/demo.py", "b/../bad.py"), "unsafe_diff_path"),
    ],
)
def test_malformed_diff(change: Any, code: str) -> None:
    value = request()
    with pytest.raises(ReviewError, match=code):
        select_files(value.model_copy(update={"diff": change(value.diff)}), ReviewLimits())


def test_rename_and_unchanged_lines() -> None:
    value = request("before = 1\nvalue = 10 / 0\n")
    diff = (
        "diff --git a/old.py b/demo.py\nsimilarity index 70%\n"
        "rename from old.py\nrename to demo.py\n"
        "--- a/old.py\n+++ b/demo.py\n@@ -1 +1,2 @@\n before = 1\n+value = 10 / 0\n"
    )
    files, _ = select_files(value.model_copy(update={"diff": diff}), ReviewLimits())
    assert files[0].changed_lines == (2,)


@pytest.mark.parametrize("kind", ["symlink", "submodule", "binary"])
def test_unsafe_types_skipped(kind: str) -> None:
    value = request()
    source = value.files[0].model_copy(update={"kind": kind})
    files, coverage = select_files(value.model_copy(update={"files": (source,)}), ReviewLimits())
    assert not files and coverage.skipped == {"unsafe_file_type": 1}


def test_config_default_mock_and_ambient_key_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "synthetic-sentinel")
    assert AnalysisSettings().provider == "mock"
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    assert AnalysisSettings().provider == "mock"


def test_pricing_expiry_model_bound_and_units() -> None:
    assert price().micro_usd(12000, 2000) == 2200
    with pytest.raises(ReviewError, match="pricing_unavailable"):
        price(model="other").check("gpt-6-luna")
    with pytest.raises(ReviewError, match="token_bound_unverified"):
        price(byte_token_bound_approved=False).check("gpt-6-luna", live=True)
    with pytest.raises(ValidationError):
        price(input_usd_per_million="NaN")


def test_dry_run_quotes_without_request_or_ledger() -> None:
    provider = ReplyProvider()
    provider.name, provider.model = "openai", "gpt-6-luna"
    result = ReviewEngine(FakeAnalyzer(), provider, store(), pricing=price()).analyze(
        request(), dry_run=True
    )
    assert (
        result.status == "dry_run" and result.estimated_cost_usd is not None and provider.calls == 0
    )


@pytest.mark.parametrize(
    "status,reason",
    [
        (429, "provider_rate_limited"),
        (401, "provider_unauthorized"),
        (500, "provider_failed"),
        (302, "provider_failed"),
    ],
)
def test_openai_error_codes_no_retries(status: int, reason: str) -> None:
    calls = []

    def handle(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return httpx.Response(status, json={"error": "PRIVATE_SOURCE_SENTINEL"})

    provider = OpenAIProvider(
        "gpt-6-luna", SecretStr("synthetic-key"), transport=httpx.MockTransport(handle)
    )
    try:
        with pytest.raises(ReviewError, match=reason):
            provider.review("{}", 2000)
        assert len(calls) == 1
    finally:
        provider.close()


def test_openai_structured_output_usage_and_timeout() -> None:
    def handle(req: httpx.Request) -> httpx.Response:
        data = json.loads(req.content)
        assert str(req.url) == "https://api.openai.com/v1/responses"
        assert data["text"]["format"]["strict"] and data["store"] is False and "tools" not in data
        assert data["max_output_tokens"] == 2000
        return httpx.Response(
            200,
            json={
                "model": "gpt-6-luna",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": '{"findings":[]}'}],
                    }
                ],
                "usage": {"input_tokens": 100, "output_tokens": 20},
            },
        )

    provider = OpenAIProvider(
        "gpt-6-luna", SecretStr("synthetic-key"), transport=httpx.MockTransport(handle)
    )
    try:
        result = provider.review("{}", 2000)
        assert result.input_tokens == 100 and result.output_tokens == 20
    finally:
        provider.close()

    def timeout(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("PRIVATE_SOURCE_SENTINEL")

    provider = OpenAIProvider(
        "gpt-6-luna", SecretStr("synthetic-key"), transport=httpx.MockTransport(timeout)
    )
    try:
        with pytest.raises(ReviewError, match="provider_timeout"):
            provider.review("{}", 2000)
    finally:
        provider.close()


def test_prompt_schema_and_evaluation_corpus() -> None:
    cases = TypeAdapter(list[EvalCase]).validate_json(
        Path("tests/fixtures/analysis/cases.json").read_bytes()
    )
    assert sum(c.expected is not None for c in cases) == 10
    assert sum(c.expected is None for c in cases) == 10
    schema = payload("gpt-6-luna", "{}", 2000)["text"]["format"]["schema"]
    assert schema["additionalProperties"] is False
    assert all(value.get("additionalProperties") is False for value in schema["$defs"].values())


def test_cache_includes_policy_model_and_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    cache, analyzer, provider = store(), FakeAnalyzer(), ReplyProvider()
    engine = ReviewEngine(analyzer, provider, cache)
    first = engine.analyze(request())
    provider.model = "mock-v2"
    second = engine.analyze(request())
    monkeypatch.setattr("shrike.application.review.PROMPT_VERSION", "review-v2")
    third = engine.analyze(request())
    assert len({first.analysis_hash, second.analysis_hash, third.analysis_hash}) == 3
    assert analyzer.calls == 3 and not third.cache_hit


def test_exclusions_missing_and_nonpython_are_disclosed() -> None:
    value = request()
    for path, reason in [("vendor/demo.py", "excluded"), ("demo.txt", "unsupported_type")]:
        modified = value.model_copy(
            update={
                "diff": value.diff.replace("demo.py", path),
                "files": (value.files[0].model_copy(update={"path": path}),),
            }
        )
        files, coverage = select_files(modified, ReviewLimits())
        assert not files and coverage.skipped == {reason: 1}
    files, coverage = select_files(value.model_copy(update={"files": ()}), ReviewLimits())
    assert not files and coverage.skipped == {"missing_content": 1}


@pytest.mark.parametrize("key", ["", "<placeholder>"])
def test_missing_live_credentials_are_safe(key: str) -> None:
    with pytest.raises(ReviewError, match="credentials_missing"):
        OpenAIProvider("gpt-6-luna", SecretStr(key))


@pytest.mark.parametrize(
    "diff",
    [
        "diff --git a/demo.py b/demo.py\nGIT binary patch\nliteral 10\nencoded-binary-data\n",
        "diff --git a/old.py b/demo.py\nsimilarity index 100%\n"
        "rename from old.py\nrename to demo.py\n",
        "diff --git a/demo.py b/demo.py\n--- a/demo.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-deleted\n",
    ],
)
def test_binary_deleted_and_pure_rename_skips(diff: str) -> None:
    files, coverage = select_files(request().model_copy(update={"diff": diff}), ReviewLimits())
    assert not files and coverage.skipped == {"unsupported_or_deleted": 1}


@pytest.mark.parametrize("code", ["value = 10 / 0.5\n", "# value = 10 / 0\n", 'value = "10 / 0"\n'])
def test_mock_does_not_report_comments_strings_or_nonzero_decimals(code: str) -> None:
    report = ReviewEngine(FakeAnalyzer(), MockProvider(), store()).analyze(request(code))
    assert not report.findings


@pytest.mark.parametrize("code", ['value = "eval(input())"\n', "# eval(input())\n"])
def test_security_evidence_does_not_accept_comment_or_string(code: str) -> None:
    provider = ReplyProvider(
        ModelOutput(
            findings=[
                candidate(category="security", rule="unsafe-eval-input", evidence="eval(input())")
            ]
        ).model_dump_json()
    )
    assert not ReviewEngine(FakeAnalyzer(), provider, store()).analyze(request(code)).findings
