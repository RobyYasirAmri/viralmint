# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Every Library tile that can show a picture shows one.

A tile without a poster drew a tinted plate. That was right for audio and text,
and wrong for a video the user owns that simply had no stored thumbnail: an
import, a download whose platform served none, a render whose thumbnail step
failed, and every tool output (nothing in the tool pipeline makes one). In dark
mode the plate read as a black box. These pin:

  1. which URL each media / store asks for its picture (and the grid width)
  2. a generated video or download without a thumbnail gets a frame poster
  3. the poster endpoint resolves only what the index lists, inside STORAGE_ROOT
  4. the single-row fast path agrees with the index for every omission rule
  5. a short clip retries at frame 0; a broken file fails once, not per render
  6. a poster request writes no DB row (a read must not mutate)
  7. deleting the item removes its cached posters
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import select

PREFIX = "poster-probe-"


async def _session():
    from backend.database import AsyncSessionLocal, init_db
    await init_db()
    return AsyncSessionLocal()


def _scratch() -> Path:
    from backend.config import settings
    d = settings.STORAGE_ROOT / "tools" / "out" / "poster-probe"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _real_file(path: Path, body: bytes = b"x" * 64) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


def _ffmpeg() -> str | None:
    bundled = Path.home() / ".viralmint" / "bin" / "ffmpeg"
    return str(bundled) if bundled.is_file() else shutil.which("ffmpeg")


def _make_mp4(path: Path, seconds: float = 3.0) -> Path:
    ff = _ffmpeg()
    if not ff:
        pytest.skip("ffmpeg not available")
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ff, "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", f"testsrc=size=1280x720:rate=10:duration={seconds}",
         "-pix_fmt", "yuv420p", str(path)],
        check=True, timeout=60,
    )
    return path


async def _cleanup(db):
    from backend.models.downloaded_video import DownloadedVideo
    from backend.models.generated_video import GeneratedVideo
    from backend.models.job import Job
    for Model in (Job, GeneratedVideo, DownloadedVideo):
        rows = (await db.execute(select(Model).where(Model.id.startswith(PREFIX)))).scalars().all()
        for r in rows:
            await db.delete(r)
    await db.commit()
    shutil.rmtree(_scratch(), ignore_errors=True)
    from backend.config import settings
    for f in settings.THUMBNAILS_DIR.glob(f"libposter_*{PREFIX}*"):
        f.unlink(missing_ok=True)


def _job(job_id, job_type, file_path, status="success", **out_extra):
    from backend.models.job import Job
    return Job(id=job_id, job_type=job_type, status=status,
               output_json=json.dumps({"file": str(file_path), **out_extra}),
               created_at=datetime.utcnow())


def _by_key(items, key):
    return next((i for i in items if i["key"] == key), None)


# ── 1 + 2: which door each tile knocks on ───────────────────────────────────

async def test_thumb_url_per_media_and_store(tmp_path):
    from backend.models.downloaded_video import DownloadedVideo
    from backend.models.generated_video import GeneratedVideo
    from backend.services import library_index
    from backend.services.thumb_scale import DEFAULT_WIDTH

    s = _scratch()
    db = await _session()
    try:
        db.add(_job(f"{PREFIX}img", "tool:gif", _real_file(s / "i.png")))
        db.add(_job(f"{PREFIX}gif", "tool:gif", _real_file(s / "g.gif")))
        db.add(_job(f"{PREFIX}anim", "tool:gif", _real_file(s / "a.webp")))
        db.add(_job(f"{PREFIX}imgfar", "tool:gif", _real_file(tmp_path / "far.png")))
        db.add(_job(f"{PREFIX}vid", "tool:captions", _real_file(s / "v.mp4")))
        db.add(_job(f"{PREFIX}vidfar", "tool:captions", _real_file(tmp_path / "far.mp4")))
        db.add(_job(f"{PREFIX}aud", "tool:voiceover", _real_file(s / "a.mp3")))
        # A download / render WITH a stored thumbnail keeps it, at grid width.
        thumb = _real_file(s / "t.jpg")
        db.add(DownloadedVideo(id=f"{PREFIX}dl-thumb", platform="youtube", title="t",
                               video_path=str(_real_file(s / "d1.mp4")),
                               thumbnail_path=str(thumb)))
        db.add(GeneratedVideo(id=f"{PREFIX}gv-thumb", source_type="smart_video",
                              video_path=str(_real_file(s / "g1.mp4")),
                              thumbnail_path=str(thumb), aspect_ratio="9:16", status="ready"))
        # WITHOUT one — the black-box case — they get a frame poster.
        db.add(DownloadedVideo(id=f"{PREFIX}dl-bare", platform="import", title="b",
                               video_path=str(_real_file(s / "d2.mp4"))))
        db.add(GeneratedVideo(id=f"{PREFIX}gv-bare", source_type="clip_extraction",
                              video_path=str(_real_file(s / "g2.mp4")),
                              aspect_ratio="9:16", status="ready"))
        # Audio-only download: no frame to show, waveform tile.
        db.add(DownloadedVideo(id=f"{PREFIX}dl-audio", platform="import", title="a",
                               audio_path=str(_real_file(s / "d3.mp3"))))
        # Outside STORAGE_ROOT: the endpoint couldn't read it, so no URL.
        db.add(DownloadedVideo(id=f"{PREFIX}dl-far", platform="import", title="f",
                               video_path=str(_real_file(tmp_path / "d4.mp4"))))
        await db.commit()

        items = await library_index.gather(db)
        url = lambda k: (_by_key(items, k) or {}).get("thumb_url")  # noqa: E731

        for probe in ("img", "gif", "vid"):
            u = url(f"job:{PREFIX}{probe}")
            assert u.startswith(f"/api/library/poster?key=job:{PREFIX}{probe}"), probe
            assert f"w={DEFAULT_WIDTH}" in u, probe
        assert url(f"job:{PREFIX}anim") == f"/api/library/asset/{PREFIX}anim"
        assert url(f"job:{PREFIX}imgfar") == f"/api/library/asset/{PREFIX}imgfar"
        assert url(f"job:{PREFIX}vidfar") is None
        assert url(f"job:{PREFIX}aud") is None

        assert url(f"dl:{PREFIX}dl-thumb").startswith(f"/api/downloaded/{PREFIX}dl-thumb/thumbnail?v=")
        assert f"w={DEFAULT_WIDTH}" in url(f"dl:{PREFIX}dl-thumb")
        assert url(f"gv:{PREFIX}gv-thumb").startswith(f"/api/videos/{PREFIX}gv-thumb/thumbnail?v=")
        assert f"w={DEFAULT_WIDTH}" in url(f"gv:{PREFIX}gv-thumb")

        assert url(f"dl:{PREFIX}dl-bare") == f"/api/library/poster?key=dl:{PREFIX}dl-bare&w={DEFAULT_WIDTH}"
        assert url(f"gv:{PREFIX}gv-bare") == f"/api/library/poster?key=gv:{PREFIX}gv-bare&w={DEFAULT_WIDTH}"
        assert url(f"dl:{PREFIX}dl-audio") is None
        assert url(f"dl:{PREFIX}dl-far") is None
    finally:
        await _cleanup(db)
        await db.close()


# ── 3 + 4: what the poster endpoint may read ────────────────────────────────

async def test_poster_source_resolves_only_indexed_media_inside_storage(tmp_path):
    from backend.models.downloaded_video import DownloadedVideo
    from backend.models.generated_video import GeneratedVideo
    from backend.services import library_index

    s = _scratch()
    db = await _session()
    try:
        db.add(_job(f"{PREFIX}v", "tool:captions", _real_file(s / "v.mp4")))
        db.add(_job(f"{PREFIX}a", "tool:voiceover", _real_file(s / "a.mp3")))
        db.add(_job(f"{PREFIX}far", "tool:captions", _real_file(tmp_path / "far.mp4")))
        db.add(DownloadedVideo(id=f"{PREFIX}dl", platform="import", title="d",
                               video_path=str(_real_file(s / "d.mp4"))))
        db.add(DownloadedVideo(id=f"{PREFIX}dla", platform="import", title="d",
                               audio_path=str(_real_file(s / "d.mp3"))))
        db.add(GeneratedVideo(id=f"{PREFIX}gv", source_type="smart_video",
                              video_path=str(_real_file(s / "g.mp4")),
                              aspect_ratio="9:16", status="ready"))
        db.add(GeneratedVideo(id=f"{PREFIX}gvgone", source_type="smart_video",
                              video_path=str(s / "never-written.mp4"),
                              aspect_ratio="9:16", status="ready"))
        await db.commit()

        src = lambda k: library_index.poster_source(db, k)  # noqa: E731
        assert (await src(f"job:{PREFIX}v")).name == "v.mp4"
        assert await src(f"job:{PREFIX}a") is None, "audio has no poster"
        assert await src(f"job:{PREFIX}far") is None, "outside STORAGE_ROOT"
        assert (await src(f"dl:{PREFIX}dl")).name == "d.mp4"
        assert await src(f"dl:{PREFIX}dla") is None, "an audio-only download has no frame"
        assert (await src(f"gv:{PREFIX}gv")).name == "g.mp4"
        assert await src(f"gv:{PREFIX}gvgone") is None
        assert await src("job:does-not-exist") is None
        assert await src("trk:../../etc/passwd") is None
        assert await src("dl:") is None
        assert library_index.poster_cache_stem("dl:../../x") is None
    finally:
        await _cleanup(db)
        await db.close()


async def test_single_row_resolution_agrees_with_the_index():
    """The poster endpoint answers for ONE row via `_job_item` rather than
    projecting the whole library per request. That speed must not open a door:
    for every omission rule, "not in the index" and "does not resolve" agree."""
    from backend.services import library_index

    s = _scratch()
    db = await _session()
    try:
        db.add(_job(f"{PREFIX}ok", "tool:reframe", _real_file(s / "ok.mp4")))
        db.add(_job(f"{PREFIX}running", "tool:reframe", _real_file(s / "r.mp4"), status="running"))
        db.add(_job(f"{PREFIX}failed", "tool:reframe", _real_file(s / "f.mp4"), status="failed"))
        db.add(_job(f"{PREFIX}dupe", "tool:reframe", _real_file(s / "d.mp4"),
                    generated_video_id="gv-somewhere"))
        db.add(_job(f"{PREFIX}unclassified", "scout", _real_file(s / "s.mp4")))
        db.add(_job(f"{PREFIX}missing", "tool:reframe", s / "never-written.mp4"))
        await db.commit()

        listed = {it["key"] for it in await library_index.gather(db)}
        for probe in ("ok", "running", "failed", "dupe", "unclassified", "missing"):
            key = f"job:{PREFIX}{probe}"
            in_index = key in listed
            assert (await library_index.resolve_job_video(db, f"{PREFIX}{probe}") is not None) == in_index, probe
            assert (await library_index.poster_source(db, key) is not None) == in_index, probe
        assert f"job:{PREFIX}ok" in listed
    finally:
        await _cleanup(db)
        await db.close()


# ── 5 + 6: the endpoint itself ──────────────────────────────────────────────

async def test_a_download_without_a_thumbnail_gets_a_real_frame_and_no_db_write():
    """The case the owner saw: an imported video with no thumbnail. A real
    file, real ffmpeg — the response must be a decodable JPEG at grid width,
    and the row must be left exactly as it was."""
    from PIL import Image

    from backend.api.library import get_poster
    from backend.models.downloaded_video import DownloadedVideo
    from backend.services.thumb_scale import DEFAULT_WIDTH

    s = _scratch()
    mp4 = _make_mp4(s / "real.mp4")
    db = await _session()
    try:
        db.add(DownloadedVideo(id=f"{PREFIX}real", platform="import", title="r",
                               video_path=str(mp4)))
        await db.commit()

        resp = await get_poster(key=f"dl:{PREFIX}real", w=DEFAULT_WIDTH, v=None, db=db)
        assert resp.media_type == "image/jpeg"
        assert "immutable" in resp.headers["cache-control"]
        with Image.open(resp.path) as im:
            im.load()
            assert im.width == DEFAULT_WIDTH

        db.expire_all()
        row = await db.get(DownloadedVideo, f"{PREFIX}real")
        assert row.thumbnail_path is None, "a poster read must not write the row"
    finally:
        await _cleanup(db)
        await db.close()


async def test_a_short_clip_retries_at_the_first_frame(monkeypatch):
    """A clip SHORTER than the 2s seek yields zero frames; retry at 0 before
    giving up."""
    from backend.api import library as library_api

    s = _scratch()
    calls: list[float] = []

    async def fake_extract(video_path, timestamp, output_path, quality=2, scale_width=None):
        calls.append(timestamp)
        if timestamp >= library_api.POSTER_SEEK_SECONDS:
            return None
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"\xff\xd8\xff")
        return output_path

    monkeypatch.setattr("backend.services.ffmpeg_service.extract_frame_at", fake_extract)
    db = await _session()
    try:
        db.add(_job(f"{PREFIX}short", "tool:trim", _real_file(s / "short.mp4")))
        await db.commit()
        resp = await library_api.get_poster(key=f"job:{PREFIX}short", w=None, v=None, db=db)
        assert calls == [2.0, 0.0]
        assert Path(resp.path).is_file()
    finally:
        await _cleanup(db)
        await db.close()


async def test_a_broken_file_fails_once_until_it_changes(monkeypatch):
    """A file ffmpeg cannot read must not cost two ffmpeg runs on every grid
    render. The failure is remembered — until the source is replaced."""
    from fastapi import HTTPException

    from backend.api import library as library_api

    s = _scratch()
    calls: list[float] = []

    async def failing_extract(video_path, timestamp, output_path, quality=2, scale_width=None):
        calls.append(timestamp)
        return None

    monkeypatch.setattr("backend.services.ffmpeg_service.extract_frame_at", failing_extract)
    db = await _session()
    src = _real_file(s / "broken.mp4", b"not a video")
    try:
        db.add(_job(f"{PREFIX}broken", "tool:trim", src))
        await db.commit()
        for _ in range(3):
            with pytest.raises(HTTPException) as exc:
                await library_api.get_poster(key=f"job:{PREFIX}broken", w=None, v=None, db=db)
            assert exc.value.status_code == 404
        assert calls == [2.0, 0.0], "a remembered failure was retried"

        # A replaced source gets a fresh attempt.
        future = src.stat().st_mtime + 10
        os.utime(src, (future, future))
        with pytest.raises(HTTPException):
            await library_api.get_poster(key=f"job:{PREFIX}broken", w=None, v=None, db=db)
        assert calls == [2.0, 0.0, 2.0, 0.0]
    finally:
        await _cleanup(db)
        await db.close()


# ── 7: a delete takes its posters with it ───────────────────────────────────

def test_drop_poster_cache_removes_frame_scaled_copies_and_marker():
    from backend.config import settings
    from backend.services import library_index

    base = settings.THUMBNAILS_DIR
    base.mkdir(parents=True, exist_ok=True)
    stem = library_index.poster_cache_stem(f"dl:{PREFIX}gone")
    made = [base / f"{stem}.jpg", base / f"{stem}.w400.jpg", base / f"{stem}.fail"]
    for f in made:
        f.write_bytes(b"x")
    keep = base / f"libposter_{PREFIX}other.jpg"
    keep.write_bytes(b"x")
    try:
        library_index.drop_poster_cache(f"dl:{PREFIX}gone")
        assert not any(f.exists() for f in made)
        assert keep.exists(), "dropped a different item's poster"
    finally:
        keep.unlink(missing_ok=True)


async def test_deleting_a_download_drops_its_poster():
    from backend.api.downloaded import delete_downloaded
    from backend.config import settings
    from backend.models.downloaded_video import DownloadedVideo
    from backend.services import library_index

    s = _scratch()
    db = await _session()
    stem = library_index.poster_cache_stem(f"dl:{PREFIX}del")
    poster = settings.THUMBNAILS_DIR / f"{stem}.jpg"
    try:
        db.add(DownloadedVideo(id=f"{PREFIX}del", platform="import", title="x",
                               video_path=str(_real_file(s / "del.mp4"))))
        await db.commit()
        poster.parent.mkdir(parents=True, exist_ok=True)
        poster.write_bytes(b"x")
        await delete_downloaded(f"{PREFIX}del")
        assert not poster.exists()
    finally:
        await _cleanup(db)
        await db.close()


async def test_a_known_failure_drops_the_url_until_the_file_changes():
    """Once the endpoint has failed on a file, the index stops emitting its
    poster URL (each one was a 404 + a console error per page load) and flags
    the item so the tile says "Preview unavailable" without asking. A replaced
    file gets its URL back."""
    from backend.config import settings
    from backend.services import library_index

    s = _scratch()
    src = _real_file(s / "bad.mp4", b"not a video")
    db = await _session()
    try:
        db.add(_job(f"{PREFIX}bad", "tool:trim", src))
        await db.commit()
        key = f"job:{PREFIX}bad"

        item = _by_key(await library_index.gather(db), key)
        assert item["thumb_url"] and not item["poster_failed"]

        marker = settings.THUMBNAILS_DIR / f"{library_index.poster_cache_stem(key)}.fail"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        os.utime(marker, (src.stat().st_mtime + 1,) * 2)
        item = _by_key(await library_index.gather(db), key)
        assert item["thumb_url"] is None and item["poster_failed"] is True

        os.utime(src, (marker.stat().st_mtime + 10,) * 2)
        item = _by_key(await library_index.gather(db), key)
        assert item["thumb_url"] and not item["poster_failed"]
    finally:
        await _cleanup(db)
        await db.close()
