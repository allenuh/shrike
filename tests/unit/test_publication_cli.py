import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fakes import publication_report

from shrike import publication_cli


def configure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://unused@localhost/unused")
    monkeypatch.setenv("GITHUB_PUBLISH_REPOSITORY_GRANTS", "710001:810001")
    monkeypatch.delenv("GITHUB_PUBLISHING_ENABLED", raising=False)
    monkeypatch.delenv("GITHUB_MODE", raising=False)


def test_publish_requires_both_opt_ins_before_database_or_key_access(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    configure(monkeypatch)

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Unexpected external resource access")

    monkeypatch.setattr(publication_cli, "Database", forbidden)
    monkeypatch.setattr(publication_cli, "GitHubAppClient", forbidden)
    assert publication_cli.main(["--job-id", str(uuid4()), "--publish"]) == 2
    assert json.loads(capsys.readouterr().out)["state"] == "publication_refused"


def test_report_only_never_reads_key_or_github_and_does_not_log_prose(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    configure(monkeypatch)

    class Database:
        def __init__(self, url: str) -> None:
            pass

        def dispose(self) -> None:
            pass

    class Store:
        def __init__(self, database: Database) -> None:
            pass

        def preview(self, *args: Any) -> Any:
            return publication_report(), "marker"

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Report-only touched GitHub")

    monkeypatch.setattr(publication_cli, "Database", Database)
    monkeypatch.setattr(publication_cli, "SqlPublicationStore", Store)
    monkeypatch.setattr(publication_cli, "GitHubAppClient", forbidden)
    output = tmp_path / "preview.json"
    assert publication_cli.main(["--job-id", str(uuid4()), "--output", str(output)]) == 0
    assert "Suggested action" in output.read_text(encoding="utf-8")
    assert "Division" not in capsys.readouterr().out
    assert publication_cli.main(["--job-id", str(uuid4()), "--output", str(output)]) == 2
