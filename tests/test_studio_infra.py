# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""The building blocks the Smart Video Studio renders with.

Every media test here runs the REAL ffmpeg: these helpers exist to keep
durations exact (scene timing is derived from them), and a mocked ffmpeg
proves nothing about a duration.
"""
import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.services import audio_utils, music_service as ms, tts_service as tts
from backend.services.ffmpeg_service import TRANSITION_STYLES, stitch_with_style
from backend.services.video_utils import orientation_fit_adjustment, probe_duration, run_ffmpeg

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _clip(path: Path, seconds: float, color: str = "red") -> Path:
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=320x568:r=30:d={seconds}",
                    "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-an", str(path)],
                   capture_output=True, check=True)
    return path


def _tone(path: Path, seconds: float, *, lead_silence: float = 0.0) -> Path:
    graph = f"sine=f=440:d={seconds}"
    args = ["ffmpeg", "-y", "-f", "lavfi", "-i", graph]
    if lead_silence:
        args += ["-af", f"adelay={int(lead_silence * 1000)}:all=1,apad=pad_dur={lead_silence}"]
    subprocess.run(args + ["-c:a", "libmp3lame", "-b:a", "128k", str(path)], capture_output=True, check=True)
    return path


# ── video ───────────────────────────────────────────────────────────────────

@needs_ffmpeg
@pytest.mark.parametrize("style", sorted(TRANSITION_STYLES))
async def test_stitch_with_style_keeps_the_hard_cut_duration(tmp_path, style):
    """A transition must not change the total — the voice is laid over it."""
    clips = [_clip(tmp_path / f"c{i}.mp4", d, c) for i, (d, c) in enumerate([(1.5, "red"), (2.0, "blue"), (1.0, "green")])]
    out = await stitch_with_style(clips, tmp_path / "out.mp4", style)
    assert abs(probe_duration(out) - 4.5) < 0.1
    # The freeze-padded intermediates never outlive the stitch.
    assert not list(tmp_path.glob("*_pad*.mp4"))


@needs_ffmpeg
async def test_stitch_with_style_unknown_style_is_a_hard_cut(tmp_path):
    clips = [_clip(tmp_path / f"c{i}.mp4", 1.0) for i in range(2)]
    out = await stitch_with_style(clips, tmp_path / "out.mp4", "sparkles")
    assert abs(probe_duration(out) - 2.0) < 0.1


@needs_ffmpeg
async def test_xfade_failure_falls_back_to_the_original_clips(tmp_path, monkeypatch):
    """When the xfade graph fails, the concat fallback must use the UNPADDED
    clips — concating the padded copies would make the video longer than the
    voice and drift every scene."""
    from backend.services import ffmpeg_service as fs
    clips = [_clip(tmp_path / f"c{i}.mp4", 1.0) for i in range(3)]
    real_run = subprocess.run

    def run(cmd, *a, **k):
        if "-filter_complex" in cmd and any("xfade" in str(x) for x in cmd):
            return subprocess.CompletedProcess(cmd, 1, "", "forced xfade failure")
        return real_run(cmd, *a, **k)
    monkeypatch.setattr(fs.subprocess, "run", run)
    out = await stitch_with_style(clips, tmp_path / "out.mp4", "smooth")
    assert abs(probe_duration(out) - 3.0) < 0.1


def test_orientation_fit_prefers_native_portrait():
    assert orientation_fit_adjustment(1080, 1920, "portrait") == 25.0
    assert orientation_fit_adjustment(1920, 1080, "portrait") < 0
    assert orientation_fit_adjustment(0, 0, "portrait") == 0.0


@needs_ffmpeg
def test_run_ffmpeg_takes_an_argv_list_and_reports_errors(tmp_path):
    r = run_ffmpeg(["-i", str(tmp_path / "missing.mp4"), str(tmp_path / "x.mp4")])
    assert r.returncode != 0 and r.stderr


# ── audio ───────────────────────────────────────────────────────────────────

@needs_ffmpeg
async def test_concat_audio_lays_silence_between_takes(tmp_path):
    a = _tone(tmp_path / "a.mp3", 1.0)
    b = _tone(tmp_path / "b.mp3", 0.5)
    out = await audio_utils.concat_audio([a, (a, 0.25), b, (b, 0.4)], tmp_path / "n.mp3")
    assert abs(audio_utils.probe_audio_duration(out) - 2.15) < 0.08


async def test_concat_audio_refuses_nothing(tmp_path):
    from backend.core.exceptions import VoiceGenerationError
    with pytest.raises(VoiceGenerationError):
        await audio_utils.concat_audio([], tmp_path / "n.mp3")


@needs_ffmpeg
def test_trim_silence_edges_strips_padding(tmp_path):
    src = _tone(tmp_path / "s.mp3", 1.0, lead_silence=0.6)
    dst = tmp_path / "t.mp3"
    assert audio_utils.trim_silence_edges_sync(src, dst)
    assert audio_utils.probe_audio_duration(dst) < audio_utils.probe_audio_duration(src) - 0.4


@needs_ffmpeg
def test_trim_silence_never_replaces_speech_with_nothing(tmp_path):
    src = tmp_path / "silent.mp3"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=d=1", "-c:a", "libmp3lame", str(src)],
                   capture_output=True, check=True)
    assert not audio_utils.trim_silence_edges_sync(src, tmp_path / "t.mp3")


def test_probe_audio_duration_is_zero_for_garbage(tmp_path):
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"not audio")
    assert audio_utils.probe_audio_duration(bad) == 0.0


@needs_ffmpeg
async def test_mix_audio_honours_custom_fades(tmp_path, monkeypatch):
    voice = _tone(tmp_path / "v.mp3", 2.0)
    music = _tone(tmp_path / "m.mp3", 5.0)
    seen = {}
    real_run = subprocess.run

    def run(cmd, *a, **k):
        if "-filter_complex" in cmd:
            seen["graph"] = cmd[cmd.index("-filter_complex") + 1]
        return real_run(cmd, *a, **k)
    monkeypatch.setattr(ms.subprocess, "run", run)
    out = await ms.mix_audio(voice, music, tmp_path / "mix.mp3", fade_in_s=0.5, fade_out_s=0.85)
    assert out == tmp_path / "mix.mp3" and out.exists()
    assert "afade=t=in:d=0.50" in seen["graph"] and "d=0.85" in seen["graph"]
    assert abs(audio_utils.probe_audio_duration(out) - 2.0) < 0.15


# ── music library ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", ["", "../x.mp3", "a/b.mp3", "a\\b.mp3"])
def test_library_path_refuses_traversal(tmp_path, monkeypatch, bad):
    monkeypatch.setattr(ms, "MUSIC_DIR", tmp_path)
    with pytest.raises(ms.LibraryPathError):
        ms.library_path(bad)


def test_library_path_resolves_inside(tmp_path, monkeypatch):
    monkeypatch.setattr(ms, "MUSIC_DIR", tmp_path)
    assert ms.library_path("lofi_rain.mp3") == (tmp_path / "lofi_rain.mp3").resolve()


def test_display_name_and_genre():
    assert ms.extract_genre("lofi_rainy_night.mp3") == "lofi"
    assert ms.display_name("lofi_rainy_night.mp3") == "rainy night"
    assert ms.extract_genre("my song.mp3") == "other"
    assert ms.display_name("my song.mp3") == "my song"


def test_music_library_route_lists_tracks(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.api import music as music_api
    from backend.main import app
    monkeypatch.setattr(music_api, "MUSIC_DIR", tmp_path)
    (tmp_path / "lofi_rain.mp3").write_bytes(b"x" * 10)
    (tmp_path / "empty.mp3").write_bytes(b"")
    (tmp_path / "notes.txt").write_text("no")
    with TestClient(app) as c:
        body = c.get("/api/music/library").json()
    assert [t["filename"] for t in body["tracks"]] == ["lofi_rain.mp3"]
    assert body["tracks"][0]["display_name"] == "rain"
    assert body["tracks"][0]["stream_url"] == "/api/music/stream/lofi_rain.mp3"
    assert "lofi" in body["genres"]


# ── tts provider answers ────────────────────────────────────────────────────

def test_provider_answers():
    assert tts.normalise_tts_provider("edge_tts") == "edge_tts"
    assert tts.normalise_tts_provider(tts.TTSProvider.OPENAI_TTS) == "openai_tts"
    assert tts.normalise_tts_provider("gemini_tts") is None and tts.normalise_tts_provider(3) is None
    assert tts.is_paid_per_take("openai_tts") and not tts.is_paid_per_take("edge_tts")
    traits = tts.provider_traits()
    assert set(traits) == {p.value for p in tts.TTSProvider}
    assert traits["edge_tts"] == {"paid_per_take": False, "needs_key": False, "heavy": False}


def test_tts_api_key_only_for_openai(monkeypatch):
    monkeypatch.setattr(tts.settings, "OPENAI_API_KEY", "sk-test")
    assert tts.tts_api_key("openai_tts") == "sk-test"
    assert tts.tts_api_key("edge_tts") == ""


def test_estimate_spoken_seconds_counts_cjk_per_character():
    assert tts.estimate_spoken_seconds("") == 0.0
    assert tts.estimate_spoken_seconds("one two three four five") == 2.0
    assert tts.estimate_spoken_seconds("你好世界你好世界") == 2.3
    assert tts.estimate_spoken_seconds("Hi 你好") == round(1 / 2.5 + 2 / 3.5, 1)


# ── jobs ────────────────────────────────────────────────────────────────────

async def test_create_job_stores_a_title():
    from backend.agents.job_helper import create_job
    job = await create_job("studio_voice", "local", {"x": 1}, title="Voice · 3 scenes")
    assert job.title == "Voice · 3 scenes"
    job2 = await create_job("studio_voice")
    assert job2.title is None


async def test_dispatch_light_runs_off_the_heavy_pool():
    """A light job must run even while every heavy slot is taken."""
    from backend.core import task_runner as tr
    done = asyncio.Event()

    async def work(job_id=None):
        done.set()

    for _ in range(3):
        await tr._task_semaphore.acquire()
    try:
        tr.dispatch_light(work())
        await asyncio.wait_for(done.wait(), 2)
    finally:
        for _ in range(3):
            tr._task_semaphore.release()


async def test_dispatch_light_skips_a_job_cancelled_while_queued():
    from backend.agents.job_helper import create_job, update_job_status
    from backend.core import task_runner as tr
    job = await create_job("studio_plan")
    await update_job_status(job.id, "cancelled")
    ran = []

    async def work(job_id):
        ran.append(job_id)

    task = tr.spawn_background(tr._run_with_limit(work(job.id), tr._light_task_semaphore))
    await task
    assert ran == []
