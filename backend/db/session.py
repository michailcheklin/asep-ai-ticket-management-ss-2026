"""SQLAlchemy engine and session helpers for backend-owned SQLite state."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import EMAIL_TICKET_TRANSMISSION_DB_PATH
from .models import Base

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _sqlite_url(path: str) -> str:
    resolved = Path(path).expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{resolved.as_posix()}"


def get_engine(db_path: str | None = None) -> Engine:
    """Return a process-wide SQLite engine (created on first use)."""
    global _engine, _SessionLocal
    if _engine is not None and db_path is None:
        return _engine

    if _engine is not None and db_path is not None:
        _engine.dispose()
        _engine = None
        _SessionLocal = None

    url = _sqlite_url(db_path or EMAIL_TICKET_TRANSMISSION_DB_PATH)
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 30},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    _engine = engine
    _SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    return _engine


def get_session_factory(db_path: str | None = None) -> sessionmaker[Session]:
    """Return a session factory bound to the configured engine."""
    get_engine(db_path)
    assert _SessionLocal is not None
    return _SessionLocal


def init_db(db_path: str | None = None) -> None:
    """Create tables if they do not exist yet."""
    engine = get_engine(db_path)
    Base.metadata.create_all(bind=engine)


def reset_engine_for_tests() -> None:
    """Drop cached engine/session so tests can use an isolated DB path."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
