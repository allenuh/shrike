import json
import sys
from pathlib import Path

import pytest

from shrike.domain.review import Candidate, SelectedFile
from shrike.review_cli import EvalCase, main, snapshot


class StaticFake:
    version = "fake-v1"

    def analyze(self, file: SelectedFile) -> tuple[Candidate, ...]:
        return ()


@pytest.fixture
def cli(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "DATABASE_URL",
        "AI_PROVIDER",
        "LLM_PROVIDER",
        "LLM_LIVE_ENABLED",
        "LLM_LIVE_EVAL_ENABLED",
        "LLM_LIVE_EVAL_MAX_REQUESTS",
        "LLM_PRICING_PROFILE_PATH",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("shrike.review_cli.RuffAnalyzer", StaticFake)


def test_mock_cli_snapshot_report_and_log_privacy(
    cli: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = snapshot(
        EvalCase(id="test", code="# PRIVATE_SOURCE_SENTINEL\nvalue = 10 / 0\n", expected=None)
    )
    input_path, output_path = tmp_path / "snapshot.json", tmp_path / "report.json"
    input_path.write_text(source.model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("LLM_API_KEY", "SYNTHETIC_KEY_SENTINEL")
    monkeypatch.setattr(
        sys,
        "argv",
        ["review", "analyze", "--snapshot", str(input_path), "--report", str(output_path)],
    )
    main()
    output = capsys.readouterr()
    assert "SENTINEL" not in output.out + output.err
    assert json.loads(output_path.read_text())["findings"][0]["line"] == 2
    assert json.loads(output.out)["findings"] == 1


@pytest.mark.parametrize(
    "flags",
    [[], ["--live"], ["--live", "--max-requests", "0"], ["--live", "--max-requests", "100"]],
)
def test_live_eval_requires_explicit_bounded_opt_in(
    cli: None, monkeypatch: pytest.MonkeyPatch, flags: list[str]
) -> None:
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setattr(sys, "argv", ["review", "evaluate", *flags])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


def test_invalid_input_errors_do_not_echo_payload(
    cli: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_path = tmp_path / "bad.json"
    input_path.write_text('{"secret":"PRIVATE_SOURCE_SENTINEL"}', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["review", "analyze", "--snapshot", str(input_path)])
    with pytest.raises(SystemExit):
        main()
    output = capsys.readouterr()
    assert "SENTINEL" not in output.out + output.err


def test_mock_dry_run_does_not_invoke_provider(
    cli: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*args: object) -> None:
        pytest.fail("Provider must not run in dry-run mode")

    monkeypatch.setattr("shrike.adapters.llm.mock.MockProvider.review", forbidden)
    input_path = tmp_path / "snapshot.json"
    input_path.write_text(
        snapshot(EvalCase(id="test", code="a=1\n", expected=None)).model_dump_json(),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys, "argv", ["review", "analyze", "--snapshot", str(input_path), "--dry-run"]
    )
    main()
    assert json.loads(capsys.readouterr().out)["status"] == "dry_run"
