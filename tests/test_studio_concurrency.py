# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Studio races, each reproduced against the real router + store.

Only synthesis is faked; the suite's isolated DATA_DIR holds the database.
Each test drives the interleaving that used to break:

  * a voice job that finished a scene must not settle that scene later, when a
    NEWER voice job has re-marked it (the old `finally` cancelled job 2's take)
  * a `rendering` claim left by a dead process (job swept, claim not) releases
    itself instead of locking the project forever
  * a render still running in this process blocks a new claim even after its
    job row was cancelled
  * a failed word-timing pass is retried, not cached as "no words" for good
  * undo (replace_doc) during or after Voice all keeps the takes
"""
import asyncio
import json

import pytest

SCRIPT = "Most people save money the wrong way. They wait until the end of the month. Flip it and pay yourself first."


@pytest.fixture(scope="module")
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api import studio
    from backend.database import init_db

    asyncio.run(init_db())
    app = FastAPI()
    app.include_router(studio.router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def captured(monkeypatch, tmp_path):
    from backend.core import task_runner
    from backend.core.ws_manager import ws_manager
    from backend.services import voice_take_service as vts

    state = {"runners": [], "calls": [], "on_synth": None, "warnings": []}
    monkeypatch.setattr(task_runner, "dispatch_light", state["runners"].append)
    monkeypatch.setattr(task_runner, "dispatch", state["runners"].append)
    monkeypatch.setattr(vts, "cache_dir", lambda: tmp_path / "voice")
    monkeypatch.setattr(vts, "probe_audio_duration", lambda _p: 1.8)
    monkeypatch.setattr(vts, "_trim_edges", lambda _p: None)

    async def fake_synth(text, spec, out):
        state["calls"].append(text)
        if state["on_synth"]:
            await state["on_synth"](text)
        out.write_bytes(b"ID3-take")

    monkeypatch.setattr(vts, "_synthesise", fake_synth)

    async def warning(constraint, message, severity="warning", wizard_id=None, user_id="local"):
        state["warnings"].append((constraint, message))

    monkeypatch.setattr(ws_manager, "send_constraint_warning", warning)
    return state


def create(client, script=SCRIPT):
    r = client.post("/api/studio/projects", json={"start": {"mode": "script", "script": script}})
    assert r.status_code == 200, r.text
    return r.json()["project"]


def get(client, pid):
    return client.get(f"/api/studio/projects/{pid}").json()["project"]


def scene(client, pid, uid):
    return next(s for s in get(client, pid)["doc"]["scenes"] if s["uid"] == uid)


def test_a_finished_voice_job_leaves_a_scene_a_newer_job_re_marked_alone(client, captured):
    """Job 1 voices scenes 1..2. While it records scene 2, the user edits scene 1
    (stale) and re-voices it — job 2 marks scene 1 generating. When job 1 ends
    it must settle only what IT still owned, so job 2 can still land."""
    p = create(client)
    uid1, uid2 = (s["uid"] for s in p["doc"]["scenes"][:2])
    r = client.post(f"/api/studio/projects/{p['id']}/voice", json={"scene_uids": [uid1, uid2]})
    assert r.status_code == 200 and r.json()["job_id"]
    job1 = captured["runners"].pop(0)
    line2 = p["doc"]["scenes"][1]["line"]

    async def edit_and_revoice_scene_1(text):
        if text != line2:
            return
        captured["on_synth"] = None
        # Takes record in parallel: wait until scene 1's take has landed, then
        # the user rewrites it and re-voices while scene 2 is still recording.
        # The client is synchronous: call it from a worker thread, never on this
        # loop — a blocking request here parks the loop while it may hold the
        # SQLite write lock the request needs ("database is locked" after 5 s).
        async def off_loop(fn, *a, **k):
            return await asyncio.to_thread(fn, *a, **k)
        for _ in range(200):
            if (await off_loop(scene, client, p["id"], uid1))["voice"]["state"] == "ready":
                break
            await asyncio.sleep(0.01)
        rev = (await off_loop(get, client, p["id"]))["revision"]
        assert (await off_loop(scene, client, p["id"], uid1))["voice"]["state"] == "ready"
        await off_loop(client.patch, f"/api/studio/projects/{p['id']}", json={"if_revision": rev, "ops": [
            {"op": "set_line", "uid": uid1, "line": "A brand new first line for the video."}]})
        again = await off_loop(client.post, f"/api/studio/projects/{p['id']}/voice", json={"scene_uids": [uid1]})
        assert again.status_code == 200 and again.json()["job_id"]
        assert (await off_loop(scene, client, p["id"], uid1))["voice"]["state"] == "generating"

    captured["on_synth"] = edit_and_revoice_scene_1
    asyncio.run(job1)
    # Job 1 is done. Scene 1 still belongs to job 2 — it must STILL be generating.
    assert scene(client, p["id"], uid1)["voice"]["state"] == "generating"
    assert scene(client, p["id"], uid2)["voice"]["state"] == "ready"
    job2 = captured["runners"].pop(0)
    asyncio.run(job2)
    s1 = scene(client, p["id"], uid1)
    assert s1["voice"]["state"] == "ready" and s1["line"].startswith("A brand new")
    assert len(captured["calls"]) == 3            # scene 1 twice (two lines), scene 2 once


def test_a_render_claim_with_no_live_job_is_released_and_taken_over(client, captured):
    """Simulates a crash mid-render: the boot sweep failed the job, the project
    row still says `rendering`. The next render must not be refused forever."""
    from sqlalchemy import update

    from backend.database import AsyncSessionLocal
    from backend.models.video_project import VideoProject

    p = create(client)

    async def strand():
        async with AsyncSessionLocal() as db:
            await db.execute(update(VideoProject).where(VideoProject.id == p["id"]).values(status="rendering"))
            await db.commit()
    asyncio.run(strand())
    assert get(client, p["id"])["status"] == "rendering"

    r = client.post(f"/api/studio/projects/{p['id']}/render")
    assert r.status_code == 200, r.text
    assert r.json()["job_id"] and len(captured["runners"]) == 1
    assert get(client, p["id"])["status"] == "rendering"

    # Now a render job IS pending for this project — a second render is a real conflict.
    again = client.post(f"/api/studio/projects/{p['id']}/render")
    assert again.status_code == 409 and again.json()["detail"]["code"] == "already_rendering"
    assert len(captured["runners"]) == 1
    captured["runners"].pop(0).close()             # never run: a real render needs ffmpeg + stock

    # Cleanup: release the claim so the module's DB isn't left with a stranded row.
    from backend.agents.job_helper import update_job_status
    from backend.services import studio_store as store
    asyncio.run(update_job_status(r.json()["job_id"], "cancelled"))
    store.release_render(p["id"])
    asyncio.run(store.finish_render(p["id"]))
    assert get(client, p["id"])["status"] == "draft"


def test_word_timings_failure_is_retried_not_cached(captured, monkeypatch):
    from backend.services import voice_take_service as vts

    spec = vts.VoiceSpec(provider="edge_tts", voice="en-US-AndrewMultilingualNeural")
    take = asyncio.run(vts.ensure_take(spec, "Words that Whisper could not time at first."))
    monkeypatch.setattr(vts, "_decode_peaks", lambda _p, count=200: [0.5] * 3)
    attempts = []

    async def flaky(path, text):
        attempts.append(text)
        return None if len(attempts) == 1 else [{"word": "Words", "start": 0.0, "end": 0.3}]
    monkeypatch.setattr(vts, "_word_timings", flaky)

    first = asyncio.run(vts.take_details(take.key))
    assert first["words"] is None and first["peaks"] == [0.5] * 3
    sidecar = json.loads((vts.cache_dir() / f"{take.key}.json").read_text())
    assert "words" not in sidecar and sidecar["peaks"] == [0.5] * 3     # peaks kept, the failure not
    second = asyncio.run(vts.take_details(take.key))
    assert second["words"] == [{"word": "Words", "start": 0.0, "end": 0.3}]
    assert len(attempts) == 2
    third = asyncio.run(vts.take_details(take.key))
    assert third["words"] == second["words"] and len(attempts) == 2      # now cached


def test_a_first_draft_voices_while_it_plans(client, captured, monkeypatch):
    """The plan job dispatches ONE voice job before planning (scene 1 is
    playable in seconds), marks the scenes generating, and finishes without
    waiting for the voices. A voice that uses the user's own API key is never
    auto-voiced — the draft says so instead."""
    from backend.services import studio_music, studio_planner

    async def no_plan(doc, **_k):
        return [], []
    monkeypatch.setattr(studio_planner, "plan_project", no_plan)

    async def no_music(doc, moods=None):
        return None
    monkeypatch.setattr(studio_music, "default_music_op", no_music)

    r = client.post("/api/studio/projects", json={"start": {"mode": "script", "script": SCRIPT}, "first_draft": True})
    assert r.status_code == 200 and r.json()["plan_job_id"]
    pid = r.json()["project"]["id"]
    plan_runner = captured["runners"].pop(0)
    asyncio.run(plan_runner)                                   # plans; dispatches the voice job
    assert len(captured["runners"]) == 1, "one voice job dispatched alongside planning"
    assert all(s["voice"]["state"] == "generating" for s in get(client, pid)["doc"]["scenes"])
    asyncio.run(captured["runners"].pop(0))
    assert all(s["voice"]["state"] == "ready" for s in get(client, pid)["doc"]["scenes"])
    assert len(captured["calls"]) == len(get(client, pid)["doc"]["scenes"])

    # A remembered voice on the user's own key: the draft plans but never records on its own.
    own_key = client.post("/api/studio/projects", json={
        "start": {"mode": "script", "script": SCRIPT}, "first_draft": True,
        "settings": {"voice": {"provider": "openai_tts", "voice": "alloy", "label": "Alloy"},
                     "captions": {"style": "bold"}},
    }).json()["project"]
    assert own_key["doc"]["settings"]["voice"]["provider"] == "openai_tts"
    assert own_key["doc"]["settings"]["captions"]["style"] == "bold"
    asyncio.run(captured["runners"].pop(0))
    assert not captured["runners"]
    assert all(s["voice"]["state"] == "none" for s in get(client, own_key["id"])["doc"]["scenes"])
    assert any(c == "studio_plan" and "Voice all" in m for c, m in captured["warnings"])


def test_a_render_still_running_in_process_blocks_a_new_claim_even_after_its_job_is_cancelled(client, captured):
    """Cancel only flips the job row; the runner keeps going until its next
    gate. A new render must wait for it, or two renders run into the same
    project and the old runner's finally resets the new one's claim."""
    from sqlalchemy import update

    from backend.database import AsyncSessionLocal
    from backend.models.job import Job
    from backend.services import studio_store as store

    p = create(client)
    r = client.post(f"/api/studio/projects/{p['id']}/render")
    assert r.status_code == 200, r.text
    assert get(client, p["id"])["render_alive"] is True

    async def cancel():
        async with AsyncSessionLocal() as db:
            await db.execute(update(Job).where(Job.id == r.json()["job_id"]).values(status="cancelled"))
            await db.commit()
    asyncio.run(cancel())
    again = client.post(f"/api/studio/projects/{p['id']}/render")
    assert again.status_code == 409 and again.json()["detail"]["code"] == "already_rendering"

    # The runner stops → the claim is released and a render may start again.
    captured["runners"].pop(0).close()
    asyncio.run(store.finish_render(p["id"]))
    store.release_render(p["id"])
    assert get(client, p["id"])["render_alive"] is False
    ok = client.post(f"/api/studio/projects/{p['id']}/render")
    assert ok.status_code == 200, ok.text
    captured["runners"].pop(0).close()
    from backend.agents.job_helper import update_job_status
    asyncio.run(update_job_status(ok.json()["job_id"], "cancelled"))
    asyncio.run(store.finish_render(p["id"]))
    store.release_render(p["id"])


def test_a_stranded_rendering_row_reports_no_live_render(client, captured):
    from sqlalchemy import update

    from backend.database import AsyncSessionLocal
    from backend.models.video_project import VideoProject
    from backend.services import studio_store as store

    p = create(client)

    async def strand():
        async with AsyncSessionLocal() as db:
            await db.execute(update(VideoProject).where(VideoProject.id == p["id"]).values(status="rendering"))
            await db.commit()
    asyncio.run(strand())
    got = get(client, p["id"])
    assert got["status"] == "rendering" and got["render_alive"] is False
    asyncio.run(store.finish_render(p["id"]))


def test_an_unexpected_take_error_lands_failed_not_stuck_generating(client, captured):
    p = create(client)
    uid = p["doc"]["scenes"][0]["uid"]

    async def disk_full(_text):
        raise OSError("No space left on device")
    captured["on_synth"] = disk_full
    r = client.post(f"/api/studio/projects/{p['id']}/voice", json={"scene_uids": [uid]})
    assert r.status_code == 200 and r.json()["job_id"]
    asyncio.run(captured["runners"].pop(0))
    voice = scene(client, p["id"], uid)["voice"]
    assert voice["state"] == "failed"
    assert "No space" not in (voice.get("error") or "")         # an internal error is never shown


def test_deleting_a_project_mid_voice_cancels_the_job_quietly(client, captured):
    from sqlalchemy import select

    from backend.database import AsyncSessionLocal
    from backend.models.job import Job

    p = create(client)
    r = client.post(f"/api/studio/projects/{p['id']}/voice", json={"scene_uids": "all"})
    job_id = r.json()["job_id"]

    async def delete_first(_text):
        captured["on_synth"] = None
        assert (await asyncio.to_thread(client.delete, f"/api/studio/projects/{p['id']}")).status_code == 200
    captured["on_synth"] = delete_first
    asyncio.run(captured["runners"].pop(0))

    async def status():
        async with AsyncSessionLocal() as db:
            return (await db.execute(select(Job.status).where(Job.id == job_id))).scalar_one()
    assert asyncio.run(status()) == "cancelled"


def test_a_voice_switch_landing_before_the_mark_is_not_recorded_in_the_old_voice(client, captured, monkeypatch):
    """The endpoint read the project in the free Edge voice; a switch to the
    OpenAI voice lands before its `generating` write. That write is conditioned
    on the revision it read, so it loses — and since the voice changed, the
    request is refused instead of recording takes nobody asked for."""
    from backend.services import studio_store as store

    p = create(client)
    real = store.write_ops
    switched = {"done": False}

    async def switch_first(project_id, ops, **kw):
        if not switched["done"] and kw.get("internal") and ops and ops[0].get("op") == "voice_result":
            switched["done"] = True
            await real(project_id, [{"op": "set_setting", "path": "voice",
                                     "value": {"provider": "openai_tts", "voice": "alloy"}}], if_revision=None)
        return await real(project_id, ops, **kw)
    monkeypatch.setattr(store, "write_ops", switch_first)
    r = client.post(f"/api/studio/projects/{p['id']}/voice", json={"scene_uids": "all"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "revision_conflict", r.text
    assert not captured["runners"]
    monkeypatch.setattr(store, "write_ops", real)
    after = get(client, p["id"])
    assert after["doc"]["settings"]["voice"]["provider"] == "openai_tts"
    assert all(s["voice"]["state"] != "generating" for s in after["doc"]["scenes"])


def test_a_concurrent_write_that_leaves_the_voice_alone_is_retried(client, captured, monkeypatch):
    """The other side of the same guard: a job landing meanwhile (a title, a
    plan) doesn't change what would be recorded, so the mark is retried."""
    from backend.services import studio_store as store

    p = create(client)
    real = store.write_ops
    bumped = {"done": False}

    async def bump_first(project_id, ops, **kw):
        if not bumped["done"] and kw.get("internal") and ops and ops[0].get("op") == "voice_result":
            bumped["done"] = True
            await real(project_id, [{"op": "set_title", "title": "Renamed meanwhile"}], if_revision=None)
        return await real(project_id, ops, **kw)
    monkeypatch.setattr(store, "write_ops", bump_first)
    r = client.post(f"/api/studio/projects/{p['id']}/voice", json={"scene_uids": "all"})
    assert r.status_code == 200 and r.json()["job_id"], r.text
    monkeypatch.setattr(store, "write_ops", real)
    asyncio.run(captured["runners"].pop(0))
    assert all(s["voice"]["state"] == "ready" for s in get(client, p["id"])["doc"]["scenes"])


def test_boot_settles_scenes_a_dead_process_left_generating(client, captured):
    from sqlalchemy import update

    from backend.database import AsyncSessionLocal
    from backend.models.job import Job
    from backend.services import studio_store as store

    async def no_live_studio_jobs():                 # this is boot: earlier tests' never-run runners are dead
        async with AsyncSessionLocal() as db:
            await db.execute(update(Job).where(Job.job_type.like("studio_%"), Job.status.in_(["pending", "running"]))
                             .values(status="failed"))
            await db.commit()
    asyncio.run(no_live_studio_jobs())
    p = create(client)
    uid1 = p["doc"]["scenes"][0]["uid"]
    asyncio.run(store.write_ops(p["id"], [
        {"op": "voice_result", "uid": uid1, "voice": {"state": "generating"}},
    ], if_revision=None, internal=True))
    assert asyncio.run(store.settle_orphaned_generating()) >= 1
    assert scene(client, p["id"], uid1)["voice"]["state"] == "none"


def test_caption_style_none_turns_captions_off(client):
    from backend.services import studio_store as store
    row = asyncio.run(store.create_project(script=SCRIPT, settings_overrides={"captions": {"enabled": True, "style": "none"}}))
    assert json.loads(row.doc_json)["settings"]["captions"] == {"enabled": False, "style": "viral", "hook": True, "hook_text": None}


def test_undo_during_voice_all_keeps_the_voice_job_landing(client, captured):
    """replace_doc used to settle every generating scene — an undo during
    Voice all cancelled work in flight (the job skipped scenes and still said
    success)."""
    p = create(client)
    snapshot = p["doc"]                                         # before voicing: every scene "none"
    uid = snapshot["scenes"][0]["uid"]
    r = client.post(f"/api/studio/projects/{p['id']}/voice", json={"scene_uids": "all"})
    assert r.status_code == 200 and r.json()["job_id"]
    rev = get(client, p["id"])["revision"]
    edited = client.patch(f"/api/studio/projects/{p['id']}", json={"if_revision": rev, "ops": [
        {"op": "set_setting", "path": "captions.style", "value": "bold"}]}).json()["project"]
    undo = client.patch(f"/api/studio/projects/{p['id']}", json={"if_revision": edited["revision"], "ops": [
        {"op": "replace_doc", "doc": snapshot}]})
    assert undo.status_code == 200, undo.text
    assert all(s["voice"]["state"] == "generating" for s in undo.json()["project"]["doc"]["scenes"])
    asyncio.run(captured["runners"].pop(0))
    assert all(s["voice"]["state"] == "ready" for s in get(client, p["id"])["doc"]["scenes"])
    assert scene(client, p["id"], uid)["voice"]["take_key"]


def test_undo_after_voice_all_landed_keeps_the_takes(client, captured):
    """An undo to a snapshot taken WHILE Voice all ran, performed AFTER the
    takes landed, used to reset every scene to "not voiced" (settle turned the
    snapshot's spinners into none/stale). The landed takes are the answer that
    snapshot was waiting for — keep them."""
    p = create(client)
    r = client.post(f"/api/studio/projects/{p['id']}/voice", json={"scene_uids": "all"})
    assert r.status_code == 200 and r.json()["job_id"]
    during = get(client, p["id"])                                # every scene "generating"
    assert all(s["voice"]["state"] == "generating" for s in during["doc"]["scenes"])
    client.patch(f"/api/studio/projects/{p['id']}", json={"if_revision": during["revision"], "ops": [
        {"op": "set_setting", "path": "captions.style", "value": "bold"}]})
    asyncio.run(captured["runners"].pop(0))                      # the takes land
    landed = get(client, p["id"])
    assert all(s["voice"]["state"] == "ready" for s in landed["doc"]["scenes"])
    undo = client.patch(f"/api/studio/projects/{p['id']}", json={"if_revision": landed["revision"], "ops": [
        {"op": "replace_doc", "doc": during["doc"]}]})
    assert undo.status_code == 200, undo.text
    after = undo.json()["project"]["doc"]
    assert all(s["voice"]["state"] == "ready" and s["voice"]["take_key"] for s in after["scenes"])
    assert after["settings"]["captions"]["style"] == during["doc"]["settings"]["captions"]["style"]  # the edit was undone


def test_generating_scenes_settle_per_project_not_all_or_nothing(client, captured):
    """One fresh (possibly draining) job used to block the settle for every
    project — after a quick restart scenes stayed generating for good."""
    from backend.agents.job_helper import create_job, update_job_status
    from backend.services import studio_store as store

    busy, stuck = create(client), create(client)
    for p in (busy, stuck):
        asyncio.run(store.write_ops(p["id"], [{"op": "voice_result", "uid": p["doc"]["scenes"][0]["uid"],
                                               "voice": {"state": "generating"}}], if_revision=None, internal=True))
    job = asyncio.run(create_job("studio_voice", "local", {"project_id": busy["id"], "scenes": 1}))
    asyncio.run(update_job_status(job.id, "running", 5, "Recording"))
    try:
        asyncio.run(store.settle_orphaned_generating())
        assert get(client, busy["id"])["doc"]["scenes"][0]["voice"]["state"] == "generating"   # its job may land
        assert get(client, stuck["id"])["doc"]["scenes"][0]["voice"]["state"] == "none"
    finally:
        asyncio.run(update_job_status(job.id, "failed", error_message="test"))
    asyncio.run(store.settle_orphaned_generating())
    assert get(client, busy["id"])["doc"]["scenes"][0]["voice"]["state"] == "none"


def test_an_upload_is_recorded_even_when_every_optimistic_retry_loses(client, captured, monkeypatch):
    """A file already on disk must never be lost to a race: past the optimistic
    retries the index write is made under SQLite's write lock."""
    from backend.services import studio_store as store

    p = create(client)
    monkeypatch.setattr(store, "_INTERNAL_WRITE_ATTEMPTS", 0)          # straight to the locked write
    before = get(client, p["id"])["revision"]
    row = asyncio.run(store.update_assets(p["id"], lambda a: {**a, "imports": {**a["imports"], "k": {"asset_id": "as_1"}}}))
    assert json.loads(row.assets_json)["imports"]["k"]["asset_id"] == "as_1"
    assert row.revision == before + 1


def test_deleting_a_clip_checks_use_on_the_row_it_writes(client, captured, monkeypatch):
    """A bind that landed after the endpoint read the project must still
    refuse the delete — no scene left on a deleted file."""
    from backend.services import studio_media
    from backend.services import studio_store as store

    p = create(client)
    uid = p["doc"]["scenes"][0]["uid"]
    record = {"asset_id": studio_media.new_asset_id(), "title": "Mine", "media": "video", "source": "upload",
              "native_duration": 3.0, "width": 1080, "height": 1920, "file": "mine.mp4", "poster": None}
    asyncio.run(store.update_assets(p["id"], lambda a: {**a, "imports": {record["asset_id"]: record}}))
    stale_row = asyncio.run(store.get_project(p["id"]))            # read BEFORE the bind lands
    asyncio.run(store.write_ops(p["id"], [{"op": "bind_visual", "uid": uid, "visual": {
        "kind": "user_clip", "asset_id": record["asset_id"]}}], if_revision=None, internal=True))
    assert scene(client, p["id"], uid)["visual"]["kind"] == "user_clip"
    real_get = store.get_project
    calls = {"n": 0}

    async def stale_first(project_id, user_id="local"):
        calls["n"] += 1
        return stale_row if calls["n"] == 1 else await real_get(project_id, user_id)
    monkeypatch.setattr(store, "get_project", stale_first)
    r = client.delete(f"/api/studio/projects/{p['id']}/media/{record['asset_id']}")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "in_use" and r.json()["detail"]["scenes"] == [1]
    monkeypatch.setattr(store, "get_project", real_get)
    assert record["asset_id"] in json.loads(asyncio.run(real_get(p["id"])).assets_json)["imports"]


def test_voice_endpoint_revoices_a_lost_take(client, captured):
    """A ready scene whose take file is gone is re-recorded."""
    from backend.services import voice_take_service as vts

    p = create(client)
    uid = p["doc"]["scenes"][0]["uid"]
    client.post(f"/api/studio/projects/{p['id']}/voice", json={"scene_uids": [uid]})
    asyncio.run(captured["runners"].pop(0))
    take = scene(client, p["id"], uid)["voice"]["take_key"]
    for path in (vts.cache_dir() / f"{take}.mp3", vts.cache_dir() / f"{take}.json"):
        path.unlink()
    again = client.post(f"/api/studio/projects/{p['id']}/voice", json={"scene_uids": [uid]})
    assert again.status_code == 200 and again.json()["job_id"]
    asyncio.run(captured["runners"].pop(0))
    assert vts.is_cached(scene(client, p["id"], uid)["voice"]["take_key"])


def test_errors_always_carry_a_code(client, captured):
    """One error shape for the editor to branch on."""
    missing = client.get("/api/studio/projects/nope")
    assert missing.status_code == 404 and missing.json()["detail"]["code"] == "not_found"
    assert missing.json()["detail"]["message"]
    bad = client.post("/api/studio/projects", json={"start": {"script": "  "}})
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "invalid"
    p = create(client)
    assert client.get(f"/api/studio/projects/{p['id']}/quote").status_code in (404, 405)


def test_the_envelope_names_the_running_render_job_so_a_remount_can_reattach(client, captured):
    """The render's job id lived only in the editor's state, so a reload or
    navigate-away-and-back showed "Rendering 0%" for the whole render and never
    the finished-video card. The envelope carries it while (and only while) a
    render is live."""
    from backend.agents.job_helper import update_job_status
    from backend.services import studio_store as store

    p = create(client)
    assert get(client, p["id"])["render_job_id"] is None
    r = client.post(f"/api/studio/projects/{p['id']}/render")
    assert r.status_code == 200, r.text
    assert get(client, p["id"])["render_job_id"] == r.json()["job_id"]
    captured["runners"].pop(0).close()             # never run: a real render needs ffmpeg + stock
    asyncio.run(update_job_status(r.json()["job_id"], "cancelled"))
    store.release_render(p["id"])
    asyncio.run(store.finish_render(p["id"]))
    assert get(client, p["id"])["render_job_id"] is None


def test_a_project_cannot_be_deleted_while_it_renders(client, captured):
    """Deleting mid-render kept rendering, wrote a Library video for a deleted
    project and orphaned its files."""
    from backend.agents.job_helper import update_job_status
    from backend.services import studio_store as store

    p = create(client)
    r = client.post(f"/api/studio/projects/{p['id']}/render")
    assert r.status_code == 200, r.text
    busy = client.delete(f"/api/studio/projects/{p['id']}")
    assert busy.status_code == 409 and busy.json()["detail"]["code"] == "busy"
    captured["runners"].pop(0).close()                       # never run: a real render needs ffmpeg + stock
    asyncio.run(update_job_status(r.json()["job_id"], "cancelled"))   # what a real cancel leaves
    store.release_render(p["id"])                            # the runner's finally, which never ran here
    asyncio.run(store.finish_render(p["id"]))
    assert client.delete(f"/api/studio/projects/{p['id']}").status_code == 200
