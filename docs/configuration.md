# Configuration

All settings are loaded from environment variables (or a `.env` file) using the `AUDIA_` prefix.
Run `audia info` at any time to inspect the active configuration.

```bash
cp .env.example .env   # create your .env from the template
audia info             # verify active settings
```

---

## LLM provider (required)

LLM curation is mandatory — audia cannot convert documents without it.

### Option A — OpenAI

```dotenv
AUDIA_LLM_PROVIDER=openai
AUDIA_OPENAI_API_KEY=sk-...
AUDIA_LLM_MODEL=gpt-4o-mini           # default; gpt-4o for higher quality
```

Custom endpoint (Azure OpenAI, corporate proxy, or any OpenAI-compatible URL):

```dotenv
AUDIA_OPENAI_API_BASE=https://your-org.openai.azure.com/
```

### Option B — Anthropic

```dotenv
AUDIA_LLM_PROVIDER=anthropic
AUDIA_ANTHROPIC_API_KEY=sk-ant-...
AUDIA_LLM_MODEL=claude-3-5-haiku-20241022
```

Custom endpoint:

```dotenv
AUDIA_ANTHROPIC_API_BASE=https://your-proxy.example.com/
```

### Shared LLM settings

| Variable | Default | Description |
|---|---|---|
| `AUDIA_LLM_MAX_CHUNK_CHARS` | `8000` | Characters per LLM curation chunk |
| `AUDIA_LLM_TEMPERATURE` | `0.1` | 0 = deterministic, 1 = creative |

---

## TTS backend

| Variable | Default | Description |
|---|---|---|
| `AUDIA_TTS_BACKEND` | `edge-tts` | `edge-tts` \| `kokoro` \| `openai` |
| `AUDIA_TTS_VOICE` | `en-US-AriaNeural` | Voice name (backend-specific) |
| `AUDIA_TTS_RATE` | `+0%` | edge-tts speaking rate, e.g. `+10%` |
| `AUDIA_TTS_CHUNK_CHARS` | `3800` | Characters per TTS chunk |

**edge-tts voices** (no key required):

```dotenv
AUDIA_TTS_VOICE=en-US-AriaNeural   # female, US
AUDIA_TTS_VOICE=en-US-GuyNeural    # male, US
AUDIA_TTS_VOICE=en-GB-SoniaNeural  # female, British
```

List all available voices: `edge-tts --list-voices`

**Kokoro** (`pip install audia[kokoro]`):

```dotenv
AUDIA_TTS_BACKEND=kokoro
AUDIA_TTS_VOICE=af_heart
```

**OpenAI TTS**:

```dotenv
AUDIA_TTS_BACKEND=openai
AUDIA_TTS_VOICE=nova    # alloy | echo | nova | shimmer | onyx | fable
```

---

## STT (voice input)

Requires: `pip install audia[stt]` (included in core dependencies).

| Variable | Default | Description |
|---|---|---|
| `AUDIA_STT_MODEL` | `base` | `tiny` \| `base` \| `small` \| `medium` \| `large-v3` |
| `AUDIA_STT_DEVICE` | `cpu` | `cpu` \| `cuda` |
| `AUDIA_STT_RECORD_SECONDS` | `30` | Max microphone recording duration |

---

## Storage

| Variable | Default | Description |
|---|---|---|
| `AUDIA_DATA_DIR` | `~/.audia` | Root directory for DB, audio, uploads, debug |

```
~/.audia/
  audia.db          ← SQLite database
  audio/            ← generated .mp3 files
  uploads/          ← uploaded PDFs
  debug/            ← per-run debug text snapshots
```

---

## Web server

| Variable | Default | Description |
|---|---|---|
| `AUDIA_SERVER_HOST` | `127.0.0.1` | FastAPI bind host |
| `AUDIA_SERVER_PORT` | `8000` | FastAPI bind port |
| `AUDIA_RELOAD` | `false` | Uvicorn auto-reload (dev only) |

---

## Research

| Variable | Default | Description |
|---|---|---|
| `AUDIA_ARXIV_MAX_RESULTS` | `10` | Max papers returned per ArXiv query |

---

## Full `.env.example`

See the annotated [`.env.example`](https://github.com/yauheniya-ai/audia/blob/main/pypi/.env.example) for a complete template.
