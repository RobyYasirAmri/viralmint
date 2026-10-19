# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Two Studio contract rules.

  * `set_visual_fields` — the op behind Pin, Fit and editing a scene's search
    term. Pinning is what makes a scene FIXED, so planning may not reassign
    it — the op and the rule have to agree or a pinned scene quietly loses
    its footage.
  * `list_projects` — the Home list reads only the summary columns, never a
    project's document, and its search filter and limit hold.
"""
import asyncio
import json

import pytest
from sqlalchemy import update

from backend.core.exceptions import StudioOpError
from backend.services import studio_doc as sd
from backend.services import studio_store as store
from backend.services.studio_ops import apply_ops

SCRIPT = ("A glass jar of coins sits on a scratched wooden table in the morning light. "
          "A hand reaches in and drops one more shiny coin down onto the pile. "
          "Small habits, repeated every single day, are quietly what fill the jar up.")


def _doc(**visual):
    base = {"kind": "stock", "state": "placeholder", "query": "coins jar",
            "asset": None, "alternates": [], "fit": "loop", "pinned": False, "reason": None}
    return sd.validate_doc({"settings": sd.default_settings(), "scenes": [
        {"uid": "u1", "line": "A jar of coins.", "voice": {"state": "none"}, "visual": {**base, **visual}},
        {"uid": "u2", "line": "A hand drops one in.", "voice": {"state": "none"}, "visual": dict(base)},
    ]}, settle=False)


# ── set_visual_fields ──────────────────────────────────────────────────────

def test_each_field_is_set_and_normalised():
    out = apply_ops(_doc(), [{"op": "set_visual_fields", "uid": "u1", "fields": {
        "query": "  coins  on  wood ", "fit": "freeze", "pinned": True,
    }}]).doc["scenes"][0]["visual"]
    assert out["query"] == "coins on wood"
    assert out["fit"] == "freeze" and out["pinned"] is True


def test_an_empty_query_keeps_the_one_the_scene_has():
    """The render searches `query` for an unbound stock scene — clearing it
    would leave the scene with nothing to look for."""
    out = apply_ops(_doc(), [{"op": "set_visual_fields", "uid": "u1", "fields": {"query": "   "}}])
    assert out.doc["scenes"][0]["visual"]["query"] == "coins jar"


def test_only_the_keys_sent_change():
    out = apply_ops(_doc(fit="slow", pinned=True),
                    [{"op": "set_visual_fields", "uid": "u1", "fields": {"query": "new terms"}}])
    v = out.doc["scenes"][0]["visual"]
    assert v["fit"] == "slow" and v["pinned"] is True and v["query"] == "new terms"


@pytest.mark.parametrize("op", [
    {"op": "set_visual_fields", "uid": "u1", "fields": "pinned"},
    {"op": "set_visual_fields", "uid": "u1", "fields": {"fit": "zoom"}},
    {"op": "set_visual_fields", "uid": "gone", "fields": {"pinned": True}},
])
def test_a_bad_field_write_is_refused_whole(op):
    doc = _doc()
    before = json.dumps(doc, sort_keys=True)
    with pytest.raises(StudioOpError):
        apply_ops(doc, [op])
    assert json.dumps(doc, sort_keys=True) == before          # all-or-nothing


def test_pinning_is_what_takes_a_scene_out_of_planning():
    """Planning moves only OPEN scenes, and `pinned` is the user saying 'not
    this one'. Pin scene 1, land a plan on both — only scene 2 takes it."""
    pinned = apply_ops(_doc(), [{"op": "set_visual_fields", "uid": "u1", "fields": {"pinned": True}}]).doc
    assert sd.is_fixed_visual(pinned["scenes"][0]) and not sd.is_fixed_visual(pinned["scenes"][1])
    planned = {"kind": "stock", "state": "placeholder", "query": "planned footage"}
    out = apply_ops(pinned, [{"op": "plan_result", "uid": u, "visual": planned} for u in ("u1", "u2")],
                    internal=True).doc
    assert [s["visual"]["query"] for s in out["scenes"]] == ["coins jar", "planned footage"]
    # …and un-pinning gives it back to planning.
    open_again = apply_ops(out, [{"op": "set_visual_fields", "uid": "u1", "fields": {"pinned": False}}]).doc
    assert not sd.is_fixed_visual(open_again["scenes"][0])


# ── the Home list ──────────────────────────────────────────────────────────

@pytest.fixture
def project():
    from backend.database import init_db
    asyncio.run(init_db())
    return asyncio.run(store.create_project(script=SCRIPT, visual_style="noir"))


def test_home_lists_from_the_summary_columns_not_the_document(project):
    """A row whose document is unreadable is still listed, from its summary
    columns — Home never parses every project's document."""
    from backend.database import AsyncSessionLocal
    from backend.models.video_project import VideoProject

    scenes = len(json.loads(project.doc_json)["scenes"])

    async def corrupt():
        async with AsyncSessionLocal() as db:
            await db.execute(update(VideoProject).where(VideoProject.id == project.id)
                             .values(doc_json="{not json", updated_at=VideoProject.updated_at))
            await db.commit()
    asyncio.run(corrupt())
    listed = next(p for p in asyncio.run(store.list_projects()) if p["id"] == project.id)
    assert listed["scenes"] == scenes and listed["visual_style"] == "noir"


def test_the_search_filter_and_limit_hold(project):
    other = asyncio.run(store.create_project(script=SCRIPT, title="Completely different name"))
    titles = [p["title"] for p in asyncio.run(store.list_projects(q="Completely"))]
    assert titles == ["Completely different name"]
    assert len(asyncio.run(store.list_projects(limit=1))) == 1
    asyncio.run(store.delete_project(other.id))
