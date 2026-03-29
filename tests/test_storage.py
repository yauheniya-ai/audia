"""Tests for the storage layer (models + database)."""

from __future__ import annotations

import json

import pytest


class TestPaperModel:
    def test_repr(self, isolated_db):
        from audia.storage.models import Paper
        p = Paper(title="Test Paper", authors="[]")
        assert "Test Paper" in repr(p)

    def test_authors_list_valid_json(self, isolated_db):
        from audia.storage.models import Paper
        p = Paper(title="T", authors=json.dumps(["Alice", "Bob"]))
        assert p.authors_list == ["Alice", "Bob"]

    def test_authors_list_fallback(self, isolated_db):
        from audia.storage.models import Paper
        p = Paper(title="T", authors="plain string")
        assert p.authors_list == ["plain string"]

    def test_persist_and_retrieve(self, isolated_db):
        from audia.storage.database import get_session
        from audia.storage.models import Paper

        with get_session() as session:
            paper = Paper(title="Attention Is All You Need", authors=json.dumps(["Vaswani"]))
            session.add(paper)
            session.flush()
            pid = paper.id

        with get_session() as session:
            fetched = session.get(Paper, pid)
            assert fetched is not None
            assert fetched.title == "Attention Is All You Need"
            assert fetched.authors_list == ["Vaswani"]


class TestAudioFileModel:
    def test_repr(self):
        from audia.storage.models import AudioFile
        af = AudioFile(filename="out.mp3", file_path="/tmp/out.mp3")
        assert "out.mp3" in repr(af)

    def test_persist_with_paper(self, isolated_db):
        from audia.storage.database import get_session
        from audia.storage.models import AudioFile, Paper

        with get_session() as session:
            paper = Paper(title="Test", authors="[]")
            session.add(paper)
            session.flush()
            af = AudioFile(
                paper_id=paper.id,
                filename="test.mp3",
                file_path="/tmp/test.mp3",
                tts_backend="edge-tts",
                tts_voice="en-US-AriaNeural",
            )
            session.add(af)
            session.flush()
            afid = af.id

        with get_session() as session:
            fetched = session.get(AudioFile, afid)
            assert fetched.filename == "test.mp3"
            assert fetched.tts_backend == "edge-tts"


class TestResearchSessionModel:
    def test_paper_ids_list(self):
        from audia.storage.models import ResearchSession
        rs = ResearchSession(query="transformers", paper_ids=json.dumps([1, 2, 3]))
        assert rs.paper_ids_list == [1, 2, 3]

    def test_paper_ids_fallback(self):
        from audia.storage.models import ResearchSession
        rs = ResearchSession(query="q", paper_ids="broken json{")
        assert rs.paper_ids_list == []

    def test_repr(self):
        from audia.storage.models import ResearchSession
        rs = ResearchSession(query="attention", paper_ids="[]")
        assert "attention" in repr(rs)


class TestDatabase:
    def test_init_db_creates_tables(self, isolated_db):
        from sqlalchemy import inspect
        inspector = inspect(isolated_db)
        assert "papers" in inspector.get_table_names()
        assert "audio_files" in inspector.get_table_names()
        assert "research_sessions" in inspector.get_table_names()

    def test_get_session_commits(self, isolated_db):
        from audia.storage.database import get_session
        from audia.storage.models import Paper

        with get_session() as session:
            session.add(Paper(title="Commit Test", authors="[]"))

        with get_session() as session:
            result = session.query(Paper).filter_by(title="Commit Test").first()
            assert result is not None

    def test_get_session_rolls_back_on_error(self, isolated_db):
        from audia.storage.database import get_session
        from audia.storage.models import Paper

        with pytest.raises(RuntimeError):
            with get_session() as session:
                session.add(Paper(title="Rollback Test", authors="[]"))
                raise RuntimeError("deliberate")

        with get_session() as session:
            result = session.query(Paper).filter_by(title="Rollback Test").first()
            assert result is None
