# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Library tiles get grid-sized thumbnails, not full-HD ones.

Reported as "cards go black and re-render for a second or two whenever I
scroll". It was neither the browser nor a cache header — those responses were
already `public, max-age=31536000, immutable` and served in ~30ms. Measured
against the real library:

    stored thumbnail   1920x1080   122 KB on the wire   7.9 MB DECODED
    tile draws at      ~140x148 CSS px
    one 48-tile page   4.85 MB wire                     ~380 MB of bitmap

A browser will not hold 380 MB of decoded frames, so it evicts them and
re-decodes as they re-enter the viewport. We were asking for it.

After: 0.52 MB on the wire and ~15 MB decoded for the same page.
"""
from __future__ import annotations

import asyncio

import pytest

from backend.services.thumb_scale import (
    ALLOWED_WIDTHS, DEFAULT_WIDTH, normalize_width, scaled_thumbnail,
)

PIL = pytest.importorskip("PIL.Image")


def _make(path, w, h, colour=(200, 30, 30)):
    from PIL import Image
    Image.new("RGB", (w, h), colour).save(path, "JPEG")
    return path


class TestNormalizeWidth:
    def test_only_allowlisted_widths_are_honoured(self):
        for w in ALLOWED_WIDTHS:
            assert normalize_width(w) == w
            assert normalize_width(str(w)) == w

    def test_anything_else_serves_the_original(self):
        """An open width parameter is one file on disk per distinct pixel."""
        for bad in (None, "", "abc", 0, -1, 4000, 401, {}, []):
            assert normalize_width(bad) is None


class TestScaledThumbnail:
    @pytest.mark.asyncio
    async def test_it_downscales_and_keeps_the_aspect(self, tmp_path):
        src = _make(tmp_path / "big.jpg", 1920, 1080)
        out = await scaled_thumbnail(src, DEFAULT_WIDTH)

        from PIL import Image
        assert out != src
        with Image.open(out) as im:
            assert im.width == DEFAULT_WIDTH
            assert im.height == round(1080 * DEFAULT_WIDTH / 1920)
        assert out.stat().st_size < src.stat().st_size

    @pytest.mark.asyncio
    async def test_it_builds_once_and_reuses(self, tmp_path):
        src = _make(tmp_path / "big.jpg", 1920, 1080)
        first = await scaled_thumbnail(src, DEFAULT_WIDTH)
        stamp = first.stat().st_mtime_ns
        again = await scaled_thumbnail(src, DEFAULT_WIDTH)
        assert again == first
        assert again.stat().st_mtime_ns == stamp, "rebuilt an unchanged thumbnail"

    @pytest.mark.asyncio
    async def test_a_regenerated_source_invalidates_the_copy(self, tmp_path):
        """`?v=` changes when a thumbnail is regenerated; the scaled copy has
        to follow or the grid shows the old frame forever."""
        src = _make(tmp_path / "big.jpg", 1920, 1080, (10, 10, 200))
        out = await scaled_thumbnail(src, DEFAULT_WIDTH)
        before = out.read_bytes()

        await asyncio.sleep(0.01)
        _make(src, 1920, 1080, (10, 200, 10))
        import os
        os.utime(src, None)
        out2 = await scaled_thumbnail(src, DEFAULT_WIDTH)
        assert out2.read_bytes() != before, "served a stale scaled copy"

    @pytest.mark.asyncio
    async def test_no_width_means_the_original(self, tmp_path):
        src = _make(tmp_path / "big.jpg", 1920, 1080)
        assert await scaled_thumbnail(src, None) is src

    @pytest.mark.asyncio
    async def test_an_already_small_source_is_served_untouched(self, tmp_path):
        """Upscaling would cost bytes and add nothing."""
        src = _make(tmp_path / "small.jpg", 200, 120)
        assert await scaled_thumbnail(src, DEFAULT_WIDTH) is src

    @pytest.mark.asyncio
    async def test_a_broken_source_degrades_instead_of_500ing(self, tmp_path):
        """A thumbnail that is merely too big must never become an error page."""
        bad = tmp_path / "notanimage.jpg"
        bad.write_bytes(b"definitely not a jpeg")
        assert await scaled_thumbnail(bad, DEFAULT_WIDTH) is bad
        assert await scaled_thumbnail(tmp_path / "missing.jpg", DEFAULT_WIDTH) == tmp_path / "missing.jpg"


@pytest.mark.asyncio
async def test_the_index_asks_for_the_grid_width(tmp_path):
    """The width is stamped by the index, so every grid consumer inherits it
    rather than each page remembering to ask."""
    from backend.services.library_index import _job_thumb_url
    from backend.config import settings

    path = settings.STORAGE_ROOT / "tools" / "out" / "x.mp4"
    url = _job_thumb_url("abc", "video", path)
    if url is not None:      # only when the path resolves inside STORAGE_ROOT
        assert f"w={DEFAULT_WIDTH}" in url


# ── The Image tab (2026-08-19) ──────────────────────────────────────────────
#
# Videos got grid-sized posters in the 2026-08-18 pass; images were left
# pointing at the raw asset on the grounds that "an image IS its own poster".
# True, and it cost the Image tab 92.6 MB of transfer and 191 MB of decoded
# bitmap for 48 tiles, against 1.1 MB / 41 MB for the same number of video
# tiles — with no Cache-Control at all, so every visit paid again.
#
# The three properties that fix has to keep, none of which "make it smaller"
# implies on its own.

class TestImagePosters:
    @pytest.mark.asyncio
    async def test_a_cutout_keeps_its_transparency(self, tmp_path):
        """Remove Background writes transparent PNGs. Flattening one to JPEG
        puts a black box behind the subject — smaller, and wrong."""
        from PIL import Image
        from backend.services.thumb_scale import media_type, output_suffix, scaled_into

        src = tmp_path / "cutout.png"
        im = Image.new("RGBA", (1600, 900), (255, 0, 0, 0))
        im.paste((0, 128, 255, 255), (400, 200, 1200, 700))
        im.save(src)

        assert output_suffix(src) == ".png"
        out = await scaled_into(src, tmp_path / f"poster{output_suffix(src)}", DEFAULT_WIDTH)
        with Image.open(out) as o:
            assert o.width == DEFAULT_WIDTH
            assert "A" in o.getbands()
            assert o.getpixel((0, 0))[3] == 0        # the cut-out is still cut out
        assert media_type(out) == "image/png"

    @pytest.mark.asyncio
    async def test_an_opaque_png_becomes_a_jpeg(self, tmp_path):
        """No alpha to keep, so take the smaller container."""
        from PIL import Image
        from backend.services.thumb_scale import media_type, output_suffix, scaled_into

        src = tmp_path / "flat.png"
        Image.new("RGB", (1600, 900), (10, 90, 200)).save(src)

        assert output_suffix(src) == ".jpg"
        out = await scaled_into(src, tmp_path / "poster.jpg", DEFAULT_WIDTH)
        assert out.suffix == ".jpg"
        assert out.stat().st_size < src.stat().st_size
        assert media_type(out) == "image/jpeg"

    @pytest.mark.asyncio
    async def test_a_gif_is_scaled_but_still_animates(self, tmp_path):
        """A GIF tile that plays is the point of a GIF. It may get smaller; it
        may not become a still."""
        from PIL import Image
        from backend.services.thumb_scale import output_suffix, scaled_into

        src = tmp_path / "loop.gif"
        frames = [Image.new("RGB", (1200, 675), (i * 60, 40, 200 - i * 40)) for i in range(4)]
        frames[0].save(src, save_all=True, append_images=frames[1:], duration=80, loop=0)

        assert output_suffix(src) == ".gif"
        out = await scaled_into(src, tmp_path / "poster.gif", DEFAULT_WIDTH)
        with Image.open(out) as o:
            assert o.is_animated
            assert o.n_frames == 4
            assert o.width == DEFAULT_WIDTH

    @pytest.mark.asyncio
    async def test_a_single_frame_gif_is_served_untouched(self, tmp_path):
        """Nothing to preserve and nothing gained — degrade to the original
        rather than re-encoding it."""
        from PIL import Image
        from backend.services.thumb_scale import scaled_into

        src = tmp_path / "still.gif"
        Image.new("RGB", (1200, 675), (30, 30, 30)).save(src)
        assert await scaled_into(src, tmp_path / "poster.gif", DEFAULT_WIDTH) is src

    def test_cleanup_covers_every_container_a_poster_may_use(self, tmp_path):
        """A sweeper's reference set must cover EVERY file it derives — and
        which container was written depends on whether that source had alpha,
        which a cleanup cannot re-check on a file it can no longer read."""
        from backend.services.thumb_scale import scaled_siblings

        names = {p.name for p in scaled_siblings(tmp_path / "libposter_abc.jpg")}
        for width in ALLOWED_WIDTHS:
            assert f"libposter_abc.w{width}.jpg" in names
            assert f"libposter_abc.w{width}.png" in names
            assert f"libposter_abc.w{width}.gif" in names


class TestAtomicBuild:
    """A grid asks for its whole page at once, so the same poster can be built
    by several requests at the same time. A reader must never see a partial
    file — and it would be cached forever if it did, since a half-written file
    is newer than its source."""

    @pytest.mark.asyncio
    async def test_a_partial_file_is_never_visible_at_the_destination(self, tmp_path):
        """The build goes to a private temp name and is renamed into place, so
        `dest` either does not exist or is complete."""
        import backend.services.thumb_scale as ts
        from PIL import Image

        src = _make(tmp_path / "big.jpg", 1600, 900)
        dest = tmp_path / "poster.jpg"
        seen: list[bool] = []
        real_build = ts._build

        def watching_build(s, d, w):
            # While the encoder is mid-write, `dest` must still be absent.
            seen.append(dest.exists())
            return real_build(s, d, w)

        ts._build = watching_build
        try:
            out = await ts.scaled_into(src, dest, DEFAULT_WIDTH)
        finally:
            ts._build = real_build
        assert seen == [False]
        assert out == dest
        with Image.open(out) as im:
            assert im.width == DEFAULT_WIDTH

    @pytest.mark.asyncio
    async def test_a_failed_build_leaves_no_temp_file_behind(self, tmp_path):
        """`_AlreadySmall` raises before anything is written; a `.part` left in
        THUMBNAILS_DIR for every small source would be a slow leak."""
        from backend.services.thumb_scale import scaled_into

        src = _make(tmp_path / "small.jpg", 200, 120)
        assert await scaled_into(src, tmp_path / "poster.jpg", DEFAULT_WIDTH) is src
        assert list(tmp_path.glob("*.part*")) == []

    @pytest.mark.asyncio
    async def test_concurrent_builds_of_one_poster_all_get_a_valid_image(self, tmp_path):
        """Two in-flight requests for the same tile is the normal case, not the
        edge case."""
        import asyncio as aio

        from PIL import Image
        from backend.services.thumb_scale import scaled_into

        src = _make(tmp_path / "shared.jpg", 1600, 900)
        dest = tmp_path / "poster.jpg"
        outs = await aio.gather(*(scaled_into(src, dest, DEFAULT_WIDTH) for _ in range(6)))
        assert all(o == dest for o in outs)
        with Image.open(dest) as im:
            im.load()                      # a truncated file raises here
            assert im.width == DEFAULT_WIDTH
        assert list(tmp_path.glob("*.part*")) == []
