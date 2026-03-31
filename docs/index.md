# audia

**Turn documents and ideas into audio, intelligently.**

audia is an agentic Python package that converts PDFs — academic papers, reports, regulations —
into podcast-style audio files. An LLM rewrites the content into natural spoken language
(math in plain English, tables as sentences, citations removed) before passing it to a TTS engine.

```{toctree}
:maxdepth: 1
:caption: Getting Started

installation
quickstart
configuration
```

```{toctree}
:maxdepth: 1
:caption: Guides

guides/pipeline
guides/cli
guides/web_ui
guides/tts_backends
guides/llm_backends
guides/storage
```

```{toctree}
:maxdepth: 1
:caption: API Reference

api/audia
api/config
api/agents
api/storage
api/cli
api/ui
```

```{toctree}
:maxdepth: 1
:caption: Project

changelog
```

---

## At a glance

| Feature | Detail |
|---|---|
| **LLM curation** | Mandatory pass rewrites math, condenses tables, removes citations |
| **TTS backends** | `edge-tts` (free default), `kokoro` (local), OpenAI TTS |
| **LLM backends** | OpenAI, Anthropic |
| **ArXiv research** | Search → select → convert in one command |
| **Voice input** | Record a spoken query → STT → LLM distillation → ArXiv search |
| **Web UI** | FastAPI backend + React/Tailwind SPA |
| **CLI** | `convert`, `research`, `listen`, `serve`, `info` |
| **Storage** | SQLite via SQLAlchemy; papers + audio files |
| **Python** | 3.10 – 3.13 |

```{admonition} Quick install
:class: tip

    pip install audia
```
