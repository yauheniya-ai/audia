"""
Text curation pipeline – the core intelligence of audia.

Two-stage process:
  1. heuristic_clean()  – fast regex pre-pass: removes citations, LaTeX artefacts,
                          collapses whitespace. Reduces LLM token cost.
  2. llm_curate()       – LLM pass (ALWAYS required): rewrites math in plain English,
                          summarises tables, condenses acknowledgements,
                          ensures smooth spoken-word flow.
"""

from __future__ import annotations

import re

from rich.console import Console

from audia.config import Settings, get_settings

console = Console(stderr=True)


# ──────────────────────────────────────────────────────────── regex patterns

# (Author et al., 2023)  /  (Smith & Jones, 2022)  /  (see Wang 2021)
_AUTHOR_CITATION = re.compile(
    r"\(\s*(?:see\s+)?[A-Z][A-Za-zÀ-ÿ\-]+(?:\s+et\s+al\.?)?(?:\s*[,&]\s*[A-Z][A-Za-zÀ-ÿ\-]+)*"
    r"(?:,\s*\d{4}[a-z]?)?\s*\)",
)
# [3], [3,4], [3-5], [3, 4, 5]
_NUMERIC_CITATION = re.compile(r"\[\s*\d+(?:\s*[,\-–]\s*\d+)*\s*\]")

# Detect an acknowledgements section heading
_ACK_HEADING = re.compile(
    r"(^|\n)\s*(?:acknowledgements?|acknowledgments?)\s*\n",
    re.IGNORECASE,
)
# Content of acknowledgements section (everything to next all-caps heading or end)
_ACK_SECTION = re.compile(
    r"(?:acknowledgements?|acknowledgments?)\s*\n(.*?)(?=\n[A-Z][A-Z\s]{3,}\n|\Z)",
    re.IGNORECASE | re.DOTALL,
)

# Isolated figure / table captions to remove
_FIGURE_TABLE_LABEL = re.compile(
    r"(Figure|Fig\.|Table)\s+\d+[.:]\s*[^\n]*\n?",
    re.IGNORECASE,
)

# LaTeX commands: \textbf{foo}, \cite{bar}, \emph{x}, standalone \cmd, etc.
_LATEX_CMD = re.compile(r"\\[a-zA-Z]+(?:\{[^}]*\})*")

# Excessive blank lines
_MULTI_BLANK = re.compile(r"\n{3,}")


def heuristic_clean(text: str) -> str:
    """
    Fast regex pre-pass – always runs before the LLM call to reduce token cost.
    """
    text = _NUMERIC_CITATION.sub("", text)
    text = _AUTHOR_CITATION.sub("", text)
    text = _LATEX_CMD.sub("", text)
    text = _FIGURE_TABLE_LABEL.sub("", text)
    text = _MULTI_BLANK.sub("\n\n", text)
    paragraphs = [p.strip() for p in text.split("\n\n")]
    return "\n\n".join(p for p in paragraphs if p)


# ──────────────────────────────────────────────────────────── LLM curation

_SYSTEM_PROMPT = """You are an expert academic editor preparing a research paper for text-to-speech conversion.
Transform the text so it reads naturally and clearly when spoken aloud.

Apply ALL rules without exception:
1. **Mathematical notation**: Never read symbol sequences. Replace with clear spoken English.
   Example: "∇L = Σᵢ αᵢ yᵢ xᵢ" → "the gradient of L equals the weighted sum of training examples"
   Example: "f(x) = x²" → "the function f of x equals x squared"
   Example: "p < 0.05" → "p less than 0.05"
2. **Tables**: Replace every raw table with ONE sentence summarising what it shows.
   If the surrounding text already summarises the table, remove the table entirely.
3. **Remove entirely**: equation labels like (1) or (2), author affiliations,
   email addresses, DOI/URL lines, running headers, page numbers.
4. **Acknowledgements**: Condense to one sentence: "The authors acknowledge support from [institutions]."
5. **Residual artefacts**: Remove leftover bullet symbols (•  ‣), hyphenated line-breaks (e.g. algo-
   rithm), and any remaining LaTeX commands.
6. **Section transitions**: Preserve section headings as natural spoken transitions,
   e.g. "Section 3, Methodology:" or "Moving on to the results:"
7. **Flow**: Merge orphaned fragments into complete sentences. Ensure natural spoken rhythm.

Return ONLY the curated spoken text. No markdown, no commentary.
"""

# How many chars of the previous curated chunk to pass as transition context.
# Large enough to cover 1-2 paragraphs; small enough not to waste tokens.
_CONTEXT_TAIL_CHARS = 600

_USER_TEMPLATE = "Curate the following text for text-to-speech:\n\n{chunk}"

# Used for chunks 2, 3, … – the tail of the previous curated chunk is injected
# so the LLM can write a smooth transition without re-reading the whole chunk.
_USER_TEMPLATE_WITH_CONTEXT = (
    "[CONTEXT — already curated text that immediately precedes this chunk. "
    "Do NOT repeat or continue it.]\n{tail}\n\n"
    "[CURRENT CHUNK — curate this for text-to-speech, "
    "ensuring a smooth spoken transition from the context above]\n{chunk}"
)


def llm_curate(
    text: str,
    settings: Settings | None = None,
    progress_cb=None,
) -> str:
    """
    LLM curation pass – ALWAYS required, always runs.
    Raises RuntimeError on misconfiguration / missing API key.

    Parameters
    ----------
    progress_cb : callable(str) | None
        Optional callback invoked with a plain-text progress line for each
        chunk so callers (e.g. the web job runner) can surface per-chunk
        progress without parsing Rich markup.
    """
    cfg = settings or get_settings()
    llm = _build_llm(cfg)

    chunks = _split_text(text, max_chars=cfg.llm_max_chunk_chars)
    total = len(chunks)
    curated: list[str] = []

    prev_tail: str = ""

    for i, chunk in enumerate(chunks, 1):
        msg = f"LLM curation chunk {i}/{total} ({len(chunk):,} chars)\u2026"
        console.print(f"  [dim]  {msg}[/dim]")
        if progress_cb:
            progress_cb(msg)
        if prev_tail:
            user_msg = _USER_TEMPLATE_WITH_CONTEXT.format(tail=prev_tail, chunk=chunk)
        else:
            user_msg = _USER_TEMPLATE.format(chunk=chunk)

        result = llm.invoke(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ]
        )
        curated_chunk = getattr(result, "content", str(result)).strip()
        curated.append(curated_chunk)
        prev_tail = _extract_tail(curated_chunk, _CONTEXT_TAIL_CHARS)

    return "\n\n".join(curated)


# back-compat alias
llm_clean = llm_curate


# ──────────────────────────────────────────────────────────── LLM factory

def _build_llm(cfg: Settings):
    """Instantiate a LangChain chat model; raises clearly on bad config."""
    if cfg.llm_provider == "openai":
        try:
            from langchain_openai import ChatOpenAI  # type: ignore
        except ImportError as e:
            raise ImportError(
                "OpenAI support requires: pip install audia[openai]"
            ) from e
        if not cfg.openai_api_key:
            raise RuntimeError(
                "AUDIA_OPENAI_API_KEY is not set.\n"
                "Add it to your .env file:  AUDIA_OPENAI_API_KEY=sk-..."
            )
        return ChatOpenAI(
            model=cfg.llm_model,
            temperature=cfg.llm_temperature,
            api_key=cfg.openai_api_key,
        )
    elif cfg.llm_provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic  # type: ignore
        except ImportError as e:
            raise ImportError(
                "Anthropic support requires: pip install audia[anthropic]"
            ) from e
        if not cfg.anthropic_api_key:
            raise RuntimeError(
                "AUDIA_ANTHROPIC_API_KEY is not set.\n"
                "Add it to your .env file:  AUDIA_ANTHROPIC_API_KEY=sk-ant-..."
            )
        return ChatAnthropic(
            model=cfg.llm_model,
            temperature=cfg.llm_temperature,
            api_key=cfg.anthropic_api_key,
        )
    else:
        raise ValueError(
            f"Unknown LLM provider: '{cfg.llm_provider}'. Valid: openai | anthropic"
        )


def _extract_tail(text: str, max_chars: int) -> str:
    """
    Return the last complete paragraph(s) of *text* up to *max_chars* chars.
    Used to give the next chunk's LLM call just enough context for a smooth
    spoken transition without re-processing the full previous chunk.
    """
    if len(text) <= max_chars:
        return text
    tail = text[-max_chars:]
    # Trim to the first paragraph boundary so we don't start mid-sentence.
    first_break = tail.find("\n\n")
    return tail[first_break + 2:] if first_break != -1 else tail


def _split_text(text: str, max_chars: int = 8000) -> list[str]:
    """
    Split text into chunks of at most max_chars, breaking at paragraph boundaries.
    """
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    paragraphs = text.split("\n\n")
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 > max_chars and current:
            chunks.append(current.strip())
            current = para + "\n\n"
        else:
            current += para + "\n\n"
    if current.strip():
        chunks.append(current.strip())
    return chunks or [text]


# ──────────────────────────────────────────────────────────── main entry

def curate_text(text: str, settings: Settings | None = None) -> str:
    """
    Full curation pipeline: heuristic pre-pass → LLM curation.

    Transition guarantee
    --------------------
    Each chunk (from chunk 2 onward) receives the tail of the previous curated
    chunk as read-only context so the LLM can write a smooth spoken transition
    without re-processing or re-outputting already-curated text.
    The full paper content is preserved as-is after the LLM pass — no content
    is dropped or deduplicated.
    """
    cfg = settings or get_settings()
    console.print("  [dim]Heuristic pre-pass (citations, LaTeX artefacts)…[/dim]")
    preprocessed = heuristic_clean(text)
    console.print(
        f"  [dim]Pre-pass: {len(text):,} → {len(preprocessed):,} chars[/dim]"
    )
    return llm_curate(preprocessed, cfg)


# Back-compat alias
def clean_text(text: str, settings: Settings | None = None) -> str:
    return curate_text(text, settings)
