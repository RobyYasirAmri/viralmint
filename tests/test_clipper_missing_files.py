# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""A Clipper source (or clip) whose FILE is gone is its own, typed answer.

Reported: "I selected a clip but it cannot be played." The source row pointed
at a file that no longer existed, and every bench read — stream, filmstrip,
frame, thumbnail — answered the same bare 404 as "no such video", so the page
could not tell the two apart and showed a silent, dead player.

Pinned here:
  * the list says `video_exists` / `thumbnail_available`, so the rail can file
    the row under "File missing" before anything is requested;
  * every read answers 410 + `X-ViralMint-Error: source_file_missing` (POSTs
    keep their 400, with the same marker), while an unknown id stays a plain
    404 — the two are distinguishable without parsing prose;
  * a read never deletes the row (the user decides);
  * the bulk delete / ZIP export the Clipper's filmstrip uses.
"""
import asyncio
import io
import zipfile
from uuid import uuid4

import pytest

MARK = "x-viralmint-error"


@pytest.fixture(scope="module")
def client():
    from starlette.testclient import TestClient

    from backend.main import app
    with TestClient(app) as c:
        yield c


async def _seed_source(video_path, **kw):
    from backend.database import AsyncSessionLocal
    from backend.models.downloaded_video import DownloadedVideo
    async with AsyncSessionLocal() as db:
        v = DownloadedVideo(user_id="local", title=kw.pop("title", "src"),
                            platform="youtube", video_path=str(video_path) if video_path else None,
                            duration_seconds=kw.pop("duration", 60.0), **kw)
        db.add(v)
        await db.commit()
        return v.id


async def _row_exists(model, row_id):
    from sqlalchemy import select
    from backend.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(model).where(model.id == row_id))).scalar_one_or_none() is not None


async def _seed_clip(video_path, title="clip", thumb=None):
    from backend.database import AsyncSessionLocal
    from backend.models.generated_video import GeneratedVideo
    async with AsyncSessionLocal() as db:
        v = GeneratedVideo(user_id="local", title=title, status="ready",
                           source_type="clip_extraction", video_path=str(video_path),
                           thumbnail_path=str(thumb) if thumb else None)
        db.add(v)
        await db.commit()
        return v.id


@pytest.fixture
def gone_source(tmp_path):
    return asyncio.run(_seed_source(tmp_path / "vanished.mp4"))


@pytest.fixture
def stored_file():
    from backend.config import settings
    settings.VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    p = settings.VIDEOS_DIR / f"present-{uuid4().hex[:8]}.mp4"
    p.write_bytes(b"\x00" * 2048)
    yield p
    p.unlink(missing_ok=True)


# ── The list and the detail say it up front ───────────────────────────────

def test_the_list_flags_a_source_whose_video_is_gone(client, gone_source, stored_file):
    present = asyncio.run(_seed_source(stored_file))
    rows = {r["id"]: r for r in client.get("/api/downloaded", params={"limit": 200}).json()["videos"]}
    assert rows[gone_source]["video_exists"] is False
    assert rows[gone_source]["thumbnail_available"] is False
    assert rows[present]["video_exists"] is True
    assert rows[present]["thumbnail_available"] is True


def test_the_detail_says_whether_the_video_is_on_disk(client, gone_source):
    assert client.get(f"/api/downloaded/{gone_source}").json()["video_exists"] is False


# ── Every bench read: 410 + the marker, never the "no such row" 404 ───────

@pytest.mark.parametrize("path", [
    "stream", "filmstrip?n=20&h=64", "frame?t=3", "thumbnail",
])
def test_a_missing_file_is_a_typed_410_on_every_bench_read(client, gone_source, path):
    r = client.get(f"/api/downloaded/{gone_source}/{path}")
    assert r.status_code == 410, r.text
    assert r.headers.get(MARK) == "source_file_missing"
    # Never cached: a file put back must not keep reading as missing.
    assert r.headers.get("cache-control") == "no-store"


@pytest.mark.parametrize("path", ["stream", "filmstrip", "frame?t=1", "thumbnail"])
def test_an_unknown_source_is_still_a_plain_404(client, path):
    r = client.get(f"/api/downloaded/no-such-row/{path}")
    assert r.status_code == 404
    assert MARK not in r.headers


def test_a_row_with_no_file_path_at_all_is_typed_too(client):
    vid = asyncio.run(_seed_source(None))
    r = client.get(f"/api/downloaded/{vid}/stream")
    assert r.status_code == 410 and r.headers.get(MARK) == "source_file_missing"


@pytest.mark.parametrize("route,body", [
    ("extract-clips", {"mode": "manual", "time_ranges": [{"start": 0, "end": 20}]}),
    ("suggest-clips", {}),
])
def test_the_posts_keep_their_400_but_carry_the_marker(client, gone_source, route, body):
    r = client.post(f"/api/downloaded/{gone_source}/{route}", json=body)
    assert r.status_code == 400
    assert r.headers.get(MARK) == "source_file_missing"
    assert "not found on disk" in r.json()["detail"]


def test_reads_never_delete_the_row(client, gone_source):
    """A read must not mutate: the user removes it, from the File-missing list."""
    from backend.models.downloaded_video import DownloadedVideo
    for path in ("stream", "filmstrip", "frame?t=1", "thumbnail", "segments"):
        client.get(f"/api/downloaded/{gone_source}/{path}")
    client.get("/api/downloaded")
    assert asyncio.run(_row_exists(DownloadedVideo, gone_source))
    # …and the user CAN remove it, file or no file.
    assert client.delete(f"/api/downloaded/{gone_source}").status_code == 200
    assert not asyncio.run(_row_exists(DownloadedVideo, gone_source))


def test_the_bench_stream_never_falls_back_to_audio(client, tmp_path, stored_file):
    """The Library plays an audio-only row through this route, so the default
    keeps the mp3 fallback; the bench asks ?require=video and gets the typed
    410 instead of sound over a black frame."""
    vid = asyncio.run(_seed_source(tmp_path / "gone.mp4", audio_path=str(stored_file)))
    assert client.get(f"/api/downloaded/{vid}/stream", headers={"Range": "bytes=0-0"}).status_code == 206
    r = client.get(f"/api/downloaded/{vid}/stream?require=video")
    assert r.status_code == 410
    assert r.headers.get(MARK) == "source_file_missing"


def test_a_file_outside_the_data_dir_says_so(client, tmp_path):
    """A row from another data dir has a REAL file the stream refuses to serve —
    the player has to be able to say that, not sit black."""
    outside = tmp_path / "elsewhere.mp4"
    outside.write_bytes(b"\x00" * 64)
    vid = asyncio.run(_seed_source(outside))
    r = client.get(f"/api/downloaded/{vid}/stream")
    assert r.status_code == 403
    assert r.headers.get(MARK) == "source_outside_storage"


def test_a_present_source_still_streams(client, stored_file):
    vid = asyncio.run(_seed_source(stored_file))
    r = client.get(f"/api/downloaded/{vid}/stream", headers={"Range": "bytes=0-0"})
    assert r.status_code == 206


# ── Clips (generated rows) ────────────────────────────────────────────────

def test_a_clip_whose_file_is_gone_is_a_typed_410(client, stored_file):
    from backend.config import settings
    gone = settings.GENERATED_DIR / f"gone-{uuid4().hex[:8]}.mp4"
    cid = asyncio.run(_seed_clip(gone))
    r = client.get(f"/api/videos/{cid}/stream")
    assert r.status_code == 410
    assert r.headers.get(MARK) == "clip_file_missing"
    assert r.headers.get("cache-control") == "no-store"


def _clip_file(name, data=b"\x00" * 128):
    from backend.config import settings
    settings.GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    p = settings.GENERATED_DIR / f"{name}-{uuid4().hex[:8]}.mp4"
    p.write_bytes(data)
    return p


def test_bulk_delete_removes_rows_and_every_file_they_own(client):
    from backend.models.generated_video import GeneratedVideo
    a, b = _clip_file("a"), _clip_file("b")
    thumb = _clip_file("t")
    ida = asyncio.run(_seed_clip(a, thumb=thumb))
    idb = asyncio.run(_seed_clip(b))
    r = client.post("/api/videos/bulk-delete", json={"clip_ids": [ida, idb, "no-such-clip"]})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "deleted": 2}
    assert not a.exists() and not b.exists() and not thumb.exists()
    assert not asyncio.run(_row_exists(GeneratedVideo, ida))


@pytest.mark.parametrize("body", [{}, {"clip_ids": []}, {"clip_ids": "x"}, {"clip_ids": [1, 2]}])
def test_bulk_delete_rejects_a_malformed_body(client, body):
    assert client.post("/api/videos/bulk-delete", json=body).status_code == 400


def test_bulk_delete_is_capped(client):
    ids = [f"id-{i}" for i in range(201)]
    assert client.post("/api/videos/bulk-delete", json={"clip_ids": ids}).status_code == 400


def test_bulk_export_zips_the_clips_and_dedupes_titles(client):
    a, b = _clip_file("a", b"A" * 10), _clip_file("b", b"B" * 10)
    ida = asyncio.run(_seed_clip(a, title="Same / title"))
    idb = asyncio.run(_seed_clip(b, title="Same / title"))
    missing = asyncio.run(_seed_clip(a.with_name("never-written.mp4")))
    r = client.post("/api/videos/bulk-export", json={"video_ids": [ida, idb, missing]})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    names = sorted(zipfile.ZipFile(io.BytesIO(r.content)).namelist())
    # "/" dropped, whitespace collapsed, the collision suffixed — never overwritten.
    assert names == ["Same title.mp4", "Same title_2.mp4"]
    assert 'viralmint-clips-2.zip' in r.headers["content-disposition"]


def test_bulk_export_404s_when_nothing_is_on_disk(client):
    cid = asyncio.run(_seed_clip(_clip_file("x").with_name("absent.mp4")))
    assert client.post("/api/videos/bulk-export", json={"video_ids": [cid]}).status_code == 404


def test_bulk_export_is_capped(client):
    ids = [f"id-{i}" for i in range(51)]
    assert client.post("/api/videos/bulk-export", json={"video_ids": ids}).status_code == 400
