"""
/api/settings – Persist and retrieve user-configured pipeline settings.
Settings are stored in the SQLite DB as key-value pairs so they survive
server restarts and are pre-loaded by the frontend on every page open.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from audia.storage import get_session
from audia.storage.models import UserSetting

router = APIRouter()

# Keys returned by GET and accepted by PUT
_DEFAULTS: dict[str, str] = {
    "stt_model": "whisper-large-v3",
    "llm1_provider": "Anthropic",
    "llm1_model": "claude-opus-4-6",
    "llm2_provider": "Anthropic",
    "llm2_model": "claude-opus-4-6",
    "tts_backend": "edge-tts",
    "tts_voice": "en-US-AriaNeural",
}


class SettingsBody(BaseModel):
    stt_model: str | None = None
    llm1_provider: str | None = None
    llm1_model: str | None = None
    llm2_provider: str | None = None
    llm2_model: str | None = None
    tts_backend: str | None = None
    tts_voice: str | None = None


@router.get("", summary="Get saved UI pipeline settings")
async def get_ui_settings() -> JSONResponse:
    """Return the user-saved pipeline settings merged with defaults."""
    with get_session() as session:
        rows = session.query(UserSetting).all()
        stored = {r.key: r.value for r in rows}
    return JSONResponse({**_DEFAULTS, **stored})


@router.put("", summary="Save UI pipeline settings")
async def save_ui_settings(body: SettingsBody) -> JSONResponse:
    """Persist the provided settings; omitted fields are left unchanged."""
    updates = body.model_dump(exclude_none=True)
    with get_session() as session:
        for key, value in updates.items():
            row = session.get(UserSetting, key)
            if row:
                row.value = str(value)
            else:
                session.add(UserSetting(key=key, value=str(value)))
        session.commit()
    return JSONResponse({"saved": True})
