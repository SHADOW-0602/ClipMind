from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings

_engine: Engine | None = None


def _enable_sqlite_pragmas(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        settings.ensure_dirs()
        connect_args = {"check_same_thread": False}
        _engine = create_engine(
            settings.resolved_database_url,
            connect_args=connect_args,
            pool_pre_ping=True,
        )
        if settings.resolved_database_url.startswith("sqlite"):
            _enable_sqlite_pragmas(_engine)
    return _engine


def init_db() -> None:
    from . import models  # noqa: F401  (register SQLModel metadata)

    SQLModel.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    with Session(get_engine()) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def reset_engine() -> None:
    """Used by tests after changing DATA_DIR/DATABASE_URL."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None
