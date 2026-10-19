# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Smart Video Studio — the `POST /api/generate/stock` adapter.

Every caller of the one-shot endpoint (MCP's `generate_smart_video`, scripts,
older bookmarks) keeps its request and its `{job_id}` answer. Underneath, the
request becomes a real Studio PROJECT — planned, voiced with the requested
voice, the caller's own stills placed on the opening scenes, a concrete music
track picked — and render v2 renders it. So every such render is an editable
project afterwards, and there is one render path to keep correct.

Scope: SCRIPT mode. A single `start_image` animated as the whole video has no
Studio equivalent and stays on the one-shot pipeline (api/generate.py routes
it there explicitly).
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

# The one-shot pipeline's transition names → the Studio's sync-safe looks.
LEGACY_TRANSITIONS = {"auto": "smooth", "fade": "smooth", "slide": "dynamic", "zoom": "dynamic", "whip": "punchy"}


async def create_from_legacy(body, *, user_id: str = "local") -> str:
    """The project for a legacy request — created synchronously so the endpoint
    can validate (400) and answer {job_id, project_id} at once. Planning, the
    caller's stills and music land later in `prepare_legacy`, inside the job.

    `body` is api/generate.StockGenerateRequest.
    """
    from backend.core.exceptions import StudioDocError
    from backend.services import studio_doc as sd
    from backend.services import studio_store as store
    from backend.services.caption_service import captions_disabled, style_id_known

    # "none"/"off" is the legacy DISABLE sentinel, honoured here before the
    # project exists (the ASS builder would render it as `viral`); any other
    # unknown id is refused — a caller must never get a silently different style.
    caption_enabled, caption_style = bool(body.caption_enabled), body.caption_style or "viral"
    if not caption_enabled:
        caption_style = "viral"            # captions off: the style is never read
    elif captions_disabled(caption_style):
        caption_enabled, caption_style = False, "viral"
    elif not await style_id_known(caption_style):
        raise StudioDocError(f"Unknown caption style {caption_style!r} — pick one from /api/captions/styles.")

    settings_overrides = {
        "voice": {"provider": body.tts_provider, "voice": body.tts_voice},
        "captions": {"enabled": caption_enabled, "style": caption_style},
        "music": {"enabled": body.music_enabled, "genre": body.music_genre},
    }
    transition = LEGACY_TRANSITIONS.get(body.transition_style or "", body.transition_style)
    if transition in sd.TRANSITIONS:
        settings_overrides["transition"] = transition
    row = await store.create_project(
        script=body.script or "",
        aspect_ratio=body.aspect_ratio if body.aspect_ratio in sd.ASPECTS else "9:16",
        visual_style=body.visual_style or "cinematic",
        input_meta={"mode": "script", "source_id": body.source_id},
        settings_overrides=settings_overrides, user_id=user_id,
    )
    return row.id


async def prepare_legacy(project_id: str, request: dict, *, user_id: str = "local") -> None:
    """Plan, then put the caller's own stills on the opening scenes, in order
    (pinned, so nothing re-plans them) — the steps that used to run inside the
    one-shot pipeline. `request` is the request body as a dict."""
    from backend.agents.generator_video import resolve_still_input
    from backend.core.tasks.studio import plan_into_project
    from backend.core.ws_manager import ws_manager
    from backend.services import studio_media
    from backend.services import studio_store as store

    await plan_into_project(project_id, user_id)

    records = []
    missing = 0
    for ref in request.get("user_images") or []:
        path = resolve_still_input(ref)
        if path is None:
            missing += 1
            continue
        try:
            # add_image writes a normalised copy into the project — the
            # caller's file is never moved or consumed.
            records.append(await studio_media.add_image(project_id, path, title=path.name, source="upload"))
        except Exception as e:  # noqa: BLE001 — one unreadable image is one image fewer
            logger.warning("legacy adapter: could not use image %s (%s)", path.name, e)
            missing += 1
    if missing:
        await ws_manager.send_constraint_warning(
            "user_images_skipped",
            f"{missing} of your image{'s' if missing != 1 else ''} couldn't be read — stock footage was used instead.",
            user_id=user_id)
    if not records:
        return

    def add(assets):
        for r in records:
            assets["imports"][r["asset_id"]] = r
        return assets

    row = await store.update_assets(project_id, add, user_id=user_id)
    scenes = [s for s in json.loads(row.doc_json)["scenes"] if s["line"]]
    if len(records) > len(scenes):
        extra = len(records) - len(scenes)
        await ws_manager.send_constraint_warning(
            "user_images_skipped",
            f"The script has {len(scenes)} scenes, so {extra} of your images weren't used — they're in the "
            "project's Media tab.", user_id=user_id)
    await store.write_ops(project_id, [
        {"op": "bind_visual", "uid": scene["uid"], "visual": {"kind": "user_clip", "asset_id": record["asset_id"]}}
        for scene, record in zip(scenes, records)
    ], if_revision=None, internal=True, user_id=user_id)
