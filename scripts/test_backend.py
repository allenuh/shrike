"""Run tests in a unique tmpfs PostgreSQL container, then remove only that container."""

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path


def docker(*args: str) -> str:
    return subprocess.run(
        ["docker", *args], check=True, capture_output=True, text=True, timeout=120
    ).stdout.strip()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    image = (root / "infra/docker/postgres-image.txt").read_text().strip()
    name = f"shrike-tests-{uuid.uuid4().hex}"
    created = False
    try:
        docker(
            "run",
            "--detach",
            "--rm",
            "--name",
            name,
            "--env",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            "--env",
            "POSTGRES_DB=shrike_test",
            "--publish",
            "127.0.0.1::5432",
            "--tmpfs",
            "/var/lib/postgresql/data",
            image,
        )
        created = True
        deadline = time.monotonic() + 45
        while True:
            try:
                docker(
                    "exec",
                    name,
                    "pg_isready",
                    "-h",
                    "127.0.0.1",
                    "-U",
                    "postgres",
                    "-d",
                    "shrike_test",
                )
                break
            except subprocess.CalledProcessError:
                if time.monotonic() > deadline:
                    raise TimeoutError("PostgreSQL startup timed out") from None
                time.sleep(0.25)
        binding = docker("port", name, "5432/tcp")
        port = int(binding.rsplit(":", 1)[1])
        env = os.environ.copy()
        # This passwordless role exists only in this disposable, loopback-bound test container.
        env["SHRIKE_TEST_DATABASE_URL"] = (
            f"postgresql+psycopg://postgres@127.0.0.1:{port}/shrike_test"
        )
        return subprocess.run(
            [sys.executable, "-m", "pytest", *sys.argv[1:]], cwd=root, env=env, check=False
        ).returncode
    except (subprocess.SubprocessError, TimeoutError, OSError, ValueError):
        print("Disposable PostgreSQL test setup failed; check Docker availability", file=sys.stderr)
        return 2
    finally:
        if created:
            try:
                docker("rm", "--force", name)
            except (subprocess.SubprocessError, OSError):
                print(f"Cleanup failed: remove task-owned container {name}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
