# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Language-aware Studio defaults: a Chinese script must not get the English
"Andrew" voice, scenes many seconds long, or lines that can't be split."""
from __future__ import annotations

from backend.services import studio_doc as sd
from backend.services import studio_ops
from backend.services.studio_store import match_voice_to_script, script_language

ZH = "冬天植物死掉，往往不是因为冷。而是因为你浇水太多了。光线少了，它们几乎不喝水。"


def test_script_language():
    assert script_language(ZH) == "zh"
    assert script_language("日本語の文章です。") == "ja"
    assert script_language("한국어 문장입니다.") == "ko"
    assert script_language("Plain English words.") == "latin"
    assert script_language("Ask Li Wei (李伟) about it, he knows everything there is to know.") is None


def test_a_chinese_script_gets_a_chinese_free_voice():
    settings = sd.default_settings()
    note = match_voice_to_script(settings, ZH)
    assert settings["voice"]["voice"] == "zh-CN-XiaoxiaoNeural"
    assert settings["voice"]["label"] == "Xiaoxiao"
    assert "Chinese" in note


def test_matching_voices_and_openai_voices_are_left_alone():
    settings = sd.default_settings()
    assert match_voice_to_script(settings, "An English script.") is None
    openai = sd.default_settings(voice={"provider": "openai_tts", "voice": "nova", "label": "Nova"})
    assert match_voice_to_script(openai, ZH) is None and openai["voice"]["voice"] == "nova"


def test_an_english_script_leaves_a_remembered_chinese_voice():
    settings = sd.default_settings(voice={"provider": "edge_tts", "voice": "zh-CN-XiaoxiaoNeural", "label": "Xiaoxiao"})
    assert match_voice_to_script(settings, "Back to English now.")
    assert settings["voice"]["voice"] == sd.default_settings()["voice"]["voice"]


def test_chinese_scenes_are_seconds_long_and_join_without_spaces():
    lines = sd.plan_lines(ZH * 2)
    assert all(sd.estimate_line_seconds(line) <= 7 for line in lines)
    assert not any(" " in line for line in lines)


def _doc(lines):
    return sd.validate_doc({"aspect_ratio": "9:16", "input": {"mode": "script"}, "settings": sd.default_settings(),
                            "scenes": [sd.make_scene(line) for line in lines]}, settle=False)


def test_a_long_chinese_line_can_be_split_and_merges_back_without_a_space():
    doc = _doc(["冬天植物死掉往往不是因为冷，而是因为你浇水太多了"])
    uid = doc["scenes"][0]["uid"]
    doc2 = studio_ops.apply_ops(doc, [{"op": "split_scene", "uid": uid}]).doc
    first, second = (s["line"] for s in doc2["scenes"])
    assert first.endswith("，") and second.startswith("而是")
    doc3 = studio_ops.apply_ops(doc2, [{"op": "merge_scenes", "uid": doc2["scenes"][0]["uid"]}]).doc
    assert doc3["scenes"][0]["line"] == "冬天植物死掉往往不是因为冷，而是因为你浇水太多了"
