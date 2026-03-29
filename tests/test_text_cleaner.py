"""Tests for the heuristic text cleaner and LLM curation helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────── heuristic_clean

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

    def test_removes_figure_labels(self):
        from audia.agents.text_cleaner import heuristic_clean

        text = "As shown below.\nFigure 3: Training loss curves.\nThe model converges."
        result = heuristic_clean(text)
        assert "Figure 3:" not in result
        assert "The model converges" in result

    def test_removes_table_labels(self):
        from audia.agents.text_cleaner import heuristic_clean

        text = "See results.\nTable 2. Comparison of methods.\nOur method wins."
        result = heuristic_clean(text)
        assert "Table 2." not in result

    def test_removes_latex_commands(self):
        from audia.agents.text_cleaner import heuristic_clean

        text = r"The \textbf{loss} is \emph{important} in \cite{goodfellow2016}."
        result = heuristic_clean(text)
        assert r"\textbf" not in result
        assert r"\emph" not in result
        assert r"\cite" not in result

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

    def test_empty_string(self):
        from audia.agents.text_cleaner import heuristic_clean
        assert heuristic_clean("") == ""


# ─────────────────────────────────────────────── _split_text

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
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 250  # small overshoot at boundary is ok

    def test_handles_single_oversized_paragraph(self):
        from audia.agents.text_cleaner import _split_text

        text = "X" * 500
        chunks = _split_text(text, max_chars=200)
        assert len(chunks) >= 1
        assert all(chunks)


# ─────────────────────────────────────────────── _extract_tail

class TestExtractTail:
    def test_short_text_returned_whole(self):
        from audia.agents.text_cleaner import _extract_tail

        text = "Short text."
        assert _extract_tail(text, max_chars=100) == text

    def test_long_text_trimmed_to_paragraph(self):
        from audia.agents.text_cleaner import _extract_tail

        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph which is long enough."
        tail = _extract_tail(text, max_chars=40)
        assert len(tail) <= 60
        assert "\n\n" not in tail[:5]


# ─────────────────────────────────────────────── _build_llm

class TestBuildLlm:
    def test_raises_import_error_for_openai_missing(self):
        from audia.config import Settings
        from audia.agents.text_cleaner import _build_llm

        cfg = Settings(data_dir="/tmp", llm_provider="openai", openai_api_key="sk-x")
        with patch.dict("sys.modules", {"langchain_openai": None}):
            with pytest.raises(ImportError, match=r"pip install audia\[openai\]"):
                _build_llm(cfg)

    def test_raises_runtime_error_missing_openai_key(self):
        from audia.config import Settings
        from audia.agents.text_cleaner import _build_llm

        cfg = Settings(data_dir="/tmp", llm_provider="openai", openai_api_key=None)
        fake_module = MagicMock()
        with patch.dict("sys.modules", {"langchain_openai": fake_module}):
            with pytest.raises(RuntimeError, match="AUDIA_OPENAI_API_KEY"):
                _build_llm(cfg)

    def test_raises_import_error_for_anthropic_missing(self):
        from audia.config import Settings
        from audia.agents.text_cleaner import _build_llm

        cfg = Settings(data_dir="/tmp", llm_provider="anthropic", anthropic_api_key="sk-ant-x")
        with patch.dict("sys.modules", {"langchain_anthropic": None}):
            with pytest.raises(ImportError, match=r"pip install audia\[anthropic\]"):
                _build_llm(cfg)

    def test_raises_runtime_error_missing_anthropic_key(self):
        from audia.config import Settings
        from audia.agents.text_cleaner import _build_llm

        cfg = Settings(data_dir="/tmp", llm_provider="anthropic", anthropic_api_key=None)
        fake_module = MagicMock()
        with patch.dict("sys.modules", {"langchain_anthropic": fake_module}):
            with pytest.raises(RuntimeError, match="AUDIA_ANTHROPIC_API_KEY"):
                _build_llm(cfg)

    def test_raises_for_unknown_provider(self):
        from audia.config import Settings
        from audia.agents.text_cleaner import _build_llm

        cfg = Settings(data_dir="/tmp", llm_provider="openai")
        cfg.__dict__["llm_provider"] = "unknown"
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            _build_llm(cfg)


# ─────────────────────────────────────────────── llm_curate

class TestLlmCurate:
    def _make_mock_llm(self, response: str):
        msg = MagicMock()
        msg.content = response
        llm = MagicMock()
        llm.invoke.return_value = msg
        return llm

    def test_single_chunk(self):
        from audia.config import Settings
        from audia.agents.text_cleaner import llm_curate

        cfg = Settings(data_dir="/tmp", llm_provider="openai",
                       openai_api_key="sk-x", llm_max_chunk_chars=10_000)
        llm = self._make_mock_llm("Curated text.")

        with patch("audia.agents.text_cleaner._build_llm", return_value=llm):
            result = llm_curate("Some input text.", cfg)

        assert result == "Curated text."
        assert llm.invoke.call_count == 1

    def test_multi_chunk_uses_tail_context(self):
        from audia.config import Settings
        from audia.agents.text_cleaner import llm_curate

        cfg = Settings(data_dir="/tmp", llm_provider="openai",
                       openai_api_key="sk-x", llm_max_chunk_chars=100)

        call_messages = []

        def capture_invoke(messages):
            call_messages.append(messages)
            msg = MagicMock()
            msg.content = f"Curated chunk {len(call_messages)}."
            return msg

        llm = MagicMock()
        llm.invoke.side_effect = capture_invoke

        para = "Word " * 30   # ~150 chars
        text = (para + "\n\n") * 3

        with patch("audia.agents.text_cleaner._build_llm", return_value=llm):
            result = llm_curate(text, cfg)

        assert llm.invoke.call_count >= 2
        second_user_msg = call_messages[1][-1]["content"]
        assert "CONTEXT" in second_user_msg
        assert "Do NOT repeat" in second_user_msg

    def test_chunks_joined_with_newlines(self):
        from audia.config import Settings
        from audia.agents.text_cleaner import llm_curate

        cfg = Settings(data_dir="/tmp", llm_provider="openai",
                       openai_api_key="sk-x", llm_max_chunk_chars=50)

        responses = iter(["Part one.", "Part two."])

        def mock_invoke(messages):
            msg = MagicMock()
            msg.content = next(responses)
            return msg

        llm = MagicMock()
        llm.invoke.side_effect = mock_invoke

        text = "A" * 40 + "\n\n" + "B" * 40

        with patch("audia.agents.text_cleaner._build_llm", return_value=llm):
            result = llm_curate(text, cfg)

        assert "Part one." in result
        assert "Part two." in result
        assert "\n\n" in result


# ─────────────────────────────────────────────── curate_text

class TestCurateText:
    def test_calls_heuristic_then_llm(self):
        from audia.config import Settings
        from audia.agents.text_cleaner import curate_text

        cfg = Settings(data_dir="/tmp", llm_provider="openai", openai_api_key="sk-x")
        msg = MagicMock()
        msg.content = "Final curated."
        llm = MagicMock()
        llm.invoke.return_value = msg

        with patch("audia.agents.text_cleaner._build_llm", return_value=llm):
            result = curate_text("Input [1] text.", cfg)

        assert result == "Final curated."
        assert llm.invoke.called

