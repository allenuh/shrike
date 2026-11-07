from typing import Protocol

from shrike.domain.ai_budget import PriceProfile


class SpendingLedger(Protocol):
    def reserve(
        self,
        call_id: str,
        amount: int,
        profile: PriceProfile,
        input_bound: int,
        output_bound: int,
        review_key: str = "",
    ) -> bool:
        """Atomically reserve money + slot, return whether warning threshold reached."""
        ...

    def settle(
        self, call_id: str, input_tokens: int | None, output_tokens: int | None
    ) -> int | None:
        """Keep full uncertainty if usage missing; return calculated micro-USD if known."""
        ...
