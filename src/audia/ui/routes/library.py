"""
/api/library – Query the local SQLite library of papers and audio files.
All endpoints accept an optional ?project= query parameter (defaults to "default").
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from audia.config import DEFAULT_PROJECT
from audia.storage import get_session, AudioFile, Paper
from audia.storage.models import ResearchSession, UserSetting
from sqlalchemy import select, desc

router = APIRouter()


def _proj(project: str | None) -> str:
    return (project or DEFAULT_PROJECT).strip() or DEFAULT_PROJECT


def _dl_url(audio_id: int, project: str) -> str:
    if project == DEFAULT_PROJECT:
        return f"/api/convert/download/{audio_id}"
    return f"/api/convert/download/{audio_id}?project={project}"


@router.get("/papers", summary="List all saved papers")
async def list_papers(project: str | None = Query(None)) -> JSONResponse:
    with get_session(_proj(project)) as session:
        rows = session.execute(
            select(Paper).order_by(desc(Paper.created_at))
        ).scalars().all()
        return JSONResponse({
            "papers": [
                {
                    "id": p.id,
                    "title": p.title,
                    "authors": p.authors_list,
                    "abstract": p.abstract,
                    "arxiv_id": p.arxiv_id,
                    "pdf_path": p.pdf_path,
                    "pdf_url": p.pdf_url,
                    "created_at": p.created_at.isoformat(),
                }
                for p in rows
            ]
        })


@router.get("/audio", summary="List all generated audio files")
async def list_audio(project: str | None = Query(None)) -> JSONResponse:
    proj = _proj(project)
    with get_session(proj) as session:
        rows = session.execute(
            select(AudioFile).order_by(desc(AudioFile.created_at))
        ).scalars().all()
        return JSONResponse({
            "audio_files": [
                {
                    "id": af.id,
                    "paper_id": af.paper_id,
                    "filename": af.filename,
                    "file_path": af.file_path,
                    "download_url": _dl_url(af.id, proj),
                    "duration_seconds": af.duration_seconds,
                    "tts_backend": af.tts_backend,
                    "tts_voice": af.tts_voice,
                    "created_at": af.created_at.isoformat(),
                }
                for af in rows
            ]
        })


@router.get("/research_sessions", summary="List all research sessions")
async def list_research_sessions(project: str | None = Query(None)) -> JSONResponse:
    with get_session(_proj(project)) as session:
        rows = session.execute(
            select(ResearchSession).order_by(desc(ResearchSession.created_at))
        ).scalars().all()
        return JSONResponse({
            "research_sessions": [
                {
                    "id": rs.id,
                    "query": rs.query,
                    "paper_ids": rs.paper_ids_list,
                    "created_at": rs.created_at.isoformat(),
                }
                for rs in rows
            ]
        })


@router.get("/user_settings", summary="List all user settings key-value pairs")
async def list_user_settings(project: str | None = Query(None)) -> JSONResponse:
    with get_session(_proj(project)) as session:
        rows = session.execute(
            select(UserSetting).order_by(UserSetting.key)
        ).scalars().all()
        return JSONResponse({
            "user_settings": [{"key": r.key, "value": r.value} for r in rows]
        })


class PaperPatch(BaseModel):
    title: str | None = None
    authors: list[str] | None = None
    abstract: str | None = None
    arxiv_id: str | None = None
    pdf_url: str | None = None


class AudioPatch(BaseModel):
    filename: str | None = None
    file_path: str | None = None
    duration_seconds: float | None = None
    tts_backend: str | None = None
    tts_voice: str | None = None
    paper_id: int | None = None


class ResearchSessionPatch(BaseModel):
    query: str | None = None


class UserSettingPatch(BaseModel):
    value: str


@router.patch("/papers/{paper_id}", summary="Update paper fields")
async def patch_paper(
    paper_id: int, body: PaperPatch, project: str | None = Query(None)
) -> JSONResponse:
    updates = body.model_dump(exclude_unset=True)
    with get_session(_proj(project)) as session:
        paper = session.get(Paper, paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="Paper not found.")
        for field, val in updates.items():
            if field == "authors":
                paper.authors = json.dumps(val)
            else:
                setattr(paper, field, val)
        session.commit()
    return JSONResponse({"status": "updated", "id": paper_id})


@router.patch("/audio/{audio_id}", summary="Update audio file fields")
async def patch_audio(
    audio_id: int, body: AudioPatch, project: str | None = Query(None)
) -> JSONResponse:
    updates = body.model_dump(exclude_unset=True)
    with get_session(_proj(project)) as session:
        af = session.get(AudioFile, audio_id)
        if af is None:
            raise HTTPException(status_code=404, detail="Audio file not found.")
        for field, val in updates.items():
            setattr(af, field, val)
        session.commit()
    return JSONResponse({"status": "updated", "id": audio_id})


@router.patch("/research_sessions/{session_id}", summary="Update research session")
async def patch_research_session(
    session_id: int, body: ResearchSessionPatch, project: str | None = Query(None)
) -> JSONResponse:
    updates = body.model_dump(exclude_unset=True)
    with get_session(_proj(project)) as session:
        rs = session.get(ResearchSession, session_id)
        if rs is None:
            raise HTTPException(status_code=404, detail="Research session not found.")
        for field, val in updates.items():
            setattr(rs, field, val)
        session.commit()
    return JSONResponse({"status": "updated", "id": session_id})


@router.patch("/user_settings/{key}", summary="Update a user setting value")
async def patch_user_setting(
    key: str, body: UserSettingPatch, project: str | None = Query(None)
) -> JSONResponse:
    with get_session(_proj(project)) as session:
        row = session.get(UserSetting, key)
        if row is None:
            raise HTTPException(status_code=404, detail="Setting not found.")
        row.value = body.value
        session.commit()
    return JSONResponse({"status": "updated", "key": key})


@router.delete("/audio/{audio_id}", summary="Delete an audio file record")
async def delete_audio(
    audio_id: int, project: str | None = Query(None)
) -> JSONResponse:
    with get_session(_proj(project)) as session:
        af = session.get(AudioFile, audio_id)
        if af is None:
            raise HTTPException(status_code=404, detail="Audio file not found.")
        path = Path(af.file_path)
        session.delete(af)
    if path.exists():
        path.unlink()
    return JSONResponse({"status": "deleted", "id": audio_id})


@router.get("/papers/{paper_id}", summary="Get a single paper with its audio files")
async def get_paper(
    paper_id: int, project: str | None = Query(None)
) -> JSONResponse:
    proj = _proj(project)
    with get_session(proj) as session:
        paper = session.get(Paper, paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="Paper not found.")
        return JSONResponse({
            "id": paper.id,
            "title": paper.title,
            "authors": paper.authors_list,
            "arxiv_id": paper.arxiv_id,
            "pdf_path": paper.pdf_path,
            "created_at": paper.created_at.isoformat(),
            "audio_files": [
                {
                    "id": af.id,
                    "filename": af.filename,
                    "download_url": _dl_url(af.id, proj),
                    "tts_backend": af.tts_backend,
                    "tts_voice": af.tts_voice,
                    "created_at": af.created_at.isoformat(),
                }
                for af in paper.audio_files
            ],
        })


@router.delete("/papers/{paper_id}", summary="Delete a paper and all its audio files")
async def delete_paper(
    paper_id: int, project: str | None = Query(None)
) -> JSONResponse:
    with get_session(_proj(project)) as session:
        paper = session.get(Paper, paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="Paper not found.")
        audio_paths = [Path(af.file_path) for af in paper.audio_files]
        pdf_path = Path(paper.pdf_path) if paper.pdf_path else None
        session.delete(paper)
    for p in audio_paths:
        if p.exists():
            p.unlink()
    if pdf_path and pdf_path.exists():
        pdf_path.unlink()
    return JSONResponse({"status": "deleted", "id": paper_id})


@router.get("/pdf/{paper_id}", summary="Serve the original PDF for a paper")
async def serve_pdf(
    paper_id: int, project: str | None = Query(None)
) -> FileResponse:
    with get_session(_proj(project)) as session:
        paper = session.get(Paper, paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="Paper not found.")
        pdf_path = Path(paper.pdf_path) if paper.pdf_path else None
    if pdf_path is None or not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found on disk.")
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )
