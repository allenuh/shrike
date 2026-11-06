from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


class Database:
    def __init__(self, url: str) -> None:
        self.engine: Engine = create_engine(
            url,
            pool_pre_ping=True,
            echo=False,
            hide_parameters=True,
            connect_args={"connect_timeout": 5, "options": "-c timezone=UTC"},
        )
        self.sessions = sessionmaker(self.engine, expire_on_commit=False, autoflush=False)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Each caller owns its session; close rolls back uncommitted reads/writes."""
        with self.sessions() as session:
            yield session

    def dispose(self) -> None:
        self.engine.dispose()
