"""
/api/projects – CRUD for project namespaces.

Each project is a sub-directory under ~/.audia/{project_name}/ that holds its
own SQLite database and file folders.  The special project named "default"
always exists and is the fallback when no project is specified.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from audia.config import DEFAULT_PROJECT, get_settings, validate_project_name
from audia.storage.database import init_db

router = APIRouter()


# ── helpers ──────────────────────────────────────────────────────────────────

def _project_info(
    project_dir: Path,
    active_project: str,
) -> dict:
    """Build the ProjectInfo dict for *project_dir*."""
    name = project_dir.name
    db_path = project_dir / "audia.db"
    exists = db_path.exists()

    # Rough size
    size_kb = 0
    doc_count = 0
    audio_count = 0
    if exists:
        try:
            size_kb = round(db_path.stat().st_size / 1024, 1)
            from audia.storage.database import get_session
            with get_session(name) as sess:
                from audia.storage.models import AudioFile, Paper
                from sqlalchemy import func, select
                doc_count  = sess.execute(select(func.count()).select_from(Paper)).scalar_one()
                audio_count = sess.execute(select(func.count()).select_from(AudioFile)).scalar_one()
        except Exception:
            pass

    created_at = ""
    try:
        created_at = project_dir.stat().st_ctime
        from datetime import datetime, timezone
        created_at = datetime.fromtimestamp(created_at, tz=timezone.utc).isoformat()
    except Exception:
        pass

    return {
        "name":        name,
        "path":        str(project_dir),
        "root":        str(get_settings().data_dir),
        "description": "",
        "size_kb":     size_kb,
        "documents":   doc_count,
        "quizzes":     audio_count,
        "is_default":  name == DEFAULT_PROJECT,
        "is_active":   name == active_project,
        "exists":      exists,
        "created_at":  created_at,
    }


def _list_projects(active_project: str) -> list[dict]:
    """Scan data_dir for project subdirectories; always include 'default'."""
    data_dir = get_settings().data_dir
    data_dir.mkdir(parents=True, exist_ok=True)

    # Collect all subdirs that look like projects
    names: set[str] = {DEFAULT_PROJECT}
    for child in data_dir.iterdir():
        if child.is_dir() and not child.name.startswith("."):
            names.add(child.name)

    projects = []
    for name in sorted(names):
        d = data_dir / name
        d.mkdir(parents=True, exist_ok=True)
        projects.append(_project_info(d, active_project))

    # Default first, rest alphabetical
    projects.sort(key=lambda p: (not p["is_default"], p["name"]))
    return projects


# ── endpoints ────────────────────────────────────────────────────────────────

@router.get("", summary="List all projects")
async def list_projects(
    active_project: str | None = Query(None, description="Name of the currently active project"),
) -> JSONResponse:
    active = (active_project or DEFAULT_PROJECT).strip() or DEFAULT_PROJECT
    return JSONResponse({"projects": _list_projects(active)})


class CreateProjectBody(BaseModel):
    name: str


@router.post("", summary="Create a new project", status_code=201)
async def create_project(body: CreateProjectBody) -> JSONResponse:
    name = body.name.strip().lower()
    err = validate_project_name(name)
    if err:
        raise HTTPException(status_code=422, detail=err)

    dirs = get_settings().get_project_dirs(name)
    dirs.ensure_dirs()
    init_db(name)

    return JSONResponse(
        _project_info(dirs.root, name),
        status_code=201,
    )


@router.delete("/{name}", summary="Delete a project")
async def delete_project(
    name: str,
    keep_files: bool = Query(False, description="If true, keep files on disk"),
) -> JSONResponse:
    if name == DEFAULT_PROJECT:
        raise HTTPException(status_code=400, detail="Cannot delete the default project.")

    err = validate_project_name(name)
    if err:
        raise HTTPException(status_code=422, detail=err)

    dirs = get_settings().get_project_dirs(name)
    if not dirs.root.exists():
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found.")

    if not keep_files:
        shutil.rmtree(dirs.root, ignore_errors=True)
    # Also remove from engine cache
    from audia.storage.database import _engines, _factories
    _engines.pop(name, None)
    _factories.pop(name, None)

    return JSONResponse({"status": "deleted", "name": name})
