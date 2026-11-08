"""Run bounded API/queue workloads only against task-owned disposable services."""

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    return subprocess.run(
        [
            sys.executable,
            "scripts/test_backend.py",
            "tests/benchmarks",
            "-q",
            "--run-benchmarks",
            "--benchmark-output",
            str(args.output_dir / "load.json"),
            "--junitxml",
            str(args.output_dir / "load-tests.xml"),
            "-o",
            f"cache_dir={args.output_dir / 'pytest-cache'}",
        ],
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
