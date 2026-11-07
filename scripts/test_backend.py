"""Run tests in a unique tmpfs PostgreSQL container, then remove only that container."""

import os
import secrets
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
    redis_created = False
    redis_name = f"shrike-redis-tests-{uuid.uuid4().hex}"
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
        redis_image = (root / "infra/docker/redis-image.txt").read_text().strip()
        redis_password = secrets.token_urlsafe(32)
        docker(
            "run",
            "--detach",
            "--rm",
            "--name",
            redis_name,
            "--publish",
            "127.0.0.1::6379",
            "--tmpfs",
            "/data",
            redis_image,
            "redis-server",
            "--requirepass",
            redis_password,
            "--save",
            "",
            "--appendonly",
            "no",
        )
        redis_created = True
        redis_port = int(docker("port", redis_name, "6379/tcp").rsplit(":", 1)[1])
        env["SHRIKE_TEST_REDIS_URL"] = f"redis://:{redis_password}@127.0.0.1:{redis_port}/0"
        deadline = time.monotonic() + 30
        while docker("exec", redis_name, "redis-cli", "ping") != "NOAUTH Authentication required.":
            if time.monotonic() > deadline:
                raise TimeoutError("Redis startup timed out")
            time.sleep(0.1)
        return subprocess.run(
            [sys.executable, "-m", "pytest", *sys.argv[1:]], cwd=root, env=env, check=False
        ).returncode
    except (subprocess.SubprocessError, TimeoutError, OSError, ValueError):
        print("Disposable PostgreSQL test setup failed; check Docker availability", file=sys.stderr)
        return 2
    finally:
        if redis_created:
            try:
                docker("rm", "--force", redis_name)
            except (subprocess.SubprocessError, OSError):
                print(f"Cleanup failed: remove task-owned container {redis_name}", file=sys.stderr)
        if created:
            try:
                docker("rm", "--force", name)
            except (subprocess.SubprocessError, OSError):
                print(f"Cleanup failed: remove task-owned container {name}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
