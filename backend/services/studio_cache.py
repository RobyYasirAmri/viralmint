# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Smart Video Studio — cache retention.

What the sweep removes (once per boot — there is no scheduler here, and the
leftovers it cleans mostly exist because a process died), and why each rule is
safe:

  * Voice takes no project document references, older than 30 days. A take
    referenced by ANY state (ready, stale — kept for undo — or generating) is
    kept at any age; the reference set is every project document — a
    sweeper's reference set must cover every place that points at a file.
    The rendered mp4 and its narration copy don't need the cached take.
  * A take's audio whose metadata never landed (a crash between the two
    atomic replaces), older than a day — it can never be served as a take.
  * Stock previews not used for 14 days. A preview is a re-downloadable copy of
    public stock (`ensure_preview` refreshes the mtime on every use).
  * `.part` files older than a day — interrupted writes.
  * Project folders whose project row no longer exists, older than a day — a
    delete that died between the row and the folder.
  * Render scratch (`TMP_DIR/studio_render_<job>`) older than RENDER_SCRATCH_HOURS
    whose render job isn't pending/running — a render killed mid-way (crash,
    quit) never reached its own cleanup. Only these folders: TMP_DIR as a
    whole is never purged (it holds yt-dlp's cookie jar and media uploads).

Nothing here touches the Library, generated videos or a live project's files.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from pathlib import Path

from sqlalchemy import select

from backend.config import settings

logger = logging.getLogger(__name__)

VOICE_UNREFERENCED_DAYS = 30
PREVIEW_UNUSED_DAYS = 14
PART_HOURS = 24
ORPHAN_PROJECT_HOURS = 24
RENDER_SCRATCH_HOURS = 6
RENDER_SCRATCH_PREFIX = "studio_render_"


async def referenced_take_keys_and_projects() -> tuple[set[str], set[str]]:
    from backend.database import AsyncSessionLocal
    from backend.models.video_project import VideoProject

    keys: set[str] = set()
    ids: set[str] = set()
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(VideoProject.id, VideoProject.doc_json))).all()
    for project_id, doc_json in rows:
        ids.add(project_id)
        try:
            doc = json.loads(doc_json or "{}")
        except ValueError:
            continue
        for scene in doc.get("scenes") or []:
            key = (scene.get("voice") or {}).get("take_key")
            if isinstance(key, str):
                keys.add(key)
    return keys, ids


def _age_seconds(path: Path, now: float) -> float:
    try:
        return now - path.stat().st_mtime
    except OSError:
        return 0.0


def _unlink(path: Path) -> bool:
    try:
        path.unlink()
        return True
    except OSError:
        return False


async def live_render_job_prefixes() -> set[str]:
    """The 8-character id prefixes render scratch folders are named by, for
    render jobs still pending/running."""
    from backend.database import AsyncSessionLocal
    from backend.models.job import Job
    async with AsyncSessionLocal() as db:
        ids = (await db.execute(select(Job.id).where(
            Job.job_type == "generate", Job.status.in_(["pending", "running"])))).scalars().all()
    return {job_id[:8] for job_id in ids}


def _sweep_files(referenced: set[str], project_ids: set[str], now: float,
                 live_renders: set[str] | None = None) -> dict:
    from backend.services import studio_media
    from backend.services import voice_take_service as vts

    counts = {"voice_takes": 0, "previews": 0, "parts": 0, "orphan_projects": 0, "orphan_take_audio": 0,
              "render_scratch": 0}
    day = 86400

    voice_dir = vts.cache_dir()
    if voice_dir.is_dir():
        for meta_path in voice_dir.glob("*.json"):
            key = meta_path.stem
            if not vts.is_valid_key(key) or key in referenced:
                continue
            try:
                created = float(json.loads(meta_path.read_text(encoding="utf-8")).get("created_at") or 0)
            except (OSError, ValueError, TypeError):
                created = 0.0
            age = now - created if created else _age_seconds(meta_path, now)
            if age > VOICE_UNREFERENCED_DAYS * day:
                _unlink(voice_dir / f"{key}.mp3")
                if _unlink(meta_path):
                    counts["voice_takes"] += 1
        for audio in voice_dir.glob("*.mp3"):
            key = audio.stem
            if not vts.is_valid_key(key) or key in referenced or (voice_dir / f"{key}.json").exists():
                continue
            if _age_seconds(audio, now) > PART_HOURS * 3600 and _unlink(audio):
                counts["orphan_take_audio"] += 1

    preview_dir = studio_media.preview_dir()
    for folder in (voice_dir, preview_dir):
        if not folder.is_dir():
            continue
        for part in folder.glob("*.part*"):
            if _age_seconds(part, now) > PART_HOURS * 3600 and _unlink(part):
                counts["parts"] += 1
    if preview_dir.is_dir():
        for preview in preview_dir.glob("*.mp4"):
            if _age_seconds(preview, now) > PREVIEW_UNUSED_DAYS * day and _unlink(preview):
                counts["previews"] += 1

    projects_dir = settings.STUDIO_DIR / "projects"
    if projects_dir.is_dir():
        for folder in projects_dir.iterdir():
            if folder.is_dir() and folder.name not in project_ids \
                    and _age_seconds(folder, now) > ORPHAN_PROJECT_HOURS * 3600:
                shutil.rmtree(folder, ignore_errors=True)
                counts["orphan_projects"] += 1

    if live_renders is not None and settings.TMP_DIR.is_dir():
        for folder in settings.TMP_DIR.glob(f"{RENDER_SCRATCH_PREFIX}*"):
            job_prefix = folder.name[len(RENDER_SCRATCH_PREFIX):]
            if folder.is_dir() and job_prefix not in live_renders \
                    and _age_seconds(folder, now) > RENDER_SCRATCH_HOURS * 3600:
                shutil.rmtree(folder, ignore_errors=True)
                counts["render_scratch"] += 1
    return counts


async def sweep(*, now: float | None = None) -> dict:
    referenced, project_ids = await referenced_take_keys_and_projects()
    try:
        live_renders = await live_render_job_prefixes()
    except Exception:  # noqa: BLE001 — unsure what's live → leave every scratch folder alone
        logger.warning("studio cache: couldn't read live render jobs", exc_info=True)
        live_renders = None
    return await asyncio.to_thread(_sweep_files, referenced, project_ids, now or time.time(), live_renders)
