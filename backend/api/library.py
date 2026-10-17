# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Library API — one faceted view over everything you own, plus its lineage.

    GET    /api/library/items?media=&origin=&producer=&q=&sort=&limit=&offset=
    GET    /api/library/families?…            group-by-what-it-was-made-from
    GET    /api/library/item?key=             one row (title, urls, store)
    GET    /api/library/lineage?key=          ancestors + children
    GET    /api/library/taxonomy              axis labels + the producer map
    GET    /api/library/poster?key=&w=        grid poster: a frame, or a scaled image
    GET    /api/library/asset/{job_id}        stream/download a tool output
    DELETE /api/library/asset/{job_id}        remove the row and its file
    POST   /api/library/bulk-delete           the same, for a selection

The classification lives in `library_taxonomy`; the projection over the four
stores lives in `library_index`. This module is the HTTP shape and nothing
else, deliberately — the two questions the taxonomy answers are the same
whether they are asked by this router, by the page or by a test.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.job import Job
from backend.services import library_index
from backend.services.library_taxonomy import classify, taxonomy_payload

# The "/api" half is added at registration, like every other router here.
router = APIRouter(prefix="/library", tags=["library"])
logger = logging.getLogger(__name__)

# Seek past a black intro frame. A clip SHORTER than this yields no frame at
# all, which is handled at the callsite rather than by lowering the seek.
POSTER_SEEK_SECONDS = 2.0

# Image outputs the poster endpoint downscales instead of extracting from.
# `.gif` is included: thumb_scale rescales every frame, so the tile still
# animates (library_index.ANIMATED_SUFFIXES lists what stays on the raw URL).
_POSTER_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff"}

# MIME by suffix used to live here as a second copy. It is `videos._MEDIA_TYPES`
# now — the same map the range-aware streamer picks a Content-Type from, so an
# asset cannot be typed one way when downloaded and another when scrubbed.


@router.get("/items")
async def list_items(
    media: str | None = Query(None, description="Comma-separated: video,image,audio,doc"),
    origin: str | None = Query(None, description="Comma-separated: created,edited,imported"),
    producer: str | None = Query(None, description="Comma-separated producer keys (e.g. tool:captions)"),
    q: str | None = Query(None, description="Substring match on title / tool / niche"),
    sort: str = Query("newest"),
    limit: int = Query(library_index.DEFAULT_LIMIT, ge=1, le=library_index.MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """One faceted page across everything you own.

    Unions generated videos, downloads/imports, tool outputs and music-library
    tracks into a single classified list. Filters are two orthogonal axes —
    `media` (what a file is) and `origin` (where it came from) — plus an
    optional `producer` narrowing and a title search.

    Rows whose file is missing on disk are omitted, never deleted: a read must
    not mutate.

    Returns: {items, total, limit, offset, facets: {all, media, origin,
    producers}, library_total}. Each item carries `key` ("gv:<id>" / "dl:<id>" /
    "job:<id>" / "trk:<name>"), `media`, `origin`, `producer`, `parent_key` for
    lineage, plus title / thumb_url / stream_url / aspect / duration_seconds /
    size_mb / created_at.
    """
    return await library_index.query(
        db, media=media, origin=origin, producer=producer,
        q=q, sort=sort, limit=limit, offset=offset,
    )


@router.get("/families")
async def list_families(
    media: str | None = Query(None),
    origin: str | None = Query(None),
    producer: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """The same items grouped by what they were made from.

    A download appears with the clips cut from it and the captioned version of
    one of those clips as one family. Members outside the current filters are
    still returned (the caller dims them) because that context is the whole
    reason to use this view.

    Paged: a family carries its whole subtree, so this is the one view that
    could otherwise hand the browser thousands of rows at once.

    Returns: {families: [{root, children: [{item, children}]}], loners,
    matched_keys, family_total, loner_total, limit, offset, total}.
    """
    return await library_index.families(
        db, limit=limit, offset=offset,
        media=media, origin=origin, producer=producer, q=q,
    )


@router.get("/item")
async def get_item(
    key: str = Query(..., description='Item key, e.g. "gv:<id>" or "job:<id>"'),
    db: AsyncSession = Depends(get_db),
):
    """One library item by key. 404 when the key names nothing in the index."""
    result = await library_index.lineage(db, key)
    if result is None:
        raise HTTPException(status_code=404, detail="Item not found in the library index")
    return result["item"]


@router.get("/lineage")
async def get_lineage(
    key: str = Query(..., description='Item key, e.g. "gv:<id>" or "job:<id>"'),
    db: AsyncSession = Depends(get_db),
):
    """What an item was made from, and what was made from it.

    Powers the drawer's Lineage tab. Asked per item rather than held for the
    whole library, because the grid deliberately does not load the family tree.

    Returns: {item, ancestors: [nearest first], children}. 404 when the key
    names nothing (a deleted row, or a file that has since gone).
    """
    result = await library_index.lineage(db, key)
    if result is None:
        raise HTTPException(status_code=404, detail="Item not found in the library index")
    return result


@router.get("/taxonomy")
async def get_taxonomy():
    """Axis labels + the producer map, so the UI renders from one source.

    Returns: {media: [{key, label}], origins: [{key, label, hint}],
    producers: [{key, label, media, origin}]}.
    """
    return taxonomy_payload()


@router.get("/poster")
async def get_poster(
    key: str = Query(..., description='Item key: "job:<id>", or "gv:<id>" / "dl:<id>" with no stored thumbnail'),
    w: int | None = Query(None, description="Grid width — see thumb_scale.ALLOWED_WIDTHS"),
    v: str | None = Query(None, description="Ignored; a cache-buster the caller may add"),
    db: AsyncSession = Depends(get_db),
):
    """Grid poster for a library item, built on first request.

    Nothing in the tool pipeline writes a thumbnail, so every edited video — a
    captioned cut, a reframe, a merge — had no image to show; nor did an import,
    a download whose platform served none, or a render whose thumbnail step
    failed. Extract one frame (2s in, past any black intro), cache it under
    THUMBNAILS_DIR, and serve it. No DB write: this is a read.

    An IMAGE output takes the same route minus the extraction — it is already
    its own poster, but at full resolution, so it gets the same downscaled,
    `immutable` copy every video tile gets.

    404 when the key names no indexed image/video, or the file cannot be read
    (a corrupt or truncated video). The tile then shows an explicit "no
    preview" state. A failed extraction is remembered until the source file
    changes, so a broken file costs one ffmpeg run, not one per page load.
    """
    from backend.config import settings as app_settings
    from backend.services import thumb_scale
    from backend.services.ffmpeg_service import extract_frame_at

    src = await library_index.poster_source(db, key)
    stem = library_index.poster_cache_stem(key)
    if src is None or stem is None:
        raise HTTPException(status_code=404, detail="No poster for that item")

    width = thumb_scale.normalize_width(w)
    immutable = {"Cache-Control": "public, max-age=31536000, immutable"}

    # An image needs no frame extraction — scale it straight into the cache.
    # The copy lands in THUMBNAILS_DIR, not beside the user's asset, so
    # `drop_poster_cache` remains the single place that cleans up after it.
    if src.suffix.lower() in _POSTER_IMAGE_SUFFIXES:
        dest = app_settings.THUMBNAILS_DIR / f"{stem}{thumb_scale.output_suffix(src)}"
        served = await thumb_scale.scaled_into(src, dest, width or thumb_scale.DEFAULT_WIDTH)
        return FileResponse(served, media_type=thumb_scale.media_type(served), headers=immutable)

    cache = app_settings.THUMBNAILS_DIR / f"{stem}.jpg"
    failed = app_settings.THUMBNAILS_DIR / f"{stem}.fail"
    try:
        src_mtime = src.stat().st_mtime
    except OSError:
        raise HTTPException(status_code=404, detail="Could not read the source file")
    # A source replaced since the frame was taken (re-rendered in place) gets a
    # fresh frame; an unchanged one that already failed is not retried.
    if cache.is_file() and cache.stat().st_mtime < src_mtime:
        cache.unlink(missing_ok=True)
    if not cache.is_file():
        if failed.is_file() and failed.stat().st_mtime >= src_mtime:
            raise HTTPException(status_code=404, detail="Could not extract a poster")
        produced = await extract_frame_at(src, POSTER_SEEK_SECONDS, cache)
        if produced is None or not cache.is_file():
            # A clip SHORTER than the seek yields zero frames and ffmpeg exits
            # non-zero — ordinary for GIF sources and quick transforms. Retry
            # from the first frame before giving up.
            produced = await extract_frame_at(src, 0.0, cache)
        if produced is None or not cache.is_file():
            try:
                failed.parent.mkdir(parents=True, exist_ok=True)
                failed.touch()
            except OSError:  # pragma: no cover — the marker is an optimisation
                pass
            raise HTTPException(status_code=404, detail="Could not extract a poster")
        failed.unlink(missing_ok=True)
    # Extracted at the video's own resolution — downscale for the grid.
    cache = await thumb_scale.scaled_thumbnail(cache, width)
    return FileResponse(cache, media_type="image/jpeg", headers=immutable)


async def resolve_asset_path(job_id: str, db: AsyncSession) -> Path:
    """Resolve a tool output's job id to its file on disk, or raise.

    The rule is: **what the Library shows, this serves.** Gating on a separate
    allowlist is how the two drift — a tile whose download 404s is worse than
    one that was never shown, because the user has already been told it exists.

    Shared by the stream and delete endpoints so both go through the same
    classification and the same traversal-safe path resolution.
    """
    job = await db.get(Job, job_id)
    if not job or job.status != "success" or classify(job.job_type) is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    if not job.output_json:
        raise HTTPException(status_code=404, detail="Asset has no output")
    try:
        out = json.loads(job.output_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Corrupt output_json")
    file_str = (out or {}).get("file")
    if not file_str:
        raise HTTPException(status_code=404, detail="Asset has no file")

    from backend.api.videos import _safe_resolve_path
    path = _safe_resolve_path(file_str)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Asset file missing on disk")
    return path


@router.get("/asset/{job_id}")
async def stream_asset(job_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Stream a tool output — the tile's preview, the drawer's player, and the
    only download the Library offers for a file no other route serves.

    Range-aware via the shared helper: the drawer's player scrubs these, and a
    media element that cannot seek re-downloads the file to move the playhead.
    """
    path = await resolve_asset_path(job_id, db)
    from backend.api.videos import serve_media_with_range
    return serve_media_with_range(path, request, filename=path.name)


@router.get("/track/{filename}")
async def stream_track(filename: str, request: Request):
    """Stream a background-music file from storage/music/.

    There is no music router here — tracks are files you drop into that
    directory yourself — but they are still files you own, so the Library lists
    them and therefore has to be able to play them. Path traversal is refused
    the same way the music service refuses it: resolve, then require the result
    to still be inside the directory.
    """
    from backend.services.music_service import MUSIC_DIR
    from backend.services.library_index import MUSIC_EXTS

    try:
        candidate = (MUSIC_DIR / filename).resolve()
    except (OSError, ValueError):
        raise HTTPException(status_code=400, detail="Bad track name")
    if not candidate.is_relative_to(MUSIC_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Bad track name")
    if not candidate.is_file() or candidate.suffix.lower() not in MUSIC_EXTS:
        raise HTTPException(status_code=404, detail="Track not found")
    from backend.api.videos import serve_media_with_range
    return serve_media_with_range(candidate, request, filename=candidate.name)


def _drop_poster_cache(job_id: str) -> None:
    """Remove the extracted poster (and its scaled copies) for a deleted job
    asset. Without this, every deleted edited video leaves orphaned JPEGs
    behind forever."""
    library_index.drop_poster_cache(f"{library_index.KEY_JOB}:{job_id}")


def _unlink_job_output(job: Job) -> None:
    """Best-effort removal of the file a job wrote.

    Traversal-rejected or already-missing paths are skipped rather than raised:
    the ROW still has to disappear, or the Library keeps a tile for a file the
    user asked to be rid of.
    """
    if not job.output_json:
        return
    try:
        out = json.loads(job.output_json)
    except json.JSONDecodeError:
        return
    file_str = (out or {}).get("file")
    if not file_str:
        return
    from backend.api.videos import _safe_resolve_path
    try:
        path = _safe_resolve_path(file_str)
    except HTTPException:
        logger.warning("Skipped unsafe file delete for job %s", job.id)
        return
    if path.is_file():
        path.unlink(missing_ok=True)


@router.delete("/asset/{job_id}")
async def delete_asset(job_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a tool output's file and its job row.

    Idempotent in the way that matters: a stale UI calling twice gets a 404 on
    the second call, but the first always cleans up everything it could.
    """
    job = await db.get(Job, job_id)
    if not job or classify(job.job_type) is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    _unlink_job_output(job)
    _drop_poster_cache(job_id)
    await db.delete(job)
    await db.commit()
    return {"ok": True}


@router.post("/bulk-delete")
async def bulk_delete_assets(body: dict, db: AsyncSession = Depends(get_db)):
    """Delete many tool outputs at once. Body: {"job_ids": [...]}.

    404 only when NONE of the requested ids exist; a partial match succeeds
    with `deleted` reflecting what actually went, because a selection spanning
    several stores is normal and failing the whole call would strand it.
    """
    job_ids = body.get("job_ids", [])
    if not job_ids or not isinstance(job_ids, list):
        raise HTTPException(status_code=400, detail="job_ids must be a non-empty list")
    if len(job_ids) > 200:
        raise HTTPException(status_code=400, detail="Cannot delete more than 200 assets at once")

    rows = (await db.execute(select(Job).where(Job.id.in_(job_ids)))).scalars().all()
    rows = [j for j in rows if classify(j.job_type) is not None]
    if not rows:
        raise HTTPException(status_code=404, detail="No matching assets found")

    deleted = 0
    for job in rows:
        _unlink_job_output(job)
        _drop_poster_cache(job.id)
        await db.delete(job)
        deleted += 1
    await db.commit()
    return {"ok": True, "deleted": deleted}
