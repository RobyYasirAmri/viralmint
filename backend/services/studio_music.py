# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Smart Video Studio — the project's music bed: a CONCRETE library track.

A bed that is on but names no track gets one picked from the music library
(storage/music/), so what the editor previews is what the render mixes — a
render never picks a random track the user didn't hear. While the genre is
still the untouched default ("lofi"), the video's Look and scene moods choose
it.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# The genre a Look suggests, and the scene moods that override it.
_STYLE_GENRES = {"cinematic": "cinematic", "documentary": "ambient", "educational": "corporate",
                 "card": "ambient", "noir": "cinematic", "neon": "upbeat", "vintage": "lofi", "vlog": "lofi"}
_MOOD_GENRES = {"energetic": "upbeat", "upbeat": "upbeat", "bright": "upbeat", "playful": "upbeat",
                "dark": "cinematic", "moody": "cinematic", "tense": "cinematic", "dramatic": "cinematic",
                "calm": "ambient", "cool": "ambient", "serene": "ambient"}


def suggested_genre(visual_style: str | None, moods: list | None = None) -> str:
    """A bed for the video: the scene moods when most of them agree, else the Look's."""
    votes: dict[str, int] = {}
    moods = [str(m).lower() for m in (moods or []) if m]
    for m in moods:
        g = _MOOD_GENRES.get(m)
        if g:
            votes[g] = votes.get(g, 0) + 1
    if votes:
        genre, n = max(votes.items(), key=lambda kv: kv[1])
        if n * 2 >= len(moods):
            return genre
    return _STYLE_GENRES.get(visual_style or "", "lofi")


async def default_music_op(doc: dict, moods: list | None = None) -> dict | None:
    """The `music_default` op for a project whose bed is on with no track: the
    genre's library track if there is one, else any library track. None when
    nothing is needed or the library is empty."""
    from backend.services import studio_doc as sd
    from backend.services.music_service import display_name, select_music

    music = doc["settings"]["music"]
    if not music.get("enabled") or music.get("track"):
        return None
    genre = music.get("genre") or "lofi"
    if genre == "lofi":
        moods = moods if moods is not None else [s.get("mood") for s in doc.get("scenes") or []]
        genre = suggested_genre(doc["settings"].get("visual_style"), moods)
    try:
        picked = await select_music(genre, int(sd.derive_timeline(doc)["total"]) or 60)
    except Exception as e:  # noqa: BLE001 — no track is a warning, never a failed plan or render
        logger.warning("studio: no library music picked (%s)", e)
        return None
    if picked is None:
        return None
    # The library's own display name, so the Music section and the timeline
    # show the same name the user sees when picking a track by hand.
    return {"op": "music_default", "track": picked.name, "track_name": display_name(picked.name), "genre": genre}
