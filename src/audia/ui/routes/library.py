"""
/api/library – Query the local SQLite library of papers and audio files.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from audia.storage import get_session, AudioFile, Paper
from sqlalchemy import select, desc

router = APIRouter()


@router.get("/papers", summary="List all saved papers")
async def list_papers() -> JSONResponse:
    """Return all papers stored in the local database."""
    with get_session() as session:
        rows = session.execute(
            select(Paper).order_by(desc(Paper.created_at))
        ).scalars().all()
        return JSONResponse({
            "papers": [
                {
                    "id": p.id,
                    "title": p.title,
                    "authors": p.authors_list,
                    "arxiv_id": p.arxiv_id,
                    "created_at": p.created_at.isoformat(),
                }
                for p in rows
            ]
        })


@router.get("/audio", summary="List all generated audio files")
async def list_audio() -> JSONResponse:
    """Return all audio files stored in the local database."""
    with get_session() as session:
        rows = session.execute(
            select(AudioFile).order_by(desc(AudioFile.created_at))
        ).scalars().all()
        return JSONResponse({
            "audio_files": [
                {
                    "id": af.id,
                    "paper_id": af.paper_id,
                    "filename": af.filename,
                    "download_url": f"/api/convert/download/{af.id}",
                    "tts_backend": af.tts_backend,
                    "tts_voice": af.tts_voice,
                    "created_at": af.created_at.isoformat(),
                }
                for af in rows
            ]
        })


@router.delete("/audio/{audio_id}", summary="Delete an audio file record")
async def delete_audio(audio_id: int) -> JSONResponse:
    """Remove an audio file record (and optionally the file on disk)."""
    import os
    from pathlib import Path

    with get_session() as session:
        af = session.get(AudioFile, audio_id)
        if af is None:
            raise HTTPException(status_code=404, detail="Audio file not found.")
        path = Path(af.file_path)
        session.delete(af)

    if path.exists():
        path.unlink()

    return JSONResponse({"status": "deleted", "id": audio_id})
