"""
SQLAlchemy engine + session factory for audia's SQLite database.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from audia.config import get_settings
from audia.storage.models import Base


def _db_url() -> str:
    db_path = get_settings().db_path
    return f"sqlite:///{db_path}"


# Lazy singleton engine – created on first use
_engine = None
_SessionLocal = None


def engine():
    """Return (and lazily create) the SQLAlchemy engine."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            _db_url(),
            connect_args={"check_same_thread": False},
            echo=False,
        )
    return _engine


def _session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=engine(), autocommit=False, autoflush=False
        )
    return _SessionLocal


def init_db() -> None:
    """Create all tables (safe to call multiple times)."""
    Base.metadata.create_all(bind=engine())


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Context-manager that yields a DB session and commits/rolls back."""
    factory = _session_factory()
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
