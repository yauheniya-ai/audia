"""
/api/research – Search ArXiv and convert selected papers to audio.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from audia.agents.research import ArxivSearcher, ArxivPaper
from audia.agents.graph import run_pipeline
from audia.config import get_settings
from audia.storage import get_session, AudioFile, Paper

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    max_results: int = 10


class ConvertRequest(BaseModel):
    arxiv_ids: list[str]


@router.post("/search", summary="Search ArXiv for papers")
async def search(body: SearchRequest) -> JSONResponse:
    """
    Search ArXiv and return paper metadata (no conversion yet).
    The client can then select papers and call /api/research/convert.
    """
    cfg = get_settings()
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


@router.post("/convert", summary="Download and convert ArXiv paper(s) to audio")
async def convert_papers(body: ConvertRequest) -> JSONResponse:
    """
    Download the PDFs for the selected ArXiv IDs and run the pipeline.
    Returns a list of audio file records.
    """
    cfg = get_settings()
    searcher = ArxivSearcher()
    results = []

    for arxiv_id in body.arxiv_ids:
        # Fetch metadata
        papers = searcher.search(f"id:{arxiv_id}")
        if not papers:
            results.append({"arxiv_id": arxiv_id, "error": "Not found on ArXiv"})
            continue

        paper = papers[0]

        try:
            pdf_path = searcher.download_pdf(paper)
        except Exception as exc:
            results.append({"arxiv_id": arxiv_id, "error": f"Download failed: {exc}"})
            continue

        state = run_pipeline(pdf_path)
        if state.get("error"):
            results.append({"arxiv_id": arxiv_id, "error": state["error"]})
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
            "audio_id": audio_id,
            "audio_filename": audio_path.name,
            "download_url": f"/api/convert/download/{audio_id}",
        })

    return JSONResponse({"results": results})
