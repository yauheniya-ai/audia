# Quick Start

## 1. Configure

Copy `.env.example` and set your LLM API key:

```bash
cp .env.example .env
```

Minimum required:

```dotenv
AUDIA_LLM_PROVIDER=openai
AUDIA_OPENAI_API_KEY=sk-...
```

## 2. Convert a local PDF

```bash
audia convert paper.pdf
```

Output: `~/.audia/audio/<stem>_<timestamp>.mp3`

## 3. Search ArXiv and convert

```bash
audia research "attention is all you need" --max-results 3 --convert
```

## 4. Voice input

```bash
audia listen
```

Record your query (up to 30 s), confirm the LLM-distilled search terms, pick papers, convert.

## 5. Web UI

```bash
audia serve
# → http://127.0.0.1:8000
```

## 6. Show active config

```bash
audia info
```

---

```{admonition} Output location
:class: note

All audio files land in `~/.audia/audio/`.
Debug snapshots (raw / preprocessed / curated text) are saved under `~/.audia/debug/<run_id>/`.
Override the root with `AUDIA_DATA_DIR=/your/path`.
```
