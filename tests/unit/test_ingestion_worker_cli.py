import pytest

from shrike_worker import ingest


def test_worker_requires_explicit_live_configuration_before_connecting(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    attempted: list[bool] = []

    def unexpected_connection(*args: object) -> None:
        attempted.append(True)
        raise AssertionError("No database connection without explicit live configuration")

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://synthetic@127.0.0.1/unused")
    monkeypatch.setenv("GITHUB_MODE", "disabled")
    monkeypatch.setenv("GITHUB_WEBHOOKS_ENABLED", "false")
    monkeypatch.setattr("sys.argv", ["ingest", "--once"])
    monkeypatch.setattr(ingest, "Database", unexpected_connection)
    with pytest.raises(SystemExit) as result:
        ingest.main()
    assert result.value.code == 2 and not attempted
    assert "details suppressed" in capsys.readouterr().err


def test_worker_requires_once_or_watch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["ingest"])
    with pytest.raises(SystemExit) as result:
        ingest.main()
    assert result.value.code == 2
