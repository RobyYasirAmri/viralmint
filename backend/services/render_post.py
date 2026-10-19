# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Finishing steps for a Smart Video Studio render, from the user's Settings
(a project can override each one — `settings.post`, None = follow Settings):

  audio      sound effects placed on the word timings, mixed into the audio;
             then the finished mix lifted to the short-form delivery level
  video      auto-zoom pulses on highlighted words

Captions' emoji density is a caption option, carried here so the renderer
reads it from one place.

Every step degrades instead of failing the render, and says so through the
caller's `warn(code, message)` — a user must never get a video missing a step
they turned on without being told.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from backend.core.exceptions import VideoGenerationError

logger = logging.getLogger(__name__)

Warn = Callable[[str, str], Awaitable[None]]

EMOJI_STYLES = ("none", "minimal", "moderate", "heavy")
SFX_STYLES = ("none", "minimal", "moderate", "heavy")

# Delivery level for a finished short (TikTok / Reels / Shorts play around
# -14 LUFS), with peaks held at -1.5 dBTP by a limiter.
DELIVERY_I = -14.0
_DELIVERY_TP = -1.5
_DELIVERY_LIMIT = round(10 ** (_DELIVERY_TP / 20), 4)
# A mix measured wildly off (near-silent, or a broken measurement) is left
# alone rather than blasted.
_DELIVERY_MAX_GAIN_DB = 12.0


@dataclass
class PostOptions:
    sfx: bool = False
    sfx_style: str = "moderate"
    auto_zoom: bool = False
    words_per_group: int = 3
    emoji_style: str = "moderate"

    @property
    def needs_word_timings(self) -> bool:
        return self.sfx or self.auto_zoom


def _setting(user_settings, name: str, default):
    value = getattr(user_settings, name, None) if user_settings is not None else None
    return default if value is None else value


def options_from_settings(user_settings, *, caption_style: str | None = None,
                          overrides: dict | None = None) -> PostOptions:
    """The finishing steps a render applies: the user's Settings, with a
    project's explicit choices (`overrides`, None = follow Settings) on top."""
    from backend.services.caption_service import CAPTION_STYLES

    o = overrides or {}

    def pick(key: str, setting_value):
        return setting_value if o.get(key) is None else o[key]

    emoji = pick("caption_emoji", _setting(user_settings, "caption_emoji_style", "moderate"))
    sfx_style = _setting(user_settings, "sfx_style", "moderate")
    return PostOptions(
        sfx=bool(pick("sfx", bool(_setting(user_settings, "sfx_enabled", False)))),
        sfx_style=sfx_style if sfx_style in SFX_STYLES else "moderate",
        auto_zoom=bool(pick("auto_zoom", bool(_setting(user_settings, "auto_zoom_enabled", False)))),
        words_per_group=int(CAPTION_STYLES.get(caption_style or "", {}).get("words_per_group", 3)),
        emoji_style=emoji if emoji in EMOJI_STYLES else "moderate",
    )


async def load_user_settings(user_id: str = "local"):
    """The user's Settings row (None when there is none yet)."""
    from sqlalchemy import select

    from backend.database import AsyncSessionLocal
    from backend.models.user_settings import UserSettings
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))).scalar_one_or_none()


def delivery_gain(measured: dict | None, target_i: float = DELIVERY_I) -> float | None:
    """The gain (dB) that takes `measured` to `target_i`, or None when no change
    is needed (already within 0.3 LU) or it would be unsafe."""
    try:
        input_i = float((measured or {})["input_i"])
    except (KeyError, TypeError, ValueError):
        return None
    gain = target_i - input_i
    if gain != gain or abs(gain) < 0.3 or abs(gain) > _DELIVERY_MAX_GAIN_DB:   # NaN / -inf too
        return None
    return gain


def delivery_af(gain: float) -> str:
    """`volume` then a fast peak limiter — a narration mix only needs a couple
    of dB, which the limiter takes transparently (`level=0` keeps alimiter
    from re-normalising its output to the ceiling)."""
    return f"volume={gain:.2f}dB,alimiter=limit={_DELIVERY_LIMIT}:attack=5:release=50:level=0"


async def deliver_loudness(audio_path: Path | None, output_path: Path, warn: Warn | None = None) -> Path | None:
    """The finished mix at the delivery level, one gain. Soft: the input when
    no change is needed or on failure (never fails a render) — and says so."""
    if not audio_path:
        return audio_path
    try:
        from backend.core.tool_runners import _measure_loudness
        gain = delivery_gain(await _measure_loudness(Path(audio_path)))
        if gain is None:
            return audio_path

        def _render() -> Path:
            r = subprocess.run(["ffmpeg", "-y", "-i", str(audio_path), "-af", delivery_af(gain),
                                "-c:a", "libmp3lame", "-b:a", "192k", str(output_path)],
                               capture_output=True, text=True, timeout=180)
            if r.returncode != 0 or not output_path.is_file() or output_path.stat().st_size == 0:
                raise VideoGenerationError(f"delivery loudness failed: {(r.stderr or '')[-300:]}")
            return output_path

        return await asyncio.to_thread(_render)
    except Exception as e:  # noqa: BLE001
        logger.warning("Delivery loudness pass failed, keeping the mix as is: %s", e)
        if warn:
            await warn("loudness_failed", "The volume couldn't be levelled — the video may sound quieter than usual.")
        return audio_path


async def add_sfx(audio_path: Path | None, segments: list[dict], opts: PostOptions, warn: Warn | None = None) -> Path | None:
    """Sound effects placed on the word timings and mixed into `audio_path`."""
    if not audio_path or not segments or not opts.sfx or opts.sfx_style == "none":
        return audio_path
    try:
        from backend.services.caption_service import _extract_word_timestamps
        from backend.services.sfx_service import auto_place_sfx, mix_sfx_into_audio
        placements = await auto_place_sfx(_extract_word_timestamps(segments), style=opts.sfx_style)
        return await mix_sfx_into_audio(Path(audio_path), placements) if placements else audio_path
    except Exception as e:  # noqa: BLE001
        logger.warning("SFX mixing failed, continuing without SFX: %s", e)
        if warn:
            await warn("sfx_failed", "Sound effects couldn't be added — the video was rendered without them.")
        return audio_path


async def finish_video(video_path: Path, segments: list[dict], opts: PostOptions, warn: Warn | None = None) -> Path:
    """Auto-zoom pulses on the captioned video (when turned on)."""
    video_path = Path(video_path)
    if segments and opts.auto_zoom:
        try:
            from backend.services.caption_service import _extract_word_timestamps
            from backend.services.ffmpeg_service import apply_auto_zoom
            words = _extract_word_timestamps(segments)
            if words:
                video_path = Path(await apply_auto_zoom(video_path, words, words_per_group=opts.words_per_group))
        except Exception as e:  # noqa: BLE001
            logger.warning("Auto-zoom failed, saving video without zoom: %s", e)
            if warn:
                await warn("auto_zoom_failed", "Auto-zoom failed — the video was saved without zoom pulses.")
    return video_path
