"""Tests for the heuristic text cleaner."""

from __future__ import annotations

import pytest


class TestHeuristicClean:
    def test_removes_numeric_citations(self):
        from audia.agents.text_cleaner import heuristic_clean

        text = "Deep learning [1] has transformed vision [2,3] and NLP [4–6]."
        result = heuristic_clean(text)
        assert "[1]" not in result
        assert "[2,3]" not in result
        assert "Deep learning" in result
        assert "has transformed vision" in result

    def test_removes_author_citations(self):
        from audia.agents.text_cleaner import heuristic_clean

        text = "This was shown by (Smith et al., 2022) in a landmark study (Jones, 2021)."
        result = heuristic_clean(text)
        assert "(Smith et al., 2022)" not in result
        assert "(Jones, 2021)" not in result
        assert "This was shown by" in result

    def test_summarises_acknowledgements(self):
        from audia.agents.text_cleaner import heuristic_clean

        text = (
            "Conclusion\nThis work concludes.\n\n"
            "Acknowledgements\n"
            "We thank the NSF for funding grant 12345, and our colleagues for helpful discussion.\n\n"
        )
        result = heuristic_clean(text)
        # Acknowledgements body should be replaced
        assert "NSF for funding grant" not in result
        assert "Acknowledgements" in result or "authors thank" in result

    def test_collapses_blank_lines(self):
        from audia.agents.text_cleaner import heuristic_clean

        text = "Paragraph one.\n\n\n\n\nParagraph two."
        result = heuristic_clean(text)
        assert "\n\n\n" not in result

    def test_preserves_body_text(self):
        from audia.agents.text_cleaner import heuristic_clean

        body = (
            "The transformer architecture introduced in 2017 uses self-attention mechanisms. "
            "This allows the model to weigh the relevance of each word."
        )
        result = heuristic_clean(body)
        assert "transformer architecture" in result
        assert "self-attention" in result


class TestSplitText:
    def test_no_split_for_short_text(self):
        from audia.agents.text_cleaner import _split_text

        text = "Short text."
        assert _split_text(text, max_chars=100) == [text]

    def test_splits_on_paragraph_boundary(self):
        from audia.agents.text_cleaner import _split_text

        para = "A" * 50
        text = (para + "\n\n") * 10
        chunks = _split_text(text, max_chars=200)
        for chunk in chunks:
            assert len(chunk) <= 250  # allow small overshoot at boundary
