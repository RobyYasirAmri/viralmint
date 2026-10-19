# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Render polish: captions don't repeat the auto title, long stock scenes cut
to a second shot (same rule as the preview), and the frame cover is a clean
frame with only the title on it."""
from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.services import studio_doc as sd
from backend.services.studio_render import after_hook, frame_cover

REPO = Path(__file__).resolve().parents[1]


def test_captions_skip_the_words_said_under_an_auto_title():
    segs = [{"start": 0.0, "end": 3.0, "text": "a b c d", "words": [
        {"word": "a", "start": 0.0, "end": 0.5}, {"word": "b", "start": 1.0, "end": 1.5},
        {"word": "c", "start": 2.6, "end": 2.9}, {"word": "d", "start": 2.9, "end": 3.0}]},
        {"start": 3.0, "end": 4.0, "text": "next line"}]
    out = after_hook(segs, 2.5)
    assert [w["word"] for w in out[0]["words"]] == ["c", "d"] and out[0]["text"] == "c d" and out[0]["start"] == 2.6
    assert out[1]["text"] == "next line"
    assert after_hook([{"start": 0.0, "end": 2.0, "text": "gone", "words": [{"word": "gone", "start": 0, "end": 1}]}], 2.5) == []
    # A segment without word timings is kept only when it starts after the title.
    assert after_hook([{"start": 1.0, "end": 2.0, "text": "early"}], 2.5) == []


def test_hook_is_auto_only_for_the_first_lines_own_words():
    doc = {"settings": sd.default_settings(), "scenes": [{"line": "Plants sleep in winter."}]}
    assert sd.hook_is_auto(doc)
    doc["settings"]["captions"]["hook_text"] = "My own title"
    assert not sd.hook_is_auto(doc)
    doc["settings"]["captions"].update(hook_text=None, hook=False)
    assert not sd.hook_is_auto(doc)


def _stock(uid, pid, alts, pinned=False):
    return {"uid": uid, "visual": {"kind": "stock", "state": "bound", "pinned": pinned,
                                   "asset": {"provider_id": pid, "download_url": f"u{pid}"},
                                   "alternates": [{"provider_id": a, "download_url": f"u{a}"} for a in alts]}}


def test_long_stock_scenes_cut_to_an_unused_alternate():
    scenes = [_stock("a", "1", ["1", "2", "3"]), _stock("b", "2", ["2", "4"]), _stock("c", "5", ["5", "4"]),
              _stock("d", "6", ["7"], pinned=True), _stock("e", "8", ["9"])]
    shots = sd.second_shots(scenes, [6.0, 6.0, 7.0, 9.0, 3.0])
    assert shots["a"] == {"asset": {"provider_id": "3", "download_url": "u3"}, "cut": 3.0}   # "2" is scene b's
    assert shots["b"]["asset"]["provider_id"] == "4"
    assert "c" not in shots                      # "4" already taken by b's second shot
    assert "d" not in shots and "e" not in shots  # pinned; short


def test_the_preview_mirror_carries_the_same_rule():
    model = (REPO / "frontend/src/components/studio/studioModel.js").read_text(encoding="utf-8")
    assert f"export const SECOND_SHOT_MIN_S = {sd.SECOND_SHOT_MIN_S}" in model
    assert "export function secondShots" in model


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_the_frame_cover_is_a_clean_frame_with_the_title(tmp_path):
    clean = tmp_path / "stitched.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x223344:s=540x960:d=3",
                    "-pix_fmt", "yuv420p", str(clean)], check=True)
    plain = asyncio.run(frame_cover(clean, None, "urban", "9:16", 1.0, tmp_path / "plain_thumb.jpg"))
    titled = asyncio.run(frame_cover(clean, "Why plants die in winter", "urban", "9:16", 1.0, tmp_path / "t_thumb.jpg"))
    assert plain and titled and plain.stat().st_size > 1024
    assert titled.stat().st_size > plain.stat().st_size      # the title was drawn
    assert not list(tmp_path.glob("*.tmp.jpg")) and not list(tmp_path.glob("*.ass"))
    assert asyncio.run(frame_cover(tmp_path / "missing.mp4", "x", "urban", "9:16", 1.0, tmp_path / "m.jpg")) is None
