from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from shrike.domain.review import StrictModel


class QueueUnavailable(Exception):
    def __init__(self) -> None:
        super().__init__("queue_unavailable")


class Envelope(StrictModel):
    version: Literal[1] = 1
    kind: Literal["ingestion", "review"]
    record_id: UUID
    generation: int = Field(ge=0, le=2147483647, strict=True)


@dataclass(frozen=True)
class DispatchClaim:
    id: UUID
    fence: UUID
    request_id: UUID
    envelope: Envelope


@dataclass(frozen=True)
class ReviewClaim:
    id: UUID
    fence: UUID
    request_id: UUID
    generation: int
    installation_generation: int
    installation_id: int
    account_id: int
    repository_id: int
    owner: str
    name: str
    private: bool
    pr_id: int
    number: int
    base_sha: str
    head_sha: str
    attempt: int
    deadline: datetime
