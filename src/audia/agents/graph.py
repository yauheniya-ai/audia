"""
LangGraph pipeline: PDF → extracted text → curated text → audio file.

Graph structure (linear – no optional steps):
  extract_text ─► preprocess ─► curate ─► synthesize_audio ─► END

  • extract_text   : PyMuPDF → raw text + metadata
  • preprocess     : heuristic regex pre-pass (fast)
  • curate         : LLM – math → English, table summaries, ack condensing
  • synthesize_audio: TTS → audio file

Each node receives the full PipelineState and returns a partial update.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph
from rich.console import Console

from audia.agents.state import PipelineState
from audia.agents.pdf_processor import extract_text
from audia.agents.text_cleaner import heuristic_clean, llm_curate
from audia.agents.tts import synthesize
from audia.config import get_settings

console = Console(stderr=True)


# ──────────────────────────────────────────────────────────── nodes

def node_extract_text(state: PipelineState) -> dict[str, Any]:
    """Extract text and basic metadata from the PDF."""
    console.print("[bold cyan]\u25b6 Step 1/4 ─ PDF extraction[/bold cyan]")
    try:
        result = extract_text(state["pdf_path"])
        console.print(
            f"  [green]✓[/green] {result.num_pages} pages extracted, "
            f"{len(result.text):,} chars"
        )
        return {
            "raw_text": result.text,
            "num_pages": result.num_pages,
            "title": result.title,
            "error": None,
        }
    except Exception as exc:
        console.print(f"  [red]✗ Extraction failed:[/red] {exc}")
        return {"error": str(exc)}


def node_preprocess(state: PipelineState) -> dict[str, Any]:
    """Heuristic regex pre-pass – fast, no LLM."""
    if state.get("error"):
        return {}
    console.print("[bold cyan]\u25b6 Step 2/4 ─ Heuristic pre-pass[/bold cyan]")
    text = state.get("raw_text", "")
    cleaned = heuristic_clean(text)
    console.print(
        f"  [green]✓[/green] {len(text):,} → {len(cleaned):,} chars after pre-pass"
    )
    return {"preprocessed_text": cleaned}


def node_curate(state: PipelineState) -> dict[str, Any]:
    """LLM curation: math → English, table summaries, ack condensing."""
    if state.get("error"):
        return {}
    console.print("[bold cyan]\u25b6 Step 3/4 ─ LLM curation[/bold cyan]")
    cfg = get_settings()
    text = state.get("preprocessed_text") or state.get("raw_text", "")
    try:
        curated = llm_curate(text, cfg)
        console.print(
            f"  [green]✓[/green] Curation complete – {len(curated):,} chars"
        )
        return {"cleaned_text": curated}
    except Exception as exc:
        console.print(f"  [red]✗ LLM curation failed:[/red] {exc}")
        return {"error": str(exc)}


def node_synthesize_audio(state: PipelineState) -> dict[str, Any]:
    """Convert the final curated text to an audio file via TTS."""
    if state.get("error"):
        return {}

    console.print("[bold cyan]\u25b6 Step 4/4 ─ TTS synthesis[/bold cyan]")
    cfg = get_settings()
    text = (
        state.get("cleaned_text")
        or state.get("preprocessed_text")
        or state.get("raw_text", "")
    )

    out_dir = state.get("output_dir") or str(cfg.audio_dir)
    stem = state.get("run_id") or _safe_stem(state.get("title", "audio"))
    console.print(
        f"  [dim]Backend: {cfg.tts_backend} · Voice: {cfg.tts_voice} · "
        f"{len(text):,} chars to synthesise[/dim]"
    )

    try:
        audio_path = synthesize(
            text=text,
            output_dir=out_dir,
            filename=stem,
            settings=cfg,
        )
        console.print(f"  [green]✓[/green] Audio saved: {audio_path}")
        return {
            "audio_path": str(audio_path),
            "audio_filename": audio_path.name,
            "tts_backend": cfg.tts_backend,
            "tts_voice": cfg.tts_voice,
        }
    except Exception as exc:
        console.print(f"  [red]✗ TTS failed:[/red] {exc}")
        return {"error": str(exc)}


# ──────────────────────────────────────────────────────────── graph

def build_pipeline() -> Any:
    """Compile and return the LangGraph CompiledGraph."""
    g = StateGraph(PipelineState)

    g.add_node("extract_text", node_extract_text)
    g.add_node("preprocess",   node_preprocess)
    g.add_node("curate",       node_curate)
    g.add_node("synthesize",   node_synthesize_audio)

    g.set_entry_point("extract_text")
    g.add_edge("extract_text", "preprocess")
    g.add_edge("preprocess",   "curate")       # LLM curation always runs
    g.add_edge("curate",       "synthesize")
    g.add_edge("synthesize",   END)

    return g.compile()


def run_pipeline(
    pdf_path: str | Path,
    output_dir: str | Path | None = None,
) -> PipelineState:
    """
    Convenience function: build and run the pipeline for a single PDF.

    Returns the final PipelineState dict.
    After each run, the three text stages are saved to
    ~/.audia/debug/<stem>_<YYYYMMDD_HHMMSS>/ for inspection.
    """
    cfg = get_settings()
    out = str(output_dir or cfg.audio_dir)

    from datetime import datetime, timezone
    pdf_stem = Path(pdf_path).stem[:50]
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = f"{pdf_stem}_{ts}"

    pipeline = build_pipeline()
    initial_state: PipelineState = {
        "pdf_path": str(pdf_path),
        "output_dir": out,
        "run_id": run_id,
    }
    state = pipeline.invoke(initial_state)
    _save_debug_texts(run_id, state, cfg)
    return state


# ──────────────────────────────────────────────────────────── helpers

def _save_debug_texts(run_id: str, state: PipelineState, cfg) -> None:
    """
    Save each text stage of a pipeline run to its own .txt file inside
    ~/.audia/debug/<run_id>/   (e.g. debug/2025_Xu+_20260329_084445/)

    Files written (only when the stage produced output):
      1_raw.txt          – text as extracted by PyMuPDF
      2_preprocessed.txt – after heuristic regex pre-pass
      3_curated.txt      – after LLM curation
    """
    run_dir = cfg.debug_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    stages = [
        ("1_raw.txt",          state.get("raw_text")),
        ("2_preprocessed.txt", state.get("preprocessed_text")),
        ("3_curated.txt",      state.get("cleaned_text")),
    ]
    for filename, text in stages:
        if text:
            (run_dir / filename).write_text(text, encoding="utf-8")

    console.print(f"  [dim]Debug texts saved → {run_dir}[/dim]")


def _safe_stem(title: str, max_len: int = 60) -> str:
    """Convert a title to a safe filename stem."""
    import re
    slug = re.sub(r"[^a-zA-Z0-9\s\-]", "", title)
    slug = re.sub(r"\s+", "_", slug.strip())
    return slug[:max_len] or "audia_output"
