from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from shrike.config import Settings, parse_grants
from shrike.domain.access import RepositoryGrant

URL = SecretStr("postgresql+psycopg://synthetic@127.0.0.1/shrike_demo")


def test_security_defaults_deny_access(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("APP_ENV", "ENABLE_DEV_AUTH", "DEV_AUTH_TOKEN", "DEV_REPOSITORY_GRANTS"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(database_url=URL)
    assert settings.app_env == "production"
    assert not settings.enable_dev_auth


@pytest.mark.parametrize("value", ["1", "1:2:3", "0:2", "-1:2", "1:no", "1:2,", f"1:{2**63}"])
def test_invalid_grants(value: str) -> None:
    with pytest.raises(ValueError, match="Invalid development repository grants"):
        parse_grants(value)


def test_grants_are_explicit_deduplicated_pairs() -> None:
    assert parse_grants("2:20,1:10,2:20") == (RepositoryGrant(1, 10), RepositoryGrant(2, 20))
    assert parse_grants("") == ()


def test_production_rejects_development_auth() -> None:
    with pytest.raises(ValidationError, match="forbidden in production"):
        Settings(database_url=URL, app_env="production", enable_dev_auth=True)


@pytest.mark.parametrize("value", ["", "short", "<generate-a-long-development-token-value>"])
def test_dev_auth_needs_generated_token(value: str) -> None:
    with pytest.raises(ValidationError, match="requires a generated"):
        Settings(
            database_url=URL,
            app_env="development",
            enable_dev_auth=True,
            dev_auth_token=SecretStr(value),
        )


def test_bad_database_url_validation_does_not_echo_secret() -> None:
    sentinel = "SYNTHETIC_DATABASE_SECRET_SENTINEL"
    with pytest.raises(ValidationError) as result:
        Settings(database_url=SecretStr(f"sqlite:///{sentinel}"))
    assert sentinel not in str(result.value)


def test_configuration_does_not_load_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    (tmp_path / ".env").write_text("DATABASE_URL=sqlite:///SYNTHETIC_SECRET\n")
    with pytest.raises(ValidationError) as result:
        Settings()
    assert "Field required" in str(result.value)
    assert "SYNTHETIC_SECRET" not in str(result.value)
