"""
Shared in-memory job store for background conversion tasks.

Both /api/convert/enqueue and /api/research/enqueue write here.
The status endpoint and the cancel endpoint read/write here.
"""

from __future__ import annotations

from typing import Any, Dict

# job_id (hex str) → job state dict
# Keys present in every job:
#   status:      "running" | "done" | "error" | "cancelled"
#   stage:       current stage key string
#   stage_label: human-readable label
#   progress:    int 0-100
#   log:         list[str] – terminal-style lines, appended as work progresses
#   stats:       dict of ad-hoc numbers (raw_chars, num_pages, …)
#   result:      dict | None – final result payload when done
#   error:       str | None
#   cancelled:   bool – set True by the cancel endpoint
#   pdf_path:    str | None – absolute path on disk once PDF is available
#   pdf_title:   str | None – display title for the PDF
#   paper_id:    int | None – DB row id once the paper is persisted

JOBS: Dict[str, Dict[str, Any]] = {}
