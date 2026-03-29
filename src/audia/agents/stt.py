"""
Speech-to-Text input – record from microphone and transcribe.

Requires: pip install audia[stt]
  - faster-whisper
  - sounddevice
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def record_and_transcribe(
    seconds: int = 30,
    samplerate: int = 16000,
    model_size: str = "base",
    device: str = "cpu",
) -> str:
    """
    Record audio from the default microphone and return the transcription.

    Parameters
    ----------
    seconds:    Maximum recording duration.
    samplerate: Audio sample rate (16 kHz is recommended for Whisper).
    model_size: faster-whisper model: tiny | base | small | medium | large-v3
    device:     'cpu' or 'cuda'
    """
    _ensure_stt_deps()

    import numpy as np
    import sounddevice as sd  # type: ignore

    print(f"[audia] Recording for up to {seconds} seconds… (Ctrl-C to stop early)")
    audio = sd.rec(
        int(seconds * samplerate),
        samplerate=samplerate,
        channels=1,
        dtype="float32",
    )
    try:
        sd.wait()
    except KeyboardInterrupt:
        sd.stop()
    print("[audia] Recording finished.")

    audio_1d: "np.ndarray" = audio.flatten()
    return _transcribe_array(audio_1d, samplerate, model_size, device)


def transcribe_file(
    audio_path: str | Path,
    model_size: str = "base",
    device: str = "cpu",
) -> str:
    """Transcribe an existing audio file (wav, mp3, …)."""
    _ensure_stt_deps()
    from faster_whisper import WhisperModel  # type: ignore

    model = WhisperModel(model_size, device=device, compute_type="int8")
    segments, _ = model.transcribe(str(audio_path), beam_size=5)
    return " ".join(seg.text.strip() for seg in segments)


def _transcribe_array(
    audio: "object",
    samplerate: int,
    model_size: str,
    device: str,
) -> str:
    """Transcribe a NumPy float32 array using faster-whisper."""
    import tempfile
    import soundfile as sf  # type: ignore
    from faster_whisper import WhisperModel  # type: ignore

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp_path = f.name

    sf.write(tmp_path, audio, samplerate)
    try:
        model = WhisperModel(model_size, device=device, compute_type="int8")
        segments, _ = model.transcribe(tmp_path, beam_size=5)
        return " ".join(seg.text.strip() for seg in segments)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _ensure_stt_deps() -> None:
    missing = []
    try:
        import sounddevice  # noqa: F401
    except ImportError:
        missing.append("sounddevice")
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        missing.append("faster-whisper")
    if missing:
        deps = " ".join(missing)
        raise ImportError(
            f"STT requires extra dependencies: pip install audia[stt]\n"
            f"Missing: {deps}"
        )
