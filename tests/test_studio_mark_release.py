# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Every `generating` mark has a release path.

`/voice` marks scenes `generating` in the same write that authorises the job —
that is what stops a second request recording the same takes. But the mark is
a STATUS CLAIM: if the job it authorises never starts, the scene spins with
nothing behind it. Render refuses ("still being voiced"), Voice all skips it,
and the editor polls forever — until a restart's boot sweep
(studio_store.settle_orphaned_generating) settles it. A `create_job` failure
left exactly that state; these tests pin the release.
"""
import asyncio
import json

import pytest

SCRIPT = ("A glass jar of coins sits on a scratched wooden table in the morning light. "
          "A hand reaches in and drops one more shiny coin down onto the pile.")


@pytest.fixture
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api import studio
    from backend.database import init_db

    asyncio.run(init_db())
    app = FastAPI()
    app.include_router(studio.router, prefix="/api")
    # The endpoint is allowed to 500 — what matters is the state it leaves.
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def env(monkeypatch):
    from backend.core import task_runner

    monkeypatch.setattr(task_runner, "dispatch", lambda c: c.close())
    monkeypatch.setattr(task_runner, "dispatch_light", lambda c: c.close())


@pytest.fixture
def project(env):
    from backend.services import studio_store as store
    return asyncio.run(store.create_project(script=SCRIPT))


def _doc(project_id):
    from backend.services import studio_store as store
    return json.loads(asyncio.run(store.get_project(project_id)).doc_json)


def _break_create_job(monkeypatch):
    from backend.agents import job_helper

    async def boom(*a, **k):
        raise RuntimeError("database is locked")
    monkeypatch.setattr(job_helper, "create_job", boom)


def test_a_job_that_never_starts_leaves_no_scene_voicing(client, project, monkeypatch):
    _break_create_job(monkeypatch)
    r = client.post(f"/api/studio/projects/{project.id}/voice", json={"scene_uids": "all"})
    assert r.status_code >= 500                                     # the request failed, loudly
    states = [s["voice"]["state"] for s in _doc(project.id)["scenes"]]
    assert states and "generating" not in states                    # …and left nothing spinning

    # The proof it matters: the project is renderable again (no "still being
    # voiced" blocker) and Voice all picks the scenes back up.
    p = client.get(f"/api/studio/projects/{project.id}").json()["project"]
    assert not [b for b in p["checks"]["blockers"] if "voiced" in b]


def test_a_released_voice_mark_keeps_a_take_the_scene_already_had(client, project, monkeypatch):
    """A scene with a recorded take goes back to `stale`, not `none` — undo
    must still find the take."""
    from backend.services import studio_store as store

    uid = _doc(project.id)["scenes"][0]["uid"]
    key = "a" * 64
    monkeypatch.setattr("backend.services.voice_take_service.is_cached", lambda k: k == key)
    asyncio.run(store.write_ops(project.id, [{"op": "voice_result", "uid": uid, "voice": {
        "state": "stale", "take_key": key, "duration": 2.0}}], if_revision=None, internal=True))

    _break_create_job(monkeypatch)
    r = client.post(f"/api/studio/projects/{project.id}/voice", json={"scene_uids": [uid]})
    assert r.status_code >= 500
    scene = next(s for s in _doc(project.id)["scenes"] if s["uid"] == uid)
    assert scene["voice"]["state"] == "stale"
    assert scene["voice"].get("take_key") == key


def test_a_stale_visual_result_never_disturbs_a_newer_choice(client, project):
    """A visual result is scoped by `expect`: one written for the visual the
    scene had when the work started lands nowhere once the scene moved on."""
    from backend.services import studio_store as store

    uid = _doc(project.id)["scenes"][0]["uid"]
    asyncio.run(store.write_ops(project.id, [
        {"op": "set_visual_fields", "uid": uid, "fields": {"query": "someone else's"}},
    ], if_revision=None))
    asyncio.run(store.write_ops(project.id, [{
        "op": "visual_result", "uid": uid, "expect": {"query": "the old query"},
        "visual": {"state": "failed", "reason": "stale"},
    }], if_revision=None, internal=True))
    scene = next(s for s in _doc(project.id)["scenes"] if s["uid"] == uid)
    assert scene["visual"]["state"] != "failed" and scene["visual"]["query"] == "someone else's"


def test_a_plan_that_never_starts_releases_its_single_flight_slot(client, project, monkeypatch):
    """The plan's single-flight slot is taken before its job is created; a
    failed create must give it back, or every later "Build storyboard" for the
    project is answered with a job that doesn't exist."""
    from backend.core.tasks import studio as studio_tasks

    _break_create_job(monkeypatch)
    r = client.post(f"/api/studio/projects/{project.id}/plan")
    assert r.status_code >= 500
    assert project.id not in studio_tasks.PLANS_IN_FLIGHT


def test_a_render_that_never_starts_releases_its_claim(client, project, monkeypatch):
    from backend.services import studio_store as store

    _break_create_job(monkeypatch)
    r = client.post(f"/api/studio/projects/{project.id}/render")
    assert r.status_code >= 500
    row = asyncio.run(store.get_project(project.id))
    assert row.status == "draft" and not store.render_running_here(project.id)
