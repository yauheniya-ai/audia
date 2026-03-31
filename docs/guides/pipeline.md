# Pipeline

audia uses a [LangGraph](https://github.com/langchain-ai/langgraph) linear state machine to
convert a PDF into audio. The graph runs in four steps; STT + LLM query distillation are
optional pre-steps that run before the graph when using voice or text queries.

---

## Entry points

| Entry point | Command |
|---|---|
| **Voice input** | `audia listen` |
| **Text query** | `audia research "<query>"` |
| **Local PDF** | `audia convert paper.pdf` |

```
 [voice input]           [text query]
      │                       │
      ▼                       │
  faster-whisper STT          │
      │                       │
      ▼                       │
  LLM query distillation      │   ← extracts concise ArXiv search terms
      │                       │      from natural speech
      ▼                       │
  Confirm / re-record?        │
      │  yes                  │
      ▼                       ▼
Step 0 ─ ArXiv search    (or local PDF)
 │        fetch metadata, download PDF
 │
 ▼
Step 1 ─ PDF extraction
 │        PyMuPDF: text + metadata per page
 │
 ▼
Step 2 ─ Heuristic pre-pass
 │        Regex: strip citations, LaTeX artefacts, figure captions
 │
 ▼
Step 3 ─ LLM curation
 │        Chunked LLM pass: math → English, tables → sentences,
 │        smooth spoken transitions via tail-context stitching
 ▼
Step 4 ─ TTS synthesis
          edge-tts / kokoro / OpenAI: split into ~3800-char chunks,
          synthesise in parallel, concatenate → .mp3
```

---

## Step 1 — PDF extraction (`pdf_processor.py`)

Uses [PyMuPDF](https://pymupdf.readthedocs.io/) to extract text and metadata from every page.
The result is a `PDFResult` dataclass with:

- `text` — full extracted text
- `title` — document title (from metadata or first heading)
- `num_pages` — page count

---

## Step 2 — Heuristic pre-pass (`text_cleaner.py`)

A fast regex-based step that strips common noise before the LLM sees the text:

- Inline citations like `[1]`, `[Smith et al. 2024]`
- LaTeX math commands (`\alpha`, `\frac{...}{...}`, display equations)
- Figure and table captions
- Running headers / footers
- Excess whitespace

This step reduces LLM token cost and prevents the model from being distracted by artefacts.

---

## Step 3 — LLM curation (`text_cleaner.py — llm_curate`)

The core of audia. Long texts are split at paragraph boundaries into chunks of
`AUDIA_LLM_MAX_CHUNK_CHARS` characters. Each chunk is sent to the configured LLM with:

- A system prompt instructing the model to rewrite for spoken audio
- For chunks after the first: the **tail of the previous curated chunk** as transition context

This *tail-context stitching* produces smooth spoken transitions across chunk boundaries.

The system prompt instructs the LLM to:

1. Rewrite mathematical notation into plain English
2. Convert tables into narrative sentences
3. Condense acknowledgements to one sentence
4. Remove citation artefacts entirely
5. Maintain a natural, engaging speaking tone

---

## Step 4 — TTS synthesis (`tts.py`)

The curated text is split into `AUDIA_TTS_CHUNK_CHARS`-character chunks and sent to the
selected TTS backend. For `edge-tts`, synthesis is async with a 90-second per-chunk timeout.
All chunk audio files are concatenated via `soundfile` into one final `.mp3`.

---

## State (`state.py`)

The LangGraph pipeline uses a typed `TypedDict` state:

| Key | Type | Description |
|---|---|---|
| `pdf_path` | `str` | Input PDF path |
| `raw_text` | `str` | PyMuPDF output |
| `preprocessed_text` | `str` | After heuristic pass |
| `cleaned_text` | `str` | After LLM curation |
| `audio_path` | `str` | Final .mp3 path |
| `title` | `str` | Extracted document title |
| `num_pages` | `int` | Page count |
| `error` | `str \| None` | Error message if a node fails |

---

## Debug output

Every run saves text snapshots for inspection:

```
~/.audia/debug/<run_id>/
  1_raw.txt            ← PyMuPDF output
  2_preprocessed.txt   ← after heuristic pass
  3_curated.txt        ← after LLM curation
```
