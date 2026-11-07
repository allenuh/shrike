from datetime import datetime
from typing import Protocol

from shrike.domain.queue import Envelope, ReviewClaim
from shrike.domain.review import Report


class ExecutionStore(Protocol):
    def claim(self, envelope: Envelope) -> ReviewClaim | None: ...

    def checkpoint(self, claim: ReviewClaim) -> None: ...

    def complete(self, claim: ReviewClaim, report: Report) -> None: ...

    def fail(
        self,
        claim: ReviewClaim,
        code: str,
        *,
        transient: bool = False,
        retry_at: datetime | None = None,
        canceled: bool = False,
    ) -> None: ...


class RequestAdmission(Protocol):
    def acquire(self) -> None: ...
