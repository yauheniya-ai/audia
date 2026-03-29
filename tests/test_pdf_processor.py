"""Tests for PDF text extraction."""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_fake_pdf(texts: list[str]) -> str:
    """Return the path to a minimal fake PDF (just bytes, not real PDF rendering)."""
    # We mock fitz, so we only need a path that exists.
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4 fake\n%%EOF\n")
        return f.name


def _mock_fitz(page_texts: list[str]):
    """Return a context-manager patch for fitz.open() that returns fake pages."""
    fake_pages = []
    for text in page_texts:
        page = MagicMock()
        page.get_text.return_value = text
        fake_pages.append(page)

    fake_doc = MagicMock()
    fake_doc.__len__ = lambda self: len(fake_pages)
    fake_doc.__iter__ = lambda self: iter(fake_pages)
    fake_doc.close = MagicMock()

    return patch("fitz.open", return_value=fake_doc)


# ── tests ─────────────────────────────────────────────────────────────────────

class TestExtractText:
    def test_basic_extraction(self, tmp_path):
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")

        pages = ["Page one content.", "Page two content."]
        with _mock_fitz(pages):
            from audia.agents.pdf_processor import extract_text
            result = extract_text(str(pdf_path))

        assert "Page one content" in result.text
        assert "Page two content" in result.text
        assert result.num_pages == 2

    def test_file_not_found(self):
        from audia.agents.pdf_processor import extract_text

        with pytest.raises(FileNotFoundError):
            extract_text("/nonexistent/path/paper.pdf")

    def test_header_footer_removal(self, tmp_path):
        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")

        # "Journal of AI" appears on every page – should be removed
        header = "Journal of AI Research"
        pages = [
            f"{header}\nIntroduction\n{header}\nSome content here.\n",
            f"{header}\nMethod\n{header}\nMore content here.\n",
            f"{header}\nConclusion\n{header}\nFinal content.\n",
        ]
        with _mock_fitz(pages):
            from audia.agents.pdf_processor import extract_text
            result = extract_text(str(pdf_path))

        # Header should be stripped from the body text
        assert result.text.count(header) == 0 or result.text.count(header) < 3

    def test_references_trimmed(self, tmp_path):
        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")

        pages = [
            "Abstract\nThis is the abstract.",
            "Introduction\nThis is the body.",
            "References\n[1] Some author. Some title. 2023.",
        ]
        with _mock_fitz(pages):
            from audia.agents.pdf_processor import extract_text
            result = extract_text(str(pdf_path))

        assert "[1] Some author" not in result.text

    def test_title_extraction(self, tmp_path):
        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")

        pages = ["Attention Is All You Need\nAuthors: Vaswani et al.\nAbstract:"]
        with _mock_fitz(pages):
            from audia.agents.pdf_processor import extract_text
            result = extract_text(str(pdf_path))

        assert "Attention Is All You Need" in result.title
