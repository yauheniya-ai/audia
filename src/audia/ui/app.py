"""
FastAPI application factory for the audia web UI.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from audia import __version__
from audia.storage import init_db
from audia.ui.routes.convert import router as convert_router
from audia.ui.routes.research import router as research_router
from audia.ui.routes.library import router as library_router
from audia.ui.routes.settings import router as settings_router

_STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    application = FastAPI(
        title="audia",
        description="Turn documents and ideas into audio files.",
        version=__version__,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialise DB on startup
    @application.on_event("startup")
    async def startup() -> None:
        init_db()

    # Package info endpoint
    @application.get("/api/info", include_in_schema=True, tags=["info"])
    async def api_info() -> JSONResponse:
        return JSONResponse({"version": __version__, "name": "audia"})

    # API routes
    application.include_router(convert_router,  prefix="/api/convert",  tags=["convert"])
    application.include_router(research_router, prefix="/api/research", tags=["research"])
    application.include_router(library_router,  prefix="/api/library",  tags=["library"])
    application.include_router(settings_router, prefix="/api/settings", tags=["settings"])

    # Serve Vite-built assets at their natural paths (/assets/*, /favicon.svg …)
    # Vite always emits JS/CSS under /assets/ – mount that sub-dir directly so
    # the browser receives the correct Content-Type (not the SPA catch-all html).
    _assets_dir = _STATIC_DIR / "assets"
    if _assets_dir.exists():
        application.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")

    # SPA catch-all: serve root-level static files (favicon, icons, …) when
    # they exist on disk; fall back to index.html for every other path so the
    # React router can handle client-side navigation.
    @application.get("/", include_in_schema=False)
    @application.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str = "") -> FileResponse:
        candidate = _STATIC_DIR / full_path
        if full_path and candidate.exists() and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_STATIC_DIR / "index.html"))

    return application


app = create_app()
