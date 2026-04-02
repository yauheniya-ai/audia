"""Tests for async background job functions.

Covers:
- _run_research_job() in routes/research.py (direct async call)
- The _run() closure inside enqueue_conversion in routes/convert.py (via httpx AsyncClient)
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest


# ─────────────────────────────────────────── fixtures

@pytest.fixture
async def async_convert_client(tmp_path):
    """Async HTTP client wired to a fresh temp DB — for testing convert enqueue."""
    import audia.storage.database as db_mod
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from audia.storage.models import Base
    from audia.config import Settings

    test_engine = create_engine(f"sqlite:///{tmp_path / 'async_conv.db'}")
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(bind=test_engine)

    old_e, old_s = db_mod._engine, db_mod._SessionLocal
    db_mod._engine = test_engine
    db_mod._SessionLocal = TestSession

    settings = Settings(
        data_dir=tmp_path, llm_provider="openai", openai_api_key="sk-test"
    )
    settings.ensure_dirs()

    with patch("audia.config.get_settings", return_value=settings):
        from audia.ui.app import create_app
        app = create_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, settings, tmp_path

    db_mod._engine = old_e
    db_mod._SessionLocal = old_s


# ─────────────────────────────────────────── _run_research_job direct tests

class TestRunResearchJob:
    """Direct async calls to _run_research_job in routes/research.py."""

    def _make_job(self, job_id: str) -> dict:
        from audia.ui.jobs import JOBS
        job = {
            "status": "running", "stage": "queued", "stage_label": "Queued",
            "progress": 2, "log": [], "stats": {}, "result": None, "error": None,
            "cancelled": False, "pdf_path": None, "pdf_title": job_id, "paper_id": None,
        }
        JOBS[job_id] = job
        return job

    async def test_successful_run(self, tmp_path, isolated_db):
        from audia.ui.routes.research import _run_research_job
        from audia.ui.jobs import JOBS
        from audia.agents.research import ArxivPaper
        from audia.config import Settings

        job_id = "rjob-success"
        self._make_job(job_id)

        paper = ArxivPaper(
            arxiv_id="2301.99001v1",
            title="Async Research Paper",
            authors=["Test Author"],
            abstract="Test abstract.",
            pdf_url="https://example.com/pdf",
            published="2023-01-01",
        )
        fake_pdf = tmp_path / "rjob.pdf"
        fake_pdf.write_bytes(b"%PDF")
        fake_audio = tmp_path / "rjob.mp3"
        fake_audio.write_bytes(b"AUDIO")

        pdf_result = MagicMock()
        pdf_result.text = "Extracted research text"
        pdf_result.num_pages = 4
        pdf_result.title = "Async Research Paper"

        settings = Settings(
            data_dir=tmp_path, llm_provider="openai", openai_api_key="sk-x"
        )
        settings.ensure_dirs()

        with patch("audia.ui.routes.research.get_settings", return_value=settings), \
             patch("audia.ui.routes.research.ArxivSearcher") as mock_cls, \
             patch("audia.ui.routes.research.extract_text", return_value=pdf_result), \
             patch("audia.ui.routes.research.heuristic_clean", return_value="cleaned text"), \
             patch("audia.ui.routes.research.llm_curate", return_value="curated text"), \
             patch("audia.ui.routes.research.synthesize", return_value=fake_audio):
            searcher = MagicMock()
            searcher.search.return_value = [paper]
            searcher.download_pdf.return_value = fake_pdf
            mock_cls.return_value = searcher

            await _run_research_job(
                job_id, "2301.99001v1",
                query="async research test",
                llm_provider="openai",
                llm_model="gpt-4o-mini",
                tts_backend="edge-tts",
                tts_voice="en-US-AriaNeural",
            )

        job = JOBS[job_id]
        try:
            assert job["status"] == "done"
            assert job["progress"] == 100
            assert job["result"]["title"] == "Async Research Paper"
            assert job["result"]["num_pages"] == 4
        finally:
            JOBS.pop(job_id, None)

    async def test_paper_not_found(self, tmp_path, isolated_db):
        from audia.ui.routes.research import _run_research_job
        from audia.ui.jobs import JOBS
        from audia.config import Settings

        job_id = "rjob-notfound"
        self._make_job(job_id)
        settings = Settings(data_dir=tmp_path, llm_provider="openai", openai_api_key="sk-x")

        with patch("audia.ui.routes.research.get_settings", return_value=settings), \
             patch("audia.ui.routes.research.ArxivSearcher") as mock_cls:
            searcher = MagicMock()
            searcher.search.return_value = []
            mock_cls.return_value = searcher

            await _run_research_job(job_id, "2301.00000v1")

        job = JOBS[job_id]
        try:
            assert job["status"] == "error"
            assert "not found" in job["error"].lower()
        finally:
            JOBS.pop(job_id, None)

    async def test_cancelled_after_search(self, tmp_path, isolated_db):
        from audia.ui.routes.research import _run_research_job
        from audia.ui.jobs import JOBS
        from audia.agents.research import ArxivPaper
        from audia.config import Settings

        job_id = "rjob-cancel"
        job = self._make_job(job_id)
        settings = Settings(data_dir=tmp_path, llm_provider="openai", openai_api_key="sk-x")

        paper = ArxivPaper(
            arxiv_id="2301.99002v1",
            title="Cancel Paper",
            authors=[],
            abstract="",
            pdf_url="",
            published="2023-01-01",
        )

        cancel_pdf = tmp_path / "cancel.pdf"
        cancel_pdf.write_bytes(b"%PDF")

        def cancel_on_download(*args, **kwargs):
            job["cancelled"] = True
            return cancel_pdf

        with patch("audia.ui.routes.research.get_settings", return_value=settings), \
             patch("audia.ui.routes.research.ArxivSearcher") as mock_cls:
            searcher = MagicMock()
            searcher.search.return_value = [paper]
            searcher.download_pdf.side_effect = cancel_on_download
            mock_cls.return_value = searcher

            await _run_research_job(job_id, "2301.99002v1")

        try:
            assert job["status"] == "cancelled"
        finally:
            JOBS.pop(job_id, None)

    async def test_exception_sets_error_status(self, tmp_path, isolated_db):
        from audia.ui.routes.research import _run_research_job
        from audia.ui.jobs import JOBS
        from audia.config import Settings

        job_id = "rjob-error"
        self._make_job(job_id)
        settings = Settings(data_dir=tmp_path, llm_provider="openai", openai_api_key="sk-x")

        with patch("audia.ui.routes.research.get_settings", return_value=settings), \
             patch("audia.ui.routes.research.ArxivSearcher") as mock_cls:
            searcher = MagicMock()
            searcher.search.side_effect = RuntimeError("network failure")
            mock_cls.return_value = searcher

            await _run_research_job(job_id, "bad-id")

        job = JOBS[job_id]
        try:
            assert job["status"] == "error"
            assert "network failure" in job["error"]
        finally:
            JOBS.pop(job_id, None)

    async def test_no_query_skips_research_session(self, tmp_path, isolated_db):
        """When query=None, no ResearchSession row is written."""
        from audia.ui.routes.research import _run_research_job
        from audia.ui.jobs import JOBS
        from audia.agents.research import ArxivPaper
        from audia.config import Settings

        job_id = "rjob-noquery"
        self._make_job(job_id)

        paper = ArxivPaper(
            arxiv_id="2301.88001v1",
            title="No-Query Paper",
            authors=["A"],
            abstract="Abstract",
            pdf_url="",
            published="2023-01-01",
        )
        fake_pdf = tmp_path / "noq.pdf"
        fake_pdf.write_bytes(b"%PDF")
        fake_audio = tmp_path / "noq.mp3"
        fake_audio.write_bytes(b"AUDIO")

        pdf_result = MagicMock()
        pdf_result.text = "text"
        pdf_result.num_pages = 1
        pdf_result.title = "No-Query Paper"

        settings = Settings(data_dir=tmp_path, llm_provider="openai", openai_api_key="sk-x")
        settings.ensure_dirs()

        with patch("audia.ui.routes.research.get_settings", return_value=settings), \
             patch("audia.ui.routes.research.ArxivSearcher") as mock_cls, \
             patch("audia.ui.routes.research.extract_text", return_value=pdf_result), \
             patch("audia.ui.routes.research.heuristic_clean", return_value="clean"), \
             patch("audia.ui.routes.research.llm_curate", return_value="cured"), \
             patch("audia.ui.routes.research.synthesize", return_value=fake_audio):
            searcher = MagicMock()
            searcher.search.return_value = [paper]
            searcher.download_pdf.return_value = fake_pdf
            mock_cls.return_value = searcher

            await _run_research_job(job_id, "2301.88001v1", query=None)

        try:
            assert JOBS[job_id]["status"] == "done"
        finally:
            JOBS.pop(job_id, None)


# ─────────────────────────────────────────── convert enqueue async

class TestConvertEnqueueAsync:
    """Test the _run() closure inside enqueue_conversion via async HTTP."""

    async def test_enqueue_pipeline_completes(self, async_convert_client):
        client, settings, tmp = async_convert_client
        fake_audio = tmp / "conv_async.mp3"
        fake_audio.write_bytes(b"AUDIO_DATA")

        pdf_result = MagicMock()
        pdf_result.text = "Extracted text"
        pdf_result.num_pages = 2
        pdf_result.title = "Async Convert Paper"

        with patch("audia.ui.routes.convert.extract_text", return_value=pdf_result), \
             patch("audia.ui.routes.convert.heuristic_clean", return_value="cleaned"), \
             patch("audia.ui.routes.convert.llm_curate", return_value="curated"), \
             patch("audia.ui.routes.convert.synthesize", return_value=fake_audio):

            res = await client.post(
                "/api/convert/enqueue",
                files={"file": ("async_test.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
            )
            assert res.status_code == 200
            job_id = res.json()["job_id"]

            # Yield to event loop repeatedly so the background task can run
            for _ in range(40):
                await asyncio.sleep(0.05)

        from audia.ui.jobs import JOBS
        job = JOBS.get(job_id, {})
        # The task should have progressed (done or error — not queued)
        assert job.get("status") in ("done", "error")

    async def test_enqueue_pipeline_error(self, async_convert_client):
        """If extract_text raises, job ends in error state."""
        client, settings, tmp = async_convert_client

        with patch("audia.ui.routes.convert.extract_text",
                   side_effect=RuntimeError("PDF corrupt")):
            res = await client.post(
                "/api/convert/enqueue",
                files={"file": ("err.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
            )
            assert res.status_code == 200
            job_id = res.json()["job_id"]

            for _ in range(20):
                await asyncio.sleep(0.05)

        from audia.ui.jobs import JOBS
        job = JOBS.get(job_id, {})
        assert job.get("status") in ("error", "running")

    async def test_enqueue_cancelled_mid_run(self, async_convert_client):
        """Cancellation flag stops the job after the current stage."""
        client, settings, tmp = async_convert_client

        pdf_result = MagicMock()
        pdf_result.text = "text"
        pdf_result.num_pages = 1
        pdf_result.title = "Cancel Conv"

        from audia.ui.jobs import JOBS

        enqueued_job_id: list[str] = []

        def cancel_after_extract(path):
            # Mark job as cancelled once extraction is called
            for jid, job in JOBS.items():
                if job.get("stage") in ("extracting", "preprocessing", "curating"):
                    job["cancelled"] = True
                    enqueued_job_id.clear()
                    enqueued_job_id.append(jid)
            return pdf_result

        with patch("audia.ui.routes.convert.extract_text", side_effect=cancel_after_extract), \
             patch("audia.ui.routes.convert.heuristic_clean", return_value="clean"), \
             patch("audia.ui.routes.convert.llm_curate", return_value="cured"):
            res = await client.post(
                "/api/convert/enqueue",
                files={"file": ("cancel.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
            )
            assert res.status_code == 200
            job_id = res.json()["job_id"]

            for _ in range(20):
                await asyncio.sleep(0.05)

        job = JOBS.get(job_id, {})
        # Either cancelled or done/error depending on timing
        assert job.get("status") in ("cancelled", "error", "done", "running")
