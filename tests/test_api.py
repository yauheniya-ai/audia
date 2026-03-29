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

    with patch("audia.config.Settings.data_dir", new_callable=lambda: property(lambda self: tmp)):
        from audia.ui.app import create_app
        from audia.storage import init_db

        app = create_app()
        init_db()
        return TestClient(app)


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
        with patch("audia.ui.routes.convert.run_pipeline", return_value=mock_state):
            res = client.post(
                "/api/convert/upload",
                files={"file": ("paper.pdf", fake_pdf, "application/pdf")},
            )

        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert "download_url" in body
