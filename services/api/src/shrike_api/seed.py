"""Opt-in local development CLI. Never registers HTTP endpoints."""

import argparse

from sqlalchemy.engine import make_url

from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.demo import seed_demo
from shrike.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed synthetic data in a local demo database")
    parser.add_argument("--confirm-development", action="store_true", required=True)
    parser.parse_args()
    try:
        settings = Settings()
        url = make_url(settings.database_url.get_secret_value())
        if (
            settings.app_env != "development"
            or url.database != "shrike_demo"
            or url.host not in {"localhost", "127.0.0.1", "::1"}
        ):
            raise ValueError
    except Exception:
        parser.exit(2, "Seed requires APP_ENV=development and a loopback shrike_demo database\n")
    database = Database(settings.database_url.get_secret_value())
    try:
        with database.session() as session, session.begin():
            inserted = seed_demo(session)
    except Exception:
        parser.exit(2, "Demo seed failed; check migrations and use an empty demo database\n")
    finally:
        database.dispose()
    print("Synthetic demo data inserted" if inserted else "Synthetic demo data already present")


if __name__ == "__main__":
    main()
