"""Validated engine contracts. Source is data; these objects never execute it."""

import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReviewError(Exception):
    def __init__(self, code: str, *, retry_at: datetime | None = None) -> None:
        self.code = code
        self.retry_at = retry_at
        super().__init__(code)


def safe_path(value: str) -> str:
    if (
        not value
        or len(value) > 512
        or value.startswith(("/", "-"))
        or "\\" in value
        or ":" in value
        or any(part in {"", ".", "..", ".git"} for part in value.split("/"))
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError("Invalid relative path")
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class SourceFile(StrictModel):
    path: str
    content: str = Field(repr=False)
    kind: Literal["file", "symlink", "submodule", "binary"] = "file"

    _path = field_validator("path")(safe_path)


class ReviewInput(StrictModel):
    installation_id: int = Field(gt=0, lt=2**63)
    repository_id: int = Field(gt=0, lt=2**63)
    base_sha: str
    head_sha: str
    diff: str = Field(repr=False)
    files: tuple[SourceFile, ...] = Field(repr=False)
    private: bool = True

    @field_validator("base_sha", "head_sha")
    @classmethod
    def sha(cls, value: str) -> str:
        if not re.fullmatch(r"[a-f0-9]{40}(?:[a-f0-9]{24})?", value):
            raise ValueError("Invalid immutable SHA")
        return value


class ReviewLimits(StrictModel):
    max_concurrency: int = Field(default=2, ge=1, le=2)
    max_diff_bytes: int = Field(default=524288, gt=0, le=4194304)
    max_file_bytes: int = Field(default=204800, gt=0, le=1048576)
    max_files: int = Field(default=20, gt=0, le=100)
    max_changed_lines: int = Field(default=2000, gt=0, le=10000)
    max_context_bytes: int = Field(default=131072, gt=0, le=262144)
    max_llm_diff_bytes: int = Field(default=65536, gt=0, le=131072)
    max_input_tokens: int = Field(default=12000, gt=0, le=12000)
    max_output_tokens: int = Field(default=2000, gt=0, le=2000)
    max_findings: int = Field(default=100, gt=0, le=100)
    exclusions: tuple[str, ...] = (
        "vendor/*",
        "*/vendor/*",
        "generated/*",
        "*/generated/*",
        "node_modules/*",
        "*/node_modules/*",
        ".venv/*",
        "*/.venv/*",
    )


Category = Literal["correctness", "security", "reliability", "maintainability"]
Severity = Literal["info", "low", "medium", "high", "critical"]


class Candidate(StrictModel):
    category: Category
    severity: Severity
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    path: str = Field(max_length=512)
    line: int = Field(gt=0, le=1000000)
    problem: str = Field(min_length=8, max_length=1000)
    suggestion: str = Field(min_length=8, max_length=1000)
    evidence: str = Field(min_length=1, max_length=500, repr=False)
    rule: str = Field(min_length=1, max_length=80)

    _path = field_validator("path")(safe_path)


class ModelOutput(StrictModel):
    findings: list[Candidate] = Field(max_length=100)


class Finding(Candidate):
    analyzers: tuple[str, ...]
    fingerprint: str


class SelectedFile(StrictModel):
    path: str
    content: str = Field(repr=False)
    changed_lines: tuple[int, ...]


class Coverage(StrictModel):
    selected_files: int
    skipped: dict[str, int]
    changed_lines: int
    context_lines: int = 0


class ModelReply(StrictModel):
    text: str = Field(repr=False)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    model: str


class Report(StrictModel):
    retry_at: datetime | None = None
    analysis_hash: str
    pricing_verified_at: str | None = None
    status: Literal["completed", "partial", "static_only", "dry_run"]
    summary: str
    findings: tuple[Finding, ...]
    coverage: Coverage
    provider: str
    model: str
    prompt_version: str
    analyzer_version: str
    input_token_estimate: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: str | None
    reported_usage_cost_usd: str | None = None
    latency_ms: int = Field(ge=0)
    cache_hit: bool = False
    reason: str | None = None
    rejected_findings: int = 0


NonNegativeInt = Annotated[int, Field(ge=0, strict=True)]
