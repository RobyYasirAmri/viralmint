# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Clip removal: an uploaded clip a scene still uses can't be deleted, so no
scene is ever left pointing at a missing file."""
import asyncio
import shutil
import subprocess

import pytest

SCRIPT = ("A jar of coins sits on a wooden table in soft morning light by the window. "
          "A hand reaches in and drops one more shiny coin into the jar.")


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


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
def test_a_clip_in_use_cannot_be_removed_until_freed(client, tmp_path):
    clip = tmp_path / "mine.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=180x320:rate=24", "-t", "1",
                    "-pix_fmt", "yuv420p", str(clip)], check=True, capture_output=True)
    p = client.post("/api/studio/projects", json={"start": {"script": SCRIPT}}).json()["project"]
    with open(clip, "rb") as f:
        up = client.post(f"/api/studio/projects/{p['id']}/media/upload", files={"file": ("mine.mp4", f, "video/mp4")}).json()
    asset, p = up["asset"], up["project"]
    uid = p["doc"]["scenes"][0]["uid"]
    p = client.patch(f"/api/studio/projects/{p['id']}", json={"if_revision": p["revision"], "ops": [
        {"op": "bind_visual", "uid": uid, "visual": {"kind": "user_clip", "asset_id": asset["asset_id"]}}]}).json()["project"]

    refused = client.delete(f"/api/studio/projects/{p['id']}/media/{asset['asset_id']}")
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "in_use"
    assert refused.json()["detail"]["scenes"] == [1]
    assert client.get(asset["url"]).status_code == 200                 # still on disk and indexed

    p = client.patch(f"/api/studio/projects/{p['id']}", json={"if_revision": p["revision"], "ops": [
        {"op": "clear_visual", "uid": uid}]}).json()["project"]
    removed = client.delete(f"/api/studio/projects/{p['id']}/media/{asset['asset_id']}")
    assert removed.status_code == 200 and removed.json()["project"]["media"] == []
    assert client.get(asset["url"]).status_code == 404
    assert client.delete(f"/api/studio/projects/{p['id']}/media/{asset['asset_id']}").status_code == 404
