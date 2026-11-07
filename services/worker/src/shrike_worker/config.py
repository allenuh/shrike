from urllib.parse import unquote, urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class QueueSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None, populate_by_name=True, hide_input_in_errors=True, extra="ignore"
    )
    broker_url: SecretStr = Field(validation_alias="CELERY_BROKER_URL")
    namespace: str = Field(
        default="shrike", pattern=r"^[a-z][a-z0-9-]{0,40}$", validation_alias="QUEUE_NAMESPACE"
    )
    repository_limit: int = Field(
        default=1, ge=1, le=2, validation_alias="REVIEW_MAX_PER_REPOSITORY"
    )
    lease_seconds: int = Field(default=240, ge=210, le=600, validation_alias="REVIEW_LEASE_SECONDS")
    deadline_seconds: int = Field(
        default=180, ge=1, le=180, validation_alias="REVIEW_TIMEOUT_SECONDS"
    )
    retry_base_seconds: float = Field(
        default=5, ge=1, le=60, validation_alias="REVIEW_RETRY_BASE_SECONDS"
    )
    provider_rpm: int = Field(
        default=60, ge=1, le=6000, validation_alias="WORKER_PROVIDER_REQUESTS_PER_MINUTE"
    )
    concurrency: int = Field(default=2, ge=1, le=2, validation_alias="REVIEW_MAX_CONCURRENCY")

    @model_validator(mode="after")
    def validate_broker(self) -> "QueueSettings":
        try:
            url = urlsplit(self.broker_url.get_secret_value())
            if (
                url.scheme not in {"redis", "rediss"}
                or not url.hostname
                or url.query
                or url.fragment
                or not url.path[1:].isdigit()
                or not 0 <= int(url.path[1:]) <= 15
                or len(unquote(url.password or "")) < 32
                or "<" in self.broker_url.get_secret_value()
            ):
                raise ValueError
            _ = url.port
        except ValueError:
            raise ValueError("Queue requires an explicit authenticated Redis URL") from None
        return self
