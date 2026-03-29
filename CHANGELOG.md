# CHANGELOG

## Version 0.1.1 (2026-03-29)


## Version 0.1.0 (2026-03-29)

First fully working release: PDF to audio via mandatory LLM curation and edge-tts synthesis.

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