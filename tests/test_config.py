"""Tests for Settings (config.py)."""

from __future__ import annotations

from pathlib import Path

import pytest


class TestSettingsDefaults:
    def test_default_llm_provider(self):
        from audia.config import Settings
        s = Settings(data_dir="/tmp/audia_test")
        assert s.llm_provider == "openai"

    def test_default_tts_backend(self):
        from audia.config import Settings
        s = Settings(data_dir="/tmp/audia_test")
        assert s.tts_backend == "edge-tts"

    def test_data_dir_field(self, tmp_path):
        from audia.config import Settings
        s = Settings(data_dir=tmp_path)
        assert s.data_dir == tmp_path


class TestSettingsProperties:
    def test_db_path(self, tmp_settings):
        assert tmp_settings.db_path == tmp_settings.data_dir / "audia.db"

    def test_audio_dir(self, tmp_settings):
        assert tmp_settings.audio_dir == tmp_settings.data_dir / "audio"

    def test_upload_dir(self, tmp_settings):
        assert tmp_settings.upload_dir == tmp_settings.data_dir / "uploads"

    def test_debug_dir(self, tmp_settings):
        assert tmp_settings.debug_dir == tmp_settings.data_dir / "debug"

    def test_ensure_dirs_creates_all(self, tmp_settings):
        tmp_settings.ensure_dirs()
        assert tmp_settings.audio_dir.is_dir()
        assert tmp_settings.upload_dir.is_dir()
        assert tmp_settings.debug_dir.is_dir()

    def test_ensure_dirs_idempotent(self, tmp_settings):
        tmp_settings.ensure_dirs()
        tmp_settings.ensure_dirs()  # must not raise


class TestSettingsValidator:
    def test_rejects_none_provider(self):
        from audia.config import Settings
        with pytest.raises(Exception, match="LLM curation is required"):
            Settings(data_dir="/tmp", llm_provider="none")

    def test_accepts_anthropic(self):
        from audia.config import Settings
        s = Settings(data_dir="/tmp", llm_provider="anthropic")
        assert s.llm_provider == "anthropic"

    def test_normalises_case(self):
        from audia.config import Settings
        s = Settings(data_dir="/tmp", llm_provider="OpenAI")
        assert s.llm_provider == "openai"


class TestGetSettings:
    def test_returns_settings_instance(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AUDIA_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("AUDIA_LLM_PROVIDER", "openai")
        from audia.config import get_settings
        s = get_settings()
        assert s.data_dir == tmp_path

    def test_is_cached(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AUDIA_DATA_DIR", str(tmp_path))
        from audia.config import get_settings
        assert get_settings() is get_settings()
