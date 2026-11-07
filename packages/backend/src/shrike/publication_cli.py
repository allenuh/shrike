"""Explicit operator publication; default report-only mode makes no GitHub requests."""

import argparse
import json
from pathlib import Path
from uuid import UUID

from shrike.adapters.github.client import GitHubAppClient
from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.publication import SqlPublicationStore
from shrike.application.publication import publish_review, render_plan
from shrike.config import Settings, parse_grants
from shrike.domain.access import ReadScope


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preview or explicitly publish one Shrike report")
    parser.add_argument("--job-id", type=UUID, required=True)
    parser.add_argument(
        "--publish", action="store_true", help="Opt in to one advisory GitHub review"
    )
    parser.add_argument(
        "--output", type=Path, help="New local JSON preview file; may contain private findings"
    )
    args = parser.parse_args(argv)
    database = None
    github = None
    try:
        settings = Settings()
        if args.publish and (
            not settings.github_publishing_enabled or settings.github_mode != "live"
        ):
            raise ValueError
        scope = ReadScope(parse_grants(settings.github_publish_repository_grants))
        database = Database(settings.database_url.get_secret_value())
        store = SqlPublicationStore(database)
        if not args.publish:
            report, marker = store.preview(args.job_id, scope)
            plan = render_plan(report, marker, summary_only=True)
            if args.output:
                # No overwrite and no console prose/source. Keep this private local artifact.
                with args.output.open("x", encoding="utf-8") as handle:
                    handle.write(plan.model_dump_json(indent=2))
            print(
                json.dumps(
                    {
                        "state": "report_only",
                        "job_id": str(args.job_id),
                        "findings": len(report.findings),
                    }
                )
            )
            return 0
        if args.output or settings.github_app_private_key_path is None:
            raise ValueError
        with settings.github_app_private_key_path.open("rb") as handle:
            key = handle.read(65537)
        if len(key) > 65536:
            raise ValueError
        github = GitHubAppClient(
            settings.github_app_id,
            key,
            client_id=settings.github_app_client_id,
            publishing_enabled=True,
        )
        outcome = publish_review(args.job_id, scope, store, github, settings.github_app_id)
        print(
            json.dumps(
                {
                    "state": outcome.state if outcome else "no_action",
                    "job_id": str(args.job_id),
                    "review_id": outcome.review_id if outcome else None,
                    "reason": outcome.reason if outcome else None,
                }
            )
        )
        return 0 if outcome is None or outcome.state == "published" else 1
    except Exception:
        # Never echo configuration, source, payloads, credentials or third-party errors.
        print(json.dumps({"state": "publication_refused"}))
        return 2
    finally:
        if github is not None:
            github.close()
        if database is not None:
            database.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
