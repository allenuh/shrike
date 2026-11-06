import argparse
import json
import time

from shrike.adapters.github.client import GitHubAppClient
from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.ingestion import SqlIngestionStore
from shrike.application.ingestion import process_one
from shrike.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Process durable GitHub webhook inbox metadata")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--once", action="store_true", help="Process up to 100 currently due deliveries"
    )
    mode.add_argument("--watch", action="store_true", help="Poll continuously; stop with Ctrl+C")
    args = parser.parse_args()
    database = None
    github = None
    try:
        settings = Settings()
        if settings.github_mode != "live" or settings.github_app_private_key_path is None:
            raise ValueError
        database = Database(settings.database_url.get_secret_value())
        with settings.github_app_private_key_path.open("rb") as handle:
            key = handle.read(65537)
        if len(key) > 65536:
            raise ValueError
        github = GitHubAppClient(
            settings.github_app_id,
            key,
            client_id=settings.github_app_client_id,
            max_files=settings.review_max_files,
            max_file_bytes=settings.review_max_file_bytes,
            max_diff_bytes=settings.review_max_diff_bytes,
        )
        store = SqlIngestionStore(database)
        while True:
            count = 0
            while count < 100 and process_one(store, github, settings.github_app_id):
                count += 1
            print(json.dumps({"event": "ingestion_batch", "processed": count}), flush=True)
            if args.once:
                return
            time.sleep(2)
    except KeyboardInterrupt:
        return
    except Exception:
        parser.exit(
            2, "Ingestion worker failed; check configuration and database (details suppressed)\n"
        )
    finally:
        if github is not None:
            github.close()
        if database is not None:
            database.dispose()


if __name__ == "__main__":
    main()
