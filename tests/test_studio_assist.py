# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Per-scene AI help: suggestions only (the editor applies a pick with
set_line), plus a scene-scoped re-plan. The AI client is faked."""
from __future__ import annotations

import asyncio
import json

import pytest

from backend.services import studio_assist
from backend.services import studio_doc as sd


def _doc(lines):
    return {"settings": sd.default_settings(), "scenes": [sd.make_scene(l) for l in lines]}


class AI:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    async def chat(self, messages, **kw):
        self.calls.append((messages[0]["content"], kw))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def run(doc, uid, action, reply, instruction=None):
    ai = AI(reply)
    return asyncio.run(studio_assist.suggest(doc, uid, action, instruction, ai_client=ai)), ai


def test_rewrites_one_scene():
    doc = _doc(["Plants sleep in winter.", "So water them less often than you think."])
    uid = doc["scenes"][1]["uid"]
    reply = 'Sure:\n```json\n{"lines": ["Water less.", "So water them less often than you think.", "Water less.", "Half the water."], "query": null}\n```'
    out, ai = run(doc, uid, "shorter", reply)
    assert out == {"lines": ["Water less.", "Half the water."], "query": None}   # unchanged + duplicate dropped
    prompt, _kw = ai.calls[0]
    assert ">>    " not in prompt and ">> 2. So water" in prompt


def test_a_picture_instruction_brings_a_query():
    doc = _doc(["Plants sleep in winter."])
    out, ai = run(doc, doc["scenes"][0]["uid"], "custom", json.dumps({"lines": [], "query": "snowy window plant"}),
                  instruction="show snow outside")
    assert out == {"lines": [], "query": "snowy window plant"}
    assert "show snow outside" in ai.calls[0][0]


@pytest.mark.parametrize("reply", ["no json here", json.dumps({"lines": []}), RuntimeError("boom")])
def test_failures_are_sentences(reply):
    doc = _doc(["Plants sleep in winter."])
    with pytest.raises(studio_assist.AssistError) as e:
        run(doc, doc["scenes"][0]["uid"], "punchier", reply)
    assert "boom" not in str(e.value)


def test_without_an_ai_key_it_says_how_to_fix_it(monkeypatch):
    from backend.services import render_post

    async def no_settings(user_id="local"):
        return None

    def no_client(*_a, **_k):
        raise RuntimeError("no key")

    monkeypatch.setattr(render_post, "load_user_settings", no_settings)
    monkeypatch.setattr("backend.core.ai_provider.get_ai_client", no_client)
    doc = _doc(["Plants sleep in winter."])
    with pytest.raises(studio_assist.AssistError, match="AI key"):
        asyncio.run(studio_assist.suggest(doc, doc["scenes"][0]["uid"], "punchier"))


def test_scene_scoped_planning_plans_only_those_scenes(monkeypatch):
    from backend.services import stock_video_service as svs
    from backend.services import studio_planner

    seen = {}

    async def extract(chunks, ai):
        seen["chunks"] = [c["text"] for c in chunks]
        return [{"query": "q"} for _ in chunks]

    monkeypatch.setattr(svs, "extract_visual_scenes", extract)
    doc = sd.validate_doc({"aspect_ratio": "9:16", "input": {"mode": "script"}, "settings": sd.default_settings(),
                           "scenes": [sd.make_scene(l) for l in ("One line here.", "Two line here.", "Three line here.")]},
                          settle=False)
    uid = doc["scenes"][1]["uid"]
    ops, _ = asyncio.run(studio_planner.plan_project(doc, project_id="p", ai_client=object(), pexels_key="",
                                                     only_uids={uid}))
    assert seen["chunks"] == ["Two line here."]
    assert [o["uid"] for o in ops if o["op"] == "plan_result"] == [uid]
    assert ops[0]["visual"]["planned_for"] == "Two line here."
