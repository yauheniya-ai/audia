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

    def test_download_fetches_via_urllib(self, tmp_path, tmp_settings):
        from audia.agents.research import ArxivPaper, ArxivSearcher

        paper = ArxivPaper(
            arxiv_id="2301.99999v1",
            title="New",
            authors=[],
            abstract="",
            pdf_url="https://arxiv.org/pdf/2301.99999v1",
            published="2023-01-01",
        )

        fake_response = MagicMock()
        fake_response.read.return_value = b"%PDF-downloaded"
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = MagicMock(return_value=False)

        with patch("audia.agents.research.get_settings", return_value=tmp_settings), \
             patch("audia.agents.research.urllib.request.urlopen", return_value=fake_response) as mock_open:
            searcher = ArxivSearcher()
            result = searcher.download_pdf(paper, dest_dir=tmp_path)

        assert result.name == "2301.99999v1.pdf"
        assert result.read_bytes() == b"%PDF-downloaded"
        assert paper.local_pdf_path == str(result)
        mock_open.assert_called_once()

    def test_download_raises_on_http_error(self, tmp_path, tmp_settings):
        from audia.agents.research import ArxivPaper, ArxivSearcher
        import urllib.error

        paper = ArxivPaper(
            arxiv_id="2301.00002v1",
            title="T",
            authors=[],
            abstract="",
            pdf_url="",
            published="2023-01-01",
        )

        with patch("audia.agents.research.get_settings", return_value=tmp_settings), \
             patch("audia.agents.research.urllib.request.urlopen",
                   side_effect=urllib.error.HTTPError(
                       url="", code=429, msg="Too Many Requests", hdrs={}, fp=None
                   )):
            searcher = ArxivSearcher()
            with pytest.raises(urllib.error.HTTPError):
                searcher.download_pdf(paper, dest_dir=tmp_path)


# ─────────────────────────────────── HTML fallback search

_FAKE_HTML = '''
<li class="arxiv-result">
    <a href="https://arxiv.org/abs/2301.12345">arxiv.org/abs/2301.12345</a>
    <p class="title is-5">Attention Is All You Need</p>
    <p class="authors">Alice Smith, Bob Jones</p>
    <span class="abstract-short">A brief abstract about transformers.</span>
</li>
<li class="arxiv-result">
    <a href="https://arxiv.org/abs/2305.99999">arxiv.org/abs/2305.99999</a>
    <p class="title is-5">Second Paper</p>
    <p class="authors">Carol</p>
    <span class="abstract-short">Second abstract.</span>
</li>
'''


class TestHtmlSearch:
    def _make_fake_response(self, html: str):
        resp = MagicMock()
        resp.read.return_value = html.encode("utf-8")
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    def test_html_search_parses_papers(self, tmp_settings):
        from audia.agents.research import ArxivSearcher

        fake_resp = self._make_fake_response(_FAKE_HTML)

        with patch("audia.agents.research.get_settings", return_value=tmp_settings), \
             patch("audia.agents.research.urllib.request.urlopen", return_value=fake_resp):
            searcher = ArxivSearcher(max_results=5)
            results = searcher._html_search("transformers")

        assert len(results) >= 1
        assert results[0].title == "Attention Is All You Need"
        assert "Alice Smith" in results[0].authors
        assert results[0].arxiv_id == "2301.12345"

    def test_html_search_respects_max_results(self, tmp_settings):
        from audia.agents.research import ArxivSearcher

        fake_resp = self._make_fake_response(_FAKE_HTML)

        with patch("audia.agents.research.get_settings", return_value=tmp_settings), \
             patch("audia.agents.research.urllib.request.urlopen", return_value=fake_resp):
            searcher = ArxivSearcher(max_results=1)
            results = searcher._html_search("transformers")

        assert len(results) == 1

    def test_html_search_empty_page(self, tmp_settings):
        from audia.agents.research import ArxivSearcher

        empty_resp = self._make_fake_response("<html><body>No results</body></html>")

        with patch("audia.agents.research.get_settings", return_value=tmp_settings), \
             patch("audia.agents.research.urllib.request.urlopen", return_value=empty_resp):
            searcher = ArxivSearcher(max_results=5)
            results = searcher._html_search("zzz_nothing")

        assert results == []

    def test_search_falls_back_to_html_on_api_error(self, tmp_settings):
        """When the arxiv API raises a non-429 error, _html_search is called."""
        from audia.agents.research import ArxivSearcher

        fake_resp = self._make_fake_response(_FAKE_HTML)

        mock_arxiv = MagicMock()
        mock_arxiv.Client.return_value.results.side_effect = RuntimeError("API unavailable")
        mock_arxiv.Search = MagicMock(return_value=MagicMock())
        mock_arxiv.SortCriterion = MagicMock()
        mock_arxiv.SortCriterion.Relevance = "relevance"

        with patch("audia.agents.research.get_settings", return_value=tmp_settings), \
             patch.dict("sys.modules", {"arxiv": mock_arxiv}), \
             patch("audia.agents.research.urllib.request.urlopen", return_value=fake_resp):
            searcher = ArxivSearcher(max_results=5)
            results = searcher.search("transformers")

        assert len(results) >= 1

    def test_search_falls_back_to_html_on_429(self, tmp_settings):
        """When the arxiv API returns HTTP 429, _html_search is called."""
        from audia.agents.research import ArxivSearcher

        fake_resp = self._make_fake_response(_FAKE_HTML)

        mock_arxiv = MagicMock()
        mock_arxiv.Client.return_value.results.side_effect = Exception("HTTP 429 Too Many Requests")
        mock_arxiv.Search = MagicMock(return_value=MagicMock())
        mock_arxiv.SortCriterion = MagicMock()
        mock_arxiv.SortCriterion.Relevance = "relevance"

        with patch("audia.agents.research.get_settings", return_value=tmp_settings), \
             patch.dict("sys.modules", {"arxiv": mock_arxiv}), \
             patch("audia.agents.research.urllib.request.urlopen", return_value=fake_resp):
            searcher = ArxivSearcher(max_results=5)
            results = searcher.search("transformers")

        assert len(results) >= 1


class TestArxivPaperPublishedNone:
    """Edge case: paper.published is None from the SDK."""

    def test_published_none_gives_empty_string(self, tmp_settings):
        from audia.agents.research import ArxivSearcher

        fake = _make_arxiv_result()
        fake.published = None  # SDK sometimes returns None

        mock_arxiv = _build_arxiv_mock([fake])

        with patch("audia.agents.research.get_settings", return_value=tmp_settings), \
             patch.dict("sys.modules", {"arxiv": mock_arxiv}):
            searcher = ArxivSearcher(max_results=5)
            results = searcher.search("transformers")

        assert results[0].published == ""
