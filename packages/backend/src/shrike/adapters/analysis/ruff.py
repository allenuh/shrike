"""Host-operated container runner. Never fall back to scanning on the host."""

import json
import os
import subprocess
import threading
from contextlib import suppress
from uuid import uuid4

from shrike.domain.review import Candidate, ReviewError, SelectedFile

RUFF_IMAGE = (
    "ghcr.io/astral-sh/ruff@sha256:c4b7e7a87e4b07d66b569dd2e6b2ce5a25e38be91dd664dc49b9882be27acd9b"
)
RULES = {
    "F821": ("Undefined name can raise NameError", "Define or import the name before using it"),
    "F823": (
        "Local variable is used before assignment",
        "Assign the local variable on every path before use",
    ),
    "F601": (
        "Repeated dictionary key discards a value",
        "Remove the duplicate key or use distinct keys",
    ),
    "F602": (
        "Repeated dictionary key discards a value",
        "Remove the duplicate key or use distinct keys",
    ),
    "F631": ("Tuple assertion always succeeds", "Assert the boolean condition without a tuple"),
    "B006": (
        "Mutable default argument is shared between calls",
        "Use None as the default and create a fresh value inside the function",
    ),
    "B012": (
        "Control flow in finally can suppress an exception",
        "Move the control flow outside finally so exceptions propagate",
    ),
}


def sandbox_args(name: str) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--pull=never",
        "--name",
        name,
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--user=65534:65534",
        "--pids-limit=32",
        "--memory=128m",
        "--memory-swap=128m",
        "--cpus=1",
        "--ulimit",
        "nofile=64:64",
        "--log-driver=none",
        "-i",
        RUFF_IMAGE,
    ]


class RuffAnalyzer:
    version = "ruff-0.17.4-policy-v1"

    def __init__(self, timeout: float = 30, output_limit: int = 262144) -> None:
        self.timeout, self.output_limit = timeout, output_limit

    def analyze(self, file: SelectedFile) -> tuple[Candidate, ...]:
        if len(file.content.encode()) > 204800:
            raise ReviewError("scanner_input_limit")
        name = f"shrike-scan-{uuid4().hex}"
        args = sandbox_args(name) + [
            "check",
            "--isolated",
            "--ignore-noqa",
            "--no-cache",
            "--output-format=json",
            "--target-version=py312",
            "--select",
            ",".join(RULES),
            "--stdin-filename",
            "input.py",
            "-",
        ]
        # Host Docker needs its own local CLI configuration. No env/mount is forwarded to container.
        process: subprocess.Popen[bytes] | None = None
        output = bytearray()
        overflow = threading.Event()
        threads: list[threading.Thread] = []

        def read(pipe: object, retain: bool) -> None:
            from typing import BinaryIO, cast

            stream = cast(BinaryIO, pipe)
            count = 0
            while chunk := stream.read(8192):
                count += len(chunk)
                if count > self.output_limit:
                    overflow.set()
                    if process is not None:
                        process.kill()
                    break
                if retain:
                    output.extend(chunk)
            stream.close()

        try:
            process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=os.environ.copy(),
            )
            for pipe, retain in ((process.stdout, True), (process.stderr, False)):
                thread = threading.Thread(target=read, args=(pipe, retain), daemon=True)
                thread.start()
                threads.append(thread)

            def write_input() -> None:
                assert process is not None and process.stdin is not None
                with suppress(OSError, subprocess.SubprocessError):
                    process.stdin.write(file.content.encode())
                    process.stdin.close()

            writer = threading.Thread(target=write_input, daemon=True)
            writer.start()
            code = process.wait(timeout=self.timeout)
            writer.join(timeout=2)
            for thread in threads:
                thread.join(timeout=2)
            if code not in (0, 1) or overflow.is_set() or any(t.is_alive() for t in threads):
                raise ReviewError("scanner_failed")
            raw = json.loads(output)
            if not isinstance(raw, list) or len(raw) > 1000:
                raise ReviewError("scanner_invalid_output")
            findings = []
            for item in raw:
                rule = item["code"]
                if rule not in RULES:
                    raise ReviewError("scanner_parse_failed")
                n = item["location"]["row"]
                lines = file.content.splitlines()
                if type(n) is not int or not 1 <= n <= len(lines):
                    raise ReviewError("scanner_invalid_location")
                if n not in file.changed_lines:
                    continue
                problem, suggestion = RULES[rule]
                findings.append(
                    Candidate(
                        category="correctness",
                        severity="medium",
                        confidence=0.95,
                        path=file.path,
                        line=n,
                        problem=problem,
                        suggestion=suggestion,
                        evidence=lines[n - 1][:500],
                        rule=rule,
                    )
                )
            return tuple(findings)
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
            raise ReviewError("scanner_failed") from None
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
                # Exact task-owned name only. Container logging is disabled and input is ephemeral.
                with suppress(OSError, subprocess.SubprocessError):
                    subprocess.run(
                        ["docker", "rm", "--force", name],
                        capture_output=True,
                        timeout=10,
                        check=False,
                    )
