"""CI entry point for preprovisioned locked tooling; installs nothing, never uses live providers."""

import argparse
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shrike.evaluation import environment, write_result

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--frontend", action="store_true")
    parser.add_argument("--benchmarks", action="store_true")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    # Drop inherited application settings; no secret values enter the report.
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(
            (
                "LLM_",
                "AI_",
                "GITHUB_",
                "DASHBOARD_",
                "DEV_",
                "SHRIKE_TEST_",
                "CELERY_",
                "REVIEW_",
                "WORKER_",
                "QUEUE_",
            )
        )
        and key not in {"DATABASE_URL", "APP_ENV", "ENABLE_DEV_AUTH", "ENABLE_DEV_JOB_OPERATIONS"}
    }
    env.update(
        AI_PROVIDER="mock",
        LLM_PROVIDER="mock",
        LLM_LIVE_ENABLED="false",
        GITHUB_MODE="disabled",
        NEXT_TELEMETRY_DISABLED="1",
        SHRIKE_WEB_MODE="demo",
        CI="true",
    )
    env["PLAYWRIGHT_JSON_OUTPUT_FILE"] = str(output / "browser.json")
    # Invented build canaries, never user credentials.
    for key in ("LLM_API_KEY", "GITHUB_OAUTH_CLIENT_SECRET", "DASHBOARD_TOKEN_KEY"):
        env[key] = "SHRIKE_SYNTHETIC_BUILD_SECRET_CANARY"
    steps: list[tuple[str, list[str], Path]] = [
        ("lint", [sys.executable, "-m", "ruff", "check", "."], ROOT),
        ("format", [sys.executable, "-m", "ruff", "format", "--check", "."], ROOT),
        ("types", [sys.executable, "-m", "mypy"], ROOT),
        (
            "backend",
            [
                sys.executable,
                "scripts/test_backend.py",
                "-q",
                "--tb=short",
                "--cov=shrike",
                "--cov=shrike_api",
                "--cov=shrike_worker",
                f"--cov-report=json:{output / 'coverage.json'}",
                "--cov-report=term",
                "--junitxml",
                str(output / "backend.xml"),
                "--basetemp",
                str(output / "tmp"),
                "-o",
                f"cache_dir={output / 'pytest-cache'}",
            ],
            ROOT,
        ),
        (
            "quality",
            [
                sys.executable,
                "-m",
                "shrike.evaluation",
                "--output",
                str(output / "quality.json"),
                "--check-baseline",
                "tests/fixtures/evaluation/baseline.json",
            ],
            ROOT,
        ),
    ]
    if args.frontend:
        npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        if npm is None:
            parser.error("npm must already be installed")
        for name in ("lint", "format:check", "typecheck", "test", "build", "test:e2e"):
            arguments = ["--", "--reporter=line,json"] if name == "test:e2e" else []
            steps.append((f"web-{name}", [npm, "run", name, *arguments], ROOT / "apps/web"))
            if name == "build":
                steps.append(
                    ("browser-secrets", [sys.executable, "scripts/check_web_secrets.py"], ROOT)
                )
    if args.benchmarks:
        steps.append(
            (
                "load",
                [sys.executable, "scripts/benchmark.py", "--output-dir", str(output / "load")],
                ROOT,
            )
        )
    results: list[dict[str, Any]] = []
    exit_code = 0
    try:
        for name, command, cwd in steps:
            print(f"Running {name}", flush=True)
            started = time.monotonic()
            try:
                code = subprocess.run(
                    command, cwd=cwd, env=env, check=False, timeout=900
                ).returncode
            except (OSError, subprocess.TimeoutExpired):
                code = 2
            results.append(
                {"step": name, "exit_code": code, "duration_seconds": time.monotonic() - started}
            )
            if code:
                exit_code = 1
                break
    finally:
        write_result(
            output / "checks.json",
            {
                "schema_version": 1,
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "environment": environment(),
                "mock_only": True,
                "steps": results,
                "planned_steps": [step[0] for step in steps],
                "complete": len(results) == len(steps) and exit_code == 0,
            },
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
