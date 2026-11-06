import pytest

from shrike_api.seed import main


@pytest.mark.parametrize(
    "environment,database",
    [
        ("production", "shrike_demo"),
        ("development", "production_database"),
    ],
)
def test_seed_cli_refuses_wrong_environment_or_database_before_connecting(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    environment: str,
    database: str,
) -> None:
    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setenv("ENABLE_DEV_AUTH", "false")
    monkeypatch.setenv("DATABASE_URL", f"postgresql+psycopg://synthetic@127.0.0.1/{database}")
    monkeypatch.setattr("sys.argv", ["shrike_api.seed", "--confirm-development"])
    with pytest.raises(SystemExit) as result:
        main()
    assert result.value.code == 2
    assert "loopback shrike_demo" in capsys.readouterr().err


def test_seed_cli_requires_explicit_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.argv", ["shrike_api.seed"])
    with pytest.raises(SystemExit) as result:
        main()
    assert result.value.code == 2
