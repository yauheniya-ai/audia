"""Tests for the Typer CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from audia.cli.app import app

runner = CliRunner()


class TestVersionFlag:
    def test_version(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "audia" in result.output
        assert "0.1.0" in result.output


class TestInfoCommand:
    def test_info_runs(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AUDIA_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("AUDIA_LLM_PROVIDER", "openai")
        result = runner.invoke(app, ["info"])
        assert result.exit_code == 0
        assert "openai" in result.output.lower() or "LLM" in result.output


class TestConvertCommand:
    def test_missing_file_errors(self, tmp_path):
        result = runner.invoke(app, ["convert", str(tmp_path / "nonexistent.pdf")])
        assert result.exit_code != 0

    def test_existing_file_accepted_by_typer(self, tmp_path):
        """Typer `exists=True` only checks the file exists; extension is not validated by the CLI."""
        txt = tmp_path / "doc.txt"
        txt.write_text("hello")
        # The CLI will accept it and attempt to run the pipeline – we patch that out.
        mock_state = {"error": "not a pdf", "audio_path": None}
        with patch("audia.agents.graph.run_pipeline", return_value=mock_state), \
             patch("audia.storage.init_db"), \
             patch("audia.config.get_settings") as mock_cfg:
            mock_cfg.return_value = MagicMock(tts_voice="en-US-AriaNeural", tts_backend="edge-tts")
            result = runner.invoke(app, ["convert", str(txt)])
        # Error reported (non-zero) because pipeline returned an error
        assert result.exit_code != 0

    def test_successful_convert(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AUDIA_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("AUDIA_LLM_PROVIDER", "openai")
        monkeypatch.setenv("AUDIA_OPENAI_API_KEY", "sk-test")

        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%%EOF")
        fake_audio = tmp_path / "paper_20260329_120000.mp3"
        fake_audio.write_bytes(b"AUDIO")

        mock_state = {
            "audio_path": str(fake_audio),
            "audio_filename": fake_audio.name,
            "title": "Test Paper",
            "num_pages": 2,
            "tts_backend": "edge-tts",
            "tts_voice": "en-US-AriaNeural",
            "error": None,
        }

        # The imports happen inside the function body, so patch at the source modules.
        mock_session_ctx = MagicMock()
        mock_session_ctx.__enter__ = MagicMock(return_value=MagicMock())
        mock_session_ctx.__exit__ = MagicMock(return_value=False)

        with patch("audia.agents.graph.run_pipeline", return_value=mock_state), \
             patch("audia.storage.database.init_db"), \
             patch("audia.storage.database.get_session", return_value=mock_session_ctx):
            result = runner.invoke(app, ["convert", str(pdf)])

        assert result.exit_code == 0
        assert "Audio saved" in result.output or str(fake_audio) in result.output

    def test_pipeline_error_reported(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AUDIA_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("AUDIA_LLM_PROVIDER", "openai")

        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%%EOF")

        mock_state = {"error": "PDF extraction failed", "audio_path": None}

        with patch("audia.agents.graph.run_pipeline", return_value=mock_state), \
             patch("audia.storage.database.init_db"):
            result = runner.invoke(app, ["convert", str(pdf)])

        assert result.exit_code != 0
        assert "Error" in result.output or "error" in result.output


class TestServeCommand:
    def test_serve_calls_uvicorn(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AUDIA_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("AUDIA_LLM_PROVIDER", "openai")
        # `uvicorn` is imported inside serve(), so patch at source
        with patch("uvicorn.run") as mock_run, \
             patch("audia.storage.database.init_db"):
            result = runner.invoke(app, ["serve"])
        mock_run.assert_called_once()

    def test_serve_custom_host_port(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AUDIA_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("AUDIA_LLM_PROVIDER", "openai")
        with patch("uvicorn.run") as mock_run, \
             patch("audia.storage.database.init_db"):
            result = runner.invoke(app, ["serve", "--host", "0.0.0.0", "--port", "9000", "--no-open"])
        args, kwargs = mock_run.call_args
        assert kwargs.get("host") == "0.0.0.0" or args[1] == "0.0.0.0"


class TestResearchCommand:
    def test_research_no_results(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AUDIA_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("AUDIA_LLM_PROVIDER", "openai")
        with patch("audia.agents.research.ArxivSearcher") as mock_cls, \
             patch("audia.storage.database.init_db"):
            mock_cls.return_value.search.return_value = []
            result = runner.invoke(app, ["research", "quantum computing"])
        assert result.exit_code == 0
        assert "No results" in result.output

    def test_research_lists_papers(self, tmp_path, monkeypatch):
        from audia.agents.research import ArxivPaper

        monkeypatch.setenv("AUDIA_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("AUDIA_LLM_PROVIDER", "openai")

        papers = [
            ArxivPaper(
                arxiv_id=f"2301.0000{i}v1",
                title=f"Paper {i}",
                authors=["Alice"],
                abstract="Abstract",
                pdf_url="",
                published="2023-01-01",
            )
            for i in range(3)
        ]
        with patch("audia.agents.research.ArxivSearcher") as mock_cls, \
             patch("audia.storage.database.init_db"):
            mock_cls.return_value.search.return_value = papers
            # 'q' to quit the prompt
            result = runner.invoke(app, ["research", "neural nets"], input="q\n")
        assert result.exit_code == 0

    def test_research_auto_convert(self, tmp_path, monkeypatch):
        """--convert flag runs pipeline without prompting."""
        from audia.agents.research import ArxivPaper

        monkeypatch.setenv("AUDIA_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("AUDIA_LLM_PROVIDER", "openai")
        monkeypatch.setenv("AUDIA_OPENAI_API_KEY", "sk-test")

        paper = ArxivPaper(
            arxiv_id="2301.00001v1",
            title="Auto Paper",
            authors=["Alice"],
            abstract="Abstract",
            pdf_url="",
            published="2023-01-01",
        )
        fake_pdf = tmp_path / "auto.pdf"
        fake_pdf.write_bytes(b"%PDF")
        fake_audio = tmp_path / "auto.mp3"
        fake_audio.write_bytes(b"AUDIO")

        mock_state = {
            "audio_path": str(fake_audio),
            "audio_filename": "auto.mp3",
            "tts_backend": "edge-tts",
            "tts_voice": "en-US-AriaNeural",
            "error": None,
        }

        mock_session_ctx = MagicMock()
        mock_session_ctx.__enter__ = MagicMock(return_value=MagicMock())
        mock_session_ctx.__exit__ = MagicMock(return_value=False)

        with patch("audia.agents.research.ArxivSearcher") as mock_cls, \
             patch("audia.storage.database.init_db"), \
             patch("audia.agents.graph.run_pipeline", return_value=mock_state), \
             patch("audia.storage.database.get_session", return_value=mock_session_ctx):
            mock_cls.return_value.search.return_value = [paper]
            mock_cls.return_value.download_pdf.return_value = fake_pdf
            result = runner.invoke(app, ["research", "neural nets", "--convert"])

        assert result.exit_code == 0
        assert "Auto Paper" in result.output or "Done" in result.output


class TestInfoCommandExtended:
    def test_info_shows_lLm_provider(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AUDIA_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("AUDIA_LLM_PROVIDER", "openai")
        monkeypatch.setenv("AUDIA_OPENAI_API_KEY", "sk-test")
        result = runner.invoke(app, ["info"])
        assert result.exit_code == 0
        assert "openai" in result.output.lower()

    def test_info_shows_server(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AUDIA_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("AUDIA_LLM_PROVIDER", "openai")
        result = runner.invoke(app, ["info"])
        assert "http://" in result.output


class TestConvertVoiceAndOpen:
    """Test voice override and open_after options of convert command."""

    def test_convert_with_voice_override(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AUDIA_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("AUDIA_LLM_PROVIDER", "openai")
        monkeypatch.setenv("AUDIA_OPENAI_API_KEY", "sk-test")

        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF")
        fake_audio = tmp_path / "out.mp3"
        fake_audio.write_bytes(b"AUDIO")

        mock_state = {
            "audio_path": str(fake_audio),
            "audio_filename": "out.mp3",
            "title": "Paper",
            "num_pages": 1,
            "tts_backend": "edge-tts",
            "tts_voice": "en-US-GuyNeural",
            "error": None,
        }

        mock_session_ctx = MagicMock()
        mock_session_ctx.__enter__ = MagicMock(return_value=MagicMock())
        mock_session_ctx.__exit__ = MagicMock(return_value=False)

        with patch("audia.agents.graph.run_pipeline", return_value=mock_state), \
             patch("audia.storage.database.init_db"), \
             patch("audia.storage.database.get_session", return_value=mock_session_ctx):
            result = runner.invoke(app, ["convert", str(pdf), "--voice", "en-US-GuyNeural"])

        assert result.exit_code == 0

    def test_convert_with_open_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AUDIA_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("AUDIA_LLM_PROVIDER", "openai")
        monkeypatch.setenv("AUDIA_OPENAI_API_KEY", "sk-test")

        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF")
        fake_audio = tmp_path / "out.mp3"
        fake_audio.write_bytes(b"AUDIO")

        mock_state = {
            "audio_path": str(fake_audio),
            "audio_filename": "out.mp3",
            "title": "Paper",
            "num_pages": 1,
            "tts_backend": "edge-tts",
            "tts_voice": "en-US-AriaNeural",
            "error": None,
        }

        mock_session_ctx = MagicMock()
        mock_session_ctx.__enter__ = MagicMock(return_value=MagicMock())
        mock_session_ctx.__exit__ = MagicMock(return_value=False)

        with patch("audia.agents.graph.run_pipeline", return_value=mock_state), \
             patch("audia.storage.database.init_db"), \
             patch("audia.storage.database.get_session", return_value=mock_session_ctx), \
             patch("audia.cli.app._open_file") as mock_open:
            result = runner.invoke(app, ["convert", str(pdf), "--open"])

        assert result.exit_code == 0
        mock_open.assert_called_once_with(str(fake_audio))


class TestOpenFileHelper:
    """Direct tests for the _open_file helper."""

    def test_darwin(self, tmp_path):
        from audia.cli.app import _open_file

        with patch("platform.system", return_value="Darwin"), \
             patch("subprocess.call") as mock_call:
            _open_file(str(tmp_path))

        mock_call.assert_called_once_with(["open", str(tmp_path)])

    def test_linux(self, tmp_path):
        from audia.cli.app import _open_file

        with patch("platform.system", return_value="Linux"), \
             patch("subprocess.call") as mock_call:
            _open_file(str(tmp_path))

        mock_call.assert_called_once_with(["xdg-open", str(tmp_path)])

    def test_windows(self, tmp_path):
        from audia.cli.app import _open_file

        with patch("platform.system", return_value="Windows"), \
             patch("os.startfile", create=True) as mock_sf:
            _open_file(str(tmp_path))

        mock_sf.assert_called_once_with(str(tmp_path))


class TestListenCommand:
    def test_listen_invokes_stt_and_research(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AUDIA_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("AUDIA_LLM_PROVIDER", "openai")

        with patch("audia.agents.stt.record_and_transcribe", return_value="neural nets"), \
             patch("audia.agents.stt.distill_search_query", return_value="neural networks"), \
             patch("audia.agents.research.ArxivSearcher") as mock_cls, \
             patch("audia.storage.database.init_db"):
            mock_cls.return_value.search.return_value = []
            result = runner.invoke(app, ["listen"], input="y\n")

        assert result.exit_code == 0
        assert "Heard" in result.output


class TestResearchCommandEdgeCases:
    """Additional research command coverage."""

    def test_research_select_all(self, tmp_path, monkeypatch):
        from audia.agents.research import ArxivPaper

        monkeypatch.setenv("AUDIA_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("AUDIA_LLM_PROVIDER", "openai")
        monkeypatch.setenv("AUDIA_OPENAI_API_KEY", "sk-test")

        paper = ArxivPaper(
            arxiv_id="2301.00005v1",
            title="All Paper",
            authors=["Alice"],
            abstract="Abstract",
            pdf_url="",
            published="2023-01-01",
        )
        fake_pdf = tmp_path / "allpaper.pdf"
        fake_pdf.write_bytes(b"%PDF")
        fake_audio = tmp_path / "allpaper.mp3"
        fake_audio.write_bytes(b"AUDIO")

        mock_state = {
            "audio_path": str(fake_audio),
            "audio_filename": "allpaper.mp3",
            "tts_backend": "edge-tts",
            "tts_voice": "en-US-AriaNeural",
            "error": None,
        }

        mock_session_ctx = MagicMock()
        mock_session_ctx.__enter__ = MagicMock(return_value=MagicMock())
        mock_session_ctx.__exit__ = MagicMock(return_value=False)

        with patch("audia.agents.research.ArxivSearcher") as mock_cls, \
             patch("audia.storage.database.init_db"), \
             patch("audia.agents.graph.run_pipeline", return_value=mock_state), \
             patch("audia.storage.database.get_session", return_value=mock_session_ctx):
            mock_cls.return_value.search.return_value = [paper]
            mock_cls.return_value.download_pdf.return_value = fake_pdf
            result = runner.invoke(app, ["research", "neural nets"], input="all\n")

        assert result.exit_code == 0

    def test_research_download_error(self, tmp_path, monkeypatch):
        from audia.agents.research import ArxivPaper

        monkeypatch.setenv("AUDIA_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("AUDIA_LLM_PROVIDER", "openai")

        paper = ArxivPaper(
            arxiv_id="2301.00006v1",
            title="Fail Paper",
            authors=[],
            abstract="",
            pdf_url="",
            published="2023-01-01",
        )

        with patch("audia.agents.research.ArxivSearcher") as mock_cls, \
             patch("audia.storage.database.init_db"):
            mock_cls.return_value.search.return_value = [paper]
            mock_cls.return_value.download_pdf.side_effect = IOError("network down")
            result = runner.invoke(app, ["research", "neural nets", "--convert"],
                                   input="\n")  # skip manual-path prompt

        assert result.exit_code == 0
        assert "Download failed" in result.output

    def test_research_no_valid_selection(self, tmp_path, monkeypatch):
        from audia.agents.research import ArxivPaper

        monkeypatch.setenv("AUDIA_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("AUDIA_LLM_PROVIDER", "openai")

        paper = ArxivPaper(
            arxiv_id="2301.00007v1",
            title="Select Paper",
            authors=[],
            abstract="",
            pdf_url="",
            published="2023-01-01",
        )

        with patch("audia.agents.research.ArxivSearcher") as mock_cls, \
             patch("audia.storage.database.init_db"):
            mock_cls.return_value.search.return_value = [paper]
            # Input empty selection (becomes "0": maps to nothing valid if index 0 is 1-indexed)
            result = runner.invoke(app, ["research", "neural nets"], input="99\n")

        assert result.exit_code == 0
        assert "No papers selected" in result.output
