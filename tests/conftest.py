import os
import re
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.demo import seed_demo
from shrike.config import Settings
from shrike_api.main import create_app

ROOT = Path(__file__).resolve().parents[1]
TEST_TOKEN = "synthetic-development-test-token-00001"


def migration_config() -> Config:
    return Config(str(ROOT / "alembic.ini"))


@pytest.fixture
def database() -> Iterator[Database]:
    supplied = os.environ.get("SHRIKE_TEST_DATABASE_URL")
    if supplied is None:
        pytest.fail("Use uv run python scripts/test_backend.py for disposable PostgreSQL tests")
    url = make_url(supplied)
    if (
        url.drivername != "postgresql+psycopg"
        or url.host not in {"localhost", "127.0.0.1", "::1"}
        or url.database != "shrike_test"
    ):
        pytest.fail("Tests require the explicit loopback shrike_test administration database")
    name = f"shrike_test_{uuid4().hex}"
    assert re.fullmatch(r"shrike_test_[0-9a-f]{32}", name)
    admin = create_engine(url, isolation_level="AUTOCOMMIT", hide_parameters=True)
    created = False
    db = Database(url.set(database=name).render_as_string(hide_password=False))
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        created = True
        with db.engine.begin() as connection:
            config = migration_config()
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield db
    finally:
        db.dispose()
        if created:
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def seeded_database(database: Database) -> Database:
    with database.session() as session, session.begin():
        seed_demo(session)
    return database


@pytest.fixture
def session(seeded_database: Database) -> Iterator[Session]:
    with seeded_database.session() as value:
        yield value


@pytest.fixture
def settings(seeded_database: Database) -> Settings:
    return Settings(
        database_url=SecretStr(seeded_database.engine.url.render_as_string(hide_password=False)),
        app_env="test",
        enable_dev_auth=True,
        dev_auth_token=SecretStr(TEST_TOKEN),
        dev_repository_grants="710001:810001",
    )


@pytest.fixture
def client(settings: Settings, seeded_database: Database) -> Iterator[TestClient]:
    with TestClient(create_app(settings, seeded_database)) as value:
        value.headers["Authorization"] = f"Bearer {TEST_TOKEN}"
        yield value
