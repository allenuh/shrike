"""Explicit process configuration; deliberately never loads a checkout's .env."""

from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from shrike.domain.access import RepositoryGrant


def parse_grants(value: str) -> tuple[RepositoryGrant, ...]:
    if not value:
        return ()
    try:
        pairs = [tuple(int(part) for part in item.split(":")) for item in value.split(",")]
        if len(pairs) > 1000 or any(
            len(pair) != 2 or any(not 0 < item < 2**63 for item in pair) for pair in pairs
        ):
            raise ValueError
        return tuple(RepositoryGrant(*pair) for pair in sorted(set(pairs)))
    except (TypeError, ValueError):
        raise ValueError("Invalid development repository grants") from None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None, populate_by_name=True, extra="ignore", hide_input_in_errors=True
    )

    database_url: SecretStr = Field(validation_alias="DATABASE_URL")
    app_env: Literal["development", "test", "production"] = Field(
        default="production", validation_alias="APP_ENV"
    )
    enable_dev_auth: bool = Field(default=False, validation_alias="ENABLE_DEV_AUTH")
    dev_auth_token: SecretStr = Field(default=SecretStr(""), validation_alias="DEV_AUTH_TOKEN")
    dev_repository_grants: str = Field(default="", validation_alias="DEV_REPOSITORY_GRANTS")

    @model_validator(mode="after")
    def validate_security(self) -> "Settings":
        try:
            url = make_url(self.database_url.get_secret_value())
            if url.drivername != "postgresql+psycopg" or not url.database:
                raise ValueError
        except Exception:
            raise ValueError("DATABASE_URL must identify a PostgreSQL psycopg database") from None
        if self.enable_dev_auth:
            if self.app_env not in {"development", "test"}:
                raise ValueError("Development authentication is forbidden in production")
            token = self.dev_auth_token.get_secret_value()
            if not 32 <= len(token) <= 512 or token.startswith("<"):
                raise ValueError(
                    "Development authentication requires a generated 32+ character token"
                )
            parse_grants(self.dev_repository_grants)
        return self
