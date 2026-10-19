# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Tests for the 24 h stock-search response cache.
The autouse conftest fixture points the cache at a per-test temp file."""
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services import stock_search_cache as C


@pytest.mark.asyncio
class TestCacheRoundtrip:
    async def test_put_then_get(self):
        cands = [{"id": 1, "download_url": "http://x/1.mp4", "quality_score": 50}]
        await C.put("pexels", "City Rain ", cands, orientation="portrait", per_page=15)
        # Same normalized query (case/whitespace) → hit.
        got = await C.get("pexels", "city rain", orientation="portrait", per_page=15)
        assert got == cands

    async def test_miss_on_unknown_key(self):
        assert await C.get("pexels", "never stored", orientation="portrait", per_page=15) is None

    async def test_params_differentiate_keys(self):
        await C.put("pexels", "city", [{"id": 1}], orientation="portrait", per_page=15)
        assert await C.get("pexels", "city", orientation="landscape", per_page=15) is None
        assert await C.get("other", "city", orientation="portrait", per_page=15) is None
        assert await C.get("pexels", "city", orientation="portrait", per_page=15) == [{"id": 1}]

    async def test_returned_list_is_a_fresh_copy(self):
        await C.put("pexels", "city", [{"id": 1, "quality_score": 10}], per_page=5)
        a = await C.get("pexels", "city", per_page=5)
        a[0]["quality_score"] = 999  # caller mutates (source bonus does this)
        b = await C.get("pexels", "city", per_page=5)
        assert b[0]["quality_score"] == 10


@pytest.mark.asyncio
class TestTtl:
    async def test_expired_entry_is_a_miss(self, monkeypatch):
        await C.put("pexels", "city", [{"id": 1}], per_page=5)
        later = time.time() + C.TTL_SECONDS + 60       # read BEFORE patching: the lambda must not call the patched time.time
        monkeypatch.setattr(C.time, "time", lambda: later)
        assert await C.get("pexels", "city", per_page=5) is None

    async def test_empty_results_use_short_ttl(self, monkeypatch):
        await C.put("pexels", "obscure query", [], per_page=5)
        # Fresh: an empty list IS a valid cached answer (not a miss).
        assert await C.get("pexels", "obscure query", per_page=5) == []
        # After the short empty-TTL it must expire so a transient API failure
        # can't blank a query for a whole day.
        later = time.time() + C.EMPTY_TTL_SECONDS + 60
        monkeypatch.setattr(C.time, "time", lambda: later)
        assert await C.get("pexels", "obscure query", per_page=5) is None


@pytest.mark.asyncio
class TestFailOpen:
    async def test_get_survives_broken_db(self, monkeypatch):
        def _boom():
            raise RuntimeError("disk on fire")
        monkeypatch.setattr(C, "_connect", _boom)
        assert await C.get("pexels", "city", per_page=5) is None

    async def test_put_survives_broken_db(self, monkeypatch):
        def _boom():
            raise RuntimeError("disk on fire")
        monkeypatch.setattr(C, "_connect", _boom)
        await C.put("pexels", "city", [{"id": 1}], per_page=5)  # must not raise


@pytest.mark.asyncio
class TestSearcherIntegration:
    """The searchers are cache-through: second identical call must not hit HTTP."""

    async def test_pexels_second_call_served_from_cache(self, monkeypatch):
        from backend.services import stock_video_service as S
        payload = {"videos": [
            {"id": 7, "url": "https://www.pexels.com/video/city-rain-777/",
             "duration": 9, "user": {"name": "Ada"}, "image": "http://t/7.jpg",
             "video_files": [
                 {"link": "L", "width": 1920, "height": 1080, "quality": "hd"}]},
        ]}
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value=payload)
        http = MagicMock(get=AsyncMock(return_value=resp))
        monkeypatch.setattr(S, "_http", http)

        first = await S.search_videos("city", orientation="landscape", per_page=15, api_key="k")
        second = await S.search_videos("city", orientation="landscape", per_page=15, api_key="k")
        assert http.get.await_count == 1, "second call must be a cache hit"
        assert [c["id"] for c in second] == [c["id"] for c in first]


@pytest.mark.asyncio
class TestSingleFlight:
    """In-flight dedup — concurrent identical
    searches must share ONE fetch and get private result copies."""

    async def test_concurrent_identical_searches_share_one_fetch(self):
        import asyncio
        calls = 0
        started, release = asyncio.Event(), asyncio.Event()

        async def fetch():
            nonlocal calls
            calls += 1
            started.set()
            await release.wait()
            return [{"id": 1, "quality_score": 5}]

        t1 = asyncio.create_task(C.cached_search("pexels", "same query", fetch, per_page=5))
        await started.wait()
        t2 = asyncio.create_task(C.cached_search("pexels", "same query", fetch, per_page=5))
        await asyncio.sleep(0.01)
        release.set()
        r1, r2 = await asyncio.gather(t1, t2)
        assert calls == 1, "second concurrent search must join the first fetch"
        assert r1 == r2
        assert r1[0] is not r2[0], "joiners must get private copies (mutation safety)"
        # And the result was cached for later callers.
        again = await C.cached_search("pexels", "same query", fetch, per_page=5)
        assert calls == 1 and again == r1

    async def test_failed_fetch_propagates_and_next_call_retries(self):
        async def bad():
            raise RuntimeError("api down")

        with pytest.raises(RuntimeError):
            await C.cached_search("pexels", "boom", bad, per_page=5)
        assert not C._inflight, "failed task must clear the in-flight slot"

        async def good():
            return [{"id": 2}]

        assert await C.cached_search("pexels", "boom", good, per_page=5) == [{"id": 2}]
