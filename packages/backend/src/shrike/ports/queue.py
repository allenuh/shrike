from typing import Protocol

from shrike.domain.queue import DispatchClaim, Envelope


class JobPublisher(Protocol):
    def publish(self, envelope: Envelope) -> None: ...


class DispatchStore(Protocol):
    def claim(self) -> DispatchClaim | None: ...

    def sent(self, claim: DispatchClaim) -> None: ...

    def failed(self, claim: DispatchClaim) -> None: ...
