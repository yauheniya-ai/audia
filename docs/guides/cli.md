# CLI Reference

audia ships a [Typer](https://typer.tiangolo.com/) CLI with [Rich](https://rich.readthedocs.io/)
output.

```bash
audia --help
```

---

## `audia convert`

Convert one or more local PDF files to audio.

```bash
audia convert [PATHS]... [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--output`, `-o` | `~/.audia/audio` | Output directory for .mp3 files |
| `--provider` | config | LLM provider override (`openai` \| `anthropic`) |
| `--model` | config | LLM model override |
| `--tts-backend` | config | TTS backend override |
| `--tts-voice` | config | TTS voice override |

**Examples:**

```bash
audia convert paper.pdf
audia convert a.pdf b.pdf --output ~/audiobooks
audia convert report.pdf --provider anthropic --model claude-3-5-sonnet-20241022
```

---

## `audia research`

Search ArXiv, select papers, and convert them to audio.

```bash
audia research [QUERY] [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--max-results`, `-n` | `10` | Max papers to retrieve |
| `--convert` | `False` | Skip interactive selection and convert all results |
| `--provider` | config | LLM provider override |
| `--model` | config | LLM model override |
| `--tts-backend` | config | TTS backend override |

**Examples:**

```bash
audia research "retrieval augmented generation"
audia research "diffusion models" --max-results 5 --convert
```

---

## `audia listen`

Record a spoken query, transcribe it, distil it with the LLM, confirm, then run the research
pipeline.

```bash
audia listen [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--seconds` | `30` | Max recording duration |
| `--max-results`, `-n` | `10` | Max ArXiv results |

After transcription, you will be prompted to:
- `y` — confirm and search
- `r` — re-record
- `q` — quit

---

## `audia serve`

Start the FastAPI web UI.

```bash
audia serve [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--host` | `127.0.0.1` | Bind host |
| `--port` | `8000` | Bind port |
| `--reload` | `False` | Enable Uvicorn auto-reload (dev) |
| `--no-browser` | `False` | Don't open a browser tab on start |

---

## `audia info`

Print all active settings — useful for verifying your `.env` is loaded.

```bash
audia info
```

---

## `audia --version`

Print the installed version and exit.

```bash
audia --version
```
