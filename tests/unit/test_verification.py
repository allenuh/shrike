"""Exercise the CI runner with fake commands; no Docker/browser/model calls here."""

import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("fail", [False, True])
def test_ci_runner_sanitizes_environment_and_reports_only_executed_steps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fail: bool
) -> None:
    output = tmp_path / "checks"
    sentinel = "SYNTHETIC_INHERITED_SECRET_SENTINEL"
    for key in (
        "LLM_API_KEY",
        "GITHUB_APP_PRIVATE_KEY_PATH",
        "DATABASE_URL",
        "SHRIKE_TEST_DATABASE_URL",
        "SHRIKE_TEST_REDIS_URL",
        "CELERY_BROKER_URL",
    ):
        monkeypatch.setenv(key, sentinel)
    monkeypatch.setattr(sys, "argv", ["verify", "--output-dir", str(output)])
    calls = []

    def run(
        command: list[str], *, cwd: Path, env: dict[str, str], check: bool, timeout: int
    ) -> subprocess.CompletedProcess[str]:
        assert sentinel not in env.values()
        assert env["AI_PROVIDER"] == "mock" and env["CI"] == "true"
        assert env["LLM_LIVE_ENABLED"] == "false" and env["SHRIKE_WEB_MODE"] == "demo"
        calls.append(command)
        return subprocess.CompletedProcess(command, 1 if fail else 0)

    monkeypatch.setattr(subprocess, "run", run)
    script = runpy.run_path("scripts/verify.py")
    assert script["main"]() == int(fail)
    result = json.loads((output / "checks.json").read_text())
    assert result["complete"] is not fail
    assert len(result["steps"]) == len(calls) == (1 if fail else 5)
    assert len(result["planned_steps"]) == 5
    assert sentinel not in json.dumps(result)
