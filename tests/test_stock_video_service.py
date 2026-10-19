# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""The Studio's stock layer: Pexels search + scoring, the per-chunk planner,
and the one-pass clip normaliser (run under the real ffmpeg — every look's
filter graph must actually parse, or a whole render ships ungraded)."""
import json
import shutil
import subprocess
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.core.exceptions import VideoGenerationError
from backend.services import stock_video_service as S
from backend.services.video_utils import probe_dimensions, probe_duration

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


def _payload():
    return {"videos": [
        {"id": 1, "url": "https://www.pexels.com/video/a-wide-city-street-11/", "duration": 8,
         "image": "https://images.pexels.com/1.jpg", "user": {"name": "Ann"},
         "video_files": [
             {"link": "https://videos.pexels.com/1_hd.mp4", "width": 1920, "height": 1080, "quality": "hd"},
             {"link": "https://videos.pexels.com/1_sd.mp4", "width": 640, "height": 360, "quality": "sd"}]},
        {"id": 2, "url": "https://www.pexels.com/video/a-tall-tower-22/", "duration": 8,
         "video_files": [
             {"link": "https://videos.pexels.com/2_hd.mp4", "width": 1080, "height": 1920, "quality": "hd"},
             {"link": "https://videos.pexels.com/2_sd.mp4", "width": 540, "height": 960, "quality": "sd"},
             {"link": "https://videos.pexels.com/2_tiny.mp4", "width": 240, "height": 426, "quality": "sd"}]},
        {"id": 3, "url": "u3", "duration": 8, "video_files": [
            {"link": "https://videos.pexels.com/3.mp4", "width": 320, "height": 240, "quality": "sd"}]},
    ]}


# ── search ───────────────────────────────────────────────────────────────────

async def test_portrait_native_outranks_landscape_for_portrait(monkeypatch):
    monkeypatch.setattr(S, "_http", MagicMock(get=AsyncMock(return_value=_Resp(_payload()))))
    out = await S.search_videos("x", orientation="portrait", per_page=15, api_key="k")
    assert [v["id"] for v in out] == [2, 1], "sub-HD-only clip 3 is dropped; native portrait first"
    assert out[0]["quality_score"] > out[1]["quality_score"]


async def test_search_carries_download_and_small_preview_files(monkeypatch):
    monkeypatch.setattr(S, "_http", MagicMock(get=AsyncMock(return_value=_Resp(_payload()))))
    out = {v["id"]: v for v in await S.search_videos("x", orientation="portrait", api_key="k")}
    assert out[2]["download_url"].endswith("2_hd.mp4")
    # The smallest file whose short side is still ≥ 360 — never the 240p one.
    assert out[2]["preview_url"].endswith("2_sd.mp4")
    assert out[1]["desc_words"] == ["a", "wide", "city", "street"]
    assert out[1]["creator"] == "Ann" and out[1]["thumbnail"].endswith("1.jpg")


async def test_search_without_a_key_raises():
    with pytest.raises(VideoGenerationError):
        await S.search_videos("x", api_key="")


async def test_search_stock_candidates_degrades_to_empty(monkeypatch):
    assert await S.search_stock_candidates("x", pexels_api_key="") == []
    monkeypatch.setattr(S, "_http", MagicMock(get=AsyncMock(side_effect=RuntimeError("down"))))
    assert await S.search_stock_candidates("x", pexels_api_key="k") == []


async def test_search_all_scenes_tries_fallback_queries_and_never_raises(monkeypatch):
    calls = []

    async def fake(query, orientation, per_page, api_key):
        calls.append(query)
        if query == "boom":
            raise RuntimeError("api down")
        if query == "good":
            return [{"id": f"{query}{i}", "duration": 30, "quality_score": i} for i in range(4)]
        return []
    monkeypatch.setattr(S, "search_videos", fake)
    scenes = [{"query": "boom", "alt1": "nothing", "alt2": "good"}, {"query": "good", "alt1": "never"}, {}]
    res = await S.search_all_scenes(scenes, "portrait", 30.0, "k")
    assert [i for i, _ in res] == [0, 1, 2]
    assert len(res[0][1]) == 4 and res[2][1] == []
    # Scene 1 found three long clips on its first query — no fallback search.
    assert "never" not in calls
    # Long-enough clips got the duration bonus.
    assert res[1][1][0]["quality_score"] == 3 + 20


async def test_search_all_scenes_without_key_is_empty():
    assert await S.search_all_scenes([{"query": "a"}], "portrait", 5, "") == [(0, [])]


# ── planning ─────────────────────────────────────────────────────────────────

def _chunks(*texts):
    return [{"text": t, "start": i * 3.0, "end": i * 3.0 + 3.0} for i, t in enumerate(texts)]


def test_align_to_chunks_reseats_by_chunk_number():
    scenes = [{"chunk": 2, "query": "b"}, {"chunk": 1, "query": "a"}, {"chunk": 2, "query": "dup"}]
    assert [s["query"] for s in S.align_to_chunks(scenes, 2)] == ["a", "b"]


def test_align_to_chunks_pads_a_gap_in_place():
    out = S.align_to_chunks([{"chunk": 1, "query": "a"}, {"chunk": 3, "query": "c"}], 3)
    assert out[0]["query"] == "a" and out[1] is None and out[2]["query"] == "c"


async def test_extract_visual_scenes_one_entry_per_chunk_in_order():
    reply = json.dumps([{"chunk": 2, "query": "ocean waves"}, {"chunk": 1, "query": "city night"}])
    ai = MagicMock(chat=AsyncMock(return_value=reply))
    out = await S.extract_visual_scenes(_chunks("The city never sleeps.", "Then the sea."), ai)
    assert [s["query"] for s in out] == ["city night", "ocean waves"]
    prompt = ai.chat.await_args.kwargs["messages"][0]["content"]
    assert "exactly 2 scenes" in prompt and "ENGLISH" in prompt
    # Stock only — the prompt never offers AI imagery this build can't make.
    assert "ai_prompt" not in prompt


async def test_extract_visual_scenes_fills_missing_chunks_from_their_words():
    ai = MagicMock(chat=AsyncMock(return_value=json.dumps([{"chunk": 1, "query": "rain"}])))
    out = await S.extract_visual_scenes(_chunks("Rain falls.", "Dogs bark loudly outside"), ai)
    assert out[0]["query"] == "rain"
    assert out[1]["query"] == "Dogs bark loudly outside"


async def test_extract_visual_scenes_without_ai_uses_english_words_only():
    out = await S.extract_visual_scenes(_chunks("猫在睡觉。", "Coffee shop morning"), None)
    # A CJK line is not a Pexels query.
    assert out[0]["query"] == "abstract concept"
    assert out[1]["query"] == "Coffee shop morning"


async def test_extract_visual_scenes_failed_call_degrades(monkeypatch):
    ai = MagicMock(chat=AsyncMock(side_effect=RuntimeError("401")))
    out = await S.extract_visual_scenes(_chunks("Mountains at dawn"), ai)
    # Words of two letters or fewer ("at") are dropped from a keyword query.
    assert out == [{"query": "Mountains dawn", "alt1": "Mountains dawn",
                    "alt2": "Mountains dawn", "mood": "neutral"}]


async def test_extract_visual_scenes_garbage_json_repaired_or_degraded(monkeypatch):
    import backend.core.ai_retry as ai_retry

    async def _no_fix(*a, **k):
        return None
    monkeypatch.setattr(ai_retry, "ai_fix_json", _no_fix)
    ai = MagicMock(chat=AsyncMock(return_value="not json at all"))
    out = await S.extract_visual_scenes(_chunks("Forest walk"), ai)
    assert out[0]["query"] == "Forest walk"


async def test_extract_visual_scenes_empty():
    assert await S.extract_visual_scenes([], None) == []


def test_every_look_resolves_to_a_known_lut():
    for name, preset in S.VISUAL_STYLE_PRESETS.items():
        assert preset["lut"] in S.LUT_PRESETS, name
    assert S.resolve_visual_style("nope") is S.VISUAL_STYLE_PRESETS["cinematic"]
    assert S.resolve_visual_style(None) is S.VISUAL_STYLE_PRESETS["cinematic"]


# ── normalising ──────────────────────────────────────────────────────────────

def _src(path, w=640, h=360, d=3):
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc2=size={w}x{h}:rate=25:duration={d}",
                    "-f", "lavfi", "-i", f"sine=d={d}", "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)],
                   capture_output=True, check=True)
    return path


@needs_ffmpeg
@pytest.mark.parametrize("lut", sorted(S.LUT_PRESETS))
async def test_every_lut_grades_without_falling_back(tmp_path, lut, monkeypatch):
    """A look whose filter graph doesn't parse silently ships ungraded (the
    fallback hides it) — so assert the graded pass itself succeeded."""
    src = _src(tmp_path / "s.mp4")
    fell_back = []
    monkeypatch.setattr(S, "_trim_fallback", lambda *a, **k: fell_back.append(a) or a[4])
    out = await S.trim_and_normalize_clip(src, 2.0, 360, 640, tmp_path / "o.mp4", lut_preset=lut)
    assert not fell_back, f"{lut} grade failed to parse"
    assert probe_dimensions(out) == (360, 640)
    assert abs(probe_duration(out) - 2.0) < 0.1


@needs_ffmpeg
async def test_normalised_clip_is_concat_ready(tmp_path):
    src = _src(tmp_path / "s.mp4", 1280, 720, 2)
    out = await S.trim_and_normalize_clip(src, 1.5, 360, 640, tmp_path / "o.mp4", ken_burns=False)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,r_frame_rate",
                            "-of", "json", str(out)], capture_output=True, text=True).stdout
    streams = json.loads(probe)["streams"]
    assert [s["codec_type"] for s in streams] == ["video"], "stock clips carry no audio"
    assert streams[0]["r_frame_rate"] == "30/1"


@needs_ffmpeg
def test_bare_normalize_raises_instead_of_passing_a_raw_clip(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    with pytest.raises(VideoGenerationError):
        S._bare_normalize(bad, 1.0, 360, 640, tmp_path / "o.mp4")
