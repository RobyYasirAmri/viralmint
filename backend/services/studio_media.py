# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Smart Video Studio — media.

Three kinds of footage reach a project, and each is trusted differently:

  * Stock candidates. Searched server-side (Pexels + Pixabay, 24 h cache) and
    REMEMBERED per project, so `bind_visual` binds the server's own copy of a
    result, never a URL the client made up. After a backend restart that
    memory is empty; a candidate is then accepted only if it is a well-formed
    candidate whose URLs are on its provider's hosts. Every download
    (preview now, render later) is limited to those hosts, with each redirect
    hop re-checked — a document can't make the backend fetch anything else.
  * Stock previews. The small variant, downloaded once into
    `STUDIO_DIR/cache/preview/` and served from there (no hotlinking),
    single-flight per file, size-capped, and probed before it is kept.
  * Your clips. Uploads are written into the project directly and get a
    poster frame; images are normalised to an opaque PNG.

Project media lives in `STUDIO_DIR/projects/<id>/assets/` and is served only
through the project's asset index — a request never names a path.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
import time
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urljoin, urlparse

from backend.config import settings
from backend.core.exceptions import StudioMediaError

logger = logging.getLogger(__name__)

STOCK_PROVIDERS = ("pexels", "pixabay")
# Hosts stock media is fetched from. Pexels serves files from videos.pexels.com
# (older links go through Vimeo's CDN); Pixabay from cdn.pixabay.com.
ALLOWED_STOCK_HOSTS = (
    "videos.pexels.com", "images.pexels.com", "player.vimeo.com", "vod-progressive.akamaized.net",
    "cdn.pixabay.com", "pixabay.com",
)
LICENSES = {"pexels": "Pexels License", "pixabay": "Pixabay Content License"}
PREVIEW_MAX_BYTES = 60 * 1024 * 1024
STOCK_MAX_BYTES = 250 * 1024 * 1024      # a full-size stock clip (render, B-roll, backgrounds)
MAX_REDIRECTS = 3
REMEMBERED_PER_PROJECT = 200
REMEMBERED_PROJECTS = 20              # projects whose search results stay in memory (LRU)
IMPORT_MAX_SECONDS = 20 * 60
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
UPLOAD_MAX_BYTES = 600 * 1024 * 1024

_ASSET_ID_RE = re.compile(r"^as_[0-9a-f]{16}$")
_PREVIEW_NAME_RE = re.compile(r"^(pexels|pixabay)_[A-Za-z0-9]{1,40}\.mp4$")


# ── hosts ───────────────────────────────────────────────────────────────────

def is_allowed_stock_url(url: object) -> bool:
    if not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and any(host == h or host.endswith(f".{h}") for h in ALLOWED_STOCK_HOSTS)


# ── stock candidates ────────────────────────────────────────────────────────

# project id → its remembered candidates, least recently used first. Bounded:
# a long-running backend used to keep every project ever opened. A project that
# falls out still binds (resolve_candidate rebuilds a well-formed candidate).
_remembered: "OrderedDict[str, OrderedDict]" = OrderedDict()


def forget(project_id: str) -> None:
    """Drop a project's remembered candidates (it was deleted)."""
    _remembered.pop(project_id, None)


def orientation(aspect_ratio: str) -> str:
    return "portrait" if aspect_ratio == "9:16" else "landscape"


def candidate_from_result(result: dict, query: str) -> dict | None:
    provider = result.get("source")
    provider_id = str(result.get("id") or "").removeprefix("pixabay_")
    download = result.get("download_url")
    if provider not in STOCK_PROVIDERS or not re.fullmatch(r"[A-Za-z0-9]{1,40}", provider_id) \
            or not is_allowed_stock_url(download):
        return None
    preview = result.get("preview_url")
    thumb = result.get("thumbnail")
    return {
        "provider": provider,
        "provider_id": provider_id,
        "download_url": download,
        "preview_url": preview if is_allowed_stock_url(preview) else download,
        "thumbnail": thumb if is_allowed_stock_url(thumb) else None,
        "creator": (result.get("creator") or "")[:120] or None,
        "license": LICENSES[provider],
        "media": "video",
        "native_duration": result.get("duration") or None,
        "width": result.get("width") or None,
        "height": result.get("height") or None,
        "query": (query or "")[:100],
    }


def remember(project_id: str, candidates: list[dict]) -> None:
    memory = _remembered.setdefault(project_id, OrderedDict())
    _remembered.move_to_end(project_id)
    while len(_remembered) > REMEMBERED_PROJECTS:
        _remembered.popitem(last=False)
    for c in candidates:
        key = (c["provider"], c["provider_id"])
        memory.pop(key, None)
        memory[key] = c
    while len(memory) > REMEMBERED_PER_PROJECT:
        memory.popitem(last=False)


def resolve_candidate_for(project_id: str):
    """The `resolve_candidate` studio_ops uses: the server copy, or None."""
    def resolve(candidate: dict) -> dict | None:
        if not isinstance(candidate, dict):
            return None
        key = (candidate.get("provider"), str(candidate.get("provider_id") or ""))
        hit = _remembered.get(project_id, {}).get(key)
        if hit is not None:
            return dict(hit)
        # Memory is empty after a restart: accept only what could have come
        # from a stock search — right provider, id shape and hosts.
        rebuilt = candidate_from_result({
            "source": candidate.get("provider"), "id": candidate.get("provider_id"),
            "download_url": candidate.get("download_url"), "preview_url": candidate.get("preview_url"),
            "thumbnail": candidate.get("thumbnail"), "creator": candidate.get("creator"),
            "duration": candidate.get("native_duration"), "width": candidate.get("width"),
            "height": candidate.get("height"),
        }, candidate.get("query") or "")
        return rebuilt
    return resolve


QUERY_MAX = 100
NO_KEY_MESSAGE = ("Add a Pexels or Pixabay API key (PEXELS_API_KEY / PIXABAY_API_KEY) "
                  "to search stock footage — or use your own clips.")


def stock_keys() -> tuple[str, str]:
    """(pexels, pixabay) keys the Studio searches with. A provider pinned by
    STOCK_MEDIA_PROVIDER leaves the other one out."""
    from backend.services.stock_media import StockProvider, configured_providers
    on = configured_providers()
    return ((settings.PEXELS_API_KEY or "").strip() if StockProvider.PEXELS in on else "",
            (settings.PIXABAY_API_KEY or "").strip() if StockProvider.PIXABAY in on else "")


async def search_candidates(project_id: str, query: str, aspect_ratio: str = "9:16") -> list[dict]:
    from backend.services.stock_video_service import search_stock_candidates

    q = " ".join((query or "").split())[:QUERY_MAX].strip()
    if len(q) < 2:
        raise StudioMediaError("Type at least two letters to search.")
    pexels, pixabay = stock_keys()
    if not pexels and not pixabay:
        raise StudioMediaError(NO_KEY_MESSAGE)
    results = await search_stock_candidates(q, orientation=orientation(aspect_ratio),
                                            pexels_api_key=pexels, pixabay_api_key=pixabay, per_page=12)
    candidates = [c for c in (candidate_from_result(r, q) for r in results) if c][:12]
    remember(project_id, candidates)
    return candidates


# ── previews ────────────────────────────────────────────────────────────────

def preview_dir() -> Path:
    return settings.STUDIO_DIR / "cache" / "preview"


def preview_path(name: object) -> Path | None:
    if not isinstance(name, str) or not _PREVIEW_NAME_RE.match(name):
        return None
    path = preview_dir() / name
    return path if path.is_file() and path.stat().st_size > 0 else None


_WRITE_BATCH_BYTES = 1024 * 1024


async def download(url: str, dest: Path, max_bytes: int = STOCK_MAX_BYTES) -> None:
    """Stream `url` to `dest`, following at most MAX_REDIRECTS hops by hand so
    EVERY hop is checked against the stock hosts. The Studio's one stock
    downloader: the render and the previews."""
    import httpx
    current = url
    async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=15), follow_redirects=False) as client:
        for _hop in range(MAX_REDIRECTS + 1):
            if not is_allowed_stock_url(current):
                raise StudioMediaError("That footage isn't on a stock footage host.")
            async with client.stream("GET", current) as resp:
                if resp.is_redirect:
                    current = urljoin(current, resp.headers.get("location", ""))
                    continue
                if resp.status_code != 200:
                    raise StudioMediaError(f"The stock site answered {resp.status_code} — try another clip.")
                size = 0
                pending: list[bytes] = []
                pending_size = 0
                # File writes run off the event loop, batched (~1 MB): a render
                # downloads five clips of up to 250 MB at once, and synchronous
                # 64 KB writes stalled the loop (worst on Windows with Defender).
                f = await asyncio.to_thread(open, dest, "wb")
                try:
                    async for chunk in resp.aiter_bytes(65536):
                        size += len(chunk)
                        if size > max_bytes:
                            raise StudioMediaError("That clip is too large.")
                        pending.append(chunk)
                        pending_size += len(chunk)
                        if pending_size >= _WRITE_BATCH_BYTES:
                            await asyncio.to_thread(f.write, b"".join(pending))
                            pending, pending_size = [], 0
                    if pending:
                        await asyncio.to_thread(f.write, b"".join(pending))
                finally:
                    await asyncio.to_thread(f.close)
                return
    raise StudioMediaError("Too many redirects fetching that clip.")


_preview_locks: dict[str, asyncio.Lock] = {}


async def ensure_preview(candidate: dict) -> str:
    """Download the candidate's preview once; returns its cache file name."""
    from backend.services.video_utils import probe_duration

    name = f"{candidate['provider']}_{candidate['provider_id']}.mp4"
    if not _PREVIEW_NAME_RE.match(name):
        raise StudioMediaError("That isn't a stock clip.")
    url = candidate.get("preview_url") or candidate.get("download_url")
    if not is_allowed_stock_url(url):
        raise StudioMediaError("That footage isn't on a stock footage host.")
    hit = preview_path(name)
    if hit:
        os.utime(hit, None)           # recently used — the sweeper keeps it
        return name
    lock = _preview_locks.setdefault(name, asyncio.Lock())
    try:
        async with lock:
            if preview_path(name):
                return name
            preview_dir().mkdir(parents=True, exist_ok=True)
            part = preview_dir() / f"{name}.part"
            try:
                await download(url, part, PREVIEW_MAX_BYTES)
                if await asyncio.to_thread(probe_duration, part, 0.0) <= 0:
                    raise StudioMediaError("That preview isn't a playable video.")
                os.replace(part, preview_dir() / name)
            finally:
                part.unlink(missing_ok=True)
    finally:
        # The file is in place before the lock is released, so a later request
        # finds it without the lock — no need to keep one entry per clip forever.
        if _preview_locks.get(name) is lock and not lock.locked() and not getattr(lock, "_waiters", None):
            _preview_locks.pop(name, None)
    return name


# ── project assets (uploads) ────────────────────────────────────────────────

def project_assets_dir(project_id: str) -> Path:
    root = (settings.STUDIO_DIR / "projects").resolve()
    path = (root / project_id).resolve()
    if path.parent != root:
        raise StudioMediaError("Bad project id.")
    return path / "assets"


def new_asset_id() -> str:
    return f"as_{secrets.token_hex(8)}"


def asset_file(project_id: str, record: dict, *, poster: bool = False) -> Path | None:
    """The file behind an index record — only names the index wrote, only
    inside this project's assets dir."""
    name = record.get("poster" if poster else "file")
    if not isinstance(name, str) or "/" in name or "\\" in name or name.startswith("."):
        return None
    base = project_assets_dir(project_id)
    path = (base / name).resolve()
    return path if path.parent == base.resolve() and path.is_file() else None


def doc_asset(record: dict) -> dict:
    """What a bound visual carries about an import (no file names)."""
    return {k: record[k] for k in ("asset_id", "title", "media", "native_duration", "width", "height")
            if record.get(k) is not None}


def public_asset(project_id: str, record: dict) -> dict:
    base = f"/api/studio/media/{project_id}/{record['asset_id']}"
    return {**doc_asset(record), "source": record.get("source"), "created_at": record.get("created_at"),
            "url": base, "poster_url": f"{base}?poster=1" if record.get("poster") else None}


async def poster(video: Path, dest: Path, duration: float) -> str | None:
    from backend.services.ffmpeg_service import extract_frame_at
    out = await extract_frame_at(video, min(1.0, max(0.0, duration / 2)), dest, scale_width=480)
    return dest.name if out and Path(out).is_file() else None


async def add_video(project_id: str, src: Path, *, title: str, source: str) -> dict:
    """Register an uploaded video file as a project asset (`src` is ours to
    move — a temp file the upload wrote)."""
    from backend.services.video_utils import probe_media

    width, height, duration = await asyncio.to_thread(probe_media, src)
    if not duration or duration <= 0 or not width or not height:
        raise StudioMediaError("That file doesn't contain a playable video.")
    if duration > IMPORT_MAX_SECONDS:
        raise StudioMediaError("That video is longer than 20 minutes — trim it in Clipper first.")
    asset_id = new_asset_id()
    suffix = src.suffix.lower() if src.suffix.lower() in VIDEO_SUFFIXES else ".mp4"
    dest = project_assets_dir(project_id) / f"{asset_id}{suffix}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(os.replace, src, dest)
    poster_name = await poster(dest, dest.with_suffix(".jpg"), float(duration))
    return {
        "asset_id": asset_id, "title": (title or dest.name)[:200], "media": "video", "source": source,
        "native_duration": round(float(duration), 3), "width": int(width), "height": int(height),
        "file": dest.name, "poster": poster_name, "created_at": time.time(),
    }


async def add_image(project_id: str, src: Path, *, title: str, source: str) -> dict:
    """Register an uploaded still as a project asset — normalised to one
    opaque, bounded PNG (an alpha cut-out composites onto black instead of
    showing garbage under the dropped channel)."""
    from backend.core.exceptions import VideoGenerationError
    from backend.services.ffmpeg_service import normalize_still
    from backend.services.video_utils import probe_dimensions

    width, height = await asyncio.to_thread(probe_dimensions, src)
    if not width or not height:
        raise StudioMediaError("That file isn't a readable image.")
    asset_id = new_asset_id()
    dest = project_assets_dir(project_id) / f"{asset_id}.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        out_w, out_h = await normalize_still(src, dest)
    except VideoGenerationError as e:
        dest.unlink(missing_ok=True)
        raise StudioMediaError("That file isn't a readable image.") from e
    return {
        "asset_id": asset_id, "title": (title or dest.name)[:200], "media": "image", "source": source,
        "width": out_w, "height": out_h, "file": dest.name, "poster": dest.name, "created_at": time.time(),
    }


def is_asset_id(value: object) -> bool:
    return isinstance(value, str) and bool(_ASSET_ID_RE.match(value))
