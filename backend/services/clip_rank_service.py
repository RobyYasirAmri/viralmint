# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""AI relevance re-rank for stock-footage candidates.

The heuristic quality_score in the searcher optimises pixels (resolution,
orientation fit, duration) — it never sees MEANING. This is the semantic step:
one batched chat call per plan ranks each scene's top candidates by how well
the footage described matches what the narrator says during that scene, with
cross-scene continuity preference (a per-scene greedy pick structurally can't
do continuity).

Contract: pure-ish function over plain dicts. Degrade, never crash — any
failure (no AI client, timeout, malformed JSON, bogus ids) returns the
heuristic order. A broken re-rank must never break a plan.
"""
import json
import logging
import re
from backend.core.prompt_rules import extract_json_text

logger = logging.getLogger(__name__)

# How many heuristic-ranked candidates per scene the LLM sees (the searcher's
# cap), and how many ranked picks come back.
from backend.services.stock_video_service import MAX_CANDIDATES_PER_SCENE  # noqa: E402
TOP_N = 3


def _candidate_line(j: int, c: dict) -> str:
    """One compact prompt line per candidate, e.g.
    ``[c2] pexels · city rain umbrella night · 21s · 1920x1080``"""
    desc = " ".join((c.get("desc_words") or [])[:10]) or "(no description)"
    parts = [
        f"[c{j}]",
        str(c.get("source") or "stock"),
        "·", desc,
        "·", f"{int(c.get('duration') or 0)}s",
        "·", f"{c.get('width') or 0}x{c.get('height') or 0}",
    ]
    if c.get("popularity"):
        parts += ["·", f"pop {c['popularity']}"]
    return " ".join(parts)


def _build_prompt(items: list[dict]) -> str:
    blocks = []
    for it in items:
        mood = it.get("mood") or "neutral"
        lines = "\n".join(
            "  " + _candidate_line(j, c) for j, c in enumerate(it["candidates"])
        )
        blocks.append(
            f'Scene {it["scene_idx"]} (mood: {mood}): "{it["text"]}"\n{lines}'
        )
    scenes_block = "\n\n".join(blocks)
    return f"""You are a video editor picking stock footage for a narrated video.
For EACH scene below, rank the best {TOP_N} candidate clips by how well the
FOOTAGE (described by its keywords) matches what the narrator says during
that scene. The audience hears the scene text while seeing the clip — a
mismatched clip is a visible bug.

Rules:
1. Semantic match to the scene text is the #1 criterion. Resolution/duration
   only break ties.
2. CONTINUITY: when adjacent scenes cover the same subject or setting, prefer
   candidates that keep the same subject/palette across them so the video
   reads as one piece, not a slideshow.
3. Drop candidates whose description clashes with the scene's mood.
4. Only use the candidate ids shown. Rank best-first, at most {TOP_N} per scene.

Scenes and candidates:
{scenes_block}

Return JSON only (no markdown), one entry per scene:
[{{"scene": 0, "ranked": ["c2", "c0", "c1"]}}]"""


def _parse_response(text: str, items: list[dict]) -> dict[int, list[int]] | None:
    """→ {scene_idx: [candidate indices]} with every id validated, or None
    when the payload is structurally unusable (caller then falls back)."""
    clean = (text or "").strip()
    clean = extract_json_text(clean)  # fence anywhere / leading prose (prompt_rules)
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1].rsplit("```", 1)[0] if "\n" in clean else clean[3:]
    try:
        data = json.loads(clean.strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None

    by_idx = {it["scene_idx"]: it for it in items}
    out: dict[int, list[int]] = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        try:
            scene_idx = int(entry.get("scene"))
        except (TypeError, ValueError):
            continue
        it = by_idx.get(scene_idx)
        if it is None:
            continue
        n = len(it["candidates"])
        ranked: list[int] = []
        for cid in entry.get("ranked") or []:
            m = re.fullmatch(r"c(\d+)", str(cid).strip())
            if not m:
                continue
            j = int(m.group(1))
            if 0 <= j < n and j not in ranked:
                ranked.append(j)
            if len(ranked) >= TOP_N:
                break
        if ranked:
            out[scene_idx] = ranked
    return out or None


def _fill_to_top_n(ranked: list[int], n_candidates: int) -> list[int]:
    """Pad a (possibly short) ranked list with heuristic-order indices so the
    download step always has up to TOP_N fallbacks."""
    for j in range(n_candidates):
        if len(ranked) >= TOP_N:
            break
        if j not in ranked:
            ranked.append(j)
    return ranked[:TOP_N]


async def rank_scene_candidates(
    items: list[dict],
    ai_client,
) -> dict[int, list[dict]]:
    """Re-rank each scene's stock candidates semantically.

    Args:
        items: [{"scene_idx": int, "text": str, "mood": str,
                 "candidates": [candidate dicts, heuristic-sorted]}].
               Candidate lists longer than MAX_CANDIDATES_PER_SCENE are
               truncated here.
        ai_client: the user's AI client, or None (→ heuristic order).

    Returns:
        {scene_idx: [candidate dicts, best-first, ≤ TOP_N]} for EVERY input
        scene — scenes the LLM skipped/botched keep heuristic order, so the
        caller never needs a second fallback path.
    """
    items = [
        {**it, "candidates": (it.get("candidates") or [])[:MAX_CANDIDATES_PER_SCENE]}
        for it in items
        if it.get("candidates")
    ]
    heuristic = {
        it["scene_idx"]: it["candidates"][:TOP_N] for it in items
    }
    if not items:
        return {}

    # Nothing to rank: every scene has at most one candidate.
    if ai_client is None or all(len(it["candidates"]) <= 1 for it in items):
        return heuristic

    prompt = _build_prompt(items)
    try:
        resp = await ai_client.chat(
            messages=[{"role": "user", "content": prompt}],
            # Output is just ids — ~15 tokens/scene + slack.
            max_tokens=min(1500, 200 + 30 * len(items)),
        )
        parsed = _parse_response(resp, items)
        if parsed is None:
            from backend.core.ai_retry import ai_fix_json
            repaired = await ai_fix_json(resp, "expected JSON array of scene rankings")
            parsed = _parse_response(json.dumps(repaired), items) if repaired else None
    except Exception as e:
        logger.warning("Clip re-rank failed — keeping heuristic order: %s", e)
        return heuristic

    if not parsed:
        logger.warning("Clip re-rank returned nothing usable — keeping heuristic order")
        return heuristic

    out: dict[int, list[dict]] = {}
    reranked_count = 0
    for it in items:
        idx = it["scene_idx"]
        cands = it["candidates"]
        ranked = parsed.get(idx)
        if ranked:
            ranked = _fill_to_top_n(list(ranked), len(cands))
            out[idx] = [cands[j] for j in ranked]
            if ranked[0] != 0:
                reranked_count += 1
        else:
            out[idx] = heuristic[idx]
    logger.info(
        "Clip re-rank: %d/%d scenes ranked by LLM (%d differ from heuristic #1)",
        sum(1 for it in items if it["scene_idx"] in parsed), len(items), reranked_count,
    )
    return out
