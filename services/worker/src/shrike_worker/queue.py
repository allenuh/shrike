"""Trusted operator entry points. No web mutation endpoints or Celery result storage."""

import argparse
import json
import os
import time
from uuid import UUID

from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.dispatch import SqlDispatchStore
from shrike.adapters.persistence.execution import SqlExecutionStore
from shrike.adapters.persistence.operations import DevJobOperations
from shrike.analysis_config import AnalysisSettings
from shrike.application.dispatch import dispatch_one
from shrike.config import Settings, parse_grants
from shrike.domain.access import ReadScope
from shrike.domain.review import ReviewError
from shrike.domain.states import JobState

from .celery_app import CeleryPublisher, create_app
from .config import QueueSettings
from .logging import configure_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Shrike asynchronous processing operations")
    commands = parser.add_subparsers(dest="command", required=True)
    dispatch = commands.add_parser("dispatch")
    dispatch_mode = dispatch.add_mutually_exclusive_group(required=True)
    dispatch_mode.add_argument("--once", action="store_true")
    dispatch_mode.add_argument("--watch", action="store_true")
    worker = commands.add_parser("worker")
    worker.add_argument(
        "--development-threads",
        action="store_true",
        help="Development-only native Windows/local transport smoke; no prefork hard limits",
    )
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--job-id", type=UUID)
    inspect.add_argument("--state", choices=[item.value for item in JobState])
    inspect.add_argument("--limit", type=int, default=20)
    retry = commands.add_parser("retry")
    retry.add_argument("--job-id", type=UUID, required=True)
    args = parser.parse_args()
    database, app = None, None
    try:
        settings = Settings()
        database = Database(settings.database_url.get_secret_value())
        if args.command in {"inspect", "retry"}:
            operations = DevJobOperations(
                database,
                ReadScope(parse_grants(settings.dev_repository_grants)),
                environment=settings.app_env,
                enabled=os.environ.get("ENABLE_DEV_JOB_OPERATIONS") == "true",
            )
            if args.command == "inspect":
                print(
                    json.dumps(
                        operations.inspect(
                            args.job_id, JobState(args.state) if args.state else None, args.limit
                        )
                    )
                )
            else:
                operations.retry(args.job_id)
                print(json.dumps({"event": "job_retry_scheduled", "job_id": str(args.job_id)}))
            return
        if AnalysisSettings().provider != "mock":
            raise ReviewError("queued_provider_must_be_mock")
        queue_settings = QueueSettings()
        app = create_app(queue_settings)
        if args.command == "worker":
            if settings.github_mode != "live" or settings.github_app_private_key_path is None:
                raise ReviewError("github_not_configured")
            if args.development_threads:
                if settings.app_env != "development":
                    raise ReviewError("development_pool_disabled")
                pool = "threads"
            else:
                if os.name == "nt":
                    raise ReviewError("use_linux_or_explicit_development_threads")
                pool = "prefork"
            configure_logging()
            app.Worker(
                pool=pool,
                concurrency=queue_settings.concurrency,
                loglevel="WARNING",
                quiet=True,
                without_gossip=True,
                without_mingle=True,
                without_heartbeat=True,
            ).start()
        else:
            publisher, dispatcher = CeleryPublisher(app), SqlDispatchStore(database)
            executions = SqlExecutionStore(
                database,
                lease_seconds=queue_settings.lease_seconds,
                deadline_seconds=queue_settings.deadline_seconds,
                retry_base_seconds=queue_settings.retry_base_seconds,
                repository_limit=queue_settings.repository_limit,
            )
            while True:
                recovered = executions.recover()
                sent = 0
                while sent < 100 and dispatch_one(dispatcher, publisher):
                    sent += 1
                if args.once:
                    print(
                        json.dumps(
                            {"event": "dispatch_batch", "attempted": sent, "recovered": recovered}
                        )
                    )
                    return
                time.sleep(1)
    except KeyboardInterrupt:
        return
    except Exception as error:
        code = (
            error.code
            if isinstance(error, ReviewError)
            else "queue_configuration_or_execution_failed"
        )
        parser.exit(2, f"Shrike queue operation refused or failed: {code}\n")
    finally:
        if app is not None:
            app.close()
        if database is not None:
            database.dispose()


if __name__ == "__main__":
    main()
