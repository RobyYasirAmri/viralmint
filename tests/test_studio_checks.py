# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""studio_checks — what blocks a render, and what's worth knowing first.

`compute_checks` is pure (the take cache is passed in); `checks_for` gets one
integration test against a real (temporary) take cache.
"""
import asyncio
import hashlib

import pytest

from backend.services import studio_doc as sd
from backend.services.studio_checks import (
    checks_for, compute_checks, effective_voice_state, needs_voice, recorded_lost,
)


def key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def sc(uid, line="A line.", voice=None, visual=None):
    return {"uid": uid, "line": line, "voice": voice or {"state": "none"},
            "visual": visual or {"kind": "stock", "state": "placeholder", "query": "q"}}


def make(scenes, **settings):
    s = sd.default_settings()
    s.update(settings)
    return sd.validate_doc({"settings": s, "scenes": scenes}, settle=False)


def nothing_cached(_key):
    return False


def checks(doc, take_known=nothing_cached):
    return compute_checks(doc, take_known)


def test_a_scene_without_a_line_blocks_render():
    c = checks(make([sc("a", "Spoken."), sc("b", "")]))
    assert any("Scene 2 has no line yet" in b for b in c["blockers"])
    # An empty scene is not "unvoiced" — it has nothing to voice.
    assert any("1 scene isn't voiced yet" in w for w in c["warnings"])


def test_blockers_and_warnings():
    d = make([
        sc("a", voice={"state": "stale", "take_key": key("x"), "duration": 1}),
        sc("b", visual={"kind": "stock", "state": "failed", "query": "q"}),
    ])
    c = checks(d)
    assert any("changed since voiced" in w for w in c["warnings"])
    assert any("isn't voiced yet" in w for w in c["warnings"])
    assert any("Scene 2 has no usable visual" in b for b in c["blockers"])


def test_a_scene_still_being_voiced_blocks_render():
    c = checks(make([sc("a", voice={"state": "generating"}), sc("b", voice={"state": "generating"})]))
    assert any("Scene 1, 2 are still being voiced" in b for b in c["blockers"])


def test_several_scenes_are_listed_in_one_blocker():
    c = checks(make([sc("a", ""), sc("b", "Spoken."), sc("c", "")]))
    assert c["blockers"] == ["Scene 1, 3 have no line yet — write it or delete the scene"]


def test_a_music_bed_without_a_track_is_a_warning_not_a_blocker():
    music = sd.default_settings()["music"]
    no_track = checks(make([sc("a")]))
    assert any("No music track picked" in w for w in no_track["warnings"]) and not no_track["blockers"]
    picked = checks(make([sc("a")], music={**music, "track": "calm.mp3"}))
    assert not any("music" in w.lower() for w in picked["warnings"])
    off = checks(make([sc("a")], music={**music, "enabled": False}))
    assert not any("music" in w.lower() for w in off["warnings"])


def test_a_ready_scene_is_voiced_unless_its_own_take_is_gone():
    """The render reuses a ready scene's own take; only a take that vanished
    from disk has to be recorded again."""
    d = make([sc("a", "One.", voice={"state": "ready", "take_key": key("a"), "duration": 1}),
              sc("b", "Two.", voice={"state": "ready", "take_key": key("b"), "duration": 1})])
    on_disk = {key("a")}.__contains__
    a, b = d["scenes"]
    assert not recorded_lost(a, on_disk) and recorded_lost(b, on_disk)
    assert effective_voice_state(a, on_disk) == "ready" and effective_voice_state(b, on_disk) == "none"
    assert not needs_voice(a, on_disk) and needs_voice(b, on_disk)
    assert any("1 scene isn't voiced yet" in w for w in checks(d, on_disk)["warnings"])
    assert not any("voiced yet" in w for w in checks(d, {key("a"), key("b")}.__contains__)["warnings"])


@pytest.mark.parametrize("voice,expected", [
    ({"state": "none"}, True),
    ({"state": "failed"}, True),
    ({"state": "stale", "take_key": "0" * 64, "duration": 1}, True),
    ({"state": "generating"}, False),
])
def test_needs_voice(voice, expected):
    scene = make([sc("a", voice=voice)])["scenes"][0]
    assert needs_voice(scene, nothing_cached) is expected


def test_a_scene_with_no_line_never_needs_a_voice():
    scene = make([sc("a", "")])["scenes"][0]
    assert not needs_voice(scene, nothing_cached)


def test_checks_for_reads_the_real_take_cache(monkeypatch, tmp_path):
    from backend.services import voice_take_service as vts

    monkeypatch.setattr(vts, "cache_dir", lambda: tmp_path / "voice")
    monkeypatch.setattr(vts, "probe_audio_duration", lambda _p: 2.0)

    async def synth(text, spec, out):
        out.write_bytes(b"audio")

    d = make([sc("a", "Recorded before.")])
    take = asyncio.run(vts.ensure_take(vts.VoiceSpec.from_settings(d["settings"]), "Recorded before.", synth=synth))
    d["scenes"][0]["voice"] = {"state": "ready", "take_key": take.key, "duration": take.duration}
    assert not any("voiced yet" in w for w in checks_for(d)["warnings"])
    take.path.unlink()                                    # the cache was cleared under the project
    assert any("1 scene isn't voiced yet" in w for w in checks_for(d)["warnings"])
