"""
FastAPI application factory for the audia web UI.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from audia import __version__
from audia.storage import init_db
from audia.ui.routes.convert import router as convert_router
from audia.ui.routes.research import router as research_router
from audia.ui.routes.library import router as library_router

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

    # API routes
    application.include_router(convert_router,  prefix="/api/convert",  tags=["convert"])
    application.include_router(research_router, prefix="/api/research", tags=["research"])
    application.include_router(library_router,  prefix="/api/library",  tags=["library"])

    # Serve static assets (JS, CSS, audio files for download)
    if _STATIC_DIR.exists():
        application.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # SPA catch-all: serve index.html for every non-API route
    @application.get("/", include_in_schema=False)
    @application.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str = "") -> FileResponse:
        return FileResponse(str(_STATIC_DIR / "index.html"))

    return application


app = create_app()
