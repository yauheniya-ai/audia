"""Tests for the FastAPI application."""

from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """Return a TestClient backed by a temp data directory."""
    tmp = tmp_path_factory.mktemp("audia_test")

    # Patch Settings so data_dir points at tmp; also wire the DB singletons.
    import audia.storage.database as db_mod
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from audia.storage.models import Base
    from audia.config import Settings

    test_engine = create_engine(f"sqlite:///{tmp / 'test.db'}")
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(bind=test_engine)

    db_mod._engine = test_engine
    db_mod._SessionLocal = TestSession

    settings = Settings(
        data_dir=tmp,
        llm_provider="openai",
        openai_api_key="sk-test",
    )
    settings.ensure_dirs()  # create uploads/, audio/, debug/

    with patch("audia.config.get_settings", return_value=settings):
        from audia.ui.app import create_app
        app = create_app()
        yield TestClient(app)

    db_mod._engine = None
    db_mod._SessionLocal = None


class TestHealthEndpoints:
    def test_docs_available(self, client):
        res = client.get("/api/docs")
        assert res.status_code == 200

    def test_library_audio_empty(self, client):
        res = client.get("/api/library/audio")
        assert res.status_code == 200
        body = res.json()
        assert "audio_files" in body

    def test_library_papers_empty(self, client):
        res = client.get("/api/library/papers")
        assert res.status_code == 200
        body = res.json()
        assert "papers" in body


class TestConvertEndpoint:
    def test_non_pdf_rejected(self, client):
        fake_txt = io.BytesIO(b"This is not a PDF")
        res = client.post(
            "/api/convert/upload",
            files={"file": ("document.txt", fake_txt, "text/plain")},
        )
        assert res.status_code == 400

    def test_pdf_upload_triggers_pipeline(self, client, tmp_path):
        fake_audio = tmp_path / "out.mp3"
        fake_audio.write_bytes(b"FAKE_AUDIO_DATA")

        mock_state = {
            "audio_path": str(fake_audio),
            "audio_filename": "out.mp3",
            "title": "Test Paper",
            "num_pages": 3,
            "tts_backend": "edge-tts",
            "tts_voice": "en-US-AriaNeural",
            "error": None,
        }

        fake_pdf = io.BytesIO(b"%PDF-1.4\n%%EOF")

        # Ensure the upload dir exists so the route can write the temp file,
        # then patch run_pipeline to skip the actual LLM + TTS work.
        with patch("audia.ui.routes.convert.run_pipeline", return_value=mock_state):
            res = client.post(
                "/api/convert/upload",
                files={"file": ("paper.pdf", fake_pdf, "application/pdf")},
            )

        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert "download_url" in body

    def test_pdf_pipeline_error_returns_500(self, client):
        mock_state = {"error": "Extraction failed", "audio_path": None}
        fake_pdf = io.BytesIO(b"%PDF-1.4\n%%EOF")
        with patch("audia.ui.routes.convert.run_pipeline", return_value=mock_state):
            res = client.post(
                "/api/convert/upload",
                files={"file": ("paper.pdf", fake_pdf, "application/pdf")},
            )
        assert res.status_code == 500


class TestLibraryEndpoints:
    """Tests for /api/library routes, including delete."""

    def _seed_audio_file(self, tmp_path):
        """Create an AudioFile row (and a parent Paper) and return the audio id."""
        import audia.storage.database as db_mod
        from audia.storage.models import Paper, AudioFile

        audio_file = tmp_path / "test_audio.mp3"
        audio_file.write_bytes(b"AUDIO")

        from audia.storage.database import get_session
        with get_session() as session:
            paper = Paper(title="Seed Paper", authors="[]", pdf_path="/tmp/x.pdf")
            session.add(paper)
            session.flush()
            af = AudioFile(
                paper_id=paper.id,
                filename="test_audio.mp3",
                file_path=str(audio_file),
                tts_backend="edge-tts",
                tts_voice="en-US-AriaNeural",
            )
            session.add(af)
            session.flush()
            af_id = af.id
        return af_id, audio_file

    def test_delete_audio_returns_deleted(self, client, tmp_path):
        af_id, audio_file = self._seed_audio_file(tmp_path)
        res = client.delete(f"/api/library/audio/{af_id}")
        assert res.status_code == 200
        assert res.json()["status"] == "deleted"
        # physical file should also be gone
        assert not audio_file.exists()

    def test_delete_audio_not_found(self, client):
        res = client.delete("/api/library/audio/999999")
        assert res.status_code == 404


class TestResearchEndpoints:
    """Tests for /api/research routes."""

    def test_search_returns_results(self, client):
        from audia.agents.research import ArxivPaper

        fake_papers = [
            ArxivPaper(
                arxiv_id="2301.00001v1",
                title="Test Paper",
                authors=["Alice"],
                abstract="An abstract.",
                pdf_url="https://arxiv.org/pdf/2301.00001",
                published="2023-01-01",
            )
        ]
        with patch("audia.ui.routes.research.ArxivSearcher") as mock_cls:
            mock_cls.return_value.search.return_value = fake_papers
            res = client.post(
                "/api/research/search",
                json={"query": "transformers", "max_results": 5},
            )

        assert res.status_code == 200
        body = res.json()
        assert body["query"] == "transformers"
        assert len(body["results"]) == 1
        assert body["results"][0]["arxiv_id"] == "2301.00001v1"

    def test_search_propagates_exception(self, client):
        with patch("audia.ui.routes.research.ArxivSearcher") as mock_cls:
            mock_cls.return_value.search.side_effect = RuntimeError("network error")
            res = client.post(
                "/api/research/search",
                json={"query": "test"},
            )
        assert res.status_code == 500

    def test_convert_not_found_on_arxiv(self, client):
        with patch("audia.ui.routes.research.ArxivSearcher") as mock_cls:
            mock_cls.return_value.search.return_value = []
            res = client.post(
                "/api/research/convert",
                json={"arxiv_ids": ["2301.99999v1"]},
            )
        assert res.status_code == 200
        body = res.json()
        assert body["results"][0]["error"] == "Not found on ArXiv"

    def test_convert_download_failure(self, client):
        from audia.agents.research import ArxivPaper

        fake_paper = ArxivPaper(
            arxiv_id="2301.00001v1",
            title="Test",
            authors=[],
            abstract="",
            pdf_url="",
            published="2023-01-01",
        )
        with patch("audia.ui.routes.research.ArxivSearcher") as mock_cls:
            mock_cls.return_value.search.return_value = [fake_paper]
            mock_cls.return_value.download_pdf.side_effect = IOError("disk full")
            res = client.post(
                "/api/research/convert",
                json={"arxiv_ids": ["2301.00001v1"]},
            )
        assert res.status_code == 200
        body = res.json()
        assert "Download failed" in body["results"][0]["error"]

    def test_convert_pipeline_error(self, client, tmp_path):
        from audia.agents.research import ArxivPaper

        fake_paper = ArxivPaper(
            arxiv_id="2301.00002v1",
            title="Test2",
            authors=[],
            abstract="",
            pdf_url="",
            published="2023-01-01",
        )
        fake_pdf = tmp_path / "fake.pdf"
        fake_pdf.write_bytes(b"%PDF")
        with patch("audia.ui.routes.research.ArxivSearcher") as mock_cls, \
             patch("audia.ui.routes.research.run_pipeline", return_value={"error": "oops"}):
            mock_cls.return_value.search.return_value = [fake_paper]
            mock_cls.return_value.download_pdf.return_value = fake_pdf
            res = client.post(
                "/api/research/convert",
                json={"arxiv_ids": ["2301.00002v1"]},
            )
        assert res.status_code == 200
        body = res.json()
        assert body["results"][0]["error"] == "oops"

    def test_convert_success(self, client, tmp_path):
        from audia.agents.research import ArxivPaper

        fake_paper = ArxivPaper(
            arxiv_id="2301.00003v1",
            title="Success Paper",
            authors=["Bob"],
            abstract="Abstract",
            pdf_url="http://example.com/pdf",
            published="2023-01-01",
        )
        fake_pdf = tmp_path / "success.pdf"
        fake_pdf.write_bytes(b"%PDF")
        fake_audio = tmp_path / "success.mp3"
        fake_audio.write_bytes(b"AUDIO")

        mock_state = {
            "audio_path": str(fake_audio),
            "audio_filename": "success.mp3",
            "tts_backend": "edge-tts",
            "tts_voice": "en-US-AriaNeural",
            "error": None,
        }
        with patch("audia.ui.routes.research.ArxivSearcher") as mock_cls, \
             patch("audia.ui.routes.research.run_pipeline", return_value=mock_state):
            mock_cls.return_value.search.return_value = [fake_paper]
            mock_cls.return_value.download_pdf.return_value = fake_pdf
            res = client.post(
                "/api/research/convert",
                json={"arxiv_ids": ["2301.00003v1"]},
            )
        assert res.status_code == 200
        body = res.json()
        assert body["results"][0]["title"] == "Success Paper"
        assert "download_url" in body["results"][0]
