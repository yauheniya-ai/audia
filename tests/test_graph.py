"""Tests for the LangGraph pipeline (graph.py)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────── helper nodes (unit)

class TestNodeExtractText:
    def test_success(self, tmp_path):
        from audia.agents.graph import node_extract_text

        fake_result = MagicMock()
        fake_result.text = "Abstract. Introduction."
        fake_result.num_pages = 5
        fake_result.title = "My Paper"

        with patch("audia.agents.graph.extract_text", return_value=fake_result):
            out = node_extract_text({"pdf_path": str(tmp_path / "paper.pdf")})

        assert out["raw_text"] == "Abstract. Introduction."
        assert out["num_pages"] == 5
        assert out["title"] == "My Paper"
        assert out["error"] is None

    def test_propagates_error(self, tmp_path):
        from audia.agents.graph import node_extract_text

        with patch("audia.agents.graph.extract_text", side_effect=FileNotFoundError("no file")):
            out = node_extract_text({"pdf_path": "/nonexistent.pdf"})

        assert "error" in out
        assert out["error"] is not None


class TestNodePreprocess:
    def test_skipped_on_error(self):
        from audia.agents.graph import node_preprocess
        out = node_preprocess({"error": "something went wrong", "raw_text": "text"})
        assert out == {}

    def test_cleans_text(self):
        from audia.agents.graph import node_preprocess
        state = {"raw_text": "Neural networks [1] are powerful [2,3]."}
        out = node_preprocess(state)
        assert "[1]" not in out["preprocessed_text"]
        assert "Neural networks" in out["preprocessed_text"]


class TestNodeCurate:
    def test_skipped_on_error(self):
        from audia.agents.graph import node_curate
        out = node_curate({"error": "boom"})
        assert out == {}

    def test_calls_llm_curate(self, tmp_path):
        from audia.agents.graph import node_curate
        from audia.config import Settings

        cfg = Settings(data_dir=tmp_path, llm_provider="openai", openai_api_key="sk-x")

        with patch("audia.agents.graph.get_settings", return_value=cfg), \
             patch("audia.agents.graph.llm_curate", return_value="Curated text.") as mock_curate:
            out = node_curate({"preprocessed_text": "Raw text."})

        mock_curate.assert_called_once()
        assert out["cleaned_text"] == "Curated text."

    def test_error_on_llm_failure(self, tmp_path):
        from audia.agents.graph import node_curate
        from audia.config import Settings

        cfg = Settings(data_dir=tmp_path, llm_provider="openai", openai_api_key="sk-x")

        with patch("audia.agents.graph.get_settings", return_value=cfg), \
             patch("audia.agents.graph.llm_curate", side_effect=RuntimeError("API key missing")):
            out = node_curate({"preprocessed_text": "text"})

        assert "error" in out
        assert "API key missing" in out["error"]


class TestNodeSynthesizeAudio:
    def test_skipped_on_error(self):
        from audia.agents.graph import node_synthesize_audio
        out = node_synthesize_audio({"error": "err"})
        assert out == {}

    def test_calls_synthesize(self, tmp_path):
        from audia.agents.graph import node_synthesize_audio
        from audia.config import Settings

        cfg = Settings(data_dir=tmp_path, llm_provider="openai",
                       tts_backend="edge-tts", tts_voice="en-US-AriaNeural")
        fake_audio = tmp_path / "out.mp3"
        fake_audio.write_bytes(b"AUDIO")

        with patch("audia.agents.graph.get_settings", return_value=cfg), \
             patch("audia.agents.graph.synthesize", return_value=fake_audio):
            out = node_synthesize_audio({
                "cleaned_text": "Hello world.",
                "output_dir": str(tmp_path),
                "run_id": "test_20260329_000000",
                "title": "Test",
            })

        assert out["audio_path"] == str(fake_audio)
        assert out["audio_filename"] == "out.mp3"


# ─────────────────────────────────────────────── helpers

class TestSafeStem:
    def test_normal_title(self):
        from audia.agents.graph import _safe_stem
        assert _safe_stem("Attention Is All You Need") == "Attention_Is_All_You_Need"

    def test_strips_special_chars(self):
        from audia.agents.graph import _safe_stem
        assert "!" not in _safe_stem("Hello! World?")

    def test_truncates_long_title(self):
        from audia.agents.graph import _safe_stem
        long = "word " * 30
        assert len(_safe_stem(long)) <= 60

    def test_empty_title_fallback(self):
        from audia.agents.graph import _safe_stem
        assert _safe_stem("") == "audia_output"


class TestSaveDebugTexts:
    def test_writes_files(self, tmp_path):
        from audia.agents.graph import _save_debug_texts
        from audia.config import Settings

        cfg = Settings(data_dir=tmp_path, llm_provider="openai")
        state = {
            "raw_text": "raw",
            "preprocessed_text": "pre",
            "cleaned_text": "curated",
        }

        _save_debug_texts("my_paper_20260329_120000", state, cfg)

        run_dir = cfg.debug_dir / "my_paper_20260329_120000"
        assert (run_dir / "1_raw.txt").read_text() == "raw"
        assert (run_dir / "2_preprocessed.txt").read_text() == "pre"
        assert (run_dir / "3_curated.txt").read_text() == "curated"

    def test_skips_missing_stages(self, tmp_path):
        from audia.agents.graph import _save_debug_texts
        from audia.config import Settings

        cfg = Settings(data_dir=tmp_path, llm_provider="openai")
        state = {"raw_text": "raw"}  # no preprocessed or cleaned

        _save_debug_texts("partial_20260329_120001", state, cfg)

        run_dir = cfg.debug_dir / "partial_20260329_120001"
        assert (run_dir / "1_raw.txt").exists()
        assert not (run_dir / "2_preprocessed.txt").exists()
        assert not (run_dir / "3_curated.txt").exists()


# ─────────────────────────────────────────────── run_pipeline integration

class TestRunPipeline:
    def test_returns_state_with_audio(self, tmp_path):
        from audia.agents.graph import run_pipeline
        from audia.config import Settings

        cfg = Settings(data_dir=tmp_path, llm_provider="openai", openai_api_key="sk-x")
        fake_audio = tmp_path / "out.mp3"
        fake_audio.write_bytes(b"MP3")

        fake_extract = MagicMock(text="body text", num_pages=2, title="My Paper")

        with patch("audia.agents.graph.get_settings", return_value=cfg), \
             patch("audia.agents.graph.extract_text", return_value=fake_extract), \
             patch("audia.agents.graph.llm_curate", return_value="Curated."), \
             patch("audia.agents.graph.synthesize", return_value=fake_audio):
            state = run_pipeline(tmp_path / "paper.pdf", output_dir=tmp_path)

        assert state.get("audio_path") == str(fake_audio)
        assert state.get("title") == "My Paper"

    def test_run_id_format(self, tmp_path):
        from audia.agents.graph import run_pipeline
        from audia.config import Settings
        import re

        cfg = Settings(data_dir=tmp_path, llm_provider="openai", openai_api_key="sk-x")
        fake_audio = tmp_path / "out.mp3"
        fake_audio.write_bytes(b"MP3")
        fake_extract = MagicMock(text="t", num_pages=1, title="T")

        with patch("audia.agents.graph.get_settings", return_value=cfg), \
             patch("audia.agents.graph.extract_text", return_value=fake_extract), \
             patch("audia.agents.graph.llm_curate", return_value="C."), \
             patch("audia.agents.graph.synthesize", return_value=fake_audio):
            state = run_pipeline(tmp_path / "my_paper.pdf", output_dir=tmp_path)

        run_id = state.get("run_id", "")
        assert re.match(r"my_paper_\d{8}_\d{6}$", run_id), f"Unexpected run_id: {run_id!r}"
