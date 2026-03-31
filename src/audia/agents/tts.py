"""
Text-to-Speech wrapper supporting multiple backends:

  - edge-tts  (default, free, requires internet)
  - kokoro    (local, requires: pip install audia[kokoro])
  - openai    (requires API key)

All backends return the absolute path to the generated audio file.
"""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from pathlib import Path
from typing import Optional

from rich.console import Console

from audia.config import Settings, get_settings

console = Console(stderr=True)

# Per-chunk timeout in seconds (edge-tts network call)
_EDGE_TTS_CHUNK_TIMEOUT = 90


# ──────────────────────────────────────────────────────────── public API

def synthesize(
    text: str,
    output_dir: str | Path | None = None,
    filename: str | None = None,
    settings: Settings | None = None,
    progress_cb=None,
) -> Path:
    """
    Convert *text* to an audio file and return its path.

    Parameters
    ----------
    text:       The cleaned text to synthesise.
    output_dir: Directory for the output file.  Defaults to settings.audio_dir.
    filename:   Desired filename (without extension). Auto-generated when None.
    settings:   Audia settings; uses global settings when None.
    """
    cfg = settings or get_settings()
    out_dir = Path(output_dir) if output_dir else cfg.audio_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = filename or f"audia_{int(time.time())}_{uuid.uuid4().hex[:6]}"

    backend = cfg.tts_backend
    if backend == "edge-tts":
        return _edge_tts(text, out_dir, stem, cfg, progress_cb)
    elif backend == "kokoro":
        return _kokoro_tts(text, out_dir, stem, cfg)
    elif backend == "openai":
        return _openai_tts(text, out_dir, stem, cfg)
    else:
        raise ValueError(f"Unknown TTS backend: {backend}")


# ──────────────────────────────────────────────────────────── edge-tts

def _edge_tts(text: str, out_dir: Path, stem: str, cfg: Settings, progress_cb=None) -> Path:
    """Use Microsoft Edge TTS (free, no API key). Generates mp3 via network."""
    try:
        import edge_tts  # type: ignore
    except ImportError as e:
        raise ImportError("edge-tts is required: pip install edge-tts") from e

    chunks = _split(text, cfg.tts_chunk_chars)
    total = len(chunks)
    hdr = f"TTS: {total} chunk(s) to synthesise"
    console.print(f"  [dim]{hdr}[/dim]")
    if progress_cb:
        progress_cb(hdr)
    chunk_paths: list[Path] = []

    for i, chunk in enumerate(chunks, 1):
        chunk_path = out_dir / f"{stem}_part{i:03d}.mp3"
        msg_start = f"Synthesising chunk {i}/{total} ({len(chunk):,} chars)\u2026"
        console.print(f"  [dim]  {msg_start}[/dim]")
        if progress_cb:
            progress_cb(msg_start)
        _run_async(
            _edge_speak(chunk, str(chunk_path), cfg.tts_voice, cfg.tts_rate, edge_tts)
        )
        chunk_paths.append(chunk_path)
        msg_done = f"Chunk {i}/{total} done \u2192 {chunk_path.name}"
        console.print(f"  [dim]  {msg_done}[/dim]")
        if progress_cb:
            progress_cb(msg_done)

    if len(chunk_paths) == 1:
        final_path = out_dir / f"{stem}.mp3"
        chunk_paths[0].rename(final_path)
        return final_path

    final_path = _concat_mp3(chunk_paths, out_dir / f"{stem}.mp3")
    for p in chunk_paths:
        p.unlink(missing_ok=True)
    return final_path


def _run_async(coro) -> None:
    """
    Run *coro* in an event loop.
    Works in both sync contexts (CLI) and when called from a thread
    inside an async server (FastAPI uses run_in_threadpool).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We're inside a running event loop (FastAPI worker thread).
        # asyncio.run() would fail here; use a new event loop in this thread.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            future.result(timeout=_EDGE_TTS_CHUNK_TIMEOUT + 5)
    else:
        asyncio.run(coro)


async def _edge_speak(
    text: str,
    output_path: str,
    voice: str,
    rate: str,
    edge_tts_module,
) -> None:
    communicate = edge_tts_module.Communicate(text, voice=voice, rate=rate)
    await asyncio.wait_for(communicate.save(output_path), timeout=_EDGE_TTS_CHUNK_TIMEOUT)


def _concat_mp3(parts: list[Path], dest: Path) -> Path:
    """Concatenate MP3 files by raw byte joining (works for CBR streams)."""
    with dest.open("wb") as out:
        for part in parts:
            out.write(part.read_bytes())
    return dest


# ──────────────────────────────────────────────────────────── kokoro

def _kokoro_tts(text: str, out_dir: Path, stem: str, cfg: Settings) -> Path:
    """Use Kokoro local TTS model (pip install audia[kokoro])."""
    try:
        from kokoro import KPipeline  # type: ignore
        import soundfile as sf  # type: ignore
        import numpy as np
    except ImportError as e:
        raise ImportError(
            "Kokoro TTS requires extra dependencies: pip install audia[kokoro]"
        ) from e

    pipeline = KPipeline(lang_code="a")  # 'a' = American English
    chunks = _split(text, cfg.tts_chunk_chars)

    all_audio: list = []
    for chunk in chunks:
        for _, _, audio in pipeline(chunk, voice=cfg.tts_voice, speed=1.0):
            all_audio.append(audio)

    combined = np.concatenate(all_audio)
    out_path = out_dir / f"{stem}.wav"
    sf.write(str(out_path), combined, samplerate=24000)
    return out_path


# ──────────────────────────────────────────────────────────── openai

def _openai_tts(text: str, out_dir: Path, stem: str, cfg: Settings) -> Path:
    """Use OpenAI TTS API."""
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as e:
        raise ImportError(
            "OpenAI TTS requires: pip install audia[openai]"
        ) from e

    client_kwargs: dict = dict(api_key=cfg.openai_api_key)
    if cfg.openai_api_base:
        client_kwargs["base_url"] = cfg.openai_api_base
    client = OpenAI(**client_kwargs)
    chunks = _split(text, 4096)  # OpenAI limit

    chunk_paths: list[Path] = []
    for i, chunk in enumerate(chunks):
        response = client.audio.speech.create(
            model="tts-1",
            voice=cfg.tts_voice,  # alloy, echo, nova, shimmer …
            input=chunk,
        )
        p = out_dir / f"{stem}_part{i:03d}.mp3"
        response.stream_to_file(str(p))
        chunk_paths.append(p)

    if len(chunk_paths) == 1:
        final_path = out_dir / f"{stem}.mp3"
        chunk_paths[0].rename(final_path)
        return final_path

    final_path = _concat_mp3(chunk_paths, out_dir / f"{stem}.mp3")
    for p in chunk_paths:
        p.unlink(missing_ok=True)
    return final_path


# ──────────────────────────────────────────────────────────── helpers

def _split(text: str, max_chars: int) -> list[str]:
    """
    Split text into chunks ≤ max_chars.
    Prefers sentence boundaries; falls back to whitespace.
    """
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    # Split at sentence ends first
    sentences = re.split(r"(?<=[.!?])\s+", text)
    current = ""
    for sent in sentences:
        if len(current) + len(sent) + 1 <= max_chars:
            current += (" " if current else "") + sent
        else:
            if current:
                chunks.append(current)
            # If a single sentence exceeds max_chars, split by words
            if len(sent) > max_chars:
                words = sent.split()
                sub = ""
                for w in words:
                    if len(sub) + len(w) + 1 <= max_chars:
                        sub += (" " if sub else "") + w
                    else:
                        if sub:
                            chunks.append(sub)
                        sub = w
                if sub:
                    current = sub
                else:
                    current = ""
            else:
                current = sent
    if current:
        chunks.append(current)
    return chunks or [text]
