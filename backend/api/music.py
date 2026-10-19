# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""REST /api/music — the background-music library (files in storage/music/).

Tracks are files you drop into that directory yourself. The Smart Video
Studio lists them to pick a bed and plays them in its preview.
"""
from fastapi import APIRouter, Request

from backend.services.music_service import LIBRARY_EXTS, MUSIC_DIR, MUSIC_GENRES, display_name, extract_genre

router = APIRouter()


@router.get("/music/library")
async def list_library():
    """Every track in the music library, with the name surfaces show for it."""
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    tracks = []
    for path in sorted(MUSIC_DIR.iterdir()):
        if not path.is_file() or path.suffix.lower() not in LIBRARY_EXTS:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size <= 0:
            continue
        tracks.append({
            "filename": path.name,
            "display_name": display_name(path.name),
            "genre": extract_genre(path.name),
            "size_bytes": size,
            "stream_url": f"/api/music/stream/{path.name}",
        })
    return {"tracks": tracks, "genres": list(MUSIC_GENRES.keys())}


@router.get("/music/stream/{filename}")
async def stream_track(filename: str, request: Request):
    """Stream one library track (Range-aware) — the same guarded route the
    Library's player uses."""
    from backend.api.library import stream_track as library_stream
    return await library_stream(filename, request)
