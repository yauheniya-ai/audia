"""Shared pytest fixtures."""

from __future__ import annotations

import os
import pytest


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Clear the lru_cache on get_settings before and after every test."""
    from audia.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def tmp_settings(tmp_path):
    """Real Settings instance pointing at a temp directory."""
    from audia.config import Settings
    return Settings(
        data_dir=tmp_path,
        llm_provider="openai",
        openai_api_key="sk-test-key",
    )


@pytest.fixture
def isolated_db(tmp_path):
    """
    Swap the module-level SQLAlchemy singletons for a fresh temp DB,
    yield the engine, then restore the originals.
    """
    import audia.storage.database as db_mod
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from audia.storage.models import Base

    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(bind=test_engine)

    old_engine, old_session = db_mod._engine, db_mod._SessionLocal
    db_mod._engine = test_engine
    db_mod._SessionLocal = TestSession

    yield test_engine

    db_mod._engine = old_engine
    db_mod._SessionLocal = old_session
