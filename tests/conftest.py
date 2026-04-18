"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def clear_settings_cache(tmp_path, monkeypatch):
    """
    Before every test:
      - redirect AUDIA_DATA_DIR to a temp dir  (no writes to ~/.audia/)
      - clear get_settings() lru_cache
      - clear the per-project engine/factory registry
    Restore everything on teardown.
    """
    from audia.config import get_settings
    import audia.storage.database as db_mod

    monkeypatch.setenv("AUDIA_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    db_mod._engines.clear()
    db_mod._factories.clear()

    yield

    get_settings.cache_clear()
    db_mod._engines.clear()
    db_mod._factories.clear()


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
    Inject a fresh SQLite test DB into the per-project registry under the
    'default' key, yield the engine, then remove it.
    """
    import audia.storage.database as db_mod
    from audia.config import DEFAULT_PROJECT
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from audia.storage.models import Base

    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)

    db_mod._engines[DEFAULT_PROJECT] = test_engine
    db_mod._factories[DEFAULT_PROJECT] = TestSession

    yield test_engine

    db_mod._engines.pop(DEFAULT_PROJECT, None)
    db_mod._factories.pop(DEFAULT_PROJECT, None)
