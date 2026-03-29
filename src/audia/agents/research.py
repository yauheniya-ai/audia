"""
ArXiv paper search and download.

Uses the `arxiv` Python SDK.  Returns lightweight result objects
that can be stored in the database and fed into the PDF pipeline.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from audia.config import get_settings


@dataclass
class ArxivPaper:
    """Lightweight representation of an ArXiv result."""

    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    pdf_url: str
    published: str          # ISO date string
    local_pdf_path: Optional[str] = None


class ArxivSearcher:
    """Search ArXiv and download PDFs."""

    def __init__(self, max_results: int | None = None):
        self._max_results = max_results or get_settings().arxiv_max_results

    def search(self, query: str) -> list[ArxivPaper]:
        """
        Search ArXiv for *query* and return up to max_results papers.

        Papers are sorted by relevance (default ArXiv sort).
        """
        try:
            import arxiv  # type: ignore
        except ImportError as e:
            raise ImportError("arxiv package required: pip install arxiv") from e

        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=self._max_results,
            sort_by=arxiv.SortCriterion.Relevance,
        )

        results: list[ArxivPaper] = []
        for r in client.results(search):
            results.append(
                ArxivPaper(
                    arxiv_id=r.get_short_id(),
                    title=r.title,
                    authors=[a.name for a in r.authors],
                    abstract=r.summary,
                    pdf_url=r.pdf_url,
                    published=r.published.date().isoformat() if r.published else "",
                )
            )
        return results

    def download_pdf(self, paper: ArxivPaper, dest_dir: str | Path | None = None) -> Path:
        """
        Download the PDF for *paper* and return the local file path.
        Skips the download if the file already exists.
        """
        try:
            import arxiv  # type: ignore
        except ImportError as e:
            raise ImportError("arxiv package required: pip install arxiv") from e

        cfg = get_settings()
        dest = Path(dest_dir) if dest_dir else cfg.upload_dir
        dest.mkdir(parents=True, exist_ok=True)

        filename = f"{paper.arxiv_id.replace('/', '_')}.pdf"
        target = dest / filename

        if target.exists():
            paper.local_pdf_path = str(target)
            return target

        # Use the arxiv SDK's built-in downloader
        client = arxiv.Client()
        search = arxiv.Search(id_list=[paper.arxiv_id])
        result = next(client.results(search))
        result.download_pdf(dirpath=str(dest), filename=filename)

        paper.local_pdf_path = str(target)
        return target
