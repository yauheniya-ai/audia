"""
SQLAlchemy engine + session factory for audia's SQLite database.
Supports per-project databases: each project lives under ~/.audia/<project>/.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from audia.config import DEFAULT_PROJECT, get_settings
from audia.storage.models import Base

# ── Per-project engine / session-factory registry ────────────────────────────
#
# _engines  : { project_name -> Engine }
# _factories: { project_name -> sessionmaker }
#
_engines: dict[str, object] = {}
_factories: dict[str, sessionmaker] = {}


def _resolve(project: str | None) -> str:
    return (project or DEFAULT_PROJECT).strip() or DEFAULT_PROJECT


def engine(project: str | None = None):
    """Return (and lazily create) the SQLAlchemy engine for *project*.
    Tables are auto-created on first access."""
    name = _resolve(project)
    if name not in _engines:
        cfg = get_settings()
        dirs = cfg.get_project_dirs(name)
        dirs.ensure_dirs()
        eng = create_engine(
            f"sqlite:///{dirs.db_path}",
            connect_args={"check_same_thread": False},
            echo=False,
        )
        # Auto-create tables for this project on first use
        Base.metadata.create_all(bind=eng)
        _engines[name] = eng
    return _engines[name]


def _session_factory(project: str | None = None) -> sessionmaker:
    name = _resolve(project)
    if name not in _factories:
        _factories[name] = sessionmaker(
            bind=engine(name), autocommit=False, autoflush=False
        )
    return _factories[name]


def init_db(project: str | None = None) -> None:
    """Create all tables for *project* (safe to call multiple times)."""
    Base.metadata.create_all(bind=engine(project))


@contextmanager
def get_session(project: str | None = None) -> Generator[Session, None, None]:
    """Context-manager that yields a DB session for *project* and commits/rolls back."""
    factory = _session_factory(project)
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
