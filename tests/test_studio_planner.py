# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""studio_planner + run_studio_plan.

The AI extractor, the stock search and the re-ranker are faked at their module
attributes; the store, ops and runner are real (isolated DATA_DIR). No network.
"""
import asyncio
import json

import pytest

SCRIPT = ("Most people save money the wrong way. They wait for the end of the month. "
          "Flip it and pay yourself first. Automate a transfer on payday. Spend the rest freely.")


def cand(n):
    return {"source": "pexels", "id": n,
            "download_url": f"https://videos.pexels.com/video-files/{n}/hd.mp4",
            "preview_url": f"https://videos.pexels.com/video-files/{n}/sd.mp4",
            "thumbnail": f"https://images.pexels.com/{n}.jpg", "duration": 8, "width": 1080, "height": 1920,
            "creator": "C"}


@pytest.fixture(autouse=True)
def db():
    from backend.database import init_db
    asyncio.run(init_db())


_RUNNERS: list = []


@pytest.fixture
def fakes(monkeypatch):
    from backend.core import task_runner
    from backend.services import clip_rank_service, studio_media
    from backend.services import stock_video_service as svs

    # A first draft DISPATCHES its voice job alongside planning; capture it so
    # plan() can run it to completion deterministically.
    _RUNNERS.clear()
    monkeypatch.setattr(task_runner, "dispatch_light", _RUNNERS.append)
    monkeypatch.setattr(task_runner, "dispatch", _RUNNERS.append)

    state = {"extract_calls": 0, "on_extract": None, "same_pool": False}
    monkeypatch.setattr(studio_media, "stock_keys", lambda: ("k", ""))
    monkeypatch.setattr("backend.core.ai_provider.get_ai_client", lambda *a, **k: object())

    async def extract(chunks, ai):
        state["extract_calls"] += 1
        if state["on_extract"]:
            await state["on_extract"]()
        return [{"query": f"visual {k}", "alt1": "a", "alt2": "b", "mood": "calm"} for k in range(len(chunks))]

    async def search_all(scenes, orientation, voice_duration, pexels_api_key, pixabay_api_key=""):
        state["keys"] = (pexels_api_key, pixabay_api_key)
        if state["same_pool"]:
            return [(k, [cand(1), cand(2)]) for k in range(len(scenes))]
        return [(k, [cand(100 + k * 10 + j) for j in range(7)]) for k in range(len(scenes))]

    async def rank(items, ai):
        return {it["scene_idx"]: list(reversed(it["candidates"]))[:3] for it in items}

    monkeypatch.setattr(svs, "extract_visual_scenes", extract)
    monkeypatch.setattr(svs, "search_all_scenes", search_all)
    monkeypatch.setattr(clip_rank_service, "rank_scene_candidates", rank)
    sent = []

    async def warn(constraint, message, severity="warning", wizard_id=None, user_id="local"):
        sent.append(message)

    monkeypatch.setattr("backend.core.ws_manager.ws_manager.send_constraint_warning", warn)
    state["warnings"] = sent
    return state


def make(script=SCRIPT):
    from backend.services import studio_store as store
    return asyncio.run(store.create_project(script=script))


def plan(row, first_draft=False):
    from backend.agents.job_helper import create_job
    from backend.core.tasks.studio import run_studio_plan
    from backend.services import studio_store as store

    job = asyncio.run(create_job("studio_plan", "local", {}))
    asyncio.run(run_studio_plan(job.id, row.id, "local", first_draft))
    while _RUNNERS:                                  # the concurrently dispatched voice job, if any
        asyncio.run(_RUNNERS.pop(0))
    return json.loads(asyncio.run(store.get_project(row.id)).doc_json)


def test_plan_binds_the_best_candidate_and_keeps_alternates(fakes):
    doc = plan(make())
    assert fakes["extract_calls"] == 1
    assert all(s["visual"]["kind"] == "stock" and s["visual"]["state"] == "bound" for s in doc["scenes"])
    first = doc["scenes"][0]["visual"]
    assert first["asset"]["provider_id"] == "106"            # the re-ranker's first pick (it reverses the pool)
    assert len(first["alternates"]) == 5 and first["alternates"][0]["provider_id"] == "106"
    assert first["query"] == "visual 0"
    assert first["planned_for"] == doc["scenes"][0]["line"]


def test_no_clip_is_used_twice_when_there_is_an_alternative(fakes):
    fakes["same_pool"] = True
    doc = plan(make("One scene line here with enough words to stand alone as a scene. "
                    "Two scene line there with enough words to stand alone too."))
    assert len(doc["scenes"]) == 2
    picks = [s["visual"]["asset"]["provider_id"] for s in doc["scenes"]]
    assert len(set(picks)) == len(picks)


def test_a_portrait_clip_in_the_top_three_is_preferred_for_vertical():
    from backend.services.studio_planner import prefer_native_orientation
    wide = {"width": 1920, "height": 1080, "id": "w"}
    tall = {"width": 1080, "height": 1920, "id": "t"}
    assert prefer_native_orientation([wide, wide, tall], True)[0] is tall
    assert prefer_native_orientation([wide, wide, wide, tall], True)[0] is wide     # outside the window
    assert prefer_native_orientation([wide, tall], False)[0] is wide


def test_plan_never_overrides_a_pin_or_a_line_edited_meanwhile(fakes):
    from backend.services import studio_store as store
    row = make()
    doc = json.loads(row.doc_json)
    pinned, edited = doc["scenes"][0]["uid"], doc["scenes"][2]["uid"]
    row, _ = asyncio.run(store.write_ops(row.id, [
        {"op": "bind_visual", "uid": pinned, "visual": {"kind": "stock", "query": "my own pick"}}], if_revision=None))

    async def edit_during_planning():
        await store.write_ops(row.id, [{"op": "set_line", "uid": edited, "line": "Rewritten while planning."}],
                              if_revision=None)

    fakes["on_extract"] = edit_during_planning
    doc = plan(row)
    by_uid = {s["uid"]: s for s in doc["scenes"]}
    assert by_uid[pinned]["visual"]["query"] == "my own pick" and by_uid[pinned]["visual"]["pinned"]
    assert by_uid[edited]["line"] == "Rewritten while planning."
    assert by_uid[edited]["visual"]["state"] == "placeholder"   # the old line's plan did not land


def test_a_planned_alternate_can_be_bound(fakes):
    from backend.services import studio_store as store
    row = make()
    doc = plan(row)
    uid = doc["scenes"][0]["uid"]
    alt = doc["scenes"][0]["visual"]["alternates"][3]
    row2, _ = asyncio.run(store.write_ops(row.id, [
        {"op": "bind_visual", "uid": uid, "visual": {"kind": "stock", "candidate": alt}}], if_revision=None))
    bound = json.loads(row2.doc_json)["scenes"][0]["visual"]
    assert bound["asset"]["provider_id"] == alt["provider_id"] and bound["pinned"]


def test_a_pixabay_only_install_still_plans_stock(fakes, monkeypatch):
    from backend.services import studio_media

    monkeypatch.setattr(studio_media, "stock_keys", lambda: ("", "px"))
    doc = plan(make())
    assert fakes["keys"] == ("", "px")
    assert all(s["visual"]["state"] == "bound" for s in doc["scenes"])
    assert studio_media.NO_KEY_MESSAGE not in fakes["warnings"]


def test_without_keys_it_still_plans_with_keywords_and_warns(fakes, monkeypatch):
    from backend.services import studio_media

    monkeypatch.setattr(studio_media, "stock_keys", lambda: ("", ""))

    def no_client(*_a, **_k):
        raise RuntimeError("no AI key configured")

    monkeypatch.setattr("backend.core.ai_provider.get_ai_client", no_client)
    doc = plan(make())
    assert fakes["extract_calls"] == 0
    assert all(s["visual"]["query"] for s in doc["scenes"])
    assert any("No AI key is set" in w for w in fakes["warnings"])
    assert studio_media.NO_KEY_MESSAGE in fakes["warnings"]


def test_first_draft_plans_then_voices_with_the_free_voice(fakes, monkeypatch, tmp_path):
    from backend.services import voice_take_service as vts
    monkeypatch.setattr(vts, "cache_dir", lambda: tmp_path / "voice")
    monkeypatch.setattr(vts, "probe_audio_duration", lambda _p: 1.5)

    async def synth(text, spec, out):
        assert spec.provider == "edge_tts"
        out.write_bytes(b"ID3")

    monkeypatch.setattr(vts, "_synthesise", synth)
    doc = plan(make(), first_draft=True)
    assert all(s["voice"]["state"] == "ready" for s in doc["scenes"])
    assert any(s["visual"]["state"] == "bound" for s in doc["scenes"])


def test_first_draft_never_auto_voices_a_voice_that_uses_the_users_key(fakes, monkeypatch):
    from backend.services import studio_store as store
    from backend.services import voice_take_service as vts

    calls = []

    async def synth(text, spec, out):
        calls.append(text)

    monkeypatch.setattr(vts, "_synthesise", synth)
    row = make()
    row, _ = asyncio.run(store.write_ops(row.id, [
        {"op": "set_setting", "path": "voice", "value": {"provider": "openai_tts", "voice": "nova"}}],
        if_revision=None))
    doc = plan(row, first_draft=True)
    assert all(s["voice"]["state"] == "none" for s in doc["scenes"]) and not calls
    assert any("isn't voiced" in w for w in fakes["warnings"])
    # …and the plan itself still ran, so the user gets a storyboard either way.
    assert any(s["visual"]["state"] == "bound" for s in doc["scenes"])


def test_plan_endpoint_and_create_with_plan(fakes, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api import studio
    from backend.core import task_runner
    from backend.core.tasks import studio as studio_tasks

    started, heavy = [], []
    # Planning is network I/O (AI + stock search): the LIGHT pool.
    monkeypatch.setattr(task_runner, "dispatch_light", started.append)
    monkeypatch.setattr(task_runner, "dispatch", heavy.append)
    app = FastAPI()
    app.include_router(studio.router, prefix="/api")
    client = TestClient(app)
    r = client.post("/api/studio/projects", json={"start": {"script": SCRIPT}, "plan": True})
    assert r.status_code == 200 and r.json()["plan_job_id"] and len(started) == 1 and not heavy
    first_job = r.json()["plan_job_id"]
    pid = r.json()["project"]["id"]
    # Single-flight: a second plan request while one runs gets that job, no new one.
    again = client.post(f"/api/studio/projects/{pid}/plan").json()["job_id"]
    assert again == first_job and len(started) == 1
    assert client.get(f"/api/studio/projects/{pid}").json()["project"]["plan_job_id"] == first_job
    started.pop().close()
    studio_tasks.PLANS_IN_FLIGHT.pop(pid, None)            # the (never run) runner would release it
    fresh = client.post(f"/api/studio/projects/{pid}/plan").json()["job_id"]
    assert fresh and fresh != first_job
    started.pop().close()
    studio_tasks.PLANS_IN_FLIGHT.pop(pid, None)
    assert client.post("/api/studio/projects/nope/plan").status_code == 404


def test_planning_picks_a_concrete_library_track_for_a_bed_that_is_on(fakes, monkeypatch):
    """A new project's music is on — without a concrete track the preview is
    silent and the render would drop the music."""
    from pathlib import Path

    from backend.services import music_service

    async def pick(genre="lofi", duration=60, track_filename=None, **_):
        return Path(f"/music/{genre}_calm_01.mp3")
    monkeypatch.setattr(music_service, "select_music", pick)
    music = plan(make())["settings"]["music"]
    # The genre follows the video (Look + scene moods), stored with the track.
    assert music["genre"] == "ambient"                      # every scene mood is "calm"
    assert music["track"] == "ambient_calm_01.mp3" and music["track_name"] == "calm 01"


def test_the_bed_follows_the_look_and_the_scene_moods():
    from backend.services.studio_music import suggested_genre
    assert suggested_genre("documentary", []) == "ambient"
    assert suggested_genre("cinematic", None) == "cinematic"
    assert suggested_genre("documentary", ["energetic", "energetic", "calm"]) == "upbeat"
    assert suggested_genre("vlog", ["energetic", "calm", "dark", "warm"]) == "lofi"   # no majority → the Look
    assert suggested_genre("unknown", []) == "lofi"


def test_planning_with_an_empty_music_library_leaves_the_bed_unpicked(fakes, monkeypatch):
    from backend.services import music_service

    async def nothing(genre="lofi", duration=60, track_filename=None, **_):
        return None
    monkeypatch.setattr(music_service, "select_music", nothing)
    assert plan(make())["settings"]["music"]["track"] is None


def test_finished_studio_jobs_tell_the_page_they_ended(fakes, monkeypatch, tmp_path):
    """create_job announces every job (job_started), so the Activity panel lists
    it. The plan and voice runners must send the matching job_complete, or the
    page shows them running until the socket reconnects."""
    from backend.core.ws_manager import ws_manager
    from backend.services import voice_take_service as vts

    monkeypatch.setattr(vts, "cache_dir", lambda: tmp_path / "voice")
    monkeypatch.setattr(vts, "probe_audio_duration", lambda _p: 1.5)

    async def synth(text, spec, out):
        out.write_bytes(b"ID3")

    monkeypatch.setattr(vts, "_synthesise", synth)
    sent = []

    async def send(message, user_id="local"):
        sent.append(message)
    monkeypatch.setattr(ws_manager, "send", send)
    plan(make(), first_draft=True)
    done = {m["job_type"]: m for m in sent if m.get("type") == "job_complete"}
    assert {"studio_plan", "studio_voice"} <= set(done)
    assert done["studio_plan"]["result"]["status"] == "success" and done["studio_plan"]["result"]["project_id"]
    assert not [m for m in sent if m.get("type") == "job_failed"]
