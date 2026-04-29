"""
repair_paths.py
---------------
Two modes:

1. repair  (default)
   Fixes broken pdf_path / file_path records in a project's DB by
   re-matching filenames against what is actually on disk in that project.

2. recover-from  (--recover-from SOURCE)
   Reads records from SOURCE project whose files are missing, relocates them
   to the TARGET project's on-disk directories, inserts them into TARGET's DB,
   then removes them from SOURCE's DB.

Usage:
    # Fix paths in-place for project 'default':
    python3 scripts/repair_paths.py --project default --dry-run
    python3 scripts/repair_paths.py --project default

    # Recover records from 'callcenter' into 'default'
    # (files must already be in default/uploads and default/audio):
    python3 scripts/repair_paths.py --project default --recover-from callcenter --dry-run
    python3 scripts/repair_paths.py --project default --recover-from callcenter
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from audia.config import DEFAULT_PROJECT, get_settings
from audia.storage.database import get_session
from audia.storage.models import AudioFile, Paper
from sqlalchemy import select


def _build_lookup(directory: Path, glob: str) -> dict[str, Path]:
    """filename → Path, also indexed by bare name (without hash prefix)."""
    lk: dict[str, Path] = {}
    for f in directory.glob(glob):
        lk[f.name] = f
        if "_" in f.name:
            lk.setdefault(f.name.split("_", 1)[1], f)
    return lk


def repair(project: str, dry_run: bool) -> None:
    cfg = get_settings()
    dirs = cfg.get_project_dirs(project)

    print(f"Project      : {project}")
    print(f"DB           : {dirs.db_path}")
    print(f"uploads dir  : {dirs.upload_dir}")
    print(f"audio dir    : {dirs.audio_dir}")
    print(f"Dry run      : {dry_run}\n")

    pdf_lookup   = _build_lookup(dirs.upload_dir, "*.pdf")
    audio_lookup = _build_lookup(dirs.audio_dir,  "*.mp3")

    fixed_papers = broken_papers = fixed_audio = broken_audio = 0

    with get_session(project) as sess:
        for paper in sess.execute(select(Paper)).scalars().all():
            if not paper.pdf_path:
                continue
            current = Path(paper.pdf_path)
            if current.exists():
                continue
            found = pdf_lookup.get(current.name) or pdf_lookup.get(current.name.split("_", 1)[-1])
            if found:
                print(f"  [PAPER {paper.id}] {paper.title[:60]}\n    {paper.pdf_path}\n -> {found}")
                if not dry_run:
                    paper.pdf_path = str(found)
                fixed_papers += 1
            else:
                print(f"  [PAPER {paper.id}] *** missing on disk: {current.name}")
                broken_papers += 1

        for af in sess.execute(select(AudioFile)).scalars().all():
            current = Path(af.file_path)
            if current.exists():
                continue
            found = audio_lookup.get(current.name) or audio_lookup.get(current.name.split("_", 1)[-1])
            if found:
                print(f"  [AUDIO {af.id}] {af.filename}\n    {af.file_path}\n -> {found}")
                if not dry_run:
                    af.file_path = str(found)
                fixed_audio += 1
            else:
                print(f"  [AUDIO {af.id}] *** missing on disk: {current.name}")
                broken_audio += 1

        if not dry_run:
            sess.commit()

    print(f"\nPDFs  fixed={fixed_papers}  still-missing={broken_papers}")
    print(f"Audio fixed={fixed_audio}  still-missing={broken_audio}")
    print("(dry-run — nothing written)" if dry_run else "\nDone.")


def recover_from(target: str, source: str, dry_run: bool) -> None:
    """
    Pull records whose files no longer exist from SOURCE db,
    re-point them to files found in TARGET's on-disk dirs,
    insert into TARGET db, delete from SOURCE db.
    """
    cfg = get_settings()
    src_dirs = cfg.get_project_dirs(source)
    dst_dirs = cfg.get_project_dirs(target)

    print(f"Source project : {source}  (DB: {src_dirs.db_path})")
    print(f"Target project : {target}  (DB: {dst_dirs.db_path})")
    print(f"Target uploads : {dst_dirs.upload_dir}")
    print(f"Target audio   : {dst_dirs.audio_dir}")
    print(f"Dry run        : {dry_run}\n")

    pdf_lookup   = _build_lookup(dst_dirs.upload_dir, "*.pdf")
    audio_lookup = _build_lookup(dst_dirs.audio_dir,  "*.mp3")

    migrated = skipped = 0

    with get_session(source) as src_sess:
        papers = src_sess.execute(select(Paper)).scalars().all()

        for paper in papers:
            # Determine new pdf path
            new_pdf: str | None = None
            if paper.pdf_path:
                old_pdf = Path(paper.pdf_path)
                if old_pdf.exists():
                    # File still in source dir — not our job here
                    skipped += 1
                    print(f"  [SKIP PAPER {paper.id}] file still exists at source: {old_pdf}")
                    continue
                found = pdf_lookup.get(old_pdf.name) or pdf_lookup.get(old_pdf.name.split("_", 1)[-1])
                if not found:
                    print(f"  [SKIP PAPER {paper.id}] cannot find '{old_pdf.name}' in target uploads")
                    skipped += 1
                    continue
                new_pdf = str(found)

            # Snapshot audio
            audio_rows = []
            all_audio_ok = True
            for af in paper.audio_files:
                old_a = Path(af.file_path)
                new_a_path: str
                if old_a.exists():
                    new_a_path = str(old_a)
                else:
                    fa = audio_lookup.get(old_a.name) or audio_lookup.get(old_a.name.split("_", 1)[-1])
                    if fa:
                        new_a_path = str(fa)
                    else:
                        print(f"    [AUDIO {af.id}] *** missing: {old_a.name}")
                        new_a_path = af.file_path  # keep stale; don't block paper migration
                audio_rows.append({
                    "filename": af.filename,
                    "file_path": new_a_path,
                    "duration_seconds": af.duration_seconds,
                    "tts_backend": af.tts_backend,
                    "tts_voice": af.tts_voice,
                    "created_at": af.created_at,
                })

            print(f"  [PAPER {paper.id}] {paper.title[:60]}")
            print(f"    pdf: {paper.pdf_path}")
            print(f"      → {new_pdf}")
            for i, a in enumerate(audio_rows):
                print(f"    audio[{i}]: {a['file_path']}")

            if not dry_run:
                with get_session(target) as dst_sess:
                    new_paper = Paper(
                        title=paper.title,
                        authors=paper.authors,
                        abstract=paper.abstract,
                        arxiv_id=paper.arxiv_id,
                        pdf_path=new_pdf,
                        pdf_url=paper.pdf_url,
                        created_at=paper.created_at,
                    )
                    dst_sess.add(new_paper)
                    dst_sess.flush()
                    for a in audio_rows:
                        dst_sess.add(AudioFile(
                            paper_id=new_paper.id,
                            filename=a["filename"],
                            file_path=a["file_path"],
                            duration_seconds=a["duration_seconds"],
                            tts_backend=a["tts_backend"],
                            tts_voice=a["tts_voice"],
                            created_at=a["created_at"],
                        ))
                    dst_sess.commit()

                src_sess.delete(paper)

            migrated += 1

        if not dry_run:
            src_sess.commit()

    print(f"\nMigrated={migrated}  Skipped={skipped}")
    print("(dry-run — nothing written)" if dry_run else f"\nDone. Records moved from '{source}' → '{target}'.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Repair or recover audia project DB records.")
    parser.add_argument("--project", default=DEFAULT_PROJECT, help="Target project (default: 'default')")
    parser.add_argument("--recover-from", metavar="SOURCE", help="Migrate broken records from SOURCE into --project")
    parser.add_argument("--dry-run", action="store_true", help="Print what would change without writing")
    args = parser.parse_args()

    if args.recover_from:
        recover_from(args.project, args.recover_from, args.dry_run)
    else:
        repair(args.project, args.dry_run)
