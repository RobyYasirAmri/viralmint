# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""studio_media — stock candidates, previews and uploads.

No network: the stock searcher and the downloader are faked. Real ffmpeg makes
a one-second clip and a still so uploads probe and poster a genuine file.
"""
import asyncio
import shutil
import subprocess

import pytest

from backend.core.exceptions import StudioMediaError
from backend.services import studio_media as sm

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")


def tiny_mp4(path):
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=320x568:rate=24", "-t", "1",
                    "-pix_fmt", "yuv420p", str(path)], check=True, capture_output=True)
    return path


def tiny_png(path):
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1", str(path)],
                   check=True, capture_output=True)
    return path


PEXELS = {
    "source": "pexels", "id": 855564, "download_url": "https://videos.pexels.com/video-files/855564/hd.mp4",
    "preview_url": "https://videos.pexels.com/video-files/855564/sd.mp4",
    "thumbnail": "https://images.pexels.com/videos/855564/pic.jpg", "creator": "Anna", "duration": 12,
    "width": 1080, "height": 1920,
}


# ── hosts ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url,ok", [
    ("https://videos.pexels.com/video-files/1/x.mp4", True),
    ("http://videos.pexels.com/x.mp4", False),
    ("https://videos.pexels.com.evil.example/x.mp4", False),
    ("https://evil.example/videos.pexels.com/x.mp4", False),
    ("file:///etc/passwd", False),
    ("javascript:alert(1)", False),
    (None, False),
])
def test_only_stock_hosts_over_https(url, ok):
    assert sm.is_allowed_stock_url(url) is ok


# ── candidates ──────────────────────────────────────────────────────────────

def test_remembered_candidates_resolve_to_the_server_copy():
    cand = sm.candidate_from_result(PEXELS, "rainy street")
    sm.remember("p1", [cand])
    tampered = {**cand, "download_url": "https://videos.pexels.com/video-files/999/other.mp4"}
    resolved = sm.resolve_candidate_for("p1")(tampered)
    assert resolved["download_url"] == PEXELS["download_url"]
    assert resolved["license"] == "Pexels License"


def test_unremembered_candidates_must_look_like_stock():
    resolve = sm.resolve_candidate_for("fresh-after-restart")
    forged = {"provider": "pexels", "provider_id": "1", "download_url": "https://evil.example/x.mp4"}
    assert resolve(forged) is None
    assert resolve({**forged, "provider": "youtube", "download_url": PEXELS["download_url"]}) is None
    assert resolve({**forged, "provider_id": "../../x", "download_url": PEXELS["download_url"]}) is None
    ok = resolve({"provider": "pexels", "provider_id": "855564", "download_url": PEXELS["download_url"]})
    assert ok and ok["preview_url"] == PEXELS["download_url"]


def _fake_search(monkeypatch, seen):
    from backend.services import stock_video_service

    async def fake_search(q, **kw):
        seen.append((q, kw))
        return [PEXELS, {**PEXELS, "id": 7, "download_url": "https://evil.example/x.mp4"}]

    monkeypatch.setattr(sm, "pexels_key", lambda: "k")
    monkeypatch.setattr(stock_video_service, "search_stock_candidates", fake_search)


def test_search_remembers_results(monkeypatch):
    seen = []
    _fake_search(monkeypatch, seen)
    found = asyncio.run(sm.search_candidates("p2", "  rainy   street ", "9:16"))
    assert [c["provider_id"] for c in found] == ["855564"]          # the off-host result is dropped
    assert sm.resolve_candidate_for("p2")({"provider": "pexels", "provider_id": "855564"})
    q, kw = seen[0]
    assert q == "rainy street" and kw["orientation"] == "portrait" and kw["pexels_api_key"] == "k"


def test_search_trims_the_query_to_the_limit(monkeypatch):
    seen = []
    _fake_search(monkeypatch, seen)
    asyncio.run(sm.search_candidates("p2b", "word " * 60, "16:9"))
    q, kw = seen[0]
    assert len(q) <= sm.QUERY_MAX and q == q.strip() and kw["orientation"] == "landscape"


def test_search_needs_two_letters(monkeypatch):
    monkeypatch.setattr(sm, "pexels_key", lambda: "k")
    with pytest.raises(StudioMediaError, match="at least two letters"):
        asyncio.run(sm.search_candidates("p3", " a "))


def test_search_without_a_key_says_how_to_fix_it(monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, "PEXELS_API_KEY", "")
    assert sm.pexels_key() == ""
    with pytest.raises(StudioMediaError) as err:
        asyncio.run(sm.search_candidates("p3", "coffee"))
    assert str(err.value) == sm.NO_KEY_MESSAGE and "PEXELS_API_KEY" in sm.NO_KEY_MESSAGE


def test_pexels_search_exposes_a_small_preview(monkeypatch):
    from backend.services import stock_video_service

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"videos": [{"id": 5, "url": "https://www.pexels.com/video/coffee-5/", "duration": 9,
                                "image": "https://images.pexels.com/5.jpg", "user": {"name": "A"},
                                "video_files": [
                                    {"link": "https://videos.pexels.com/5/uhd.mp4", "width": 2160, "height": 3840, "quality": "uhd"},
                                    {"link": "https://videos.pexels.com/5/hd.mp4", "width": 1080, "height": 1920, "quality": "hd"},
                                    {"link": "https://videos.pexels.com/5/sd.mp4", "width": 540, "height": 960, "quality": "sd"},
                                    {"link": "https://videos.pexels.com/5/tiny.mp4", "width": 240, "height": 426, "quality": "sd"},
                                ]}]}

    async def fake_get(*_a, **_k):
        return Resp()

    monkeypatch.setattr(stock_video_service._http, "get", fake_get)
    results = asyncio.run(stock_video_service.search_videos("coffee", orientation="portrait", api_key="k"))
    assert results[0]["download_url"].endswith("hd.mp4")
    assert results[0]["preview_url"].endswith("/sd.mp4")


# ── previews ────────────────────────────────────────────────────────────────

@pytest.fixture
def studio_dir(tmp_path, monkeypatch):
    from backend.config import Settings
    monkeypatch.setattr(Settings, "STUDIO_DIR", property(lambda self: tmp_path / "studio"))
    return tmp_path / "studio"


@needs_ffmpeg
def test_a_preview_is_downloaded_once(monkeypatch, studio_dir, tmp_path):
    sample = tiny_mp4(tmp_path / "sample.mp4")
    calls = []

    async def fake_download(url, dest, max_bytes=None):
        calls.append(url)
        shutil.copyfile(sample, dest)

    monkeypatch.setattr(sm, "download", fake_download)
    cand = sm.candidate_from_result(PEXELS, "street")
    name = asyncio.run(sm.ensure_preview(cand))
    assert name == "pexels_855564.mp4" and sm.preview_path(name)
    assert str(sm.preview_path(name)).startswith(str(studio_dir))
    assert asyncio.run(sm.ensure_preview(cand)) == name
    assert calls == [PEXELS["preview_url"]]
    assert sm.preview_path("../../etc/passwd") is None


def test_a_non_stock_preview_is_refused(studio_dir):
    with pytest.raises(StudioMediaError, match="stock footage host"):
        asyncio.run(sm.ensure_preview({"provider": "pexels", "provider_id": "1",
                                       "preview_url": "https://evil.example/x.mp4"}))


def test_redirects_off_the_stock_hosts_are_refused(monkeypatch, tmp_path):
    import httpx

    def handler(request):
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data"})

    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=transport, **kw))
    with pytest.raises(StudioMediaError, match="stock footage host"):
        asyncio.run(sm.download("https://videos.pexels.com/x.mp4", tmp_path / "x.part", 1000))


def test_download_writes_the_whole_body_in_batches(monkeypatch, tmp_path):
    """The file writes run off the event loop in ~1 MB batches — the result
    must still be the exact body, including a short tail."""
    import httpx

    body = bytes(range(256)) * 12000            # ~3 MB, not a multiple of the batch
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=body))
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=transport, **kw))
    dest = tmp_path / "clip.part"
    asyncio.run(sm.download("https://videos.pexels.com/x.mp4", dest, len(body) + 1))
    assert dest.read_bytes() == body
    with pytest.raises(StudioMediaError, match="too large"):
        asyncio.run(sm.download("https://videos.pexels.com/x.mp4", tmp_path / "big.part", 1000))


def test_remembered_candidates_are_bounded_and_forgotten_on_delete():
    sm._remembered.clear()
    cand = {"provider": "pexels", "provider_id": "1", "download_url": "https://videos.pexels.com/1.mp4"}
    for i in range(sm.REMEMBERED_PROJECTS + 5):
        sm.remember(f"p{i}", [cand])
    assert len(sm._remembered) == sm.REMEMBERED_PROJECTS
    assert "p0" not in sm._remembered and f"p{sm.REMEMBERED_PROJECTS + 4}" in sm._remembered
    sm.forget(f"p{sm.REMEMBERED_PROJECTS + 4}")
    assert f"p{sm.REMEMBERED_PROJECTS + 4}" not in sm._remembered


# ── uploads ─────────────────────────────────────────────────────────────────

@needs_ffmpeg
def test_an_uploaded_clip_is_moved_in_and_postered(studio_dir, tmp_path):
    src = tiny_mp4(tmp_path / "upload.mp4")
    record = asyncio.run(sm.add_video("proj1", src, title="Beach", source="upload"))
    dest = sm.asset_file("proj1", record)
    assert dest and dest.parent == sm.project_assets_dir("proj1")
    assert not src.exists()                                         # the upload's temp file is moved, not copied
    assert sm.is_asset_id(record["asset_id"]) and record["title"] == "Beach"
    assert record["media"] == "video" and record["native_duration"] > 0.5
    assert (record["width"], record["height"]) == (320, 568)
    assert sm.asset_file("proj1", record, poster=True)
    assert sm.asset_file("proj1", {**record, "file": "../../../etc/passwd"}) is None
    public = sm.public_asset("proj1", record)
    assert public["url"] == f"/api/studio/media/proj1/{record['asset_id']}" and public["poster_url"]
    assert "file" not in sm.doc_asset(record) and "poster" not in sm.doc_asset(record)


@needs_ffmpeg
def test_an_upload_that_is_not_a_video_is_refused(studio_dir, tmp_path):
    bad = tmp_path / "notes.mp4"
    bad.write_bytes(b"hello, not a video")
    with pytest.raises(StudioMediaError, match="playable video"):
        asyncio.run(sm.add_video("proj1", bad, title="Notes", source="upload"))


@needs_ffmpeg
def test_an_uploaded_still_is_normalised_to_a_png(studio_dir, tmp_path):
    src = tiny_png(tmp_path / "still.png")
    record = asyncio.run(sm.add_image("proj1", src, title="Still", source="upload"))
    dest = sm.asset_file("proj1", record)
    assert dest and dest.suffix == ".png" and record["media"] == "image"
    assert record["width"] and record["height"]
    assert sm.asset_file("proj1", record, poster=True) == dest
    bad = tmp_path / "broken.png"
    bad.write_bytes(b"not an image")
    with pytest.raises(StudioMediaError, match="readable image"):
        asyncio.run(sm.add_image("proj1", bad, title="Broken", source="upload"))


def test_a_project_id_cannot_escape_the_projects_dir(studio_dir):
    with pytest.raises(StudioMediaError, match="Bad project id"):
        sm.project_assets_dir("../outside")
    assert sm.UPLOAD_MAX_BYTES > 0 and ".png" in sm.IMAGE_SUFFIXES
