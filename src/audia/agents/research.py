"""
ArXiv paper search and download.

Primary:  arxiv Python SDK.
Fallback: HTML scrape of arxiv.org/search (used when the API returns 429).
"""

from __future__ import annotations

import calendar
import html as _html
import re
import shutil
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rich import print as rprint

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

        Falls back to HTML scraping if the API returns an error (e.g. HTTP 429).
        """
        try:
            import arxiv  # type: ignore
        except ImportError as e:
            raise ImportError("arxiv package required: pip install arxiv") from e

        try:
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
        except Exception as exc:
            msg = str(exc)
            if "429" in msg:
                rprint("[yellow]Page request resulted in HTTP 429 — starting alternative search…[/yellow]")
            else:
                rprint("[yellow]ArXiv API unavailable — starting alternative search…[/yellow]")

        return self._html_search(query)

    def _html_search(self, query: str) -> list[ArxivPaper]:
        """Fallback: scrape arxiv.org/search HTML when the API is unavailable."""
        q = urllib.parse.quote_plus(query)
        url = (
            f"https://arxiv.org/search/?query={q}"
            "&searchtype=all&source=header&start=0"
        )
        req = urllib.request.Request(
            url, headers={"User-Agent": "audia/0.1 (research fallback)"}
        )
        with urllib.request.urlopen(req, timeout=40) as resp:
            body = resp.read().decode("utf-8", errors="replace")

        papers: list[ArxivPaper] = []
        for block in re.findall(
            r'<li class="arxiv-result">(.*?)</li>', body, re.DOTALL
        ):
            id_m = re.search(r'arxiv\.org/abs/([\.\w]+)', block)
            if not id_m:
                continue
            arxiv_id = id_m.group(1)

            title_m = re.search(r'<p class="title[^"]*">(.*?)</p>', block, re.DOTALL)
            title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else arxiv_id

            authors_m = re.search(r'<p class="authors">(.*?)</p>', block, re.DOTALL)
            authors: list[str] = []
            if authors_m:
                raw_authors = re.sub(r'<[^>]+>', '', authors_m.group(1))
                authors = [a.strip() for a in raw_authors.split(',') if a.strip()]

            date_m = re.match(r'(\d{2})(\d{2})\.', arxiv_id)
            if date_m:
                yy, mm = int(date_m.group(1)), int(date_m.group(2))
                published = f"{calendar.month_abbr[mm]} {2000 + yy}"
            else:
                published = ""

            abstract_m = re.search(
                r'<span class="abstract-[^"]*">(.*?)</span>', block, re.DOTALL
            )
            abstract = (
                re.sub(r'<[^>]+>', '', abstract_m.group(1)).strip()
                if abstract_m else ""
            )

            papers.append(
                ArxivPaper(
                    arxiv_id=arxiv_id,
                    title=_html.unescape(title),
                    authors=[_html.unescape(a) for a in authors],
                    abstract=_html.unescape(abstract),
                    pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
                    published=published,
                )
            )
            if len(papers) >= self._max_results:
                break

        return papers

    def download_pdf(self, paper: ArxivPaper, dest_dir: str | Path | None = None) -> Path:
        """
        Download the PDF for *paper* directly from arxiv.org/pdf/<id>.

        Bypasses the arxiv SDK export API entirely to avoid HTTP 429 rate-limits.
        Skips the download if the file already exists.
        """
        cfg = get_settings()
        dest = Path(dest_dir) if dest_dir else cfg.upload_dir
        dest.mkdir(parents=True, exist_ok=True)

        filename = f"{paper.arxiv_id.replace('/', '_')}.pdf"
        target = dest / filename

        if target.exists():
            paper.local_pdf_path = str(target)
            return target

        pdf_url = f"https://arxiv.org/pdf/{paper.arxiv_id}"
        req = urllib.request.Request(
            pdf_url,
            headers={
                "User-Agent": "audia/0.1 (PDF download)",
                "Accept": "application/pdf,*/*",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            target.write_bytes(resp.read())

        paper.local_pdf_path = str(target)
        return target
