"""
PDF text extraction using PyMuPDF (fitz).

Handles:
- Multi-page PDFs
- Basic heuristic removal of headers, footers, page numbers,
  references section, and acknowledgements section.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple


class ExtractionResult(NamedTuple):
    text: str
    num_pages: int
    title: str


# ──────────────────────────────────────────────────────── constants
_REFERENCES_PATTERNS = re.compile(
    r"^\s*references?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_ACKNOWLEDGEMENTS_PATTERNS = re.compile(
    r"^\s*acknowledgements?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
# Lines that look like isolated page numbers (e.g. "— 3 —", "3", "Page 3")
_PAGE_NUMBER_LINE = re.compile(r"^\s*(?:page\s+)?\d+\s*$", re.IGNORECASE)

# Repeated short lines across pages are likely headers/footers;
# collect them and strip later.
_MAX_HEADER_FOOTER_LENGTH = 80


def extract_text(pdf_path: str | Path) -> ExtractionResult:
    """
    Extract and pre-clean text from a PDF.

    Returns an ExtractionResult with cleaned text, page count, and guessed title.
    Raises FileNotFoundError if the PDF does not exist.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise ImportError("PyMuPDF is required: pip install PyMuPDF") from e

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    doc = fitz.open(str(pdf_path))
    num_pages = len(doc)

    # 1. Extract text per page
    page_texts: list[str] = []
    for page in doc:
        page_texts.append(page.get_text("text"))  # type: ignore[attr-defined]

    doc.close()

    # 2. Detect repeated short lines (header / footer candidates)
    candidate_hf = _detect_header_footer_lines(page_texts)

    # 3. Clean each page
    cleaned_pages: list[str] = []
    for text in page_texts:
        cleaned = _clean_page(text, candidate_hf)
        if cleaned.strip():
            cleaned_pages.append(cleaned)

    full_text = "\n\n".join(cleaned_pages)

    # 4. Try to guess title from first non-empty line
    title = _guess_title(full_text, pdf_path.stem)

    # 5. Trim everything after References section
    full_text = _trim_references_and_beyond(full_text)

    return ExtractionResult(
        text=full_text,
        num_pages=num_pages,
        title=title,
    )


# ──────────────────────────────────────────────────────── helpers

def _detect_header_footer_lines(page_texts: list[str]) -> set[str]:
    """
    Identify lines that appear verbatim in ≥50% of pages AND are short.
    These are most likely running headers/footers.
    """
    if len(page_texts) < 2:
        return set()

    from collections import Counter

    line_counts: Counter[str] = Counter()
    for text in page_texts:
        seen_on_this_page: set[str] = set()
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and len(stripped) <= _MAX_HEADER_FOOTER_LENGTH:
                if stripped not in seen_on_this_page:
                    line_counts[stripped] += 1
                    seen_on_this_page.add(stripped)

    threshold = max(2, len(page_texts) * 0.4)
    return {line for line, cnt in line_counts.items() if cnt >= threshold}


def _clean_page(text: str, header_footer_lines: set[str]) -> str:
    """Remove header/footer lines and lone page numbers from a page."""
    lines = text.splitlines()
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped in header_footer_lines:
            continue
        if _PAGE_NUMBER_LINE.match(stripped):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def _trim_references_and_beyond(text: str) -> str:
    """
    Remove the References section and everything after it.
    Keep the Acknowledgements section intact so the LLM can summarise it.
    """
    match = _REFERENCES_PATTERNS.search(text)
    if match:
        text = text[: match.start()].rstrip()
    return text


def _guess_title(text: str, fallback: str) -> str:
    """Return the first meaningful line of the document as the title."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and len(stripped) > 8:
            return stripped[:200]
    return fallback
