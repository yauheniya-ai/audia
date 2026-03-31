# Web UI

The audia web UI is a FastAPI backend serving a React + Tailwind SPA.

## Starting the server

```bash
audia serve
# → http://127.0.0.1:8000
```

Or with custom options:

```bash
audia serve --port 8080 --no-browser
```

---

## Tabs

### Convert

Upload a PDF (drag-and-drop or file browser). The PDF opens immediately in the preview panel.
Click **Convert** to start the pipeline; progress streams in real time with per-stage and
per-chunk updates. Cancel any running job with the **Cancel** button.

### Research

Enter an ArXiv query (text or voice). Use **Normalize query** to let the LLM distil your
raw query into concise search terms. Select papers from the results table, then click
**Convert selected**. Each paper runs as an independent background job.

### Configuration

Set the LLM provider / model, TTS backend / voice. Settings are saved to the database and
persist across server restarts. The animated pipeline diagram illustrates where each component
fits in the flow.

### Library (Database)

Browse all tables (`papers`, `audio_files`, `research_sessions`, `user_settings`).
All displayed fields are **inline-editable** — click a cell to edit, Enter to commit,
Escape to cancel. Hide/show columns with the eye icon. Clicking a paper ID opens its PDF
in the preview panel.

---

## API endpoints (summary)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/convert/enqueue` | Enqueue a PDF conversion job |
| `GET` | `/api/convert/jobs/{id}` | Poll job status and log stream |
| `DELETE` | `/api/convert/jobs/{id}` | Cancel a running job |
| `POST` | `/api/research/enqueue` | Enqueue ArXiv research jobs |
| `POST` | `/api/research/transcribe` | Transcribe uploaded audio |
| `POST` | `/api/research/normalize` | LLM-distil a search query |
| `GET` | `/api/library/papers` | List all papers |
| `PATCH` | `/api/library/papers/{id}` | Update paper fields |
| `GET` | `/api/library/audio` | List all audio files |
| `PATCH` | `/api/library/audio/{id}` | Update audio file fields |
| `GET` | `/api/library/research_sessions` | List research sessions |
| `GET` | `/api/library/user_settings` | List user settings |
| `GET` | `/api/settings` | Load persisted configuration |
| `PUT` | `/api/settings` | Save configuration |

Full interactive API docs are available at `http://127.0.0.1:8000/docs` (Swagger UI) while
the server is running.
