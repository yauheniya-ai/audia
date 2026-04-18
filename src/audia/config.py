"""
Global settings, loaded from environment variables or a .env file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── Project helpers ──────────────────────────────────────────────────────────

DEFAULT_PROJECT = "default"
_PROJECT_NAME_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')


def validate_project_name(name: str) -> str | None:
    """Return an error message if *name* is invalid, else None."""
    if not name.strip():
        return "Project name cannot be empty."
    if not _PROJECT_NAME_RE.match(name):
        return (
            "Lowercase letters, digits, hyphens and underscores only. "
            "Must start with a letter or digit."
        )
    return None


@dataclass
class ProjectDirs:
    """File-system paths for a single project under *base_dir*."""
    root: Path

    @property
    def db_path(self) -> Path:
        return self.root / "audia.db"

    @property
    def audio_dir(self) -> Path:
        return self.root / "audio"

    @property
    def upload_dir(self) -> Path:
        return self.root / "uploads"

    @property
    def debug_dir(self) -> Path:
        return self.root / "debug"

    def ensure_dirs(self) -> None:
        for d in (self.root, self.audio_dir, self.upload_dir, self.debug_dir):
            d.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="AUDIA_",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ server
    server_host: str = Field("127.0.0.1", description="FastAPI host")
    server_port: int = Field(8000, description="FastAPI port")
    reload: bool = Field(False, description="Uvicorn auto-reload (dev only)")

    # ------------------------------------------------------------------ storage
    data_dir: Path = Field(
        default_factory=lambda: Path.home() / ".audia",
        description="Root data directory for DB, audio output, and PDF uploads",
    )

    def get_project_dirs(self, project: str | None = None) -> ProjectDirs:
        """Return filesystem paths for *project* (defaults to 'default')."""
        name = (project or DEFAULT_PROJECT).strip() or DEFAULT_PROJECT
        return ProjectDirs(root=self.data_dir / name)

    # ── Convenience shorthands for the default project (backward-compat) ────

    @property
    def db_path(self) -> Path:
        return self.get_project_dirs().db_path

    @property
    def audio_dir(self) -> Path:
        return self.get_project_dirs().audio_dir

    @property
    def upload_dir(self) -> Path:
        return self.get_project_dirs().upload_dir

    @property
    def debug_dir(self) -> Path:
        return self.get_project_dirs().debug_dir

    def ensure_dirs(self) -> None:
        """Create all required directories if they don't exist."""
        dirs = self.get_project_dirs()
        for d in (self.data_dir, dirs.root, dirs.audio_dir, dirs.upload_dir, dirs.debug_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ LLM
    # LLM curation is the core of audia – it MUST be configured.
    # Set AUDIA_LLM_PROVIDER=openai or anthropic, plus the matching API key.
    llm_provider: Literal["openai", "anthropic", "google"] = Field(
        "openai",
        description=(
            "LLM backend for intelligent text curation. "
            "The LLM rewrites math formulas in plain English, summarises tables, "
            "condenses acknowledgements, and removes citations. "
            "Required – set AUDIA_LLM_PROVIDER=openai|anthropic|google."
        ),
    )
    openai_api_key: Optional[str] = Field(None, description="OpenAI API key (env: AUDIA_OPENAI_API_KEY)")
    openai_api_base: Optional[str] = Field(
        None,
        description=(
            "Custom OpenAI-compatible base URL, e.g. an Azure OpenAI endpoint or "
            "a corporate proxy. When set, all OpenAI calls (LLM + TTS) use this URL "
            "instead of the default https://api.openai.com/v1. "
            "(env: AUDIA_OPENAI_API_BASE)"
        ),
    )
    anthropic_api_key: Optional[str] = Field(None, description="Anthropic API key (env: AUDIA_ANTHROPIC_API_KEY)")
    anthropic_api_base: Optional[str] = Field(
        None,
        description=(
            "Custom Anthropic-compatible base URL, e.g. a corporate proxy. "
            "When set, all Anthropic LLM calls use this URL instead of the default. "
            "(env: AUDIA_ANTHROPIC_API_BASE)"
        ),
    )
    google_api_key: Optional[str] = Field(None, description="Google AI API key (env: AUDIA_GOOGLE_API_KEY)")
    google_api_base: Optional[str] = Field(
        None,
        description=(
            "Custom Google AI-compatible base URL, e.g. a Vertex AI endpoint or "
            "a corporate proxy. When set, all Google LLM calls use this URL instead "
            "of the default. (env: AUDIA_GOOGLE_API_BASE)"
        ),
    )
    llm_model: str = Field(
        "gpt-4o-mini",
        description="Model name, e.g. 'gpt-4o-mini', 'gpt-4o', 'claude-3-5-haiku-20241022', 'gemini-2.0-flash'",
    )
    llm_temperature: float = Field(0.1, ge=0.0, le=1.0)
    llm_max_chunk_chars: int = Field(
        8000,
        description="Max characters per LLM cleaning chunk. Larger = fewer API calls, higher cost.",
    )

    # ------------------------------------------------------------------ TTS
    tts_backend: Literal["edge-tts", "kokoro", "openai"] = Field(
        "edge-tts",
        description=(
            "TTS engine. 'edge-tts' requires no API key. "
            "'kokoro' requires `pip install audia[kokoro]`. "
            "'openai' requires an OpenAI key."
        ),
    )
    tts_voice: str = Field(
        "en-US-AriaNeural",
        description=(
            "Voice identifier. For edge-tts use e.g. 'en-US-AriaNeural'. "
            "For kokoro use e.g. 'af_heart'. "
            "For OpenAI use 'alloy' | 'echo' | 'nova' | 'shimmer'."
        ),
    )
    tts_rate: str = Field(
        "+0%", description="edge-tts speaking rate offset, e.g. '+10%' or '-5%'"
    )
    tts_chunk_chars: int = Field(
        3800,
        description="Max characters per TTS chunk (long texts are split and concatenated)",
    )

    # ------------------------------------------------------------------ STT
    stt_model: str = Field(
        "base",
        description=(
            "faster-whisper model size: tiny | base | small | medium | large-v3"
        ),
    )
    stt_device: str = Field("cpu", description="Device for faster-whisper: cpu | cuda")
    stt_record_seconds: int = Field(
        30, description="Max recording duration via microphone (seconds)"
    )

    # ------------------------------------------------------------------ Research
    arxiv_max_results: int = Field(
        10, description="Max papers returned per ArXiv query"
    )

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _normalise_provider(cls, v: str) -> str:
        v = v.lower().strip()
        if v == "none":
            raise ValueError(
                "AUDIA_LLM_PROVIDER cannot be 'none'. "
                "LLM curation is required. Set it to 'openai', 'anthropic', or 'google'."
            )
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance (reads .env on first call)."""
    s = Settings()
    s.ensure_dirs()
    return s
