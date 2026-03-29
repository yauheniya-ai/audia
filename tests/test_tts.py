"""Tests for the TTS helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSplitTts:
    """Tests for tts._split (sentence-aware splitting)."""

    def test_short_text_not_split(self):
        from audia.agents.tts import _split
        text = "Hello world."
        assert _split(text, 100) == [text]

    def test_splits_at_sentence_boundary(self):
        from audia.agents.tts import _split
        text = "First sentence. " + "Second sentence. " * 20
        chunks = _split(text, 80)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 200  # generous — last chunk may be larger

    def test_oversized_sentence_split_by_word(self):
        from audia.agents.tts import _split
        # One very long "sentence" with no punctuation
        text = ("word " * 100).strip()
        chunks = _split(text, 50)
        assert len(chunks) > 1
        assert all(chunks)

    def test_empty_string(self):
        from audia.agents.tts import _split
        result = _split("", 100)
        assert result == [""]


class TestConcatMp3:
    def test_concatenates_bytes(self, tmp_path):
        from audia.agents.tts import _concat_mp3

        p1 = tmp_path / "a.mp3"
        p2 = tmp_path / "b.mp3"
        p1.write_bytes(b"AAA")
        p2.write_bytes(b"BBB")

        dest = tmp_path / "out.mp3"
        result = _concat_mp3([p1, p2], dest)

        assert result == dest
        assert dest.read_bytes() == b"AAABBB"


class TestRunAsync:
    def test_runs_coroutine_in_sync_context(self):
        from audia.agents.tts import _run_async
        import asyncio

        called = []

        async def coro():
            called.append(True)

        _run_async(coro())
        assert called == [True]

    def test_runs_inside_existing_event_loop(self):
        """Simulate FastAPI: _run_async called from within a running loop."""
        from audia.agents.tts import _run_async
        import asyncio

        results = []

        async def outer():
            async def inner():
                results.append("done")

            # _run_async must handle the already-running loop
            _run_async(inner())

        asyncio.run(outer())
        assert results == ["done"]


class TestSynthesize:
    def test_unknown_backend_raises(self, tmp_path):
        from audia.config import Settings
        from audia.agents.tts import synthesize

        cfg = Settings(data_dir=tmp_path, llm_provider="openai")
        cfg.__dict__["tts_backend"] = "unknown"

        with pytest.raises(ValueError, match="Unknown TTS backend"):
            synthesize("Hello.", output_dir=tmp_path, settings=cfg)

    def test_edge_tts_called(self, tmp_path):
        from audia.config import Settings
        from audia.agents.tts import synthesize

        cfg = Settings(
            data_dir=tmp_path,
            llm_provider="openai",
            tts_backend="edge-tts",
            tts_voice="en-US-AriaNeural",
            tts_chunk_chars=10_000,
        )

        fake_mp3 = tmp_path / "output.mp3"

        with patch("audia.agents.tts._edge_tts", return_value=fake_mp3) as mock_edge:
            result = synthesize("Hello world.", output_dir=tmp_path,
                                filename="output", settings=cfg)

        mock_edge.assert_called_once()
        assert result == fake_mp3

    def test_missing_edge_tts_package_raises(self, tmp_path):
        from audia.config import Settings
        from audia.agents.tts import synthesize

        cfg = Settings(data_dir=tmp_path, llm_provider="openai", tts_backend="edge-tts")

        with patch.dict("sys.modules", {"edge_tts": None}):
            with pytest.raises(ImportError, match="edge-tts"):
                synthesize("Hello.", output_dir=tmp_path, settings=cfg)

    def test_kokoro_backend_dispatched(self, tmp_path):
        from audia.config import Settings
        from audia.agents.tts import synthesize

        cfg = Settings(
            data_dir=tmp_path,
            llm_provider="openai",
            tts_backend="kokoro",
        )
        fake_wav = tmp_path / "output.wav"

        with patch("audia.agents.tts._kokoro_tts", return_value=fake_wav) as mock_k:
            result = synthesize("Hello world.", output_dir=tmp_path,
                                filename="output", settings=cfg)

        mock_k.assert_called_once()
        assert result == fake_wav

    def test_openai_backend_dispatched(self, tmp_path):
        from audia.config import Settings
        from audia.agents.tts import synthesize

        cfg = Settings(
            data_dir=tmp_path,
            llm_provider="openai",
            openai_api_key="sk-test",
            tts_backend="openai",
        )
        fake_mp3 = tmp_path / "output.mp3"

        with patch("audia.agents.tts._openai_tts", return_value=fake_mp3) as mock_o:
            result = synthesize("Hello world.", output_dir=tmp_path,
                                filename="output", settings=cfg)

        mock_o.assert_called_once()
        assert result == fake_mp3


class TestKokoroTts:
    """Direct tests for the kokoro TTS backend."""

    def test_missing_kokoro_raises(self, tmp_path):
        from audia.config import Settings
        from audia.agents.tts import _kokoro_tts

        cfg = Settings(data_dir=tmp_path, llm_provider="openai",
                       tts_backend="kokoro", tts_voice="af_bella")
        with patch.dict("sys.modules", {"kokoro": None, "soundfile": None, "numpy": None}):
            with pytest.raises(ImportError, match="Kokoro"):
                _kokoro_tts("Hello.", tmp_path, "stem", cfg)

    def test_kokoro_writes_wav(self, tmp_path):
        from audia.config import Settings
        from audia.agents.tts import _kokoro_tts

        cfg = Settings(data_dir=tmp_path, llm_provider="openai",
                       tts_backend="kokoro", tts_voice="af_bella",
                       tts_chunk_chars=10_000)

        # Mock the kokoro, soundfile, numpy modules
        fake_audio = MagicMock()
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = [("", "", fake_audio)]

        mock_kokoro = MagicMock()
        mock_kokoro.KPipeline.return_value = mock_pipeline.return_value
        mock_kokoro.KPipeline = mock_pipeline

        mock_sf = MagicMock()
        mock_np = MagicMock()
        mock_np.concatenate.return_value = MagicMock()

        # Create the KPipeline to return audio chunks
        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.return_value = [("", "", fake_audio)]
        mock_kokoro.KPipeline.return_value = mock_pipeline_instance

        with patch.dict("sys.modules", {"kokoro": mock_kokoro, "soundfile": mock_sf, "numpy": mock_np}):
            result = _kokoro_tts("Hello world.", tmp_path, "stem", cfg)

        mock_sf.write.assert_called_once()
        assert result.suffix == ".wav"


class TestOpenAITts:
    """Direct tests for the OpenAI TTS backend."""

    def test_missing_openai_raises(self, tmp_path):
        from audia.config import Settings
        from audia.agents.tts import _openai_tts

        cfg = Settings(data_dir=tmp_path, llm_provider="openai",
                       openai_api_key="sk-test", tts_backend="openai",
                       tts_voice="alloy")
        with patch.dict("sys.modules", {"openai": None}):
            with pytest.raises(ImportError, match="OpenAI TTS"):
                _openai_tts("Hello.", tmp_path, "stem", cfg)

    def test_openai_single_chunk(self, tmp_path):
        from audia.config import Settings
        from audia.agents.tts import _openai_tts

        cfg = Settings(data_dir=tmp_path, llm_provider="openai",
                       openai_api_key="sk-test", tts_backend="openai",
                       tts_voice="alloy", tts_chunk_chars=10_000)

        mock_response = MagicMock()

        def fake_stream_to_file(path):
            Path(path).write_bytes(b"AUDIO_DATA")

        mock_response.stream_to_file.side_effect = fake_stream_to_file

        mock_openai_mod = MagicMock()
        mock_client = MagicMock()
        mock_openai_mod.OpenAI.return_value = mock_client
        mock_client.audio.speech.create.return_value = mock_response

        with patch.dict("sys.modules", {"openai": mock_openai_mod}):
            result = _openai_tts("Hello world.", tmp_path, "stem", cfg)

        mock_client.audio.speech.create.assert_called_once()
        assert result.suffix == ".mp3"
        assert result.exists()

    def test_openai_multi_chunk_concatenated(self, tmp_path):
        from audia.config import Settings
        from audia.agents.tts import _openai_tts

        # _openai_tts uses hardcoded 4096, so send >4096 chars
        cfg = Settings(data_dir=tmp_path, llm_provider="openai",
                       openai_api_key="sk-test", tts_backend="openai",
                       tts_voice="alloy", tts_chunk_chars=10_000)

        call_count = [0]

        def fake_stream_to_file(path):
            call_count[0] += 1
            Path(path).write_bytes(b"PART")

        mock_response = MagicMock()
        mock_response.stream_to_file.side_effect = fake_stream_to_file

        mock_openai_mod = MagicMock()
        mock_client = MagicMock()
        mock_openai_mod.OpenAI.return_value = mock_client
        mock_client.audio.speech.create.return_value = mock_response

        # Build text >4096 chars that splits cleanly at sentence boundaries
        long_text = "This is a sentence. " * 250  # ~5000 chars

        with patch.dict("sys.modules", {"openai": mock_openai_mod}):
            result = _openai_tts(long_text, tmp_path, "stem2", cfg)

        assert call_count[0] > 1
        assert result.suffix == ".mp3"


class TestEdgeTtsInternal:
    """Test the internal _edge_tts with mocked edge_tts module."""

    def test_edge_tts_single_chunk(self, tmp_path):
        from audia.config import Settings
        from audia.agents.tts import _edge_tts

        cfg = Settings(data_dir=tmp_path, llm_provider="openai",
                       tts_backend="edge-tts", tts_voice="en-US-AriaNeural",
                       tts_chunk_chars=10_000)

        async def fake_save(path):
            Path(path).write_bytes(b"MP3_DATA")

        mock_communicate = MagicMock()
        mock_communicate.save = fake_save

        mock_edge = MagicMock()
        mock_edge.Communicate.return_value = mock_communicate

        with patch("audia.agents.tts._run_async") as mock_run:
            def side_effect(coro):
                import asyncio
                asyncio.run(coro)
            mock_run.side_effect = side_effect
            # Actually use the edge_tts mock inline
            with patch.dict("sys.modules", {"edge_tts": mock_edge}):
                result = _edge_tts("Hello world.", tmp_path, "stem", cfg)

        assert result.suffix == ".mp3"
