"""
audia CLI – powered by Typer.

Commands
--------
  audia convert <pdf_path> [options]   Convert one or more PDFs to audio
  audia research <query> [options]     Search ArXiv and convert selected papers
  audia listen <query>                 Record voice query, search, convert
  audia serve                          Start the FastAPI web UI
  audia info                           Show current settings
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

app = typer.Typer(
    name="audia",
    help="Turn documents and ideas into audio files.",
    rich_markup_mode="rich",
    invoke_without_command=True,
)
console = Console()

_ASCII_BANNER = """
 [bold purple]▄▄▄▄▄▄▄▄▄▄▄  ▄         ▄  ▄▄▄▄▄▄▄▄▄▄  ▄▄▄▄▄▄▄▄▄▄▄  ▄▄▄▄▄▄▄▄▄▄▄ 
▐░░░░░░░░░░░▌▐░▌       ▐░▌▐░░░░░░░░░░▌▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌
▐░█▀▀▀▀▀▀▀█░▌▐░▌       ▐░▌▐░█▀▀▀▀▀▀▀█░▌▀▀▀▀█░█▀▀▀▀ ▐░█▀▀▀▀▀▀▀█░▌
▐░▌       ▐░▌▐░▌       ▐░▌▐░▌       ▐░▌    ▐░▌     ▐░▌       ▐░▌
▐░█▄▄▄▄▄▄▄█░▌▐░▌       ▐░▌▐░▌       ▐░▌    ▐░▌     ▐░█▄▄▄▄▄▄▄█░▌
▐░░░░░░░░░░░▌▐░▌       ▐░▌▐░▌       ▐░▌    ▐░▌     ▐░░░░░░░░░░░▌
▐░█▀▀▀▀▀▀▀█░▌▐░▌       ▐░▌▐░▌       ▐░▌    ▐░▌     ▐░█▀▀▀▀▀▀▀█░▌
▐░▌       ▐░▌▐░▌       ▐░▌▐░▌       ▐░▌    ▐░▌     ▐░▌       ▐░▌
▐░▌       ▐░▌▐░█▄▄▄▄▄▄▄█░▌▐░█▄▄▄▄▄▄▄█░▌▄▄▄▄█░█▄▄▄▄ ▐░▌       ▐░▌
▐░▌       ▐░▌▐░░░░░░░░░░░▌▐░░░░░░░░░░▌▐░░░░░░░░░░░▌▐░▌       ▐░▌
 ▀         ▀  ▀▀▀▀▀▀▀▀▀▀▀  ▀▀▀▀▀▀▀▀▀▀  ▀▀▀▀▀▀▀▀▀▀▀  ▀         ▀ [/bold purple]
"""


def _version_callback(value: bool) -> None:
    if value:
        from audia import __version__
        rprint(f"audia [bold cyan]{__version__}[/bold cyan]")
        raise typer.Exit()


@app.callback()
def _main(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """audia – Turn documents and ideas into audio files."""
    if ctx.invoked_subcommand is None:
        rprint(_ASCII_BANNER)
        rprint(ctx.get_help())
        raise typer.Exit()


# ──────────────────────────────────────────────────────────── convert

@app.command()
def convert(
    pdf_paths: list[Path] = typer.Argument(
        ...,
        help="One or more PDF files to convert to audio.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output", "-o",
        help="Directory for audio output. Defaults to ~/.audia/audio/",
    ),
    voice: Optional[str] = typer.Option(
        None, "--voice", "-v",
        help="TTS voice override (e.g. 'en-US-GuyNeural' for edge-tts).",
    ),
    open_after: bool = typer.Option(
        False, "--open",
        help="Open the generated audio file immediately.",
    ),
) -> None:
    """
    [bold green]Convert PDF(s) to audio.[/bold green]

    Extracts text, applies agentic cleaning, and synthesises speech.
    Example:
      audia convert paper.pdf
      audia convert paper1.pdf paper2.pdf --output ~/my_audio
    """
    from audia.config import get_settings
    from audia.agents.graph import run_pipeline
    from audia.storage import init_db, get_session, AudioFile, Paper

    cfg = get_settings()
    if voice:
        cfg.__dict__["tts_voice"] = voice

    init_db()
    errors: list[str] = []

    for pdf_path in pdf_paths:
        console.print(Rule(f"[bold]{pdf_path.name}[/bold]"))
        state = run_pipeline(pdf_path, output_dir=output_dir)

        if state.get("error"):
            rprint(f"[red]Error:[/red] {state['error']}")
            errors.append(state["error"])
            continue

        audio_path = state["audio_path"]
        rprint(f"[green]✓ Audio saved:[/green] {audio_path}")

        # Persist to database
        with get_session() as session:
            paper = Paper(
                title=state.get("title", pdf_path.stem),
                authors=json.dumps([]),
                pdf_path=str(pdf_path),
            )
            session.add(paper)
            session.flush()
            af = AudioFile(
                paper_id=paper.id,
                filename=state.get("audio_filename", Path(audio_path).name),
                file_path=audio_path,
                tts_backend=state.get("tts_backend", cfg.tts_backend),
                tts_voice=state.get("tts_voice", cfg.tts_voice),
            )
            session.add(af)

        if open_after:
            _open_file(audio_path)

    if errors:
        rprint(f"\n[red]{len(errors)} file(s) failed.[/red]")
        raise typer.Exit(code=1)


# ──────────────────────────────────────────────────────────── research

@app.command()
def research(
    query: str = typer.Argument(..., help="Topic to search on ArXiv."),
    max_results: int = typer.Option(
        10, "--max", "-n", help="Maximum number of ArXiv results."
    ),
    output_dir: Optional[Path] = typer.Option(
        None, "--output", "-o",
        help="Directory for audio output.",
    ),
    auto_convert: bool = typer.Option(
        False, "--convert", "-c",
        help="Automatically convert selected papers to audio.",
    ),
) -> None:
    """
    [bold green]Search ArXiv and optionally convert papers to audio.[/bold green]

    Presents a numbered list of results and lets you pick which to convert.
    Example:
      audia research "diffusion models image generation" --convert
    """
    from audia.agents.research import ArxivSearcher
    from audia.storage import init_db, get_session, Paper, ResearchSession
    import json

    searcher = ArxivSearcher(max_results=max_results)
    init_db()

    rprint(f"[cyan]Searching ArXiv for:[/cyan] {query}…")
    papers = searcher.search(query)

    if not papers:
        rprint("[yellow]No results found.[/yellow]")
        raise typer.Exit()

    table = Table(title=f"ArXiv results for: [bold]{query}[/bold]", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="bold", max_width=50)
    table.add_column("Authors", max_width=28)
    table.add_column("Date", width=12)
    table.add_column("Link", style="cyan", no_wrap=True)

    for i, p in enumerate(papers, 1):
        authors_str = ", ".join(p.authors[:2])
        if len(p.authors) > 2:
            authors_str += " et al."
        abs_url = f"https://arxiv.org/abs/{p.arxiv_id}"
        table.add_row(str(i), p.title, authors_str, p.published, abs_url)

    console.print(table)

    if not auto_convert:
        raw = typer.prompt(
            "Enter the # of study to convert to audio (comma-separated, or 'all', or 'q' to quit)",
            default="q",
        )
        if raw.strip().lower() in ("q", ""):
            raise typer.Exit()
        if raw.strip().lower() == "all":
            selected = papers
        else:
            indices = [int(x.strip()) - 1 for x in raw.split(",") if x.strip().isdigit()]
            selected = [papers[i] for i in indices if 0 <= i < len(papers)]
    else:
        selected = papers

    if not selected:
        rprint("[yellow]No papers selected.[/yellow]")
        raise typer.Exit()

    from audia.agents.graph import run_pipeline
    from audia.storage import AudioFile

    for paper in selected:
        rprint(f"\n[cyan]Downloading[/cyan] {paper.title[:60]}…")
        abs_url = f"https://arxiv.org/abs/{paper.arxiv_id}"
        pdf_path: Optional[Path] = None
        try:
            pdf_path = searcher.download_pdf(paper)
        except Exception as exc:
            short = str(exc).splitlines()[0][:120]
            rprint(f"[red]Download failed:[/red] {short}")
            rprint(
                f"[yellow]Please download the PDF manually:[/yellow] {abs_url}\n"
                "then enter the local path below (or press Enter to skip)."
            )
            manual = typer.prompt("Local PDF path", default="").strip()
            if manual:
                manual_path = Path(manual).expanduser()
                if manual_path.is_file():
                    pdf_path = manual_path
                else:
                    rprint(f"[red]File not found:[/red] {manual_path}")
            if pdf_path is None:
                continue

        rprint(f"[cyan]Converting[/cyan] {paper.title[:60]}…")
        state = run_pipeline(pdf_path, output_dir=output_dir)

        if state.get("error"):
            rprint(f"[red]Pipeline error:[/red] {state['error']}")
            continue

        audio_path = state["audio_path"]
        rprint(f"[green]✓ Audio saved:[/green] {audio_path}")

        # Persist
        with get_session() as session:
            db_paper = Paper(
                title=paper.title,
                authors=json.dumps(paper.authors),
                abstract=paper.abstract,
                arxiv_id=paper.arxiv_id,
                pdf_path=str(pdf_path),
                pdf_url=paper.pdf_url,
            )
            session.add(db_paper)
            session.flush()
            af = AudioFile(
                paper_id=db_paper.id,
                filename=state.get("audio_filename", Path(audio_path).name),
                file_path=audio_path,
            )
            session.add(af)

        # Save session record
        with get_session() as session:
            pass  # session already committed above

    rprint("\n[bold green]Done.[/bold green]")


# ──────────────────────────────────────────────────────────── listen

@app.command()
def listen(
    seconds: int = typer.Option(
        30, "--seconds", "-s", help="Max recording duration in seconds."
    ),
    output_dir: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Directory for audio output."
    ),
) -> None:
    """
    [bold green]Record a voice query, search ArXiv, and convert to audio.[/bold green]

    Pipeline: record → transcribe → LLM extracts search query → confirm → research
    """
    from audia.agents.stt import record_and_transcribe, distill_search_query

    while True:
        rprint("[cyan]Listening…[/cyan] Speak your research topic.")
        speech = record_and_transcribe(seconds=seconds)
        rprint(f"[green]Heard:[/green] {speech}")

        rprint("[dim]Distilling search query…[/dim]")
        query = distill_search_query(speech)
        rprint(f"[bold cyan]Search query:[/bold cyan] {query}")

        choice = typer.prompt(
            "Search ArXiv with this query? [y=yes / r=re-record / q=quit]",
            default="y",
        ).strip().lower()

        if choice in ("y", "yes", ""):
            break
        elif choice in ("r", "re", "retry"):
            rprint("[yellow]OK, let's try again.[/yellow]")
            continue
        else:
            rprint("[yellow]Cancelled.[/yellow]")
            raise typer.Exit()

    # Run research — user always picks which papers to convert
    research(
        query=query,
        max_results=10,
        output_dir=output_dir,
        auto_convert=False,
    )


# ──────────────────────────────────────────────────────────── serve

@app.command()
def serve(
    host: str = typer.Option(None, "--host", "-h", help="Server host."),
    port: int = typer.Option(None, "--port", "-p", help="Server port."),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload (dev)."),
    open_browser: bool = typer.Option(True, "--browser/--no-browser", help="Open browser."),
) -> None:
    """
    [bold green]Start the audia web UI.[/bold green]

    Launches a FastAPI server.  Open http://localhost:8000 in your browser.
    """
    import uvicorn
    from audia.config import get_settings
    from audia.storage import init_db

    cfg = get_settings()
    _host = host or cfg.server_host
    _port = port or cfg.server_port
    _reload = reload or cfg.reload

    init_db()
    rprint(
        Panel(
            f"[green]audia UI[/green] running at [bold]http://{_host}:{_port}[/bold]\n"
            "Press [bold]Ctrl+C[/bold] to stop.",
            border_style="green",
        )
    )
    if open_browser:
        import threading, time, webbrowser
        def _open():
            time.sleep(1.2)
            webbrowser.open(f"http://{_host}:{_port}")
        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(
        "audia.ui.app:app",
        host=_host,
        port=_port,
        reload=_reload,
    )


# ──────────────────────────────────────────────────────────── info

@app.command()
def info() -> None:
    """Show current audia configuration."""
    from audia.config import get_settings
    from audia import __version__

    cfg = get_settings()
    table = Table(title=f"audia v{__version__} – Configuration", show_header=False)
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Value")

    rows = [
        ("Data directory", str(cfg.data_dir)),
        ("Database", str(cfg.db_path)),
        ("Audio output", str(cfg.audio_dir)),
        ("LLM provider", cfg.llm_provider),
        ("LLM model", cfg.llm_model),
        ("TTS backend", cfg.tts_backend),
        ("TTS voice", cfg.tts_voice),
        ("STT model", cfg.stt_model),
        ("Server", f"http://{cfg.server_host}:{cfg.server_port}"),
    ]
    for k, v in rows:
        table.add_row(k, v)

    console.print(table)


# ──────────────────────────────────────────────────────────── helpers

def _open_file(path: str) -> None:
    import subprocess
    import platform

    system = platform.system()
    if system == "Darwin":
        subprocess.call(["open", path])
    elif system == "Linux":
        subprocess.call(["xdg-open", path])
    elif system == "Windows":
        import os
        os.startfile(path)


if __name__ == "__main__":
    app()
