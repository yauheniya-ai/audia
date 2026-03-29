"""
/api/convert – Upload PDF → run pipeline → return audio file path.
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from audia.config import get_settings
from audia.agents.graph import run_pipeline
from audia.storage import init_db, get_session, AudioFile, Paper

router = APIRouter()


@router.post("/upload", summary="Upload a PDF and convert it to audio")
async def upload_and_convert(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF file to convert"),
    voice: Optional[str] = Form(None, description="TTS voice override"),
) -> JSONResponse:
    """
    Upload a PDF, run the audia pipeline, and return the audio file location.

    The heavy lifting (PDF extraction + TTS) is done synchronously here for
    simplicity.  For large files you may want to use the `/enqueue` endpoint
    which processes in the background and lets the client poll for status.
    """
    cfg = get_settings()

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    # Save upload
    upload_id = uuid.uuid4().hex[:8]
    upload_path = cfg.upload_dir / f"{upload_id}_{file.filename}"
    with upload_path.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)

    # Voice override
    if voice:
        cfg.__dict__["tts_voice"] = voice

    # Run pipeline (sync – acceptable for API server; see /enqueue for async)
    state = run_pipeline(upload_path)

    if state.get("error"):
        raise HTTPException(status_code=500, detail=state["error"])

    audio_path = Path(state["audio_path"])

    # Persist to DB
    with get_session() as session:
        paper = Paper(
            title=state.get("title", upload_path.stem),
            authors=json.dumps([]),
            pdf_path=str(upload_path),
        )
        session.add(paper)
        session.flush()
        af = AudioFile(
            paper_id=paper.id,
            filename=audio_path.name,
            file_path=str(audio_path),
            tts_backend=state.get("tts_backend", cfg.tts_backend),
            tts_voice=state.get("tts_voice", cfg.tts_voice),
        )
        session.add(af)
        session.flush()
        audio_id = af.id

    return JSONResponse({
        "status": "ok",
        "audio_id": audio_id,
        "audio_filename": audio_path.name,
        "download_url": f"/api/convert/download/{audio_id}",
        "title": state.get("title", ""),
        "num_pages": state.get("num_pages", 0),
        "tts_backend": state.get("tts_backend", ""),
        "tts_voice": state.get("tts_voice", ""),
    })


@router.get("/download/{audio_id}", summary="Download generated audio file")
async def download_audio(audio_id: int) -> FileResponse:
    """Stream the generated audio file for download."""
    with get_session() as session:
        af = session.get(AudioFile, audio_id)
        if af is None:
            raise HTTPException(status_code=404, detail="Audio file not found.")
        file_path = Path(af.file_path)
        filename = af.filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found on disk.")

    media_type = "audio/mpeg" if filename.endswith(".mp3") else "audio/wav"
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type=media_type,
    )
