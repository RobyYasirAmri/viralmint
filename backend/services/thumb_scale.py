# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Grid-sized copies of oversized posters.

The Library renders tiles at ~140x148 CSS px and the stored thumbnails are
whatever the render produced — 1920x1080 for a 16:9 output. On the wire that is
a tolerable ~120 KB, which is why it never looked like a problem; DECODED it is
1920*1080*4 = 7.9 MB of bitmap EACH, so one 48-tile page asks the browser to
hold ~380 MB. It can't, so it evicts decoded frames and re-decodes them as they
re-enter the viewport — the "tile goes black, then fills in a second later"
that made scrolling feel like a reload. Not a cache-header problem (those
responses are already `immutable`) and not a browser bug: we were asking for it.

A downscaled copy is written once and served forever after — beside the
original for stored thumbnails, or into THUMBNAILS_DIR for the Library's poster
cache (`scaled_into`), which keeps derived files out of the user's asset dirs.
Widths come from a small allowlist so an attacker (or a typo) cannot fill the
disk with one variant per pixel.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# Retina-safe for the two tile sizes the Library draws (~140 and ~112 wide).
# One entry, not a range: every distinct width is another file on disk.
ALLOWED_WIDTHS = (400,)
DEFAULT_WIDTH = 400


def normalize_width(raw: int | str | None) -> int | None:
    """The requested width, or None to serve the original untouched."""
    if raw in (None, ""):
        return None
    try:
        w = int(raw)
    except (TypeError, ValueError):
        return None
    return w if w in ALLOWED_WIDTHS else None


def _scaled_path(src: Path, width: int, suffix: str | None = None) -> Path:
    return src.with_name(f"{src.stem}.w{width}{suffix or src.suffix or '.jpg'}")


def output_suffix(src: Path) -> str:
    """The container a scaled copy of `src` should be written in.

    JPEG for everything opaque — it is smaller at the same quality. PNG when
    the source carries an alpha channel, because Remove Background writes
    transparent cut-outs and flattening one to JPEG puts a black box behind
    the subject in the grid.
    """
    if src.suffix.lower() == ".gif":
        return ".gif"   # stays a GIF so the tile keeps animating
    if src.suffix.lower() not in (".png", ".webp", ".tif", ".tiff"):
        return ".jpg"
    try:
        from PIL import Image

        with Image.open(src) as im:
            return ".png" if "A" in im.getbands() else ".jpg"
    except Exception:  # noqa: BLE001 — an unreadable source degrades, never 500s
        return ".jpg"


_MEDIA_TYPES = {".png": "image/png", ".gif": "image/gif"}


def media_type(path: Path) -> str:
    """What to serve a scaled copy as — the suffix is chosen by `output_suffix`."""
    return _MEDIA_TYPES.get(path.suffix.lower(), "image/jpeg")


def scaled_siblings(src: Path) -> list[Path]:
    """Every scaled-copy path that may exist beside `src`.

    For deletion sites: whoever unlinks a thumbnail must unlink these too, or
    each deleted row leaves a `X.w400.jpg` orphan forever (the 2026-08-06
    audit rule — a sweeper's reference set must cover EVERY file it derives).

    Both containers are listed for every width. Which one was written depends
    on whether that source had alpha, and a cleanup that has to re-open the
    file to find out would be one Pillow call away from leaking on any source
    it can no longer read.
    """
    return [
        _scaled_path(src, w, suffix)
        for w in ALLOWED_WIDTHS
        for suffix in dict.fromkeys((".jpg", ".png", ".gif", src.suffix or ".jpg"))
    ]


def _build_animated(src: Path, dest: Path, width: int) -> None:
    """Scale an animated GIF, frame by frame, still animated.

    A GIF tile that plays is the point of a GIF, so it cannot be flattened to a
    still — but the library's own GIFs measured 11 MB each at full size, drawn
    into a 200 px tile. Per-frame durations are carried across so the timing
    survives; anything unexpected raises and the caller serves the original.

    128 colours per frame, not 256: at tile size the difference is invisible and
    it is a third off the file (11.1 MB → 7.2 at 256, → 5.7 at 128, measured on
    a real 45-frame library GIF). A single shared palette would be smaller still
    and is NOT used — Pillow's writer crashes on a transparent frame when one is
    passed, which is the kind of failure a thumbnail must never have.
    """
    from PIL import Image, ImageSequence

    colors = 128

    with Image.open(src) as im:
        if not getattr(im, "is_animated", False):
            raise _NotAnimated
        if im.width <= width:
            raise _AlreadySmall
        height = max(1, round(im.height * width / im.width))
        frames, durations = [], []
        for frame in ImageSequence.Iterator(im):
            durations.append(frame.info.get("duration", im.info.get("duration", 100)))
            frames.append(
                frame.convert("RGB").resize((width, height), Image.LANCZOS)
                .convert("P", palette=Image.ADAPTIVE, colors=colors)
            )
        if not frames:
            raise _NotAnimated
        frames[0].save(
            dest, "GIF", save_all=True, append_images=frames[1:],
            duration=durations, loop=im.info.get("loop", 0), optimize=True,
        )


def _build(src: Path, dest: Path, width: int) -> None:
    from PIL import Image

    if dest.suffix.lower() == ".gif":
        try:
            _build_animated(src, dest, width)
            return
        except (_AlreadySmall, _NotAnimated):
            raise
        except Exception:  # noqa: BLE001 — a still GIF still scales below
            logger.debug("animated GIF downscale failed for %s", src, exc_info=True)
            raise

    with Image.open(src) as im:
        if im.width <= width:
            # Already small enough — hardlink/copy so the caller has one rule
            # ("serve the scaled path") instead of two.
            raise _AlreadySmall
        keep_alpha = dest.suffix.lower() == ".png" and "A" in im.getbands()
        im = im.convert("RGBA" if keep_alpha else "RGB")
        height = max(1, round(im.height * width / im.width))
        im = im.resize((width, height), Image.LANCZOS)
        if keep_alpha:
            im.save(dest, "PNG", optimize=True)
        else:
            im.save(dest, "JPEG", quality=82, optimize=True)


class _AlreadySmall(Exception):
    pass


class _NotAnimated(Exception):
    """A .gif with a single frame — nothing to preserve, so serve it as-is."""


def _build_atomic(src: Path, dest: Path, width: int) -> None:
    """Build into a private temp file, then rename it into place.

    A grid asks for its whole page at once, so several requests for the SAME
    poster can be in flight together, and a reader that opens `dest` while
    another thread is still writing it gets a truncated image — cached forever,
    because the half-written file is newer than its source. `os.replace` is
    atomic on both POSIX and Windows, so `dest` only ever exists complete.

    The temp name carries the pid and thread id: two builders racing write to
    different files and the last rename wins, which is fine — they produce the
    same bytes.

    It also KEEPS `dest`'s suffix, because that suffix is what `_build`
    dispatches the encoder on. A plain `<name>.part` silently sent every GIF
    and every transparent cut-out down the JPEG branch — the tests for both
    caught it, which is the reason they assert the decoded image and not just
    that a smaller file appeared.
    """
    tmp = dest.with_name(
        f".{dest.stem}.{os.getpid()}.{threading.get_ident()}.part{dest.suffix}")
    try:
        _build(src, tmp, width)
        os.replace(tmp, dest)
    finally:
        # A failed build (including _AlreadySmall, raised before anything is
        # written) must not leave a .part behind.
        try:
            tmp.unlink(missing_ok=True)
        except OSError:  # pragma: no cover — best effort
            pass


async def scaled_into(src: Path, dest: Path, width: int | None) -> Path:
    """`src` scaled to `width`, written at `dest` rather than beside the source.

    The Library's poster cache lives in THUMBNAILS_DIR, away from the user's
    asset directories, so one sweeper covers every derived image and a stray
    `.w400` never turns up next to a file the user recognises.

    Returns `src` unchanged when no scaling is wanted, the source is already
    small enough, or anything at all goes wrong — a thumbnail that is merely
    too big must never become a 500.
    """
    if not width:
        return src
    try:
        if dest.is_file() and dest.stat().st_mtime >= src.stat().st_mtime:
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(_build_atomic, src, dest, width)
        return dest
    except (_AlreadySmall, _NotAnimated):
        return src
    except Exception:  # noqa: BLE001 — Pillow raises a wide family
        logger.debug("thumbnail downscale failed for %s", src, exc_info=True)
        return src


async def scaled_thumbnail(src: Path, width: int | None) -> Path:
    """`src` scaled to `width`, built once and cached beside it."""
    if not width:
        return src
    return await scaled_into(src, _scaled_path(src, width, output_suffix(src)), width)
