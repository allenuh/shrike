from datetime import datetime
from typing import Protocol

from shrike.domain.ingestion import IngestionClaim, IngestionResult


class IngestionStore(Protocol):
    def claim(self) -> IngestionClaim | None: ...

    def complete(self, claim: IngestionClaim, result: IngestionResult) -> None: ...

    def fail(self, claim: IngestionClaim, code: str, retry_at: datetime | None = None) -> None: ...
