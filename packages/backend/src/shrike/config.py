"""Explicit process configuration; deliberately never loads a checkout's .env."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

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
    github_webhooks_enabled: bool = Field(default=False, validation_alias="GITHUB_WEBHOOKS_ENABLED")
    github_mode: Literal["disabled", "live"] = Field(
        default="disabled", validation_alias="GITHUB_MODE"
    )
    github_publishing_enabled: bool = Field(
        default=False, validation_alias="GITHUB_PUBLISHING_ENABLED"
    )
    github_publish_repository_grants: str = Field(
        default="", validation_alias="GITHUB_PUBLISH_REPOSITORY_GRANTS"
    )
    github_user_auth_enabled: bool = Field(
        default=False, validation_alias="GITHUB_USER_AUTH_ENABLED"
    )
    github_oauth_client_secret: SecretStr = Field(
        default=SecretStr(""), validation_alias="GITHUB_OAUTH_CLIENT_SECRET"
    )
    dashboard_origin: str = Field(
        default="http://localhost:3000", validation_alias="DASHBOARD_ORIGIN"
    )
    dashboard_token_key: SecretStr = Field(
        default=SecretStr(""), validation_alias="DASHBOARD_TOKEN_KEY"
    )

    @property
    def dashboard_callback(self) -> str:
        return self.dashboard_origin + "/api/backend/auth/github/callback"

    @property
    def secure_dashboard_cookies(self) -> bool:
        return self.dashboard_origin.startswith("https://")

    github_app_id: int = Field(default=0, ge=0, lt=2**63, validation_alias="GITHUB_APP_ID")
    github_app_client_id: str | None = Field(default=None, validation_alias="GITHUB_APP_CLIENT_ID")
    github_app_private_key_path: Path | None = Field(
        default=None, repr=False, validation_alias="GITHUB_APP_PRIVATE_KEY_PATH"
    )
    github_webhook_secret: SecretStr = Field(
        default=SecretStr(""), validation_alias="GITHUB_WEBHOOK_SECRET"
    )
    webhook_max_bytes: int = Field(
        default=1048576, ge=1024, le=4194304, validation_alias="WEBHOOK_MAX_BYTES"
    )
    review_max_files: int = Field(default=20, ge=1, le=1000, validation_alias="REVIEW_MAX_FILES")
    review_max_file_bytes: int = Field(
        default=204800, ge=1, le=1048576, validation_alias="REVIEW_MAX_FILE_BYTES"
    )
    review_max_diff_bytes: int = Field(
        default=524288, ge=1, le=4194304, validation_alias="REVIEW_MAX_DIFF_BYTES"
    )

    @model_validator(mode="after")
    def validate_security(self) -> "Settings":
        parse_grants(self.github_publish_repository_grants)
        if self.github_user_auth_enabled:
            from cryptography.fernet import Fernet

            origin = urlsplit(self.dashboard_origin)
            if (
                origin.scheme not in {"http", "https"}
                or not origin.hostname
                or origin.username
                or origin.password
                or origin.path
                or origin.query
                or origin.fragment
                or (
                    origin.scheme == "http"
                    and (
                        self.app_env == "production"
                        or origin.hostname not in {"localhost", "127.0.0.1", "::1"}
                    )
                )
            ):
                raise ValueError(
                    "Dashboard requires a fixed HTTPS origin (loopback HTTP in development)"
                )
            if (
                self.github_app_id <= 0
                or not self.github_app_client_id
                or not self.github_oauth_client_secret.get_secret_value()
                or self.github_oauth_client_secret.get_secret_value().startswith("<")
            ):
                raise ValueError("User authorization requires explicit GitHub App credentials")
            try:
                Fernet(self.dashboard_token_key.get_secret_value().encode())
            except Exception:
                raise ValueError("Dashboard requires a generated Fernet encryption key") from None
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
        if self.github_webhooks_enabled:
            secret = self.github_webhook_secret.get_secret_value()
            if self.github_app_id <= 0 or not 32 <= len(secret) <= 512 or secret.startswith("<"):
                raise ValueError("Webhooks require an App ID and generated webhook secret")
        if self.github_mode == "live" and (
            self.github_app_id <= 0 or self.github_app_private_key_path is None
        ):
            raise ValueError("Live GitHub requires explicit App ID and private key path")
        return self
