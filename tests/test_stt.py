"""Tests for the STT module (audia.agents.stt)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────── _ensure_stt_deps

class TestEnsureSttDeps:
    def test_raises_when_both_missing(self):
        from audia.agents.stt import _ensure_stt_deps
        with patch.dict("sys.modules", {"sounddevice": None, "faster_whisper": None}):
            with pytest.raises(ImportError, match=r"pip install audia\[stt\]"):
                _ensure_stt_deps()

    def test_raises_when_sounddevice_missing(self):
        from audia.agents.stt import _ensure_stt_deps
        fake_fw = MagicMock()
        with patch.dict("sys.modules", {"sounddevice": None, "faster_whisper": fake_fw}):
            with pytest.raises(ImportError, match="sounddevice"):
                _ensure_stt_deps()

    def test_raises_when_faster_whisper_missing(self):
        from audia.agents.stt import _ensure_stt_deps
        fake_sd = MagicMock()
        with patch.dict("sys.modules", {"sounddevice": fake_sd, "faster_whisper": None}):
            with pytest.raises(ImportError, match="faster-whisper"):
                _ensure_stt_deps()

    def test_passes_when_both_present(self):
        from audia.agents.stt import _ensure_stt_deps
        fake_sd = MagicMock()
        fake_fw = MagicMock()
        with patch.dict("sys.modules", {"sounddevice": fake_sd, "faster_whisper": fake_fw}):
            # Must not raise
            _ensure_stt_deps()


# ─────────────────────────────────────────────── transcribe_file

class TestTranscribeFile:
    def test_transcribes_audio_file(self, tmp_path):
        wav = tmp_path / "test.wav"
        wav.write_bytes(b"FAKE_WAV")

        fake_seg = MagicMock()
        fake_seg.text = " Hello world "
        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([fake_seg], MagicMock())

        fake_fw = MagicMock()
        fake_fw.WhisperModel.return_value = fake_model
        fake_sd = MagicMock()

        with patch.dict("sys.modules", {"sounddevice": fake_sd, "faster_whisper": fake_fw}):
            from audia.agents.stt import transcribe_file
            result = transcribe_file(str(wav), model_size="base", device="cpu")

        assert result == "Hello world"

    def test_multiple_segments_joined(self, tmp_path):
        wav = tmp_path / "multi.wav"
        wav.write_bytes(b"FAKE")

        seg1, seg2 = MagicMock(), MagicMock()
        seg1.text = " First "
        seg2.text = " Second "
        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([seg1, seg2], MagicMock())

        fake_fw = MagicMock()
        fake_fw.WhisperModel.return_value = fake_model

        with patch.dict("sys.modules", {"sounddevice": MagicMock(), "faster_whisper": fake_fw}):
            from audia.agents.stt import transcribe_file
            result = transcribe_file(str(wav))

        assert result == "First Second"


# ─────────────────────────────────────────────── _transcribe_array

class TestTranscribeArray:
    def test_transcribes_numpy_array(self):
        import numpy as np

        audio = np.zeros(16000, dtype="float32")

        fake_seg = MagicMock()
        fake_seg.text = " Spoken words "
        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([fake_seg], MagicMock())

        fake_fw = MagicMock()
        fake_fw.WhisperModel.return_value = fake_model
        fake_sf = MagicMock()

        with patch.dict("sys.modules", {
            "sounddevice": MagicMock(),
            "faster_whisper": fake_fw,
            "soundfile": fake_sf,
        }):
            from audia.agents.stt import _transcribe_array
            result = _transcribe_array(audio, 16000, "base", "cpu")

        assert result == "Spoken words"
        assert fake_sf.write.called

    def test_temp_file_cleaned_up(self):
        import numpy as np

        audio = np.zeros(8000, dtype="float32")

        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([], MagicMock())
        fake_fw = MagicMock()
        fake_fw.WhisperModel.return_value = fake_model
        fake_sf = MagicMock()

        with patch.dict("sys.modules", {
            "sounddevice": MagicMock(),
            "faster_whisper": fake_fw,
            "soundfile": fake_sf,
        }):
            from audia.agents.stt import _transcribe_array
            _transcribe_array(audio, 16000, "base", "cpu")

        # sf.write called with a tmp path argument
        assert fake_sf.write.call_count == 1


# ─────────────────────────────────────────────── record_and_transcribe

class TestRecordAndTranscribe:
    def _make_mocks(self, seg_text=" Recording result "):
        import numpy as np

        fake_audio = np.zeros((16000, 1), dtype="float32")
        fake_sd = MagicMock()
        fake_sd.rec.return_value = fake_audio

        fake_seg = MagicMock()
        fake_seg.text = seg_text
        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([fake_seg], MagicMock())
        fake_fw = MagicMock()
        fake_fw.WhisperModel.return_value = fake_model
        fake_sf = MagicMock()

        return fake_sd, fake_fw, fake_sf

    def test_records_and_transcribes(self):
        fake_sd, fake_fw, fake_sf = self._make_mocks()
        with patch.dict("sys.modules", {
            "sounddevice": fake_sd,
            "faster_whisper": fake_fw,
            "soundfile": fake_sf,
        }):
            from audia.agents.stt import record_and_transcribe
            result = record_and_transcribe(seconds=1)

        assert isinstance(result, str)
        assert fake_sd.rec.called
        assert fake_sd.wait.called

    def test_handles_keyboard_interrupt(self):
        fake_sd, fake_fw, fake_sf = self._make_mocks(" Interrupted ")
        fake_sd.wait.side_effect = KeyboardInterrupt()

        with patch.dict("sys.modules", {
            "sounddevice": fake_sd,
            "faster_whisper": fake_fw,
            "soundfile": fake_sf,
        }):
            from audia.agents.stt import record_and_transcribe
            result = record_and_transcribe(seconds=1)

        fake_sd.stop.assert_called_once()
        assert isinstance(result, str)


# ─────────────────────────────────────────────── distill_search_query

class TestDistillSearchQuery:
    def test_distills_and_strips_period(self, tmp_path):
        from audia.config import Settings

        cfg = Settings(data_dir=tmp_path, llm_provider="openai", openai_api_key="sk-x")

        mock_result = MagicMock()
        mock_result.content = "agentic AI research."
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_result

        with patch("audia.agents.text_cleaner._build_llm", return_value=mock_llm), \
             patch("audia.config.get_settings", return_value=cfg):
            from audia.agents.stt import distill_search_query
            result = distill_search_query("I would like to research about agentic AI.")

        # trailing period must be stripped
        assert result == "agentic AI research"
        assert mock_llm.invoke.call_count == 1

    def test_passes_speech_as_human_message(self, tmp_path):
        from audia.config import Settings
        from langchain_core.messages import HumanMessage

        cfg = Settings(data_dir=tmp_path, llm_provider="openai", openai_api_key="sk-x")

        captured = []

        def fake_invoke(messages):
            captured.extend(messages)
            m = MagicMock()
            m.content = "neural networks"
            return m

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = fake_invoke

        with patch("audia.agents.text_cleaner._build_llm", return_value=mock_llm), \
             patch("audia.config.get_settings", return_value=cfg):
            from audia.agents.stt import distill_search_query
            result = distill_search_query("Tell me about neural networks")

        assert result == "neural networks"
        human_msgs = [m for m in captured if isinstance(m, HumanMessage)]
        assert any("neural networks" in m.content for m in human_msgs)
