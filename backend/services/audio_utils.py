# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Small shared audio helpers for the Smart Video Studio's voice takes.

  * `probe_audio_duration` / `decoded_audio_duration` — how long a take is.
  * `trim_silence_edges_sync` — strip a synthesised take's padded silence.
  * `concat_audio` — join takes (and spans of silence) into one narration.
"""
import asyncio
import subprocess
from pathlib import Path
from typing import Optional

from backend.core.exceptions import VoiceGenerationError

# A voice take's mp3 must decode to exactly the duration it reports: the
# Studio times every scene from the probed duration and joins the takes by
# decoding them. With libmp3lame's Xing/LAME header the decoder drops the
# encoder padding but ffprobe 7.1 doesn't, so each take read ~0.06 s long;
# across 12+ scenes the joined narration came up short of the planned
# timeline and the render failed its output check. Without the header both
# agree.
MP3_EXACT_DURATION = ("-write_xing", "0")


def probe_audio_duration(path: Path) -> float:
    """Duration in seconds via ffprobe (0.0 on failure). Sync — call via
    to_thread from async contexts."""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=15,
        )
        return float((proc.stdout or "0").strip() or 0.0)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0.0


# Edge silence left on a synthesised take: enough that the first consonant
# isn't clipped, short enough that joined takes don't hiccup at every cut
# (Edge pads ~0.1-0.3 s at each end; with the scene gap on top every line
# break was an audible pause).
TAKE_EDGE_KEEP_S = 0.06
_SILENCE_DB = -45


def trim_silence_edges_sync(src: Path, dst: Path) -> bool:
    """Write `src` to `dst` (mp3) without its leading/trailing silence. True
    only when `dst` was written and is non-empty; the caller keeps `src`
    otherwise. Blocking — call through `asyncio.to_thread`."""
    keep = TAKE_EDGE_KEEP_S
    edge = (f"silenceremove=start_periods=1:start_threshold={_SILENCE_DB}dB"
            f":start_silence={keep}:detection=peak")
    af = f"{edge},areverse,{edge},areverse"
    try:
        r = subprocess.run(["ffmpeg", "-y", "-i", str(src), "-af", af,
                            "-c:a", "libmp3lame", "-b:a", "192k", *MP3_EXACT_DURATION, str(dst)],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    if r.returncode != 0 or not dst.is_file() or dst.stat().st_size == 0:
        return False
    # A take that was all "silence" at this threshold would come back empty —
    # never replace speech with nothing.
    return probe_audio_duration(dst) >= 0.3


async def concat_audio(
    paths, out_path: Path, *, bitrate: str = "192k", timeout_s: int = 900,
) -> Path:
    """Join audio sources end to end into one mp3.

    `paths` entries are a path (use its audio as-is) or a `(path, seconds)`
    pair, which stands for `seconds` of SILENCE in its place — the Studio
    lays the gap between takes this way. The concat *filter* (never the
    demuxer) decodes and resamples every input, so differing sample rates or
    channel counts can't fail the join; `aformat` pins one layout first, as
    the filter requires. Raises VoiceGenerationError.
    """
    items: list[tuple[Path, Optional[float]]] = []
    for entry in paths:
        if isinstance(entry, tuple):
            items.append((Path(entry[0]), entry[1]))
        else:
            items.append((Path(entry), None))
    if not items:
        raise VoiceGenerationError("No audio segments to concatenate")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = len(items)

    def _run() -> None:
        cmd = ["ffmpeg", "-y"]
        pre: list[str] = []
        labels: list[str] = []
        for i, (src, silence_for) in enumerate(items):
            if silence_for is not None:
                cmd += ["-f", "lavfi", "-t", f"{max(0.05, float(silence_for)):.3f}",
                        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
            else:
                cmd += ["-i", str(src)]
            pre.append(f"[{i}:a]aformat=sample_fmts=fltp:sample_rates=44100:"
                       f"channel_layouts=stereo[a{i}]")
            labels.append(f"[a{i}]")
        graph = ";".join(pre + ["".join(labels) + f"concat=n={n}:v=0:a=1[out]"])
        cmd += ["-filter_complex", graph, "-map", "[out]",
                "-c:a", "libmp3lame", "-b:a", bitrate, *MP3_EXACT_DURATION, str(out_path)]
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout_s)
        if proc.returncode != 0 or not out_path.exists() or out_path.stat().st_size == 0:
            err = proc.stderr[-300:].decode("utf-8", "ignore") if proc.stderr else f"exit {proc.returncode}"
            raise VoiceGenerationError(f"Audio concat failed: {err}")

    await asyncio.to_thread(_run)
    return out_path
