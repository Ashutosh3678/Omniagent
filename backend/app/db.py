"""SQLAlchemy engine and session helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_sessionmaker: sessionmaker[Session] | None = None


def init_engine(url: str = DATABASE_URL) -> Engine:
    global _engine, _sessionmaker
    # pool_pre_ping and a short recycle survive Neon suspending an idle database. psycopg's automatic
    # prepared statements break behind a transaction-mode pooler (Neon's "-pooler" host), so turn them off.
    kwargs: dict = {"pool_pre_ping": True, "pool_recycle": 300, "connect_args": {"prepare_threshold": None}}
    if url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
    _engine = create_engine(url, **kwargs)
    _sessionmaker = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    return _engine or init_engine()


@contextmanager
def session_scope() -> Iterator[Session]:
    get_engine()
    assert _sessionmaker is not None
    session = _sessionmaker()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
