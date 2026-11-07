from typing import Protocol

from shrike.domain.review import Candidate, ModelReply, Report, ReviewInput, SelectedFile


class Analyzer(Protocol):
    version: str

    def analyze(self, file: SelectedFile) -> tuple[Candidate, ...]: ...


class LLMProvider(Protocol):
    name: str
    model: str

    def review(self, context: str, max_output_tokens: int) -> ModelReply: ...


class AnalysisStore(Protocol):
    def authorize(self, request: ReviewInput) -> None: ...

    def cached(self, request: ReviewInput, digest: str) -> Report | None: ...

    def save(self, request: ReviewInput, digest: str, report: Report) -> None: ...
