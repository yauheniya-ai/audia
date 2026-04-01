"""
/api/research – Search ArXiv and convert selected papers to audio.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from audia.agents.graph import run_pipeline
from audia.agents.research import ArxivSearcher
from audia.agents.pdf_processor import extract_text
from audia.agents.text_cleaner import heuristic_clean, llm_curate
from audia.agents.tts import synthesize
from audia.config import get_settings
from audia.storage import get_session, AudioFile, Paper, ResearchSession
from audia.ui.jobs import JOBS

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    max_results: int = 10


class NormalizeRequest(BaseModel):
    query: str
    llm_provider: str | None = None
    llm_model: str | None = None


class ConvertResearchRequest(BaseModel):
    arxiv_ids: list[str]


class EnqueueRequest(BaseModel):
    arxiv_ids: list[str]
    query: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    tts_backend: str | None = None
    tts_voice: str | None = None


def _make_job(pdf_title: str | None = None) -> dict:
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
        "pdf_path": None,
        "pdf_title": pdf_title,
        "paper_id": None,
    }


def _log(job: dict, line: str) -> None:
    job["log"].append(line)


# ─────────────────────────────────────────────────── normalize

@router.post("/normalize", summary="Distil a natural-language query into a short ArXiv search string via LLM")
async def normalize(body: NormalizeRequest) -> JSONResponse:
    """Uses the same distill_search_query function as the CLI speech pipeline."""
    from audia.agents.text_cleaner import _build_llm
    from langchain_core.messages import HumanMessage, SystemMessage  # type: ignore

    cfg = get_settings()
    # Apply user-selected provider/model overrides (sent from the UI settings)
    if body.llm_provider:
        cfg.__dict__["llm_provider"] = body.llm_provider.lower()
    if body.llm_model:
        cfg.__dict__["llm_model"] = body.llm_model

    try:
        def _run() -> str:
            llm = _build_llm(cfg)
            messages = [
                SystemMessage(content=(
                    "You are a search query assistant. "
                    "Extract a concise ArXiv search query (3-8 words) from the user's message. "
                    "Return ONLY the search query, nothing else."
                )),
                HumanMessage(content=body.query),
            ]
            result = llm.invoke(messages)
            return getattr(result, "content", str(result)).strip()

        search_string = await asyncio.to_thread(_run)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return JSONResponse({"search_string": search_string})


# ─────────────────────────────────────────────────── search

@router.post("/search", summary="Search ArXiv for papers")
async def search(body: SearchRequest) -> JSONResponse:
    """Search ArXiv and return paper metadata."""
    searcher = ArxivSearcher(max_results=body.max_results)
    try:
        papers = searcher.search(body.query)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return JSONResponse({
        "query": body.query,
        "results": [
            {
                "arxiv_id": p.arxiv_id,
                "title": p.title,
                "authors": p.authors,
                "abstract": p.abstract,
                "pdf_url": p.pdf_url,
                "published": p.published,
            }
            for p in papers
        ],
    })


# ─────────────────────────────────────────────────── convert (synchronous)

@router.post("/convert", summary="Synchronously convert ArXiv papers to audio")
async def convert_papers(body: ConvertResearchRequest) -> JSONResponse:
    """Search, download, run pipeline, and save for each arxiv_id. Returns results synchronously."""
    cfg = get_settings()
    cfg.upload_dir.mkdir(parents=True, exist_ok=True)
    cfg.audio_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for arxiv_id in body.arxiv_ids:
        searcher = ArxivSearcher()
        papers = await asyncio.to_thread(searcher.search, f"id:{arxiv_id}")
        if not papers:
            results.append({"arxiv_id": arxiv_id, "error": "Not found on ArXiv"})
            continue

        paper = papers[0]
        try:
            pdf_path: Path = await asyncio.to_thread(
                searcher.download_pdf, paper, cfg.upload_dir
            )
        except Exception as exc:
            results.append({"arxiv_id": arxiv_id, "error": f"Download failed: {exc}"})
            continue

        state = await asyncio.to_thread(run_pipeline, str(pdf_path))
        if state.get("error") or not state.get("audio_path"):
            results.append({"arxiv_id": arxiv_id, "error": state.get("error", "Pipeline failed")})
            continue

        audio_path = Path(state["audio_path"])
        with get_session() as session:
            db_paper = Paper(
                title=paper.title,
                authors=json.dumps(paper.authors),
                abstract=paper.abstract,
                arxiv_id=paper.arxiv_id,
                pdf_path=str(pdf_path),
                pdf_url=paper.pdf_url,
            )
            session.add(db_paper)
            session.flush()
            af = AudioFile(
                paper_id=db_paper.id,
                filename=audio_path.name,
                file_path=str(audio_path),
                tts_backend=state.get("tts_backend", cfg.tts_backend),
                tts_voice=state.get("tts_voice", cfg.tts_voice),
            )
            session.add(af)
            session.flush()
            audio_id = af.id

        results.append({
            "arxiv_id": arxiv_id,
            "title": paper.title,
            "download_url": f"/api/convert/download/{audio_id}",
        })

    return JSONResponse({"results": results})


# ─────────────────────────────────────────────────── enqueue

@router.post("/enqueue", summary="Enqueue ArXiv paper(s) for async conversion")
async def enqueue_research(body: EnqueueRequest) -> JSONResponse:
    """
    For each arxiv_id, create an async job that downloads, processes, and
    saves to the library.  Returns job_ids immediately; poll
    /api/research/status/{job_id} for progress.
    """
    cfg = get_settings()
    cfg.upload_dir.mkdir(parents=True, exist_ok=True)
    cfg.audio_dir.mkdir(parents=True, exist_ok=True)

    jobs_out = []
    for arxiv_id in body.arxiv_ids:
        job_id = uuid.uuid4().hex
        job = _make_job(pdf_title=arxiv_id)
        JOBS[job_id] = job
        asyncio.create_task(_run_research_job(
            job_id, arxiv_id,
            query=body.query,
            llm_provider=body.llm_provider,
            llm_model=body.llm_model,
            tts_backend=body.tts_backend,
            tts_voice=body.tts_voice,
        ))
        jobs_out.append({"arxiv_id": arxiv_id, "job_id": job_id})

    return JSONResponse({"jobs": jobs_out})


async def _run_research_job(
    job_id: str,
    arxiv_id: str,
    query: str | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    tts_backend: str | None = None,
    tts_voice: str | None = None,
) -> None:
    job = JOBS[job_id]
    cfg = get_settings()
    upload_id = uuid.uuid4().hex[:8]

    try:
        # Stage 1 – Search ArXiv for metadata
        job.update(stage="searching", stage_label="Step 1/6 \u2500 Searching ArXiv", progress=5)
        _log(job, f"Step 1/6 \u2500 Searching ArXiv for {arxiv_id}")
        searcher = ArxivSearcher()
        papers = await asyncio.to_thread(searcher.search, f"id:{arxiv_id}")
        if job["cancelled"]:
            job.update(status="cancelled", stage="cancelled", stage_label="Cancelled"); return
        if not papers:
            job.update(status="error", stage="error", stage_label="Failed",
                       error=f"Paper {arxiv_id} not found on ArXiv.")
            _log(job, f"  \u2717 {arxiv_id} not found on ArXiv")
            return
        paper = papers[0]
        job["pdf_title"] = paper.title
        _log(job, f"  \u2713 Found: {paper.title[:80]}")

        # Stage 2 – Download PDF
        job.update(stage="downloading", stage_label="Step 2/6 \u2500 Downloading PDF", progress=15)
        _log(job, "Step 2/6 \u2500 Downloading PDF")
        pdf_path: Path = await asyncio.to_thread(
            searcher.download_pdf, paper, cfg.upload_dir
        )
        if job["cancelled"]:
            job.update(status="cancelled", stage="cancelled", stage_label="Cancelled"); return
        job["pdf_path"] = str(pdf_path)  # available now for preview
        _log(job, f"  \u2713 Saved to {pdf_path.name}")

        # Stage 3 – PDF extraction
        job.update(stage="extracting", stage_label="Step 3/6 \u2500 PDF extraction", progress=28)
        _log(job, "Step 3/6 \u2500 PDF extraction")
        pdf_result = await asyncio.to_thread(extract_text, str(pdf_path))
        if job["cancelled"]:
            job.update(status="cancelled", stage="cancelled", stage_label="Cancelled"); return
        raw_chars = len(pdf_result.text)
        job["stats"].update(raw_chars=raw_chars, num_pages=pdf_result.num_pages)
        if pdf_result.title:
            job["pdf_title"] = pdf_result.title
        _log(job, f"  \u2713 {pdf_result.num_pages} pages, {raw_chars:,} chars")

        # Stage 4 – Heuristic pre-pass
        job.update(stage="preprocessing", stage_label="Step 4/6 \u2500 Heuristic pre-cleaning", progress=40)
        _log(job, "Step 4/6 \u2500 Heuristic pre-cleaning")
        precleaned = await asyncio.to_thread(heuristic_clean, pdf_result.text)
        if job["cancelled"]:
            job.update(status="cancelled", stage="cancelled", stage_label="Cancelled"); return
        job["stats"]["precleaned_chars"] = len(precleaned)
        _log(job, f"  \u2713 {raw_chars:,} \u2192 {len(precleaned):,} chars after pre-pass")

        # Stage 5 – LLM curation
        job.update(stage="curating", stage_label="Step 5/6 \u2500 LLM curation", progress=55)
        _log(job, "Step 5/6 \u2500 LLM curation")
        cfg2 = get_settings()
        if llm_provider:
            cfg2.__dict__["llm_provider"] = llm_provider.lower()
        if llm_model:
            cfg2.__dict__["llm_model"] = llm_model
        if tts_backend:
            cfg2.__dict__["tts_backend"] = tts_backend
        if tts_voice:
            cfg2.__dict__["tts_voice"] = tts_voice

        def _cb_llm(msg: str) -> None:
            _log(job, f"  {msg}")

        curated = await asyncio.to_thread(llm_curate, precleaned, cfg2, _cb_llm)
        if job["cancelled"]:
            job.update(status="cancelled", stage="cancelled", stage_label="Cancelled"); return
        job["stats"]["curated_chars"] = len(curated)
        _log(job, f"  \u2713 Curation complete \u2013 {len(curated):,} chars")

        # Stage 6 – TTS synthesis
        job.update(stage="synthesizing", stage_label="Step 6/6 \u2500 TTS synthesis", progress=72)
        _log(job, "Step 6/6 \u2500 TTS synthesis")
        _log(job, f"  Backend: {cfg2.tts_backend} \u00b7 Voice: {cfg2.tts_voice}")

        def _cb_tts(msg: str) -> None:
            _log(job, f"  {msg}")
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
        _log(job, f"  \u2713 Audio saved: {audio_path.name}")

        # Save to DB
        job.update(stage="saving", stage_label="Saving to library", progress=95)
        _log(job, "Saving to library\u2026")
        with get_session() as session:
            db_paper = Paper(
                title=job["pdf_title"] or paper.title,
                authors=json.dumps(paper.authors),
                abstract=paper.abstract,
                arxiv_id=paper.arxiv_id,
                pdf_path=str(pdf_path),
                pdf_url=paper.pdf_url,
            )
            session.add(db_paper)
            session.flush()
            af = AudioFile(
                paper_id=db_paper.id,
                filename=audio_path.name,
                file_path=str(audio_path),
                tts_backend=cfg2.tts_backend,
                tts_voice=cfg2.tts_voice,
            )
            session.add(af)
            session.flush()
            audio_id = af.id
            paper_id = db_paper.id
            # Save research session so the Database tab shows the query history
            if query:
                session.add(ResearchSession(
                    query=query,
                    paper_ids=json.dumps([paper_id]),
                ))

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
                "title": job["pdf_title"] or paper.title,
                "num_pages": pdf_result.num_pages,
            },
        )

    except Exception as exc:
        job.update(status="error", stage="error", stage_label="Failed", error=str(exc))
        _log(job, f"  \u2717 Error: {exc}")


# ─────────────────────────────────────────────────── transcribe

@router.post("/transcribe", summary="Transcribe uploaded audio to text")
async def transcribe_audio(file: UploadFile = File(...)) -> JSONResponse:
    """Accept a browser audio recording and return the Whisper transcription."""
    import tempfile
    cfg = get_settings()
    suffix = Path(file.filename or "audio.webm").suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    try:
        from audia.agents.stt import transcribe_file
        text = await asyncio.to_thread(
            transcribe_file, tmp_path, cfg.stt_model, cfg.stt_device
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    return JSONResponse({"text": text})


# ─────────────────────────────────────────────────── status / cancel / pdf

@router.get("/status/{job_id}", summary="Poll research job status")
async def get_job_status(job_id: str) -> JSONResponse:
    """Return current status, stage, progress, log, result when done."""
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return JSONResponse(job)


@router.delete("/jobs/{job_id}", summary="Cancel a running research job")
async def cancel_job(job_id: str) -> JSONResponse:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job["status"] == "running":
        job["cancelled"] = True
        job["stage_label"] = "Cancelling\u2026"
        _log(job, "Cancellation requested\u2026")
    return JSONResponse({"status": "cancel_requested", "job_id": job_id})


@router.get("/jobs/{job_id}/pdf", summary="Serve the PDF for an in-progress or completed research job")
async def serve_job_pdf(job_id: str) -> FileResponse:
    """Stream the PDF associated with a research job (once downloaded)."""
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
