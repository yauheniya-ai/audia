# CHANGELOG

## Version 0.2.0 (2026-03-29)

### Web UI overhaul

- **Async conversion jobs**: PDF upload and ArXiv research conversions now run in the background; a `job_id` is returned immediately and the frontend polls for live progress
- **Streaming terminal log**: each pipeline stage (PDF extraction, heuristic cleaning, LLM curation chunk-by-chunk, TTS chunk-by-chunk) streams log lines into a scrollable terminal pane
- **Cancel button**: any running conversion can be cancelled mid-pipeline via a cancel button that calls `DELETE /api/{convert,research}/jobs/{id}`
- **Inline PDF preview**: clicking a paper in the sidebar now opens the PDF in a side panel instead of downloading it; `Content-Disposition: inline` is set on all PDF-serving endpoints
- **Live PDF preview during conversion**: the preview panel opens automatically as soon as the PDF is available (right after upload or ArXiv download), before the pipeline finishes
- **Research async pipeline**: `POST /api/research/enqueue` replaces the old blocking `/convert`; each ArXiv ID gets its own job with 6 stages (searching → downloading → extracting → pre-cleaning → LLM curation → TTS synthesis)
- **Progress callbacks**: `llm_curate` and `synthesize`/`_edge_tts` accept a `progress_cb` parameter used by the web job runner to emit per-chunk log lines
- **Shared job store**: `audia.ui.jobs.JOBS` dict is imported by both `convert.py` and `research.py` routers so cancel and PDF-serve endpoints work across both flows
- **UI fixes**: "Convert another file" reset button only appears after conversion completes; PreviewPanel refactored to accept `title`/`pdfUrl` directly instead of a `Paper` object

## Version 0.1.2 (2026-03-29)

### ArXiv search robustness & CLI improvements

#### ArXiv search
- **HTTP fallback**: when the ArXiv export API returns HTTP 429, the search automatically retries via HTML scraping of `arxiv.org/search` — no user action required; a short one-line warning is shown instead of a full traceback
- **Date from arxiv ID**: publication date is now derived from the paper ID (`YYMM` prefix, e.g. `2603` → `Mar 2026`) instead of unreliable HTML scraping

#### PDF download
- **SDK-free download**: PDFs are now fetched directly from `https://arxiv.org/pdf/<id>` via `urllib`, bypassing the export API entirely and eliminating 429 rate-limit failures on download
- **Manual fallback prompt**: if a download still fails, the user is shown the `arxiv.org/abs/` link and prompted to provide a local PDF path to continue conversion

#### CLI output
- **Results table**: added a **Link** column (`https://arxiv.org/abs/<id>`) with `no_wrap=True` — URLs are never truncated so they remain clickable
- **ASCII banner**: running `audia` with no arguments now displays a block-art banner before the help text
- **Paper selection always prompted**: `audia listen` and `audia research` both show the results table and ask the user to pick papers; `--convert` flag still skips the prompt for power users

## Version 0.1.1 (2026-03-29)

### `listen` command pipeline overhaul

- **LLM query distillation**: raw transcribed speech is now passed through the configured LLM to extract a concise ArXiv search query (e.g. _"I would like to research agentic AI"_ → _"agentic AI research"_)
- `distill_search_query()` moved to `audia.agents.stt` (proper agent layer, not CLI)
- **Confirmation loop before searching**: after distillation the user sees the extracted query and can confirm (`y`), re-record (`r`), or quit (`q`) — prevents accidental searches from mis-transcriptions
- `typer.confirm()` replaced with explicit `typer.prompt()` to support the three-way choice

## Version 0.1.0 (2026-03-29)

### First fully working release: PDF to audio via mandatory LLM curation and edge-tts synthesis.

- Linear LangGraph pipeline: PDF extraction → heuristic clean → LLM curation → TTS synthesis
- LLM curation is mandatory; supports OpenAI and Anthropic backends via `AUDIA_LLM_PROVIDER`
- Chunk-level LLM curation with tail-context stitching for smooth spoken transitions
- edge-tts default TTS backend: async with 90 s per-chunk timeout and asyncio context fix for FastAPI
- Rich per-step progress output; `audia --version` flag
- Consistent run ID (`<pdf_stem>_<YYYYMMDD_HHMMSS>`) shared by audio filename and debug folder
- Debug text snapshots saved to `~/.audia/debug/<run_id>/` (raw, preprocessed, curated)
- SQLite storage for papers and audio files via SQLAlchemy
- FastAPI web UI (SPA) and Typer CLI with `convert`, `research`, `listen`, `serve`, `info` commands
- `.env.example` with full documentation of all `AUDIA_*` settings

## Version 0.0.1 (2026-03-28)

First release of the basic package structure