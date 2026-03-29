"""Tests for ArxivSearcher (research.py) — all network calls are mocked."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _make_arxiv_result(
    short_id="2301.00001v1",
    title="Test Paper",
    authors=("Alice", "Bob"),
    abstract="An abstract.",
    pdf_url="https://arxiv.org/pdf/2301.00001",
    published=date(2023, 1, 1),
):
    r = MagicMock()
    r.get_short_id.return_value = short_id
    r.title = title
    # Each author mock must have a .name attribute (not just MagicMock(name=...))
    author_mocks = []
    for a in authors:
        m = MagicMock()
        m.name = a
        author_mocks.append(m)
    r.authors = author_mocks
    r.summary = abstract
    r.pdf_url = pdf_url
    r.published = MagicMock()
    r.published.date.return_value = published
    return r


def _build_arxiv_mock(results):
    mock_arxiv = MagicMock()
    mock_arxiv.Client.return_value.results.return_value = iter(results)
    mock_arxiv.Search = MagicMock(return_value=MagicMock())
    mock_arxiv.SortCriterion = MagicMock()
    mock_arxiv.SortCriterion.Relevance = "relevance"
    return mock_arxiv


class TestArxivSearcherSearch:
    """ArxivSearcher.search() with mocked arxiv SDK."""

    def test_search_returns_paper_fields(self, tmp_settings):
        from audia.agents.research import ArxivSearcher

        fake = _make_arxiv_result()
        mock_arxiv = _build_arxiv_mock([fake])

        with patch("audia.agents.research.get_settings", return_value=tmp_settings), \
             patch.dict("sys.modules", {"arxiv": mock_arxiv}):
            searcher = ArxivSearcher(max_results=5)
            results = searcher.search("transformers")

        assert len(results) == 1
        p = results[0]
        assert p.title == "Test Paper"
        assert p.arxiv_id == "2301.00001v1"
        assert p.authors == ["Alice", "Bob"]
        assert p.published == "2023-01-01"
        assert p.abstract == "An abstract."
        assert p.pdf_url == "https://arxiv.org/pdf/2301.00001"

    def test_search_empty_results(self, tmp_settings):
        from audia.agents.research import ArxivSearcher

        mock_arxiv = _build_arxiv_mock([])
        with patch("audia.agents.research.get_settings", return_value=tmp_settings), \
             patch.dict("sys.modules", {"arxiv": mock_arxiv}):
            searcher = ArxivSearcher(max_results=5)
            results = searcher.search("zzz_nonexistent_zzz")

        assert results == []

    def test_search_multiple_papers(self, tmp_settings):
        from audia.agents.research import ArxivSearcher

        fakes = [
            _make_arxiv_result(short_id=f"2301.0000{i}v1", title=f"Paper {i}")
            for i in range(3)
        ]
        mock_arxiv = _build_arxiv_mock(fakes)
        with patch("audia.agents.research.get_settings", return_value=tmp_settings), \
             patch.dict("sys.modules", {"arxiv": mock_arxiv}):
            searcher = ArxivSearcher(max_results=3)
            results = searcher.search("neural networks")

        assert len(results) == 3
        assert results[2].title == "Paper 2"

    def test_uses_settings_default_max_results(self, tmp_settings):
        from audia.agents.research import ArxivSearcher

        mock_arxiv = _build_arxiv_mock([])
        with patch("audia.agents.research.get_settings", return_value=tmp_settings), \
             patch.dict("sys.modules", {"arxiv": mock_arxiv}):
            searcher = ArxivSearcher()  # no explicit max_results
            searcher.search("test")

        mock_arxiv.Search.assert_called_once()

    def test_search_raises_import_error(self, tmp_settings):
        """ImportError from missing arxiv package is re-raised with message."""
        from audia.agents.research import ArxivSearcher

        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "arxiv":
                raise ImportError("No module named 'arxiv'")
            return real_import(name, *args, **kwargs)

        with patch("audia.agents.research.get_settings", return_value=tmp_settings):
            searcher = ArxivSearcher(max_results=1)

        with patch("builtins.__import__", side_effect=mock_import):
            with pytest.raises(ImportError):
                searcher.search("test")


class TestArxivSearcherDownload:
    """ArxivSearcher.download_pdf() with mocked arxiv SDK."""

    def test_skips_download_if_file_exists(self, tmp_path, tmp_settings):
        from audia.agents.research import ArxivPaper, ArxivSearcher

        paper = ArxivPaper(
            arxiv_id="2301.00001v1",
            title="Test",
            authors=[],
            abstract="",
            pdf_url="https://example.com/pdf",
            published="2023-01-01",
        )
        existing = tmp_path / "2301.00001v1.pdf"
        existing.write_bytes(b"%PDF-fake")

        mock_arxiv = MagicMock()
        with patch("audia.agents.research.get_settings", return_value=tmp_settings), \
             patch.dict("sys.modules", {"arxiv": mock_arxiv}):
            searcher = ArxivSearcher()
            result = searcher.download_pdf(paper, dest_dir=tmp_path)

        mock_arxiv.Client.assert_not_called()
        assert result == existing
        assert paper.local_pdf_path == str(existing)

    def test_download_calls_arxiv_sdk(self, tmp_path, tmp_settings):
        from audia.agents.research import ArxivPaper, ArxivSearcher

        paper = ArxivPaper(
            arxiv_id="2301.99999v1",
            title="New",
            authors=[],
            abstract="",
            pdf_url="https://example.com/pdf",
            published="2023-01-01",
        )
        mock_result = MagicMock()
        mock_arxiv = _build_arxiv_mock([mock_result])

        def fake_download_pdf(*, dirpath, filename):
            (Path(dirpath) / filename).write_bytes(b"%PDF-downloaded")

        mock_result.download_pdf.side_effect = fake_download_pdf

        with patch("audia.agents.research.get_settings", return_value=tmp_settings), \
             patch.dict("sys.modules", {"arxiv": mock_arxiv}):
            searcher = ArxivSearcher()
            result = searcher.download_pdf(paper, dest_dir=tmp_path)

        assert result.name == "2301.99999v1.pdf"
        assert paper.local_pdf_path == str(result)
        mock_result.download_pdf.assert_called_once()

    def test_download_raises_import_error(self, tmp_path, tmp_settings):
        from audia.agents.research import ArxivPaper, ArxivSearcher

        paper = ArxivPaper(
            arxiv_id="2301.00002v1",
            title="T",
            authors=[],
            abstract="",
            pdf_url="",
            published="2023-01-01",
        )
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "arxiv":
                raise ImportError("No module named 'arxiv'")
            return real_import(name, *args, **kwargs)

        with patch("audia.agents.research.get_settings", return_value=tmp_settings):
            searcher = ArxivSearcher()

        with patch("builtins.__import__", side_effect=mock_import):
            with pytest.raises(ImportError):
                searcher.download_pdf(paper, dest_dir=tmp_path)
