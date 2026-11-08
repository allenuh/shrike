"""Opt-in bounded local measurements; no external target URL is accepted."""

import hashlib
import hmac
import json
import socket
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx2 as httpx
import pytest
import redis
import uvicorn
from celery.contrib.testing.worker import start_worker
from fakes import ReviewGitHub, github_fixture
from pydantic import SecretStr
from sqlalchemy import select

from shrike.adapters.github.webhooks import parse_webhook
from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.dispatch import SqlDispatchStore
from shrike.adapters.persistence.ingestion import SqlIngestionStore, accept_delivery
from shrike.adapters.persistence.models import ReviewExecution, ReviewJob
from shrike.application.dispatch import dispatch_one
from shrike.application.ingestion import process_one
from shrike.config import Settings
from shrike.domain.github import GitHubPullRequest, GitHubRepository
from shrike.evaluation import environment, percentile, write_result
from shrike_api.main import create_app as create_api
from shrike_worker.celery_app import CeleryPublisher, create_app
from shrike_worker.config import QueueSettings
from shrike_worker.runtime import Runtime

pytestmark = [pytest.mark.integration, pytest.mark.benchmark]
SECRET = "synthetic-benchmark-webhook-secret-not-a-real-credential"


def output(config: pytest.Config, name: str, result: dict[str, Any]) -> None:
    path = Path(config.getoption("--benchmark-output"))
    write_result(
        path.with_name(f"{path.stem}-{name}.json"),
        {
            "schema_version": 1,
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "kind": name,
            "environment": environment(),
            **result,
        },
    )


def test_api_load(
    seeded_database: Database, settings: Settings, pytestconfig: pytest.Config
) -> None:
    config = settings.model_copy(
        update={
            "github_webhooks_enabled": True,
            "github_app_id": 12345,
            "github_webhook_secret": SecretStr(SECRET),
        }
    )
    server = uvicorn.Server(
        uvicorn.Config(
            create_api(config, seeded_database),
            host="127.0.0.1",
            access_log=False,
            log_config=None,
            log_level="critical",
        )
    )
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    raw = json.dumps(github_fixture("pull_request_opened.json")).encode()
    duplicate = str(uuid4())

    def headers(body: bytes, delivery: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": delivery,
            "X-Hub-Signature-256": "sha256="
            + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest(),
        }

    samples: list[tuple[str, float, int, int]] = []
    started = time.monotonic()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(0.01)
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=10
        ) as client:
            assert (
                client.post(
                    "/webhooks/github", content=raw, headers=headers(raw, duplicate)
                ).status_code
                == 202
            )

            def request(kind: str) -> tuple[str, float, int, int]:
                begin = time.monotonic()
                body = b"{" if kind == "malformed" else raw
                auth = headers(body, duplicate if kind == "duplicate" else str(uuid4()))
                if kind == "bad_signature":
                    auth["X-Hub-Signature-256"] = "sha256=" + "0" * 64
                if kind in {"read", "unauthorized"}:
                    response = client.get(
                        "/v1/review-jobs",
                        headers={
                            "Authorization": "Bearer " + config.dev_auth_token.get_secret_value()
                        }
                        if kind == "read" and config.dev_auth_token
                        else {},
                    )
                    expected = 200 if kind == "read" else 401
                else:
                    response = client.post("/webhooks/github", content=body, headers=auth)
                    expected = {"duplicate": 200, "malformed": 400, "bad_signature": 401}.get(
                        kind, 202
                    )
                return kind, (time.monotonic() - begin) * 1000, response.status_code, expected

            kinds = ["accept", "duplicate", "bad_signature", "malformed", "read", "unauthorized"]
            started = time.monotonic()
            with ThreadPoolExecutor(max_workers=8) as pool:
                samples = list(pool.map(request, kinds * 20))
            elapsed = time.monotonic() - started
        results: dict[str, Any] = {}
        for kind in kinds:
            subset = [sample for sample in samples if sample[0] == kind]
            results[kind] = {
                "requests": len(subset),
                "unexpected_responses": sum(
                    status != expected for _, _, status, expected in subset
                ),
                "status_counts": dict(Counter(str(s[2]) for s in subset)),
                "p50_ms": percentile([s[1] for s in subset], 0.5),
                "p95_ms": percentile([s[1] for s in subset], 0.95),
            }
        output(
            pytestconfig,
            "api",
            {
                "transport": "loopback HTTP/uvicorn; warm pool; no external GitHub/OAuth",
                "concurrency": 8,
                "requests": len(samples),
                "duration_seconds": elapsed,
                "requests_per_second": len(samples) / elapsed,
                "scenarios": results,
                "webhook_bytes": len(raw),
            },
        )
        assert all(row[2] == row[3] for row in samples)
        assert results["accept"]["p95_ms"] < 500
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        listener.close()
        assert not thread.is_alive()


class RoutingGitHub(ReviewGitHub):
    def repository(
        self, installation_id: int, repository_id: int, owner: str, name: str
    ) -> GitHubRepository:
        return next(repo for repo in self.inventory if repo.id == repository_id)

    def pull_request(
        self, installation_id: int, repository: GitHubRepository, number: int
    ) -> GitHubPullRequest:
        return replace(
            self.pr_data,
            id=repository.id + 100000,
            base_repository_id=repository.id,
            head_repository_id=repository.id,
        )


@pytest.mark.parametrize("rpm", [6000, 60])
def test_queue_load(
    database: Database, queue_settings: QueueSettings, pytestconfig: pytest.Config, rpm: int
) -> None:
    github = RoutingGitHub()
    github.inventory = tuple(
        replace(github.repository_data, id=810001 + i, name=f"fixture-{i}") for i in range(10)
    )
    # Canonical metadata ingestion, not direct insertion of completed jobs/results.
    for repo in github.inventory:
        payload = github_fixture("pull_request_opened.json")
        payload["repository"].update(
            id=repo.id, name=repo.name, full_name=f"shrike-demo/{repo.name}"
        )
        payload["pull_request"]["id"] = repo.id + 100000
        for side in ("base", "head"):
            payload["pull_request"][side]["repo"].update(id=repo.id, name=repo.name)
        raw = json.dumps(payload).encode()
        with database.session() as session, session.begin():
            accept_delivery(
                session,
                str(uuid4()),
                hashlib.sha256(raw).hexdigest(),
                parse_webhook("pull_request", raw, 12345),
            )
        assert process_one(SqlIngestionStore(database), github, 12345)
    config = queue_settings.model_copy(update={"provider_rpm": rpm, "retry_base_seconds": 1.0})
    runtime = Runtime(database, github, 12345, config)
    app = create_app(config, runtime.consume)
    publisher = CeleryPublisher(app)
    broker = redis.Redis.from_url(config.broker_url.get_secret_value())
    dispatcher = SqlDispatchStore(database)
    started = time.monotonic()
    try:
        with start_worker(
            app,
            pool="threads",
            concurrency=2,
            perform_ping_check=False,
            loglevel="WARNING",
            shutdown_timeout=15,
        ):
            deadline = time.monotonic() + 60
            while True:
                runtime.executions.recover()
                for _ in range(20):
                    if not dispatch_one(dispatcher, publisher):
                        break
                with database.session() as session:
                    jobs = list(session.scalars(select(ReviewJob)))
                    states = Counter(job.state.value for job in jobs)
                    if states["completed"] + states["failed"] + states["canceled"] == 10:
                        break
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.05)
            elapsed = time.monotonic() - started
        with database.session() as session:
            jobs = list(session.scalars(select(ReviewJob)))
            attempts = list(session.scalars(select(ReviewExecution)))
            durations = [
                (j.finished_at - j.created_at).total_seconds() * 1000 for j in jobs if j.finished_at
            ]
            services = [float(a.duration_ms) for a in attempts if a.duration_ms is not None]
            intervals = sorted(
                [(a.started_at, 1) for a in attempts]
                + [(a.finished_at, -1) for a in attempts if a.finished_at]
            )
            active = peak = 0
            for _, delta in intervals:
                active += delta
                peak = max(peak, active)
            waits = [
                (j.first_started_at - j.created_at).total_seconds() * 1000
                for j in jobs
                if j.first_started_at
            ]
            errors = Counter(j.error_code for j in jobs if j.error_code)
            output(
                pytestconfig,
                f"queue-rpm-{rpm}",
                {
                    "transport": "real Redis/Celery threads; actual isolated Ruff; mock GitHub/AI",
                    "jobs": 10,
                    "repositories": 10,
                    "concurrency": 2,
                    "repository_limit": 1,
                    "provider_rpm": rpm,
                    "retry_base_seconds": 1,
                    "attempt_deadline_seconds": 180,
                    "source_bytes_per_job": len(github.source),
                    "duration_seconds": elapsed,
                    "states": dict(states),
                    "timed_out": states["completed"] + states["failed"] + states["canceled"] != 10,
                    "errors": dict(errors),
                    "attempts": len(attempts),
                    "peak_running_attempts": peak,
                    "queue_wait_p95_ms": percentile(waits, 0.95),
                    "attempt_error_counts": dict(
                        Counter(a.error_code for a in attempts if a.error_code)
                    ),
                    "max_attempts_per_job": max(j.attempt_count for j in jobs),
                    "end_to_end_p50_ms": percentile(durations, 0.5),
                    "end_to_end_p95_ms": percentile(durations, 0.95),
                    "attempt_p95_ms": percentile(services, 0.95),
                    "completed_jobs_per_second": states["completed"] / elapsed,
                },
            )
            assert all(j.attempt_count <= 3 for j in jobs)
            assert states["completed"] + states["failed"] + states["canceled"] == 10
            assert peak <= 2
            assert all(a.duration_ms is None or a.duration_ms < 180000 for a in attempts)
            if rpm == 6000:
                assert peak == 2
                assert states["completed"] == 10
                p95 = percentile(durations, 0.95)
                assert p95 is not None and p95 < 60000
            else:
                # Failure counts depend on timing. Improved admission scheduling may
                # complete every job; retain the observation rather than demanding failure.
                assert states["canceled"] == 0
                assert all(code == "provider_throttled" for code in errors)
    finally:
        app.close()
        keys = list(broker.scan_iter(match=config.namespace + ":*"))
        if keys:
            broker.delete(*keys)
        broker.close()
