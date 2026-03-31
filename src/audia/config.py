"""
Global settings, loaded from environment variables or a .env file.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @property
    def db_path(self) -> Path:
        return self.data_dir / "audia.db"

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def debug_dir(self) -> Path:
        return self.data_dir / "debug"

    def ensure_dirs(self) -> None:
        """Create all required directories if they don't exist."""
        for d in (self.data_dir, self.audio_dir, self.upload_dir, self.debug_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ LLM
    # LLM curation is the core of audia – it MUST be configured.
    # Set AUDIA_LLM_PROVIDER=openai or anthropic, plus the matching API key.
    llm_provider: Literal["openai", "anthropic"] = Field(
        "openai",
        description=(
            "LLM backend for intelligent text curation. "
            "The LLM rewrites math formulas in plain English, summarises tables, "
            "condenses acknowledgements, and removes citations. "
            "Required – set AUDIA_LLM_PROVIDER=openai|anthropic."
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
    llm_model: str = Field(
        "gpt-4o-mini",
        description="Model name, e.g. 'gpt-4o-mini', 'gpt-4o', 'claude-3-5-haiku-20241022'",
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
                "LLM curation is required. Set it to 'openai' or 'anthropic'."
            )
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance (reads .env on first call)."""
    s = Settings()
    s.ensure_dirs()
    return s
