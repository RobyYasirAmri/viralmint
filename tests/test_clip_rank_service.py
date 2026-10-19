# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Tests for the LLM relevance re-rank .
The dollar-adjacent property under test: any failure mode returns the
heuristic order — the re-rank can only ever reorder, never lose a scene."""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services import clip_rank_service as R


def _cands(n, prefix="c"):
    return [
        {"id": f"{prefix}{j}", "source": "pexels", "download_url": f"http://x/{j}.mp4",
         "desc_words": ["word", str(j)], "duration": 10, "width": 1920, "height": 1080,
         "popularity": 0, "quality_score": 100 - j}
        for j in range(n)
    ]


def _items(scene_specs):
    """scene_specs: {scene_idx: n_candidates}"""
    return [
        {"scene_idx": idx, "text": f"narration {idx}", "mood": "neutral",
         "candidates": _cands(n, prefix=f"s{idx}_")}
        for idx, n in scene_specs.items()
    ]


def _ai(reply):
    return MagicMock(chat=AsyncMock(return_value=reply))


@pytest.mark.asyncio
class TestRankSceneCandidates:
    async def test_llm_order_wins(self):
        items = _items({0: 4})
        reply = json.dumps([{"scene": 0, "ranked": ["c2", "c0", "c3"]}])
        out = await R.rank_scene_candidates(items, _ai(reply))
        assert [c["id"] for c in out[0]] == ["s0_2", "s0_0", "s0_3"]

    async def test_no_ai_client_keeps_heuristic_order(self):
        items = _items({0: 5, 3: 2})
        out = await R.rank_scene_candidates(items, None)
        assert [c["id"] for c in out[0]] == ["s0_0", "s0_1", "s0_2"]
        assert [c["id"] for c in out[3]] == ["s3_0", "s3_1"]

    async def test_llm_failure_keeps_heuristic_order(self):
        items = _items({0: 4})
        ai = MagicMock(chat=AsyncMock(side_effect=RuntimeError("timeout")))
        out = await R.rank_scene_candidates(items, ai)
        assert [c["id"] for c in out[0]] == ["s0_0", "s0_1", "s0_2"]

    async def test_garbage_json_keeps_heuristic_order(self, monkeypatch):
        # ai_fix_json also fails → heuristic order everywhere.
        async def _no_fix(*a, **k):
            return None
        import backend.core.ai_retry as ai_retry
        monkeypatch.setattr(ai_retry, "ai_fix_json", _no_fix)
        items = _items({0: 4})
        out = await R.rank_scene_candidates(items, _ai("totally not json"))
        assert [c["id"] for c in out[0]] == ["s0_0", "s0_1", "s0_2"]

    async def test_partial_response_scene_missing_gets_heuristic(self):
        items = _items({0: 4, 1: 4})
        reply = json.dumps([{"scene": 1, "ranked": ["c3", "c1"]}])
        out = await R.rank_scene_candidates(items, _ai(reply))
        assert [c["id"] for c in out[0]] == ["s0_0", "s0_1", "s0_2"]  # untouched
        # Scene 1: LLM picks first, padded back to TOP_N from heuristic order.
        assert [c["id"] for c in out[1]] == ["s1_3", "s1_1", "s1_0"]

    async def test_bogus_ids_are_dropped(self):
        items = _items({0: 3})
        reply = json.dumps([{"scene": 0, "ranked": ["c9", "banana", "c1", "c1"]}])
        out = await R.rank_scene_candidates(items, _ai(reply))
        # c9/banana invalid, duplicate c1 collapsed, padded from heuristic.
        assert [c["id"] for c in out[0]] == ["s0_1", "s0_0", "s0_2"]

    async def test_single_candidate_scenes_skip_the_llm(self):
        items = _items({0: 1, 1: 1})
        ai = MagicMock(chat=AsyncMock())
        out = await R.rank_scene_candidates(items, ai)
        ai.chat.assert_not_awaited()
        assert [c["id"] for c in out[0]] == ["s0_0"]

    async def test_markdown_fenced_json_is_parsed(self):
        items = _items({0: 3})
        reply = "```json\n" + json.dumps([{"scene": 0, "ranked": ["c1"]}]) + "\n```"
        out = await R.rank_scene_candidates(items, _ai(reply))
        assert out[0][0]["id"] == "s0_1"

    async def test_candidates_truncated_to_max(self):
        items = _items({0: R.MAX_CANDIDATES_PER_SCENE + 5})
        ai = _ai(json.dumps([{"scene": 0, "ranked": ["c0"]}]))
        await R.rank_scene_candidates(items, ai)
        prompt = ai.chat.await_args.kwargs["messages"][0]["content"]
        assert f"c{R.MAX_CANDIDATES_PER_SCENE - 1}" in prompt
        assert f"c{R.MAX_CANDIDATES_PER_SCENE}]" not in prompt

    async def test_empty_items_no_call(self):
        ai = MagicMock(chat=AsyncMock())
        assert await R.rank_scene_candidates([], ai) == {}
        ai.chat.assert_not_awaited()
