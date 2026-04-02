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


# ─────────────────────────────────────────────── Settings routes

class TestSettingsRoutes:
    def test_get_settings_returns_defaults(self, client):
        res = client.get("/api/settings")
        assert res.status_code == 200
        body = res.json()
        assert "tts_backend" in body
        assert "tts_voice" in body
        assert "llm1_provider" in body

    def test_put_settings_persists(self, client):
        res = client.put("/api/settings", json={"tts_voice": "en-GB-SoniaNeural"})
        assert res.status_code == 200
        assert res.json()["saved"] is True

        # Verify persistence
        res2 = client.get("/api/settings")
        assert res2.json()["tts_voice"] == "en-GB-SoniaNeural"

    def test_put_settings_partial_update(self, client):
        client.put("/api/settings", json={"stt_model": "whisper-small"})
        res = client.get("/api/settings")
        assert res.json()["stt_model"] == "whisper-small"

    def test_put_settings_empty_body(self, client):
        res = client.put("/api/settings", json={})
        assert res.status_code == 200


# ─────────────────────────────────────────────── Convert job endpoints

class TestConvertJobEndpoints:
    def test_enqueue_non_pdf_rejected(self, client):
        import io
        res = client.post(
            "/api/convert/enqueue",
            files={"file": ("doc.txt", io.BytesIO(b"text"), "text/plain")},
        )
        assert res.status_code == 400

    def test_enqueue_returns_job_id(self, client):
        import io
        res = client.post(
            "/api/convert/enqueue",
            files={"file": ("paper.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF"), "application/pdf")},
        )
        assert res.status_code == 200
        assert "job_id" in res.json()

    def test_job_status_not_found(self, client):
        res = client.get("/api/convert/status/nonexistent-job-xyz")
        assert res.status_code == 404

    def test_job_status_found(self, client):
        from audia.ui.jobs import JOBS
        jid = "convert_status_test"
        JOBS[jid] = {"status": "running", "stage": "queued", "log": [], "progress": 2}
        try:
            res = client.get(f"/api/convert/status/{jid}")
            assert res.status_code == 200
            assert res.json()["status"] == "running"
        finally:
            JOBS.pop(jid, None)

    def test_cancel_job_not_found(self, client):
        res = client.delete("/api/convert/jobs/nonexistent-cancel")
        assert res.status_code == 404

    def test_cancel_running_job(self, client):
        from audia.ui.jobs import JOBS
        jid = "convert_cancel_test"
        JOBS[jid] = {
            "status": "running", "stage": "curating", "log": [],
            "cancelled": False, "stage_label": "Curating",
        }
        try:
            res = client.delete(f"/api/convert/jobs/{jid}")
            assert res.status_code == 200
            assert JOBS[jid]["cancelled"] is True
            assert res.json()["status"] == "cancel_requested"
        finally:
            JOBS.pop(jid, None)

    def test_cancel_non_running_job_is_noop(self, client):
        from audia.ui.jobs import JOBS
        jid = "convert_done_test"
        JOBS[jid] = {
            "status": "done", "stage": "done", "log": [],
            "cancelled": False, "stage_label": "Complete",
        }
        try:
            res = client.delete(f"/api/convert/jobs/{jid}")
            assert res.status_code == 200
            assert JOBS[jid]["cancelled"] is False  # unchanged
        finally:
            JOBS.pop(jid, None)

    def test_serve_job_pdf_not_found_job(self, client):
        res = client.get("/api/convert/jobs/nonexistent-pdf/pdf")
        assert res.status_code == 404

    def test_serve_job_pdf_no_path(self, client):
        from audia.ui.jobs import JOBS
        jid = "convert_pdf_none"
        JOBS[jid] = {"status": "running", "pdf_path": None, "log": []}
        try:
            res = client.get(f"/api/convert/jobs/{jid}/pdf")
            assert res.status_code == 404
        finally:
            JOBS.pop(jid, None)

    def test_serve_job_pdf_file_exists(self, client, tmp_path):
        from audia.ui.jobs import JOBS
        fake_pdf = tmp_path / "job.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4")
        jid = "convert_pdf_real"
        JOBS[jid] = {"status": "running", "pdf_path": str(fake_pdf), "log": []}
        try:
            res = client.get(f"/api/convert/jobs/{jid}/pdf")
            assert res.status_code == 200
            assert res.headers["content-type"] == "application/pdf"
        finally:
            JOBS.pop(jid, None)

    def test_download_audio_not_found(self, client):
        res = client.get("/api/convert/download/999999")
        assert res.status_code == 404

    def test_download_audio_file_missing_on_disk(self, client):
        """DB record exists but file is gone from disk → 404."""
        import io
        from audia.storage.database import get_session
        from audia.storage.models import Paper, AudioFile

        with get_session() as session:
            paper = Paper(title="DL Paper", authors="[]", pdf_path="/tmp/dl.pdf")
            session.add(paper)
            session.flush()
            af = AudioFile(
                paper_id=paper.id,
                filename="ghost.mp3",
                file_path="/nonexistent/path/ghost.mp3",
                tts_backend="edge-tts",
                tts_voice="en-US-AriaNeural",
            )
            session.add(af)
            session.flush()
            af_id = af.id

        res = client.get(f"/api/convert/download/{af_id}")
        assert res.status_code == 404

    def test_download_audio_success(self, client, tmp_path):
        import io
        from audia.storage.database import get_session
        from audia.storage.models import Paper, AudioFile

        real_audio = tmp_path / "real_out.mp3"
        real_audio.write_bytes(b"ID3\x00FAKE_MP3")

        with get_session() as session:
            paper = Paper(title="Real Paper", authors="[]", pdf_path="/tmp/rp.pdf")
            session.add(paper)
            session.flush()
            af = AudioFile(
                paper_id=paper.id,
                filename=real_audio.name,
                file_path=str(real_audio),
                tts_backend="edge-tts",
                tts_voice="en-US-AriaNeural",
            )
            session.add(af)
            session.flush()
            af_id = af.id

        res = client.get(f"/api/convert/download/{af_id}")
        assert res.status_code == 200
        assert "audio" in res.headers["content-type"]


# ─────────────────────────────────────────────── Research job endpoints

class TestResearchJobEndpoints:
    def test_normalize_success(self, client):
        mock_result = MagicMock()
        mock_result.content = "attention mechanisms transformers"
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_result

        with patch("audia.agents.text_cleaner._build_llm", return_value=mock_llm):
            res = client.post(
                "/api/research/normalize",
                json={"query": "I want to learn about attention in transformers"},
            )
        assert res.status_code == 200
        assert res.json()["search_string"] == "attention mechanisms transformers"

    def test_normalize_with_provider_override(self, client):
        mock_result = MagicMock()
        mock_result.content = "diffusion models"
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_result

        with patch("audia.agents.text_cleaner._build_llm", return_value=mock_llm):
            res = client.post(
                "/api/research/normalize",
                json={
                    "query": "diffusion image gen",
                    "llm_provider": "openai",
                    "llm_model": "gpt-4o-mini",
                },
            )
        assert res.status_code == 200

    def test_normalize_error_returns_500(self, client):
        with patch("audia.agents.text_cleaner._build_llm",
                   side_effect=RuntimeError("API key missing")):
            res = client.post(
                "/api/research/normalize",
                json={"query": "something"},
            )
        assert res.status_code == 500

    def test_enqueue_research_returns_job_ids(self, client):
        res = client.post(
            "/api/research/enqueue",
            json={"arxiv_ids": ["2301.00001v1", "2301.00002v1"]},
        )
        assert res.status_code == 200
        body = res.json()
        assert "jobs" in body
        assert len(body["jobs"]) == 2
        assert body["jobs"][0]["arxiv_id"] == "2301.00001v1"
        assert "job_id" in body["jobs"][0]

    def test_research_status_not_found(self, client):
        res = client.get("/api/research/status/nonexistent-research-xyz")
        assert res.status_code == 404

    def test_research_status_found(self, client):
        from audia.ui.jobs import JOBS
        jid = "research_status_test"
        JOBS[jid] = {"status": "running", "stage": "searching", "log": [], "progress": 5}
        try:
            res = client.get(f"/api/research/status/{jid}")
            assert res.status_code == 200
            assert res.json()["stage"] == "searching"
        finally:
            JOBS.pop(jid, None)

    def test_research_cancel_not_found(self, client):
        res = client.delete("/api/research/jobs/nonexistent-cancel-r")
        assert res.status_code == 404

    def test_research_cancel_running(self, client):
        from audia.ui.jobs import JOBS
        jid = "research_cancel_test"
        JOBS[jid] = {
            "status": "running", "stage": "downloading", "log": [],
            "cancelled": False, "stage_label": "Downloading",
        }
        try:
            res = client.delete(f"/api/research/jobs/{jid}")
            assert res.status_code == 200
            assert JOBS[jid]["cancelled"] is True
        finally:
            JOBS.pop(jid, None)

    def test_research_serve_pdf_not_found(self, client):
        res = client.get("/api/research/jobs/nonexistent-pdf-r/pdf")
        assert res.status_code == 404

    def test_research_serve_pdf_file_exists(self, client, tmp_path):
        from audia.ui.jobs import JOBS
        fake_pdf = tmp_path / "research.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4")
        jid = "research_pdf_real"
        JOBS[jid] = {"status": "running", "pdf_path": str(fake_pdf), "log": []}
        try:
            res = client.get(f"/api/research/jobs/{jid}/pdf")
            assert res.status_code == 200
        finally:
            JOBS.pop(jid, None)

    def test_transcribe_audio(self, client):
        import io
        with patch("audia.agents.stt.transcribe_file", return_value="hello world"):
            res = client.post(
                "/api/research/transcribe",
                files={"file": ("audio.webm", io.BytesIO(b"\x00\x01\x02"), "audio/webm")},
            )
        assert res.status_code == 200
        assert res.json()["text"] == "hello world"


# ─────────────────────────────────────────────── Library extended CRUD

class TestLibraryExtended:
    def _seed_paper_with_audio(self, tmp_path):
        from audia.storage.database import get_session
        from audia.storage.models import Paper, AudioFile

        audio_file = tmp_path / f"lib_ext_{id(self)}.mp3"
        audio_file.write_bytes(b"AUDIO_DATA")

        with get_session() as session:
            paper = Paper(
                title="Library Test Paper",
                authors='["Carol"]',
                pdf_path=str(tmp_path / "lib.pdf"),
            )
            session.add(paper)
            session.flush()
            af = AudioFile(
                paper_id=paper.id,
                filename=audio_file.name,
                file_path=str(audio_file),
                tts_backend="edge-tts",
                tts_voice="en-US-AriaNeural",
            )
            session.add(af)
            session.flush()
            return paper.id, af.id, audio_file

    def test_list_research_sessions_empty(self, client):
        res = client.get("/api/library/research_sessions")
        assert res.status_code == 200
        assert "research_sessions" in res.json()

    def test_list_user_settings_empty(self, client):
        res = client.get("/api/library/user_settings")
        assert res.status_code == 200
        assert "user_settings" in res.json()

    def test_get_paper_found(self, client, tmp_path):
        paper_id, _, _ = self._seed_paper_with_audio(tmp_path)
        res = client.get(f"/api/library/papers/{paper_id}")
        assert res.status_code == 200
        body = res.json()
        assert body["id"] == paper_id
        assert "audio_files" in body

    def test_get_paper_not_found(self, client):
        res = client.get("/api/library/papers/999888")
        assert res.status_code == 404

    def test_patch_paper_success(self, client, tmp_path):
        paper_id, _, _ = self._seed_paper_with_audio(tmp_path)
        res = client.patch(
            f"/api/library/papers/{paper_id}",
            json={"title": "Updated Title"},
        )
        assert res.status_code == 200
        assert res.json()["id"] == paper_id

        # Verify change
        res2 = client.get(f"/api/library/papers/{paper_id}")
        assert res2.json()["title"] == "Updated Title"

    def test_patch_paper_not_found(self, client):
        res = client.patch("/api/library/papers/999777", json={"title": "X"})
        assert res.status_code == 404

    def test_patch_audio_success(self, client, tmp_path):
        _, af_id, _ = self._seed_paper_with_audio(tmp_path)
        res = client.patch(
            f"/api/library/audio/{af_id}",
            json={"tts_voice": "en-GB-SoniaNeural"},
        )
        assert res.status_code == 200

    def test_patch_audio_not_found(self, client):
        res = client.patch("/api/library/audio/999666", json={"tts_voice": "x"})
        assert res.status_code == 404

    def test_patch_user_setting_not_found(self, client):
        res = client.patch("/api/library/user_settings/nonexistent_key", json={"value": "v"})
        assert res.status_code == 404

    def test_patch_user_setting_found(self, client):
        # First PUT a setting via the settings route, then PATCH it via library
        client.put("/api/settings", json={"tts_backend": "kokoro"})
        res = client.patch("/api/library/user_settings/tts_backend", json={"value": "edge-tts"})
        assert res.status_code == 200
        assert res.json()["key"] == "tts_backend"

    def test_delete_paper_not_found(self, client):
        res = client.delete("/api/library/papers/999555")
        assert res.status_code == 404

    def test_delete_paper_success(self, client, tmp_path):
        paper_id, _, audio_file = self._seed_paper_with_audio(tmp_path)
        res = client.delete(f"/api/library/papers/{paper_id}")
        assert res.status_code == 200
        assert res.json()["status"] == "deleted"
        assert not audio_file.exists()

        # Confirm gone
        res2 = client.get(f"/api/library/papers/{paper_id}")
        assert res2.status_code == 404

    def test_serve_pdf_not_found(self, client):
        res = client.get("/api/library/pdf/999444")
        assert res.status_code == 404

    def test_serve_pdf_no_file_on_disk(self, client, tmp_path):
        from audia.storage.database import get_session
        from audia.storage.models import Paper

        with get_session() as session:
            paper = Paper(
                title="Ghost PDF Paper",
                authors="[]",
                pdf_path="/nonexistent/ghost.pdf",
            )
            session.add(paper)
            session.flush()
            pid = paper.id

        res = client.get(f"/api/library/pdf/{pid}")
        assert res.status_code == 404

    def test_patch_research_session_not_found(self, client):
        res = client.patch(
            "/api/library/research_sessions/999333",
            json={"query": "new query"},
        )
        assert res.status_code == 404


# ─────────────────────────────────────────────── UI app / SPA

class TestUIApp:
    def test_api_info_endpoint(self, client):
        res = client.get("/api/info")
        assert res.status_code == 200
        body = res.json()
        assert "version" in body
        assert body["name"] == "audia"

    def test_spa_catch_all_for_unknown_path(self, client):
        # Unknown paths fall back to index.html (404 from TestClient if static
        # dir missing, but the route should exist and not 405)
        res = client.get("/some/deep/spa/route")
        # Either 200 (index.html served) or 404 (no static dir in test env)
        assert res.status_code in (200, 404, 500)
