# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Per-scene AI help in the Smart Video Studio editor.

"Make this punchier", hook alternatives, "say it shorter": this module answers
one scene at a time with up to three rewrites of its line (and, for a custom
instruction about the picture, a stock search query). It never edits the
project — the editor applies the pick with the ordinary `set_line` op, so
undo and re-voicing work as for a hand edit.

One AI call with the user's own key.
"""
from __future__ import annotations

import json
import logging

from backend.core.prompt_rules import extract_json_text
from backend.services import studio_doc as sd

logger = logging.getLogger(__name__)

MAX_OPTIONS = 3

ACTIONS = {
    "punchier": "Make it punchier: stronger verbs, a sharper claim, more tension. Keep the meaning.",
    "shorter": "Say the same thing in noticeably fewer words (about half). Keep the key fact.",
    "clearer": "Make it clearer and easier to follow when heard once. Plain words, one idea.",
    "hook": ("This is the video's OPENING line. Write three different scroll-stopping hooks, each under 12 "
             "words and spoken in under 2 seconds: one bold claim, one sharp question, one with a number "
             "or a mistake the viewer is making. No greetings, no 'in this video'."),
    "custom": "Follow the creator's instruction below.",
}


class AssistError(Exception):
    """The AI didn't give a usable answer — said to the user as a sentence."""


def _prompt(doc: dict, uid: str, action: str, instruction: str | None) -> str:
    scenes = doc["scenes"]
    idx = next(i for i, s in enumerate(scenes) if s["uid"] == uid)
    script = "\n".join(f"{'>> ' if i == idx else '   '}{i + 1}. {s['line']}" for i, s in enumerate(scenes))
    ask = ACTIONS[action]
    if action == "custom":
        ask += f'\nCreator\'s instruction: "{(instruction or "").strip()[:300]}"'
    return f"""You are editing ONE scene of a short narrated video. The full script, one scene per line
(the scene to change is marked >>):

{script}

Scene {idx + 1} now says: "{scenes[idx]['line']}"

{ask}

Rules:
- Write {MAX_OPTIONS} alternative versions of scene {idx + 1}'s line ONLY. It must still flow from the
  scene before it into the scene after it.
- Spoken narration: plain sentences, no emojis, no hashtags, no stage directions, under {sd.LINE_MAX} characters.
- Write in the same language as the script.
- If (and only if) the instruction is about what the PICTURE should show, also give "query": 3-6 English
  words to search stock footage for it; otherwise "query": null.

Reply with JSON only: {{"lines": ["...", "...", "..."], "query": null}}"""


def _clean(answer: str, current: str) -> dict:
    try:
        data = json.loads(extract_json_text(answer or ""))
    except (ValueError, TypeError):
        raise AssistError("The AI's answer couldn't be read — try again.") from None
    if not isinstance(data, dict):
        raise AssistError("The AI's answer couldn't be read — try again.")
    lines: list[str] = []
    for raw in data.get("lines") or []:
        line = sd.normalise_line(raw)[: sd.LINE_MAX] if isinstance(raw, str) else ""
        if line and line != current and line not in lines:
            lines.append(line)
    query = data.get("query")
    query = sd.normalise_line(query)[:100] if isinstance(query, str) and query.strip() else None
    if not lines and not query:
        raise AssistError("The AI didn't suggest anything new — try a different ask.")
    return {"lines": lines[:MAX_OPTIONS], "query": query}


async def suggest(doc: dict, uid: str, action: str, instruction: str | None = None, ai_client=None) -> dict:
    if action not in ACTIONS:
        raise AssistError("Unknown request.")
    current = next(s["line"] for s in doc["scenes"] if s["uid"] == uid)
    if ai_client is None:
        from backend.core.ai_provider import get_ai_client
        from backend.services.render_post import load_user_settings
        try:
            ai_client = get_ai_client(await load_user_settings())
        except Exception as e:  # noqa: BLE001
            raise AssistError("Add an AI key in Settings to use AI suggestions.") from e
    try:
        answer = await ai_client.chat(messages=[{"role": "user", "content": _prompt(doc, uid, action, instruction)}],
                                      max_tokens=900)
    except Exception as e:  # noqa: BLE001 — a sentence, never the exception
        logger.warning("studio assist failed: %s", e)
        raise AssistError("The AI didn't answer — try again in a moment.") from e
    return _clean(answer, current)
