"""Bounded advisory publication contracts; no transport or analysis execution."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from shrike.domain.queue import ReviewClaim
from shrike.domain.review import Report, StrictModel, safe_path


class InlineComment(StrictModel):
    path: str
    line: int = Field(gt=0, le=1000000)
    side: Literal["RIGHT"] = "RIGHT"
    body: str = Field(min_length=1, max_length=3000)

    def github_payload(self) -> dict[str, object]:
        safe_path(self.path)
        return self.model_dump()


class PublicationPlan(StrictModel):
    body: str = Field(min_length=1, max_length=24000)
    comments: tuple[InlineComment, ...] = Field(max_length=10)


@dataclass(frozen=True)
class PublishedReview:
    id: int
    commit_id: str
    body: str
    own: bool
    state: str


@dataclass(frozen=True)
class PublishedComment:
    id: int
    body: str
    own: bool


@dataclass(frozen=True)
class PublicationClaim:
    context: ReviewClaim
    report: Report
    marker: str
    uncertain: bool
    summary_only: bool
    plan: PublicationPlan | None
    review_id: int | None


@dataclass(frozen=True)
class PublicationOutcome:
    job_id: UUID
    state: str
    review_id: int | None = None
    comment_ids: tuple[int, ...] = ()
    reason: str | None = None
    retry_at: datetime | None = None
