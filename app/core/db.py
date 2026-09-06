"""SQLAlchemy 2.0 database layer: engine/session factory, base classes, mixins."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import DateTime, create_engine, event, func
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .logging import get_logger

logger = get_logger("app.db")


def utcnow() -> datetime:
    """UTC now as a *naive* datetime.

    SQLite has no timezone support and returns naive datetimes on read, while
    Postgres would return aware ones. Storing naive UTC consistently keeps
    comparisons and defaults portable across both backends. Serialize with
    `iso_utc()` to present ISO-8601 with a Z suffix.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso_utc(dt: datetime | None) -> str | None:
    """ISO-8601 string with explicit UTC marker; None-safe for serialization."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        text = dt.isoformat()
        return text if text.endswith("Z") else f"{text}Z"
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class Base(DeclarativeBase):
    pass


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampsMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


def _ensure_sqlite_dir(database_url: str) -> None:
    """Create the directory for a file-based SQLite database."""
    if database_url.startswith("sqlite:///"):
        path = database_url.removeprefix("sqlite:///")
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)


def make_engine(database_url: str, *, echo: bool = False) -> Engine:
    _ensure_sqlite_dir(database_url)
    kwargs: dict = {"echo": echo, "future": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(database_url, **kwargs)

    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _record):  # pragma: no cover
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    """Create all tables. Idempotent; safe on every startup."""
    from . import auth  # noqa: F401  (import registers models on Base)

    Base.metadata.create_all(engine)
    logger.info("Database tables ensured: %s", sorted(Base.metadata.tables))


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yield a session and close it after the request."""
    from .state import get_app_state  # local import to avoid circular imports

    factory = get_app_state().session_factory
    if factory is None:  # pragma: no cover - defensive
        raise RuntimeError("Database not initialised (session_factory is None)")
    with factory() as session:
        yield session


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Context manager for non-request code paths (scripts, tests, background)."""
    with session_factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
