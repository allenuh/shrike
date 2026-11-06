from alembic import context
from sqlalchemy.engine import Connection

from shrike.adapters.persistence.database import Database
from shrike.adapters.persistence.models import Base
from shrike.config import Settings

config = context.config


def migrate(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(
        url=Settings().database_url.get_secret_value(),
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        migrate(supplied_connection)
    else:
        database = Database(Settings().database_url.get_secret_value())
        try:
            with database.engine.connect() as connection:
                migrate(connection)
        finally:
            database.dispose()
