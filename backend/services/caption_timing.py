# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Word timings for captions over OUR OWN narration (the Studio's voice takes).

Whisper is used for TIMING ONLY: the narration's true text is known, so it is
aligned onto the timed words and captions never show speech-recognition
homophone errors. The audio is clean single-speaker TTS, so the fast greedy
decode is enough.
"""
from __future__ import annotations

from pathlib import Path


async def timed_segments(path: Path, text: str | None) -> list[dict]:
    """Whisper segments (with `words`) for `path`, their text replaced by
    `text` when it is known. Raises when Whisper can't run — callers decide
    whether that is fatal."""
    from backend.services.caption_service import align_script_to_segments
    from backend.services.whisper_service import whisper_service

    result = await whisper_service.transcribe(Path(path), language=None, quality="fast", timing_only=True)
    segments = result.get("segments") or []
    return align_script_to_segments(text, segments) if text else segments


def flat_words(segments: list[dict]) -> list[dict]:
    """The segments' words as one list of {word, start, end} (ms-rounded)."""
    return [
        {"word": str(w.get("word", "")).strip(), "start": round(float(w["start"]), 3), "end": round(float(w["end"]), 3)}
        for seg in segments for w in (seg.get("words") or [])
        if "start" in w and "end" in w and str(w.get("word", "")).strip()
    ]
