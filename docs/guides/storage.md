# Storage

audia stores all data in a local SQLite database managed by SQLAlchemy.

## Location

Default: `~/.audia/audia.db`

Override with:

```dotenv
AUDIA_DATA_DIR=/path/to/your/data
```

The full directory structure:

```
~/.audia/
  audia.db          ← SQLite database
  audio/            ← generated .mp3 files
  uploads/          ← PDFs uploaded via the web UI
  debug/            ← per-run text snapshots
    <run_id>/
      1_raw.txt
      2_preprocessed.txt
      3_curated.txt
```

---

## Schema

### `papers`

Stores academic papers (from ArXiv or uploaded manually).

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `title` | VARCHAR(512) | Document title |
| `authors` | TEXT | JSON array of strings |
| `abstract` | TEXT | Abstract text |
| `arxiv_id` | VARCHAR(64) | ArXiv ID (e.g. `2603.12345`) |
| `pdf_path` | TEXT | Local path to the PDF |
| `pdf_url` | TEXT | Remote URL |
| `created_at` | DATETIME | UTC timestamp |

### `audio_files`

Generated audio files, optionally linked to a paper.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `paper_id` | INTEGER FK | → `papers.id` (SET NULL on delete) |
| `filename` | TEXT | File name |
| `file_path` | TEXT | Absolute path to `.mp3` |
| `tts_backend` | VARCHAR | `edge-tts` \| `kokoro` \| `openai` |
| `tts_voice` | VARCHAR | Voice name used |
| `duration_seconds` | FLOAT | Audio duration |
| `created_at` | DATETIME | UTC timestamp |

### `research_sessions`

Stores ArXiv query sessions.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `query` | TEXT | User search query |
| `created_at` | DATETIME | UTC timestamp |

### `user_settings`

Key-value store for persisted configuration (LLM provider, TTS backend, etc.).

| Column | Type | Notes |
|---|---|---|
| `key` | VARCHAR PK | Setting name |
| `value` | TEXT | Setting value |

---

## Exploring the database

Use the bundled `explore_db.py` script for a full terminal dump:

```bash
python scripts/explore_db.py
python scripts/explore_db.py --db /custom/path/audia.db
```

The script prints table schema, foreign keys, row counts, and all cell values using only
the Python standard library (no extra dependencies).
