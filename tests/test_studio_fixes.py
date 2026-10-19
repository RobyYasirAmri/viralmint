# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Smart Video Studio fixes, pinned.

  * the render keeps the source lineage (source_downloaded_video_id / scout / niche)
  * a cancelled studio job gets its `completed_at`
  * an unknown caption style is refused at every writer (create, edit, the /generate/stock adapter)
"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "Most people water their plants at the wrong time. Morning watering lets roots drink first. Try it for a week."


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api import generate, studio
    from backend.database import init_db

    asyncio.run(init_db())
    app = FastAPI()
    app.include_router(studio.router, prefix="/api")
    app.include_router(generate.router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def quiet(monkeypatch):
    from backend.core import task_runner
    dispatched = []

    def capture(coro):
        dispatched.append(coro)
        coro.close()

    monkeypatch.setattr(task_runner, "dispatch_light", capture)
    monkeypatch.setattr(task_runner, "dispatch", capture)
    return dispatched


def _run(coro):
    return asyncio.run(coro)


# ── lineage ─────────────────────────────────────────────────────────────────

def test_source_lineage_reads_the_source_and_its_scout_niche():
    from backend.database import AsyncSessionLocal, init_db
    from backend.models.downloaded_video import DownloadedVideo
    from backend.models.scout_result import ScoutResult
    from backend.services.studio_render import source_lineage

    async def seed():
        await init_db()
        sid, did = str(uuid.uuid4()), str(uuid.uuid4())
        async with AsyncSessionLocal() as db:
            db.add(ScoutResult(id=sid, niche="houseplants", platform="youtube", video_id="abc", video_url="https://y/abc"))
            db.add(DownloadedVideo(id=did, title="src", scout_result_id=sid))
            await db.commit()
        return sid, did

    sid, did = _run(seed())
    out = _run(source_lineage(did))
    assert out == {"source_downloaded_video_id": did, "source_scout_result_id": sid, "niche": "houseplants"}
    empty = {"source_downloaded_video_id": None, "source_scout_result_id": None, "niche": None}
    assert _run(source_lineage(None)) == empty
    assert _run(source_lineage("   ")) == empty
    assert _run(source_lineage("nope"))["source_downloaded_video_id"] is None


def test_source_lineage_without_a_scout_result_has_no_niche():
    from backend.database import AsyncSessionLocal, init_db
    from backend.models.downloaded_video import DownloadedVideo
    from backend.services.studio_render import source_lineage

    async def seed():
        await init_db()
        did = str(uuid.uuid4())
        async with AsyncSessionLocal() as db:
            db.add(DownloadedVideo(id=did, title="an upload"))
            await db.commit()
        return did

    did = _run(seed())
    assert _run(source_lineage(did)) == {"source_downloaded_video_id": did, "source_scout_result_id": None,
                                         "niche": None}


def test_render_writes_the_lineage_columns():
    src = (ROOT / "backend/services/studio_render.py").read_text()
    assert "source_downloaded_video_id=lineage[" in src and "source_scout_result_id=lineage[" in src
    assert 'source_lineage((doc.get("input") or {}).get("source_id"))' in src


def test_create_project_records_the_source_id(client, quiet):
    r = client.post("/api/studio/projects", json={"start": {"script": SCRIPT, "source_id": "dl-abc_1"}})
    assert r.status_code == 200, r.text
    assert r.json()["project"]["doc"]["input"]["source_id"] == "dl-abc_1"
    r = client.post("/api/studio/projects", json={"start": {"script": SCRIPT, "source_id": "../etc"}})
    assert r.status_code == 422


# ── cancelled jobs get an end ───────────────────────────────────────────────

def test_stamp_cancelled_sets_completed_at_and_keeps_cancelled():
    from sqlalchemy import select

    from backend.agents.job_helper import create_job
    from backend.core.tasks.studio import _stamp_cancelled
    from backend.database import AsyncSessionLocal, init_db
    from backend.models.job import Job

    async def go():
        await init_db()
        job = await create_job("generate", "local", {"project_id": "p"}, title="t")
        async with AsyncSessionLocal() as db:            # what DELETE /api/jobs/{id} does
            row = (await db.execute(select(Job).where(Job.id == job.id))).scalar_one()
            row.status = "cancelled"
            await db.commit()
        await _stamp_cancelled(job.id, step="Cancelled after 1 of 3")
        async with AsyncSessionLocal() as db:
            return (await db.execute(select(Job).where(Job.id == job.id))).scalar_one()

    row = _run(go())
    assert row.status == "cancelled" and row.completed_at is not None and row.current_step == "Cancelled after 1 of 3"


def test_render_and_voice_cancel_paths_stamp_the_row():
    src = (ROOT / "backend/core/tasks/studio.py").read_text()
    assert src.count("await _stamp_cancelled(job_id") >= 2


def test_a_cancelled_voice_job_is_stamped_and_settles_its_scenes(client, quiet, monkeypatch, tmp_path):
    """Driven, not just grepped: the voice runner sees the cancel, records
    nothing more, stamps the row and leaves no scene spinning."""
    from sqlalchemy import select

    from backend.agents.job_helper import update_job_status
    from backend.core.tasks import studio as studio_tasks
    from backend.database import AsyncSessionLocal
    from backend.models.job import Job
    from backend.services import voice_take_service as vts

    monkeypatch.setattr(vts, "cache_dir", lambda: tmp_path / "voice")
    calls = []

    async def synth(text, spec, out):
        calls.append(text)
        out.write_bytes(b"ID3")
    monkeypatch.setattr(vts, "_synthesise", synth)

    p = client.post("/api/studio/projects", json={"start": {"script": SCRIPT}}).json()["project"]
    r = client.post(f"/api/studio/projects/{p['id']}/voice", json={"scene_uids": "all"})
    job_id = r.json()["job_id"]
    uids = [s["uid"] for s in p["doc"]["scenes"]]
    _run(update_job_status(job_id, "cancelled"))
    _run(studio_tasks.run_studio_voice(job_id, p["id"], uids))

    async def row():
        async with AsyncSessionLocal() as db:
            return (await db.execute(select(Job).where(Job.id == job_id))).scalar_one()
    job = _run(row())
    assert job.status == "cancelled" and job.completed_at is not None and job.current_step.startswith("Cancelled")
    assert calls == []
    doc = client.get(f"/api/studio/projects/{p['id']}").json()["project"]["doc"]
    assert all(s["voice"]["state"] != "generating" for s in doc["scenes"])


# ── caption styles are validated at every writer ────────────────────────────

def test_studio_api_refuses_an_unknown_caption_style(client, quiet):
    r = client.post("/api/studio/projects", json={"start": {"script": SCRIPT}, "settings": {"captions": {"style": "nope-style"}}})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid"
    p = client.post("/api/studio/projects", json={"start": {"script": SCRIPT}, "settings": {"captions": {"style": "bold"}}}).json()["project"]
    assert p["doc"]["settings"]["captions"]["style"] == "bold"
    bad = client.patch(f"/api/studio/projects/{p['id']}", json={"ops": [{"op": "set_setting", "path": "captions.style", "value": "nope-style"}]})
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "invalid_edit"
    off = client.patch(f"/api/studio/projects/{p['id']}", json={"ops": [{"op": "set_setting", "path": "captions.style", "value": "none"}]})
    assert off.status_code == 400 and "captions.enabled" in off.json()["detail"]["message"]
    ok = client.patch(f"/api/studio/projects/{p['id']}", json={"ops": [{"op": "set_setting", "path": "captions.style", "value": "karaoke"}]})
    assert ok.status_code == 200 and ok.json()["project"]["doc"]["settings"]["captions"]["style"] == "karaoke"


def test_studio_api_accepts_a_saved_user_preset(client, quiet):
    from backend.database import AsyncSessionLocal
    from backend.models.caption_style import CaptionStyle

    sid = f"cs_mine_{uuid.uuid4().hex[:6]}"

    async def seed():
        async with AsyncSessionLocal() as db:
            db.add(CaptionStyle(id=sid, name="Mine"))
            await db.commit()
    _run(seed())
    r = client.post("/api/studio/projects", json={"start": {"script": SCRIPT}, "settings": {"captions": {"style": sid}}})
    assert r.status_code == 200, r.text
    assert r.json()["project"]["doc"]["settings"]["captions"]["style"] == sid


def _release(job_id, project_id):
    """The adapter claimed the project and its job never ran here: end both."""
    from backend.agents.job_helper import update_job_status
    from backend.services import studio_store as store
    _run(update_job_status(job_id, "cancelled"))
    store.release_render(project_id)
    _run(store.finish_render(project_id))


def test_generate_stock_refuses_an_unknown_caption_style(client, quiet):
    """/generate/stock is the Studio adapter: an unknown style is a 400 before
    any project or job exists; "none" there is the legacy captions-off switch."""
    import json

    from backend.services import studio_store as store

    body = {"script": SCRIPT, "caption_enabled": True, "caption_style": "nope-style", "music_enabled": False}
    r = client.post("/api/generate/stock", json=body)
    assert r.status_code == 400 and "nope-style" in str(r.json()["detail"])
    assert not quiet                                          # nothing dispatched

    off = client.post("/api/generate/stock", json={**body, "caption_style": "none"})
    assert off.status_code == 200, off.text
    pid = off.json()["project_id"]
    assert off.json()["job_id"] and len(quiet) == 1
    doc = json.loads(_run(store.get_project(pid)).doc_json)
    assert doc["settings"]["captions"] == {"enabled": False, "style": "viral", "hook": True, "hook_text": None}
    _release(off.json()["job_id"], pid)

    ok = client.post("/api/generate/stock", json={**body, "caption_style": "bold"})
    assert ok.status_code == 200, ok.text
    doc = json.loads(_run(store.get_project(ok.json()["project_id"])).doc_json)
    assert doc["settings"]["captions"]["enabled"] is True and doc["settings"]["captions"]["style"] == "bold"
    _release(ok.json()["job_id"], ok.json()["project_id"])


def test_legacy_adapter_maps_none_to_captions_off_and_refuses_unknown(quiet):
    import json
    from types import SimpleNamespace

    from backend.core.exceptions import StudioDocError
    from backend.database import init_db
    from backend.services import studio_autofill, studio_store

    def body(style):
        return SimpleNamespace(script=SCRIPT, tts_provider="edge_tts", tts_voice=None, caption_enabled=True,
                               caption_style=style, music_enabled=False, music_genre="lofi",
                               transition_style="none", aspect_ratio="9:16", visual_style=None, source_id=None)

    async def go():
        await init_db()
        pid = await studio_autofill.create_from_legacy(body("none"))
        doc = json.loads((await studio_store.get_project(pid)).doc_json)
        assert doc["settings"]["captions"] == {"enabled": False, "style": "viral", "hook": True, "hook_text": None}
        with pytest.raises(StudioDocError):
            await studio_autofill.create_from_legacy(body("nope-style"))
    _run(go())
