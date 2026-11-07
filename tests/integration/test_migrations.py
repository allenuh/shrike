import pytest
from alembic import command
from conftest import migration_config
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError

from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.demo import demo_id, seed_demo
from shrike.adapters.persistence.models import Installation, ReviewJob

pytestmark = pytest.mark.integration
TABLES = {
    "installations",
    "repositories",
    "pull_requests",
    "review_jobs",
    "review_findings",
    "review_executions",
    "webhook_deliveries",
    "analysis_reports",
    "ai_budgets",
    "ai_price_snapshots",
    "ai_spend_entries",
}


def test_upgrade_downgrade_upgrade_and_metadata_agreement(database: Database) -> None:
    assert set(inspect(database.engine).get_table_names()) == TABLES | {"alembic_version"}
    with database.engine.begin() as connection:
        config = migration_config()
        config.attributes["connection"] = connection
        command.check(config)
        command.downgrade(config, "base")
    assert set(inspect(database.engine).get_table_names()) == {"alembic_version"}
    with database.engine.begin() as connection:
        config = migration_config()
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        command.check(config)
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0003_analysis"
    assert set(inspect(database.engine).get_table_names()) == TABLES | {"alembic_version"}


def test_fresh_test_database_is_empty(database: Database) -> None:
    assert database.engine.url.database is not None
    assert database.engine.url.database.startswith("shrike_test_")
    assert database.engine.url.database != "shrike_test"
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Installation)) == 0


def test_seed_is_deterministic_and_idempotent(database: Database) -> None:
    with database.session() as session, session.begin():
        assert seed_demo(session)
    with database.session() as session, session.begin():
        assert not seed_demo(session)
        assert session.scalar(select(func.count()).select_from(ReviewJob)) == 6
        assert session.get(ReviewJob, demo_id("completed")) is not None


def test_sessions_rollback_uncommitted_work_and_recover_after_errors(database: Database) -> None:
    with database.session() as session:
        session.add(Installation(github_id=111, account_github_id=112, account_type="User"))
        session.flush()
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Installation)) == 0
        with pytest.raises(IntegrityError), session.begin_nested():
            session.add(Installation(github_id=-1, account_github_id=1, account_type="User"))
            session.flush()
        assert session.scalar(select(func.count()).select_from(Installation)) == 0


def test_seed_refuses_nonempty_non_demo_database(database: Database) -> None:
    with database.session() as session, session.begin():
        session.add(Installation(github_id=111, account_github_id=112, account_type="User"))
    with database.session() as session, pytest.raises(ValueError, match="empty database"):
        seed_demo(session)
