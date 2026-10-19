# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Stock footage for the Smart Video Studio — search, plan, normalise.

  * `search_videos` / `search_stock_candidates` / `search_all_scenes` — Pexels
    candidates with a quality score, a small preview file and an HD download
    file, cached 24 h (stock_search_cache).
  * `extract_visual_scenes` — one AI call that turns timed script chunks into
    one stock search per chunk, IN ORDER (scene N depicts chunk N).
  * `trim_and_normalize_clip` — one ffmpeg pass: cover-crop to the canvas,
    colour grade (the project's look), subtle Ken Burns motion, 30 fps, no
    audio — every scene clip comes out byte-compatible for a `-c copy` concat.

The legacy one-shot pipeline (`pexels_service.build_stock_video`) keeps its own
helpers; this module is what the Studio plans and renders with.
"""
import asyncio
import json
import logging
import random
import re
import subprocess

import httpx

from backend.core.exceptions import VideoGenerationError
from backend.core.prompt_rules import extract_json_text
from backend.services import stock_search_cache
from backend.services.ffmpeg_service import ffmpeg_error
from backend.services.video_utils import cover_vf, orientation_fit_adjustment

logger = logging.getLogger(__name__)

# ── Pexels API ─────────────────────────────────────────────────────────────────

PEXELS_API = "https://api.pexels.com"

# Shared httpx client — connection pooling across all Pexels calls
_http = httpx.AsyncClient(timeout=30, follow_redirects=True, limits=httpx.Limits(max_connections=10))

# Minimum acceptable resolution for stock clips (checked on the SHORT side)
MIN_WIDTH_PORTRAIT = 720
MIN_HEIGHT_PORTRAIT = 1280
MIN_WIDTH_LANDSCAPE = 1280
MIN_HEIGHT_LANDSCAPE = 720

# How many heuristic-ranked candidates per scene the planner keeps (and the
# AI re-rank sees).
MAX_CANDIDATES_PER_SCENE = 8


def _slug_words(pexels_url: str) -> list[str]:
    """Human words from a Pexels video page URL — the only textual description
    Pexels exposes (no tags field). E.g.
    ``…/video/a-man-walking-on-a-rainy-street-855564/`` → ["a", "man", …]."""
    if not pexels_url:
        return []
    slug = pexels_url.rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"-?\d+$", "", slug)  # strip the trailing numeric id
    return [w for w in slug.split("-") if w]


async def search_videos(
    query: str,
    orientation: str = "portrait",
    per_page: int = 10,
    api_key: str = "",
) -> list[dict]:
    """Search Pexels for stock footage matching a keyword, best-first.

    Orientation is NOT passed to the Pexels API — any orientation can be
    cover-cropped to the target, which doubles the candidate pool; the score
    prefers orientation-native files instead. `size=small` IS passed: it is
    Pexels' "at least HD" floor, so sub-HD files never leave the API.

    Each result carries `download_url` (the best HD file, for the render) and
    `preview_url` (the smallest file whose short side is ≥ 360, for the
    Studio's player). Responses are cached 24 h.
    """
    if not api_key:
        raise VideoGenerationError("Pexels API key not configured")

    cache_params = {"orientation": orientation, "per_page": per_page, "size": "small"}

    async def _fetch() -> list[dict]:
        resp = await _http.get(
            f"{PEXELS_API}/videos/search",
            params={"query": query, "per_page": per_page, "size": "small"},
            headers={"Authorization": api_key},
        )
        resp.raise_for_status()
        data = resp.json()

        min_w = MIN_WIDTH_PORTRAIT if orientation == "portrait" else MIN_WIDTH_LANDSCAPE
        min_h = MIN_HEIGHT_PORTRAIT if orientation == "portrait" else MIN_HEIGHT_LANDSCAPE

        videos = []
        for v in data.get("videos", []):
            best_file = None
            best_score = 0
            preview_file = None

            for f in v.get("video_files", []):
                w = f.get("width") or 0
                h = f.get("height") or 0
                quality = f.get("quality", "")
                if f.get("link") and min(w, h) >= 360 and (
                        preview_file is None
                        or w * h < (preview_file.get("width") or 0) * (preview_file.get("height") or 0)):
                    preview_file = f

                if min(w, h) < min(min_w, min_h):
                    continue

                # Prefer HD at a reasonable size, and orientation-native files:
                # a landscape clip CAN cover-crop to portrait, but it keeps
                # only ~31% of its width and upscales ~1.8× (soft).
                score = 0
                if quality == "hd":
                    score += 100
                if w <= 1920 and h <= 1920:
                    score += 50
                score += min(w, 1920) / 100
                score += orientation_fit_adjustment(w, h, orientation)

                if score > best_score and f.get("link"):
                    best_score = score
                    best_file = f

            if best_file:
                duration = v.get("duration") or 0
                videos.append({
                    "id": v["id"],
                    "url": v.get("url", ""),
                    "download_url": best_file["link"],
                    "preview_url": (preview_file or best_file)["link"],
                    "width": best_file.get("width") or 0,
                    "height": best_file.get("height") or 0,
                    "duration": duration,
                    "quality_score": best_score + min(duration / 5, 10),
                    "source": "pexels",
                    # Pexels has no tags — the page-URL slug is its only
                    # description; the AI re-rank reads it.
                    "desc_words": _slug_words(v.get("url", "")),
                    "thumbnail": v.get("image", ""),
                    "creator": (v.get("user") or {}).get("name", ""),
                })

        videos.sort(key=lambda x: x["quality_score"], reverse=True)
        return videos

    # Cache-through + single-flight: concurrent identical searches share one
    # HTTP call; results cached 24 h.
    return await stock_search_cache.cached_search("pexels", query, _fetch, **cache_params)


async def search_stock_candidates(
    query: str,
    orientation: str = "landscape",
    pexels_api_key: str = "",
    per_page: int = 10,
) -> list[dict]:
    """Candidates for ONE query, best-first. A search failure degrades to an
    empty list (logged), never an exception."""
    if not pexels_api_key:
        return []
    try:
        return await search_videos(query, orientation=orientation, per_page=per_page,
                                   api_key=pexels_api_key)
    except Exception as e:  # noqa: BLE001 — a failed search is "no candidates"
        logger.warning("Stock candidate search failed for %r: %s", query, e)
        return []


async def search_all_scenes(
    scenes: list[dict],
    orientation: str,
    voice_duration: float,
    pexels_api_key: str,
) -> list[tuple[int, list[dict]]]:
    """Search Pexels for all scenes in parallel.

    Returns ``[(scene_idx, candidates)]`` — each scene's candidate POOL,
    heuristic-sorted best-first and truncated to MAX_CANDIDATES_PER_SCENE.
    Per scene it tries `query`, then `alt1`, then `alt2`, stopping early once
    three candidates are at least as long as the scene needs.
    """
    target_per_clip = voice_duration / len(scenes) if scenes else 10

    async def _search_scene(i: int, scene: dict) -> tuple[int, list[dict]]:
        queries = [q for q in (scene.get("query"), scene.get("alt1"), scene.get("alt2")) if q]
        if not queries or not pexels_api_key:
            return i, []
        try:
            all_candidates: list[dict] = []
            seen: set = set()
            for query in queries:
                try:
                    results = await search_videos(query, orientation=orientation, per_page=15,
                                                  api_key=pexels_api_key)
                except Exception as e:  # noqa: BLE001 — try the next query
                    logger.warning("Stock search failed for query %r: %s", query, e)
                    continue
                for r in results:
                    if r["id"] not in seen:
                        seen.add(r["id"])
                        all_candidates.append(r)
                if sum(1 for r in all_candidates if (r.get("duration") or 0) >= target_per_clip) >= 3:
                    break
            for c in all_candidates:
                if (c.get("duration") or 0) >= target_per_clip:
                    c["quality_score"] = c.get("quality_score", 0) + 20
            all_candidates.sort(key=lambda x: x.get("quality_score", 0), reverse=True)
            return i, all_candidates[:MAX_CANDIDATES_PER_SCENE]
        except Exception as e:  # noqa: BLE001 — one scene never sinks the plan
            logger.warning("Search failed for scene %d %r: %s", i, queries[0], e)
            return i, []

    results = await asyncio.gather(*(_search_scene(i, s) for i, s in enumerate(scenes)))
    return sorted(results, key=lambda x: x[0])


# ── Ken Burns presets ──────────────────────────────────────────────────────────
#
# Subtle zoom/pan on stock clips. Uses scale+crop (NOT zoompan): zoompan is
# for images — it creates d output frames PER INPUT FRAME, impossibly slow on
# video. The clip is scaled to ~110% of the canvas and the crop window moves.
# Each preset: (crop_x_expr, crop_y_expr) with {w}/{h}/{dur} placeholders.

_KENBURNS_PRESETS = [
    ("(in_w-{w})/2", "(in_h-{h})/2"),                    # slow zoom in (static center)
    ("(in_w-{w})*t/{dur}", "(in_h-{h})/2"),              # pan left → right
    ("(in_w-{w})*(1-t/{dur})", "(in_h-{h})/2"),          # pan right → left
    ("(in_w-{w})/2", "(in_h-{h})*t/{dur}"),              # pan top → bottom
    ("(in_w-{w})*t/{dur}", "(in_h-{h})*t/{dur}"),        # diagonal drift
]


# Colour-grade looks layered on top of the base grade. Values are ffmpeg
# filter fragments — empty string = the base ("neutral") look.
LUT_PRESETS: dict[str, str] = {
    "neutral": "",
    "teal_orange": (
        "colorbalance=rs=-0.05:gs=-0.02:bs=+0.10:rm=0:gm=0:bm=0:"
        "rh=+0.10:gh=+0.04:bh=-0.08,"
        "eq=saturation=1.10:contrast=1.05"
    ),
    "moody": (
        "curves=preset=darker,"
        "eq=saturation=0.70:contrast=1.15:brightness=-0.03,"
        "colorbalance=rs=-0.05:bs=+0.05"
    ),
    "warm_film": (
        # Warm = red lifted / blue pulled in the mids. (ffmpeg has no
        # `curves=preset=warmer` — a grade naming it fails every clip.)
        "curves=r='0/0 0.5/0.56 1/1':b='0/0 0.5/0.45 1/1',"
        "eq=saturation=1.05:contrast=1.02,"
        "colorbalance=rs=+0.08:gs=+0.02:bs=-0.04"
    ),
    "bw_film": (
        "hue=s=0,"
        "eq=contrast=1.18:brightness=0.02"
    ),
    "neon": (
        "eq=saturation=1.40:contrast=1.10,"
        "colorbalance=rs=-0.05:bs=+0.12:rm=+0.05:bm=+0.06"
    ),
    "vintage": (
        "curves=preset=vintage,"
        "eq=saturation=0.85:contrast=1.03:brightness=0.01"
    ),
}


def _color_grade_filters(lut_preset: str = "neutral") -> list[str]:
    """ffmpeg filters for the base grade (white balance, contrast, slight
    desaturation, soft vignette — unifies mismatched stock clips) plus the
    look's LUT on top."""
    filters = [
        "normalize=blackpt=black:whitept=white:smoothing=20",
        "eq=contrast=1.08:brightness=0.02:saturation=0.85",
        "vignette=PI/5",
    ]
    lut = LUT_PRESETS.get(lut_preset)
    if lut is None:
        logger.warning("Unknown LUT preset %r — falling back to neutral", lut_preset)
        lut = ""
    if lut:
        filters.append(lut)
    return filters


def _kenburns_crop(target_w: int, target_h: int, duration: float) -> tuple[int, int, str]:
    """(oversized w, oversized h, crop filter) for one random Ken Burns move."""
    preset = random.choice(_KENBURNS_PRESETS)
    crop_x = preset[0].format(w=target_w, h=target_h, dur=duration)
    crop_y = preset[1].format(w=target_w, h=target_h, dur=duration)
    # 12% for the static centre zoom, 10% for the panning presets
    sf = 1.12 if "t/" not in preset[0] and "t/" not in preset[1] else 1.10
    return int(target_w * sf), int(target_h * sf), f"crop={target_w}:{target_h}:{crop_x}:{crop_y}"


def _encode_args(clip_path, duration: float, vf: str, output_path) -> list[str]:
    return [
        "ffmpeg", "-y", "-i", str(clip_path), "-t", str(duration), "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-r", "30", "-an", str(output_path),
    ]


async def trim_and_normalize_clip(
    clip_path,
    duration: float,
    target_w: int,
    target_h: int,
    output_path=None,
    color_grade: bool = True,
    ken_burns: bool = True,
    lut_preset: str = "neutral",
):
    """Trim a clip to `duration`, cover-crop it to the canvas, grade it and add
    subtle Ken Burns motion — all in one ffmpeg pass. A failed graded pass
    retries without the heavy grade, then bare-normalises; a clip that can't
    be normalised at all raises VideoGenerationError (never a raw, mismatched
    clip that would corrupt the concat)."""
    if output_path is None:
        output_path = clip_path.parent / f"{clip_path.stem}_trimmed.mp4"

    def _trim():
        use_kb = ken_burns and duration >= 1.0
        if use_kb:
            kb_w, kb_h, crop = _kenburns_crop(target_w, target_h, duration)
            vf_parts = [cover_vf(kb_w, kb_h)]
            if color_grade:
                vf_parts.extend(_color_grade_filters(lut_preset))
            vf_parts.append(crop)
        else:
            vf_parts = [cover_vf(target_w, target_h)]
            if color_grade:
                vf_parts.extend(_color_grade_filters(lut_preset))
        try:
            # 180 s: the full grade chain on a 10 s clip can take >60 s on a
            # loaded laptop.
            result = subprocess.run(_encode_args(clip_path, duration, ",".join(vf_parts), output_path),
                                    capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            logger.warning("Clip trim timed out after 180s (clip=%s, dur=%.1fs)", clip_path.name, duration)
            if color_grade:
                return _trim_fallback(clip_path, duration, target_w, target_h, output_path, ken_burns=use_kb)
            return _bare_normalize(clip_path, duration, target_w, target_h, output_path)
        if result.returncode != 0:
            if color_grade:
                logger.warning("Color grading failed for %s (dur=%.1fs, lut=%s) — retrying without it: %s",
                               clip_path.name, duration, lut_preset, ffmpeg_error(result.stderr))
                return _trim_fallback(clip_path, duration, target_w, target_h, output_path, ken_burns=use_kb)
            logger.warning("Clip trim failed for %s — bare-normalizing: %s",
                           clip_path.name, ffmpeg_error(result.stderr))
            return _bare_normalize(clip_path, duration, target_w, target_h, output_path)
        return output_path

    return await asyncio.to_thread(_trim)


def _trim_fallback(clip_path, duration, target_w, target_h, output_path, ken_burns: bool = False):
    """The graded pass failed: a lighter grade (eq only), Ken Burns kept."""
    if ken_burns and duration >= 1.0:
        kb_w, kb_h, crop = _kenburns_crop(target_w, target_h, duration)
        vf = f"{cover_vf(kb_w, kb_h)},eq=contrast=1.08:brightness=0.02:saturation=0.85,{crop}"
    else:
        vf = f"{cover_vf(target_w, target_h)},eq=contrast=1.08:brightness=0.02:saturation=0.85"
    try:
        result = subprocess.run(_encode_args(clip_path, duration, vf, output_path),
                                capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return _bare_normalize(clip_path, duration, target_w, target_h, output_path)
    if result.returncode != 0:
        logger.warning("Clip trim fallback failed: %s — bare-normalizing", ffmpeg_error(result.stderr))
        return _bare_normalize(clip_path, duration, target_w, target_h, output_path)
    return output_path


def _bare_normalize(clip_path, duration, target_w, target_h, output_path):
    """Last resort: scale+crop to the canvas, 30 fps, no audio, no grade —
    the simplest chain that is still concat-compatible. Raises
    VideoGenerationError so the caller handles a missing scene instead of a
    raw source clip poisoning the whole concat."""
    try:
        result = subprocess.run(_encode_args(clip_path, duration, cover_vf(target_w, target_h), output_path),
                                capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired as e:
        raise VideoGenerationError(f"Bare clip normalize timed out: {clip_path.name}") from e
    if result.returncode != 0 or not output_path.exists() or output_path.stat().st_size == 0:
        raise VideoGenerationError(f"Bare clip normalize failed: {ffmpeg_error(result.stderr, 200)}")
    return output_path


# ── Looks + scene planning ─────────────────────────────────────────────────────

# Visual style → colour grade. Keep in step with studio_doc.VISUAL_STYLES and
# SmartVideoStyles.jsx. Unknown values fall back to "cinematic".
VISUAL_STYLE_PRESETS: dict[str, dict] = {
    "documentary": {"lut": "neutral", "label": "Documentary — real footage, neutral grade"},
    "cinematic": {"lut": "teal_orange", "label": "Cinematic — teal-and-orange grade"},
    "vlog": {"lut": "warm_film", "label": "Vlog — warm-film grade"},
    "card": {"lut": "moody", "label": "Card — moody grade"},
    "educational": {"lut": "neutral", "label": "Educational — clean, neutral grade"},
    "noir": {"lut": "bw_film", "label": "Noir — black & white, high contrast"},
    "neon": {"lut": "neon", "label": "Neon — vivid cyberpunk grade"},
    "vintage": {"lut": "vintage", "label": "Vintage — faded retro film"},
}
DEFAULT_VISUAL_STYLE = "cinematic"


def resolve_visual_style(style: str | None) -> dict:
    """A visual style preset, falling back to the default — never None."""
    return VISUAL_STYLE_PRESETS.get(
        (style or DEFAULT_VISUAL_STYLE).lower(),
        VISUAL_STYLE_PRESETS[DEFAULT_VISUAL_STYLE],
    )


def align_to_chunks(scenes: list, n_chunks: int) -> list:
    """Re-seat the model's entries on the chunk each one says it depicts.

    Position alone is not alignment: a model that gives a two-sentence chunk
    two entries shifts every later visual one line early, and trimming the
    surplus then hides it (scene 16 showing scene 14's subject). Entries
    carrying a valid `chunk` number are placed by it (the first claim on a
    chunk wins); a chunk nobody claimed is left for the caller's pad (a short
    list) or filled with the first unclaimed unnumbered entry. Without numbers
    the order is kept.
    """
    if not scenes or not all(isinstance(e, dict) for e in scenes):
        return scenes
    numbered = {}
    loose = []
    for e in scenes:
        n = e.get("chunk")
        if isinstance(n, bool) or not isinstance(n, (int, float, str)):
            loose.append(e)
            continue
        try:
            k = int(n)
        except (TypeError, ValueError):
            loose.append(e)
            continue
        if 1 <= k <= n_chunks and k not in numbered:
            numbered[k] = e
    if not numbered:
        return scenes
    if len(numbered) < n_chunks or len(scenes) != n_chunks:
        logger.warning("extract_visual_scenes: %d entries for %d chunks; re-seated %d by chunk number",
                       len(scenes), n_chunks, len(numbered))
    out: list = []
    for k in range(1, n_chunks + 1):
        if k in numbered:
            out.append(numbered[k])
        elif loose:
            out.append(loose.pop(0))
        else:
            break
    # A gap mid-list must not shift later chunks: pad it in place.
    if len(out) < n_chunks and any(k in numbered for k in range(len(out) + 2, n_chunks + 1)):
        out = [numbered.get(k) for k in range(1, n_chunks + 1)]
    return out


def _chunk_query(text: str) -> str:
    """A stock query from a chunk's own words: its first substantive ENGLISH
    words (a CJK line is not a Pexels query — Pexels searches English)."""
    words = (w.strip(".,!?;:'\"()") for w in (text or "").split()[:8])
    return " ".join(w for w in words if len(w) > 2 and w.isascii() and w.isalpha())[:80] or "abstract concept"


def _chunk_scene(text: str) -> dict:
    q = _chunk_query(text)
    return {"query": q, "alt1": q, "alt2": q, "mood": "neutral"}


async def extract_visual_scenes(script_chunks: list[dict], ai_client) -> list[dict]:
    """One stock-footage plan per timed chunk, IN ORDER.

    `script_chunks` is `[{text, start, end}]` — the scene lines with their
    timing. One AI call returns `{chunk, query, alt1, alt2, mood}` per chunk;
    entries are re-seated by their chunk number and any gap is filled from
    the chunk's own words, so the result always has exactly one entry per
    chunk. With no AI client (or a failed call) every entry comes from the
    chunk's words.
    """
    n_chunks = len(script_chunks)
    if not n_chunks:
        return []
    if ai_client is None:
        return [_chunk_scene(c.get("text") or "") for c in script_chunks]

    chunk_block = "\n".join(
        f'  Chunk {i + 1} ({c["start"]:.1f}s–{c["end"]:.1f}s): "{c["text"]}"'
        for i, c in enumerate(script_chunks)
    )
    prompt = f"""You are a professional video editor choosing stock footage for a narrated video.

The script has been split into {n_chunks} timed chunks (one per visual scene).
You MUST produce exactly {n_chunks} scenes, one per chunk, IN ORDER. Scene N's
footage MUST depict what is being said in Chunk N — not what is said earlier
or later. The audience hears chunk N while seeing scene N, so any mismatch
is a visible bug.

The footage comes from Pexels — real filmed clips of generic subjects: cities,
nature, business, technology, people, vehicles, etc. For abstract ideas, pick a
concrete visual metaphor stock sites actually have.

Timed chunks (read each one carefully — scene N depicts chunk N):
{chunk_block}

RULES:
1. Output exactly {n_chunks} scenes, in chunk order, ONE per chunk — never one per sentence (a chunk with two sentences still gets ONE scene). Every entry carries "chunk": its chunk number from the listing above (1 to {n_chunks}).
2. Scene content must depict THAT chunk's text. Do not borrow subjects from other chunks.
3. For EACH scene give 3 search queries: "query" (specific), "alt1" (broader), "alt2" (fallback).
4. NEVER put a real person's name or a brand name in a query. Describe the ROLE or object instead: "Trump" → "politician speaking podium"; "Apple iPhone" → "smartphone close up".
5. Be SPECIFIC and CONCRETE: "military tank desert" is much better than "dramatic scene".
6. Vary camera angles across scenes: close-up, wide shot, aerial, tracking shot, slow pan.
7. Prefer visual CONTINUITY: when consecutive chunks discuss the same subject or place, keep the same subject / setting across them. Switch only when the script's topic shifts.
8. Include a short "mood" per scene (e.g. "bright", "dark", "moody", "warm", "calm", "energetic").

Write every "query", "alt1" and "alt2" in ENGLISH, whatever language the script is in — stock sites are searched in English.

Return a JSON array only (no markdown), exactly {n_chunks} entries in chunk order:
[
  {{"chunk": 1, "query": "specific search terms", "alt1": "broader query", "alt2": "fallback query", "mood": "bright"}}
]"""
    try:
        resp = await ai_client.chat(
            messages=[{"role": "user", "content": prompt}],
            # ~100 tokens/scene plus headroom; a flat budget truncated the
            # JSON at 13+ scenes.
            max_tokens=min(4000, max(1500, 300 + 120 * n_chunks)),
        )
        clean = extract_json_text(resp)
        try:
            scenes = json.loads(clean)
        except json.JSONDecodeError as je:
            from backend.core.ai_retry import ai_fix_json
            scenes = await ai_fix_json(clean, str(je))
    except Exception as e:  # noqa: BLE001 — planning degrades to keyword queries
        logger.warning("Visual scene extraction failed: %s", e)
        scenes = None

    if not isinstance(scenes, list) or not scenes:
        return [_chunk_scene(c.get("text") or "") for c in script_chunks]
    scenes = align_to_chunks(scenes, n_chunks)[:n_chunks]
    scenes = list(scenes) + [None] * (n_chunks - len(scenes))
    out: list[dict] = []
    for i, entry in enumerate(scenes):
        if isinstance(entry, dict) and str(entry.get("query") or "").strip():
            out.append(entry)
        else:
            logger.warning("extract_visual_scenes: no usable entry for chunk %d of %d — "
                           "using the chunk's own words", i + 1, n_chunks)
            out.append(_chunk_scene(script_chunks[i].get("text") or ""))
    return out
