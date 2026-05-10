# <img src="https://api.iconify.design/streamline-freehand:help-headphones-customer-support-human.svg?color=%23a855f7" width="24" height="24"> audia — turn your ideas into audio

<div align="center">

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-purple.svg)](https://opensource.org/licenses/MIT)
[![PyPI version](https://img.shields.io/pypi/v/audia?color=blue&label=PyPI)](https://pypi.org/project/audia/)
[![PyPI Downloads](https://img.shields.io/pypi/dm/audia)](https://pypistats.org/packages/audia)
[![Tests](https://github.com/yauheniya-ai/audia/actions/workflows/tests.yml/badge.svg)](https://github.com/yauheniya-ai/audia/actions/workflows/tests.yml)
[![Coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/yauheniya-ai/88593f7c590674e0f8c99c66c7b58b36/raw/coverage.json)](https://github.com/yauheniya-ai/audia/actions/workflows/tests.yml)
[![GitHub last commit](https://img.shields.io/github/last-commit/yauheniya-ai/audia)](https://github.com/yauheniya-ai/audia/commits/main)

</div>

**audia** is an agentic Python package that converts PDFs — academic papers, reports, regulations — into podcast-style audio files.
It uses an LLM to rewrite content into natural spoken language (math in plain English, tables as sentences, no citations) before passing it to a TTS engine, so the result actually sounds good when read aloud.

<p align="center">
  <img src="https://raw.githubusercontent.com/yauheniya-ai/audia/main/docs/images/Screenshot_CLI.png" width="100%" />
  <em>The audia CLI</em>
</p>

## Features

- **LLM-curated text** — mandatory LLM pass rewrites math notation, condenses tables and acknowledgements, removes citation artefacts, and ensures smooth spoken flow
- **Chunk-level stitching** — long documents are split at paragraph boundaries; each chunk receives the tail of the previous curated output as transition context
- **ArXiv research** — search papers by query and convert them to audio in one command
- **Voice input (STT)** — record a spoken query to trigger an ArXiv search
- **Multiple TTS backends** — `edge-tts` (default, free), `kokoro` (local), or OpenAI TTS
- **Multiple LLM backends** — OpenAI (`gpt-4o-mini` default) or Anthropic
- **CLI** — `audia convert`, `research`, `listen`, `serve`, `info`
- **Web UI** — FastAPI backend + SPA frontend
- **Local storage** — SQLite database for papers and audio files via SQLAlchemy
- **Debug output** — every run saves raw, preprocessed, and curated text to `~/.audia/debug/<run_id>/`

## Tech Stack

**Backend**
- ![Python](https://api.iconify.design/devicon:python.svg?height=16) [Python](https://www.python.org) 3.10+ — package language
- ![FastAPI](https://api.iconify.design/devicon:fastapi.svg?height=16) [FastAPI](https://fastapi.tiangolo.com) — backend for the web UI
- ![LangGraph](https://api.iconify.design/simple-icons:langgraph.svg?height=16) [LangGraph](https://github.com/langchain-ai/langgraph) — agentic pipeline orchestration (PDF → preprocess → LLM curate → TTS)
- ![LangChain](https://api.iconify.design/simple-icons:langchain.svg?height=16) [LangChain](https://github.com/langchain-ai/langchain) — LLM abstraction
    - Current support for LLMs from ![Anthropic](https://api.iconify.design/logos:claude-icon.svg?height=16) Anthropic, ![Google](https://api.iconify.design/vscode-icons:file-type-gemini.svg?height=16) Google, and ![OpenAI](https://api.iconify.design/simple-icons:openai.svg?height=16) OpenAI
- ![Microsoft](https://api.iconify.design/logos:microsoft-icon.svg?height=16) [edge-tts](https://github.com/rany2/edge-tts) — default TTS backend, no API key required
- ![Hugging Face](https://api.iconify.design/devicon:huggingface.svg?height=16) [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — STT for voice input (by SYSTRAN on Hugging Face)
- ![PyMuPDF](https://api.iconify.design/arcticons:mupdf.svg?height=16) [PyMuPDF](https://pymupdf.readthedocs.io/) — PDF text extraction
- ![SQLite](https://api.iconify.design/devicon:sqlite.svg?height=16) [SQLite](https://sqlite.org/docs.html) — local database for papers and audio files

**Frontend**
- ![React](https://api.iconify.design/devicon:react.svg?height=16) [React](https://react.dev) — interactive frontend
- ![Vite](https://api.iconify.design/devicon:vitejs.svg?height=16) [Vite](https://vite.dev) — fast dev server and production bundler
- ![Tailwind CSS](https://api.iconify.design/devicon:tailwindcss.svg?height=16) [Tailwind CSS](https://v2.tailwindcss.com/docs) — utility-first styling
- ![TypeScript](https://api.iconify.design/devicon:typescript.svg?height=16) [TypeScript](https://www.typescriptlang.org/docs/) — type-safe component and API code

**CLI**
- ![Typer](https://api.iconify.design/devicon:typer.svg?height=16) [Typer](https://typer.tiangolo.com/) + [Rich](https://rich.readthedocs.io/) — CLI with coloured progress output

**Packaging**
- ![PyPI](https://api.iconify.design/devicon:pypi.svg?height=16) [PyPI](https://pypi.org/project/audia/) — distributed as an installable Python package

## Installation

```bash
pip install audia
```

For CLI usage, [pipx](https://pipx.pypa.io/) is recommended — it installs `audia` in an isolated environment while exposing the command globally:

```bash
pipx install audia
```

Optional extras:

| Extra | Installs |
|---|---|
| `kokoro` | local Kokoro TTS |

```bash
pip install "audia[kokoro]"
```

## Configuration

Copy `.env.example` to `.env` in your working directory and set your API key:

```bash
cp .env.example .env
```

Minimum required settings:

```dotenv
AUDIA_LLM_PROVIDER=openai           # or anthropic
AUDIA_OPENAI_API_KEY=sk-...
```

All settings use the `AUDIA_` prefix. Run `audia info` to see the active configuration.

## Quick Start

**Show active configuration:**

```bash
audia info
```

**Convert a local PDF:**

```bash
audia convert paper.pdf
```

**Convert multiple PDFs to a specific output folder:**

```bash
audia convert paper1.pdf paper2.pdf --output ~/audiobooks
```

**Search ArXiv and convert the top results:**

```bash
audia research "retrieval augmented generation" --max-results 3 --convert
```

**Start the web UI:**

```bash
audia serve
# → http://localhost:8000
```

<p align="center">
  <img src="https://raw.githubusercontent.com/yauheniya-ai/audia/main/docs/images/ScreenRecordingAudia.webp" width="100%" />
  <em>The audia UI</em>
</p>

## Pipeline

The pipeline can be entered in three ways:

| Entry point | Command |
|---|---|
| Voice input | `audia listen` — record speech, LLM distils a search query, confirm, then runs the full pipeline |
| Text query | `audia research "retrieval augmented generation"` — search ArXiv by text, select papers, run pipeline |
| Local PDF | `audia convert paper.pdf` — skip Steps 0, go straight to extraction |

When starting from voice or text, the full five-step [LangGraph](https://github.com/langchain-ai/langgraph) pipeline runs. For local PDFs, Steps 1–4 run directly:

```
 [voice input]          [text query]
      │                      │
      ▼                      │
  Microphone                 │
  (faster-whisper STT)       │
      │                      │
      ▼                      │
  LLM query distillation     │        ← extracts concise ArXiv search terms
      │                      │           from natural speech
      ▼                      │
  Confirm / re-record?       │
      │  yes                 │
      ▼                      ▼
Step 0 — ArXiv search    (or use local PDF)
 │        arxiv API: fetch metadata, download PDF
 │
 ▼
Step 1 — PDF extraction       PyMuPDF: text + metadata per page
 │
 ▼
Step 2 — Heuristic pre-pass   Regex: strip citations, LaTeX commands, figure captions
 │
 ▼
Step 3 — LLM curation         Chunked LLM pass: math → English, tables → sentences,
 │                             smooth spoken transitions between chunks
 ▼
Step 4 — TTS synthesis        edge-tts (or kokoro / OpenAI): split into ~3800-char
                               chunks, synthesise, concatenate → .mp3
```

Output files for a run on `2025_Xu+.pdf`:

```
~/.audia/audio/2025_Xu+_20260329_084445.mp3
~/.audia/debug/2025_Xu+_20260329_084445/
    1_raw.txt            ← PyMuPDF output
    2_preprocessed.txt   ← after heuristic pass
    3_curated.txt        ← after LLM curation
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-change`)
3. Make your changes
4. Run the test suite: `pytest --cov=src --cov-report=term-missing`
5. Submit a pull request

## License

MIT — see [LICENSE](https://raw.githubusercontent.com/yauheniya-ai/audia/main/LICENSE) for details.