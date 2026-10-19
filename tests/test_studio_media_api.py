# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""/api/studio media endpoints — upload, bind, serve.

A FastAPI app with only the studio router, on the suite's isolated DATA_DIR.
Real ffmpeg makes a one-second clip and a still so uploads probe and poster
a genuine file.
"""
import asyncio
import shutil
import subprocess

import pytest

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")


def tiny_mp4(path):
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=320x568:rate=24", "-t", "1",
                    "-pix_fmt", "yuv420p", str(path)], check=True, capture_output=True)
    return path


def tiny_png(path):
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1", str(path)],
                   check=True, capture_output=True)
    return path


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


@needs_ffmpeg
def test_upload_a_clip_and_an_image_then_bind_the_clip(client, tmp_path):
    r = client.post("/api/studio/projects", json={"start": {"script": "A first line here. A second line there."}})
    p = r.json()["project"]
    clip = tiny_mp4(tmp_path / "mine.mp4")
    with open(clip, "rb") as f:
        up = client.post(f"/api/studio/projects/{p['id']}/media/upload", files={"file": ("mine.mp4", f, "video/mp4")})
    assert up.status_code == 200, up.text
    asset = up.json()["asset"]
    assert asset["media"] == "video" and asset["poster_url"]
    assert client.get(asset["url"]).status_code == 200
    assert client.get(asset["poster_url"]).status_code == 200

    png = tiny_png(tmp_path / "still.png")
    with open(png, "rb") as f:
        img = client.post(f"/api/studio/projects/{p['id']}/media/upload", files={"file": ("still.png", f, "image/png")})
    assert img.status_code == 200 and img.json()["asset"]["media"] == "image"
    envelope = img.json()["project"]
    assert {m["media"] for m in envelope["media"]} == {"video", "image"}

    uid = envelope["doc"]["scenes"][0]["uid"]
    bound = client.patch(f"/api/studio/projects/{p['id']}", json={"if_revision": envelope["revision"], "ops": [
        {"op": "bind_visual", "uid": uid, "visual": {"kind": "user_clip", "asset_id": asset["asset_id"]}}]})
    assert bound.status_code == 200, bound.text
    visual = bound.json()["project"]["doc"]["scenes"][0]["visual"]
    assert visual["kind"] == "user_clip" and visual["asset"]["asset_id"] == asset["asset_id"]


def test_upload_rejects_other_file_types(client):
    p = client.post("/api/studio/projects", json={"start": {"script": "One line only."}}).json()["project"]
    r = client.post(f"/api/studio/projects/{p['id']}/media/upload", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "media"
    assert client.get(f"/api/studio/projects/{p['id']}").json()["project"]["media"] == []


def test_media_is_served_only_through_the_index(client):
    p = client.post("/api/studio/projects", json={"start": {"script": "One line only."}}).json()["project"]
    assert client.get(f"/api/studio/media/{p['id']}/as_0000000000000000").status_code == 404
    assert client.get(f"/api/studio/media/{p['id']}/..%2F..%2Fetc").status_code == 404
