# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Chinese captions must burn as glyphs, not tofu boxes — under the real
libass + font lookup, on the machine running the tests.

A tofu box looks the same for every character, so two different strings
that render to identical pixels prove the glyphs are missing. (Mapping CJK
to "PingFang SC" did exactly that on current macOS: fontconfig can't see it.)
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from backend.services.caption_service import resolve_caption_font

_needs_cjk_burn = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or sys.platform not in ("darwin", "win32"),
    reason="needs ffmpeg and a platform whose system CJK font is mapped by name")

_ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 400
PlayResY: 200

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},60,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,{text}
"""


def _burn(tmp: Path, font: str, text: str, name: str) -> bytes:
    ass = tmp / f"{name}.ass"
    ass.write_text(_ASS.format(font=font, text=text), encoding="utf-8")
    out = tmp / f"{name}.rgb"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=400x200:d=1",
                    "-frames:v", "1", "-vf", f"ass={ass.name}", "-f", "rawvideo", "-pix_fmt", "gray", out.name],
                   cwd=tmp, check=True, capture_output=True)
    return out.read_bytes()


@_needs_cjk_burn
def test_chinese_captions_render_real_glyphs(tmp_path):
    font = resolve_caption_font("Arial Black", "章鱼")
    a = _burn(tmp_path, font, "章鱼", "a")
    b = _burn(tmp_path, font, "心脏", "b")
    assert any(a), "nothing was drawn at all"
    assert a != b, f"{font!r} burns Chinese as identical boxes (tofu) — fontconfig can't resolve it"


# ── the opening title on a CJK script ───────────────────────────────────────
# libass wraps only at spaces, so a Chinese title was one line at title size
# and ran off both edges of the frame.

def test_a_cjk_title_wraps_inside_the_frame():
    from backend.services import caption_service as cs
    title = "你知道吗，每天早上喝一杯温水，可以让你的身体发生惊人的变化。"
    capacity = (1080 - 80) / cs.hook_font_size(cs.CAPTION_STYLES["urban"], "9:16")
    event = cs._build_hook_event(title, 2.5, capacity_em=capacity)
    lines = event.split("}", 1)[1].strip().split("\\N")
    assert len(lines) > 1 and all(len(line) <= capacity for line in lines)
    assert "".join(lines) == title


def test_latin_titles_keep_wrapping_at_spaces():
    from backend.services import caption_service as cs
    assert "\\N" not in cs._build_hook_event("Make a coin vanish with one simple move", 2.5, capacity_em=8)


def test_the_title_is_on_the_first_frame():
    """No fade-IN: the title is the scroll-stopper, and an early-frame cover must carry it."""
    from backend.services import caption_service as cs
    assert "\\fad(0," in cs._build_hook_event("Hook", 2.5)
