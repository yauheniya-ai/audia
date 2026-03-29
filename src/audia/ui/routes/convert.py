"""
/api/convert – Upload PDF → run pipeline → return audio file path.
Includes background-job endpoints for granular progress tracking.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from audia.config import get_settings
from audia.agents.pdf_processor import extract_text
from audia.agents.text_cleaner import heuristic_clean, llm_curate
from audia.agents.tts import synthesize
from audia.storage import get_session, AudioFile, Paper
from audia.ui.jobs import JOBS

router = APIRouter()


def _make_job(pdf_path: str | None = None, pdf_title: str | None = None) -> dict:
    return {
        "status": "running",
        "stage": "queued",
        "stage_label": "Queued",
        "progress": 2,
        "log": [],
        "stats": {},
        "result": None,
        "error": None,
        "cancelled": False,
        "pdf_path": pdf_path,
        "pdf_title": pdf_title,
        "paper_id": None,
    }


def _log(job: dict, line: str) -> None:
    job["log"].append(line)


# ─────────────────────────────────────────────────── enqueue (upload)

@router.post("/enqueue", summary="Enqueue a PDF conversion job (with progress tracking)")
async def enqueue_conversion(
    file: UploadFile = File(..., description="PDF file to convert"),
    voice: Optional[str] = Form(None, description="TTS voice override"),
) -> JSONResponse:
    """Upload a PDF and return a job_id immediately; poll /status/{job_id} for progress."""
    cfg = get_settings()

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    cfg.upload_dir.mkdir(parents=True, exist_ok=True)
    cfg.audio_dir.mkdir(parents=True, exist_ok=True)

    upload_id = uuid.uuid4().hex[:8]
    upload_path = cfg.upload_dir / f"{upload_id}_{file.filename}"
    contents = await file.read()
    upload_path.write_bytes(contents)

    job_id = uuid.uuid4().hex
    job = _make_job(pdf_path=str(upload_path), pdf_title=file.filename)
    JOBS[job_id] = job

    async def _run() -> None:
        effective_voice = voice
        try:
            # Stage 1 – PDF extraction
            job.update(stage="extracting", stage_label="Step 1/4 \u2500 PDF extraction", progress=10)
            _log(job, "Step 1/4 \u2500 PDF extraction")
            pdf_result = await asyncio.to_thread(extract_text, str(upload_path))
            if job["cancelled"]:
                job.update(status="cancelled", stage="cancelled", stage_label="Cancelled"); return
            raw_chars = len(pdf_result.text)
            job["stats"].update(raw_chars=raw_chars, num_pages=pdf_result.num_pages,
                                title=pdf_result.title or upload_path.stem)
            job["pdf_title"] = pdf_result.title or upload_path.stem
            _log(job, f"  \u2713 {pdf_result.num_pages} pages extracted, {raw_chars:,} chars")

            # Stage 2 – Heuristic pre-pass
            job.update(stage="preprocessing", stage_label="Step 2/4 \u2500 Heuristic pre-cleaning", progress=28)
            _log(job, "Step 2/4 \u2500 Heuristic pre-cleaning")
            precleaned = await asyncio.to_thread(heuristic_clean, pdf_result.text)
            if job["cancelled"]:
                job.update(status="cancelled", stage="cancelled", stage_label="Cancelled"); return
            job["stats"]["precleaned_chars"] = len(precleaned)
            _log(job, f"  \u2713 {raw_chars:,} \u2192 {len(precleaned):,} chars after pre-pass")

            # Stage 3 – LLM curation
            job.update(stage="curating", stage_label="Step 3/4 \u2500 LLM curation", progress=48)
            _log(job, "Step 3/4 \u2500 LLM curation")
            cfg2 = get_settings()
            if effective_voice:
                cfg2.__dict__["tts_voice"] = effective_voice
            def _cb_llm(msg: str):
                _log(job, f"  {msg}")
            curated = await asyncio.to_thread(llm_curate, precleaned, cfg2, _cb_llm)
            if job["cancelled"]:
                job.update(status="cancelled", stage="cancelled", stage_label="Cancelled"); return
            job["stats"]["curated_chars"] = len(curated)
            _log(job, f"  \u2713 Curation complete \u2013 {len(curated):,} chars")

            # Stage 4 – TTS synthesis
            job.update(stage="synthesizing", stage_label="Step 4/4 \u2500 TTS synthesis", progress=72)
            _log(job, "Step 4/4 \u2500 TTS synthesis")
            _log(job, f"  Backend: {cfg2.tts_backend} \u00b7 Voice: {cfg2.tts_voice} \u00b7 {len(curated):,} chars")
            def _cb_tts(msg: str):
                _log(job, f"  {msg}")
                # bump progress slightly per TTS chunk
                job["progress"] = min(92, job["progress"] + 1)
            audio_path = await asyncio.to_thread(
                synthesize,
                text=curated,
                output_dir=str(cfg2.audio_dir),
                filename=upload_id,
                settings=cfg2,
                progress_cb=_cb_tts,
            )
            if job["cancelled"]:
                job.update(status="cancelled", stage="cancelled", stage_label="Cancelled"); return
            job["stats"]["audio_filename"] = audio_path.name
            _log(job, f"  \u2713 Audio saved: {audio_path}")

            # Save to DB
            job.update(stage="saving", stage_label="Saving to library", progress=95)
            _log(job, "Saving to library\u2026")
            with get_session() as session:
                paper = Paper(
                    title=pdf_result.title or upload_path.stem,
                    authors=json.dumps([]),
                    pdf_path=str(upload_path),
                )
                session.add(paper)
                session.flush()
                af = AudioFile(
                    paper_id=paper.id,
                    filename=audio_path.name,
                    file_path=str(audio_path),
                    tts_backend=cfg2.tts_backend,
                    tts_voice=cfg2.tts_voice,
                )
                session.add(af)
                session.flush()
                audio_id = af.id
                paper_id = paper.id

            job["paper_id"] = paper_id
            _log(job, f"  \u2713 Saved (paper_id={paper_id}, audio_id={audio_id})")
            job.update(
                status="done",
                stage="done",
                stage_label="Complete",
                progress=100,
                result={
                    "audio_id": audio_id,
                    "paper_id": paper_id,
                    "audio_filename": audio_path.name,
                    "download_url": f"/api/convert/download/{audio_id}",
                    "title": pdf_result.title or upload_path.stem,
                    "num_pages": pdf_result.num_pages,
                },
            )
        except Exception as exc:
            job.update(status="error", stage="error", stage_label="Failed", error=str(exc))
            _log(job, f"  \u2717 Error: {exc}")

    asyncio.create_task(_run())
    return JSONResponse({"job_id": job_id})


# ─────────────────────────────────────────────────── status / cancel / pdf

@router.get("/status/{job_id}", summary="Poll conversion job status")
async def get_job_status(job_id: str) -> JSONResponse:
    """Return current status, stage, progress, log, result when done."""
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return JSONResponse(job)


@router.delete("/jobs/{job_id}", summary="Cancel a running conversion job")
async def cancel_job(job_id: str) -> JSONResponse:
    """Signal the job runner to stop after the current stage."""
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job["status"] == "running":
        job["cancelled"] = True
        job["stage_label"] = "Cancelling\u2026"
        _log(job, "Cancellation requested\u2026")
    return JSONResponse({"status": "cancel_requested", "job_id": job_id})


@router.get("/jobs/{job_id}/pdf", summary="Serve the PDF for an in-progress or completed job")
async def serve_job_pdf(job_id: str) -> FileResponse:
    """Stream the PDF associated with a conversion job (available as soon as uploaded/downloaded)."""
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    pdf_path = job.get("pdf_path")
    if not pdf_path or not Path(pdf_path).exists():
        raise HTTPException(status_code=404, detail="PDF not yet available.")
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )


# ─────────────────────────────────────────────────── download

@router.get("/download/{audio_id}", summary="Download generated audio file")
async def download_audio(audio_id: int) -> FileResponse:
    """Stream the generated audio file."""
    with get_session() as session:
        af = session.get(AudioFile, audio_id)
        if af is None:
            raise HTTPException(status_code=404, detail="Audio file not found.")
        file_path = Path(af.file_path)
        filename = af.filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found on disk.")

    media_type = "audio/mpeg" if filename.endswith(".mp3") else "audio/wav"
    return FileResponse(path=str(file_path), filename=filename, media_type=media_type)

