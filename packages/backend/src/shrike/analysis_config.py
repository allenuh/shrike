"""Standalone engine settings; no dotenv loading or paid credential lookup in mock mode."""

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from shrike.domain.review import ReviewLimits


class AnalysisSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None, extra="ignore", hide_input_in_errors=True, populate_by_name=True
    )
    provider: Literal["mock", "openai"] = Field(
        default="mock", validation_alias=AliasChoices("AI_PROVIDER", "LLM_PROVIDER")
    )
    model: str = Field(default="gpt-6-luna", validation_alias="LLM_OPENAI_MODEL")
    live_enabled: bool = Field(default=False, validation_alias="LLM_LIVE_ENABLED")
    allow_private: bool = Field(default=False, validation_alias="LLM_ALLOW_PRIVATE_CODE")
    allowlist: str = Field(default="", validation_alias="LLM_MODEL_ALLOWLIST")
    pricing_path: Path | None = Field(default=None, validation_alias="LLM_PRICING_PROFILE_PATH")
    max_input: int = Field(
        default=12000, gt=0, le=12000, validation_alias="REVIEW_MAX_LLM_INPUT_TOKENS"
    )
    max_output: int = Field(
        default=2000, gt=0, le=2000, validation_alias="REVIEW_MAX_LLM_OUTPUT_TOKENS"
    )
    max_context: int = Field(
        default=131072, gt=0, le=262144, validation_alias="REVIEW_MAX_LLM_CONTEXT_BYTES"
    )
    max_llm_diff: int = Field(
        default=65536, gt=0, le=131072, validation_alias="REVIEW_MAX_LLM_DIFF_BYTES"
    )
    max_diff: int = Field(
        default=524288, gt=0, le=4194304, validation_alias="REVIEW_MAX_DIFF_BYTES"
    )
    max_file: int = Field(
        default=204800, gt=0, le=1048576, validation_alias="REVIEW_MAX_FILE_BYTES"
    )
    max_files: int = Field(default=20, gt=0, le=100, validation_alias="REVIEW_MAX_FILES")
    max_lines: int = Field(
        default=2000, gt=0, le=10000, validation_alias="REVIEW_MAX_CHANGED_LINES"
    )
    concurrency: int = Field(default=2, ge=1, le=2, validation_alias="REVIEW_MAX_CONCURRENCY")
    exclusions: str = Field(
        default="vendor/*,*/vendor/*,generated/*,*/generated/*,node_modules/*,*/node_modules/*,.venv/*,*/.venv/*",
        validation_alias="REVIEW_EXCLUSIONS",
    )
    timeout: int = Field(default=30, ge=1, le=30, validation_alias="LLM_REQUEST_TIMEOUT_SECONDS")
    attempts: Literal[1] = Field(default=1, validation_alias="LLM_MAX_REQUEST_ATTEMPTS")
    live_eval_enabled: bool = Field(default=False, validation_alias="LLM_LIVE_EVAL_ENABLED")
    live_eval_max: int = Field(default=0, ge=0, le=5, validation_alias="LLM_LIVE_EVAL_MAX_REQUESTS")

    def limits(self) -> ReviewLimits:
        return ReviewLimits(
            max_input_tokens=self.max_input,
            max_output_tokens=self.max_output,
            max_context_bytes=self.max_context,
            max_llm_diff_bytes=self.max_llm_diff,
            max_diff_bytes=self.max_diff,
            max_file_bytes=self.max_file,
            max_files=self.max_files,
            max_changed_lines=self.max_lines,
            exclusions=tuple(item for item in self.exclusions.split(",") if item),
            max_concurrency=self.concurrency,
        )
