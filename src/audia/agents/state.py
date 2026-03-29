"""
LangGraph state definition for the PDF → audio pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from typing_extensions import TypedDict


class PipelineState(TypedDict, total=False):
    """State that flows through every node of the LangGraph pipeline."""

    # Input
    pdf_path: str                    # absolute path to source PDF
    output_dir: str                  # directory where audio file is saved

    # Intermediate
    raw_text: str                    # text as extracted by PyMuPDF (all pages)
    preprocessed_text: str           # after heuristic cleaning
    cleaned_text: str                # after LLM cleaning (if enabled)

    # Output
    audio_path: Optional[str]        # absolute path to final .mp3 / .wav
    audio_filename: str              # e.g. "my_paper.mp3"

    # Metadata
    title: str
    num_pages: int
    tts_backend: str
    tts_voice: str
    run_id: str                      # "<pdf_stem>_<YYYYMMDD_HHMMSS>" – shared by audio file and debug folder

    # Error handling
    error: Optional[str]
