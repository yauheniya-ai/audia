"""
/api/library – Query the local SQLite library of papers and audio files.
All endpoints accept an optional ?project= query parameter (defaults to "default").
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import desc, select

from audia.config import DEFAULT_PROJECT, get_settings, validate_project_name
from audia.storage import AudioFile, Paper, get_session
from audia.storage.models import ResearchSession, UserSetting

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
        rows = session.execute(select(Paper).order_by(desc(Paper.created_at))).scalars().all()
        return JSONResponse(
            {
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
            }
        )


@router.get("/audio", summary="List all generated audio files")
async def list_audio(project: str | None = Query(None)) -> JSONResponse:
    proj = _proj(project)
    with get_session(proj) as session:
        rows = (
            session.execute(select(AudioFile).order_by(desc(AudioFile.created_at))).scalars().all()
        )
        return JSONResponse(
            {
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
            }
        )


@router.get("/research_sessions", summary="List all research sessions")
async def list_research_sessions(project: str | None = Query(None)) -> JSONResponse:
    with get_session(_proj(project)) as session:
        rows = (
            session.execute(select(ResearchSession).order_by(desc(ResearchSession.created_at)))
            .scalars()
            .all()
        )
        return JSONResponse(
            {
                "research_sessions": [
                    {
                        "id": rs.id,
                        "query": rs.query,
                        "paper_ids": rs.paper_ids_list,
                        "created_at": rs.created_at.isoformat(),
                    }
                    for rs in rows
                ]
            }
        )


@router.get("/user_settings", summary="List all user settings key-value pairs")
async def list_user_settings(project: str | None = Query(None)) -> JSONResponse:
    with get_session(_proj(project)) as session:
        rows = session.execute(select(UserSetting).order_by(UserSetting.key)).scalars().all()
        return JSONResponse({"user_settings": [{"key": r.key, "value": r.value} for r in rows]})


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

        # If filename is being renamed, also rename the file on disk and update file_path.
        if "filename" in updates and af.file_path:
            old_path = Path(af.file_path)
            new_name = updates["filename"]
            # Preserve the original extension if the new name has none.
            if not Path(new_name).suffix and old_path.suffix:
                new_name = new_name + old_path.suffix
            new_path = old_path.parent / new_name
            if old_path.exists() and old_path != new_path:
                old_path.rename(new_path)
            af.file_path = str(new_path)
            updates["filename"] = new_name  # normalised name with extension

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
async def delete_audio(audio_id: int, project: str | None = Query(None)) -> JSONResponse:
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
async def get_paper(paper_id: int, project: str | None = Query(None)) -> JSONResponse:
    proj = _proj(project)
    with get_session(proj) as session:
        paper = session.get(Paper, paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="Paper not found.")
        return JSONResponse(
            {
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
            }
        )


@router.delete("/papers/{paper_id}", summary="Delete a paper and all its audio files")
async def delete_paper(paper_id: int, project: str | None = Query(None)) -> JSONResponse:
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
async def serve_pdf(paper_id: int, project: str | None = Query(None)) -> FileResponse:
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


class MovePaperBody(BaseModel):
    target_project: str


@router.post(
    "/papers/{paper_id}/move", summary="Move a paper and its audio files to another project"
)
async def move_paper(
    paper_id: int,
    body: MovePaperBody,
    project: str | None = Query(None),
) -> JSONResponse:
    src = _proj(project)
    dst = body.target_project.strip().lower()

    if not dst:
        raise HTTPException(status_code=422, detail="target_project cannot be empty.")
    err = validate_project_name(dst)
    if err:
        raise HTTPException(status_code=422, detail=err)
    if src == dst:
        raise HTTPException(status_code=400, detail="Source and target project are the same.")

    cfg = get_settings()
    dst_dirs = cfg.get_project_dirs(dst)
    dst_dirs.ensure_dirs()

    # ── 1. Read source records ────────────────────────────────────────────────
    with get_session(src) as src_sess:
        paper = src_sess.get(Paper, paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="Paper not found.")

        # Snapshot all data we need before the session closes
        paper_data = {
            "title": paper.title,
            "authors": paper.authors,
            "abstract": paper.abstract,
            "arxiv_id": paper.arxiv_id,
            "pdf_path": paper.pdf_path,
            "pdf_url": paper.pdf_url,
            "created_at": paper.created_at,
        }
        audio_data = [
            {
                "filename": af.filename,
                "file_path": af.file_path,
                "duration_seconds": af.duration_seconds,
                "tts_backend": af.tts_backend,
                "tts_voice": af.tts_voice,
                "created_at": af.created_at,
            }
            for af in paper.audio_files
        ]

    # ── 2. Copy files to destination ─────────────────────────────────────────
    new_pdf_path: str | None = None
    if paper_data["pdf_path"]:
        src_pdf = Path(paper_data["pdf_path"])
        if src_pdf.exists():
            dst_pdf = dst_dirs.upload_dir / src_pdf.name
            # Avoid collisions
            if dst_pdf.exists():
                dst_pdf = dst_dirs.upload_dir / f"{paper_id}_{src_pdf.name}"
            shutil.copy2(src_pdf, dst_pdf)
            new_pdf_path = str(dst_pdf)

    new_audio_paths: list[str] = []
    for af in audio_data:
        src_audio = Path(af["file_path"])
        if src_audio.exists():
            dst_audio = dst_dirs.audio_dir / src_audio.name
            if dst_audio.exists():
                dst_audio = dst_dirs.audio_dir / f"{paper_id}_{src_audio.name}"
            shutil.copy2(src_audio, dst_audio)
            new_audio_paths.append(str(dst_audio))
        else:
            new_audio_paths.append(af["file_path"])  # keep old path as-is (best effort)

    # ── 3. Insert records in destination DB ──────────────────────────────────
    with get_session(dst) as dst_sess:
        new_paper = Paper(
            title=paper_data["title"],
            authors=paper_data["authors"],
            abstract=paper_data["abstract"],
            arxiv_id=paper_data["arxiv_id"],
            pdf_path=new_pdf_path,
            pdf_url=paper_data["pdf_url"],
            created_at=paper_data["created_at"],
        )
        dst_sess.add(new_paper)
        dst_sess.flush()  # assigns new_paper.id

        for i, af in enumerate(audio_data):
            dst_sess.add(
                AudioFile(
                    paper_id=new_paper.id,
                    filename=af["filename"],
                    file_path=new_audio_paths[i],
                    duration_seconds=af["duration_seconds"],
                    tts_backend=af["tts_backend"],
                    tts_voice=af["tts_voice"],
                    created_at=af["created_at"],
                )
            )
        dst_sess.commit()
        new_id = new_paper.id

    # ── 4. Delete source records + files ─────────────────────────────────────
    with get_session(src) as src_sess:
        paper = src_sess.get(Paper, paper_id)
        if paper:
            old_audio_files = [Path(af.file_path) for af in paper.audio_files]
            old_pdf = Path(paper.pdf_path) if paper.pdf_path else None
            src_sess.delete(paper)
        else:
            old_audio_files, old_pdf = [], None

    for p in old_audio_files:
        if p.exists():
            p.unlink(missing_ok=True)
    if old_pdf and old_pdf.exists():
        old_pdf.unlink(missing_ok=True)

    return JSONResponse(
        {
            "status": "moved",
            "source_project": src,
            "target_project": dst,
            "new_paper_id": new_id,
        }
    )
