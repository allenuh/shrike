from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal

from pydantic import Field, model_validator

from shrike.domain.review import ReviewError, StrictModel


class PriceProfile(StrictModel):
    model: str
    source: str
    verified_at: datetime
    expires_at: datetime
    input_usd_per_million: Decimal = Field(gt=0, allow_inf_nan=False)
    output_usd_per_million: Decimal = Field(gt=0, allow_inf_nan=False)
    tier: str = "standard"
    # A deliberately explicit bounded override, never enabled by the shipped profile.
    # Operator must verify byte-token encoding and framing bounds for this exact API/model.
    byte_token_bound_approved: bool = False
    framing_token_bound: int = Field(default=4096, ge=4096, le=8192)

    @model_validator(mode="after")
    def valid(self) -> "PriceProfile":
        if (
            self.verified_at.tzinfo is None
            or self.expires_at.tzinfo is None
            or not timedelta(0) < self.expires_at - self.verified_at <= timedelta(hours=24)
            or self.tier != "standard"
            or self.source != "https://developers.openai.com/api/docs/pricing"
        ):
            raise ValueError("Invalid verified price profile")
        return self

    def check(self, model: str, *, live: bool = False) -> None:
        now = datetime.now(UTC)
        if model != self.model or not self.verified_at <= now < self.expires_at:
            raise ReviewError("pricing_unavailable")
        if live and not self.byte_token_bound_approved:
            raise ReviewError("token_bound_unverified")

    def micro_usd(self, input_tokens: int, output_tokens: int) -> int:
        # USD/million tokens == micro-USD/token.
        return int(
            (
                input_tokens * self.input_usd_per_million
                + output_tokens * self.output_usd_per_million
            ).to_integral_value(rounding=ROUND_CEILING)
        )


def dollars(micro_usd: int) -> str:
    return format(Decimal(micro_usd) / 1000000, ".6f")
