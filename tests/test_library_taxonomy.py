# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""The taxonomy's guards — the ones that stop the invisibility bug returning.

Before the Library index existed, every tool wrote its output to disk and no
surface showed it. The fix is a map from stored key → (label, media, origin),
and a map is only as good as the guarantee that it covers everything. These
tests are that guarantee:

  1. every job type a tool endpoint creates is either classified or explicitly
     recorded as producing no file — never merely absent
  2. a producer's declared media matches the extension its runner writes
  3. the frontend mirror agrees with this map, entry for entry
  4. a key is a library item or an activity-only row, never both

(1) and (3) are the two that would have caught the original bug.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _emitted_job_types() -> set[str]:
    """Every job type this variant actually creates, anywhere in backend/.

    Read out of the source rather than listed here on purpose: a hand-written
    copy is one more thing to forget when a tool is added, and forgetting is
    precisely the failure being guarded against. Backend-wide, not just
    tools.py — a render, a batch or a download that Activity cannot name reads
    as a raw key in the panel.
    """
    found: set[str] = set()
    for py in (REPO / "backend").rglob("*.py"):
        src = py.read_text(encoding="utf-8")
        found.update(re.findall(r'create_job\(\s*"([a-z_]+(?::[a-z_]+)?)"', src))
    return found


def _js_object_keys(js: str, name: str) -> set[str]:
    """Keys of a top-level `export const NAME = { … }` literal in assetModel.js."""
    block = js.split(f"export const {name} = {{", 1)[1].split("\n}\n", 1)[0]
    return set(re.findall(r'^\s*"?([A-Za-z_][\w:]*)"?:\s', block, re.M))


def test_every_tool_endpoint_job_type_is_accounted_for():
    """A tool that writes a file the map doesn't know is invisible in the
    Library — the whole reason this module exists. Being deliberately
    file-less is fine, but it has to be SAID, in NON_LIBRARY_JOB_TYPES."""
    from backend.services.library_taxonomy import NON_LIBRARY_JOB_TYPES, classify

    emitted = _emitted_job_types()
    assert {"scout", "generate", "tool:captions"} <= emitted, (
        "parsed too few job types out of backend/ — did create_job's shape change?"
    )

    unaccounted = sorted(
        jt for jt in emitted
        if classify(jt) is None and jt not in NON_LIBRARY_JOB_TYPES
    )
    assert unaccounted == [], (
        f"job types with no taxonomy entry: {unaccounted} — add them to "
        "PRODUCERS, or to NON_LIBRARY_JOB_TYPES if they genuinely write no file"
    )


def test_the_taxonomy_lists_only_job_types_this_variant_creates():
    """The map was ported from the hosted app, which has tools this one does
    not (AI Image, AI Music, voice cloning, …). A producer or a file-less entry
    for a job type nothing here creates is a filter option, a label and a test
    fixture for a feature that does not exist — so every `tool:` producer and
    every NON_LIBRARY entry must be a job type some `create_job` call emits."""
    from backend.services.library_taxonomy import NON_LIBRARY_JOB_TYPES, PRODUCERS

    emitted = _emitted_job_types()
    phantom_tools = sorted(k for k in PRODUCERS if k.startswith("tool:") and k not in emitted)
    phantom_file_less = sorted(NON_LIBRARY_JOB_TYPES - emitted)
    assert phantom_tools == [], f"producers for tools this variant never runs: {phantom_tools}"
    assert phantom_file_less == [], f"file-less job types nothing creates: {phantom_file_less}"


def test_generated_video_source_types_all_classify():
    """A generated_videos row is filed by its `source_type`; a NULL one is the
    stock render. A source_type written somewhere and missing from the map is a
    video the Library silently drops."""
    from backend.services.library_taxonomy import classify

    written: set[str] = set()
    for py in (REPO / "backend").rglob("*.py"):
        written.update(re.findall(r'source_type\s*=\s*"([a-z_]+)"', py.read_text(encoding="utf-8")))
    assert "clip_extraction" in written, "parsed no source_type literals — did the shape change?"
    unclassified = sorted(t for t in written | {"smart_video"} if classify(t) is None)
    assert unclassified == [], f"generated_videos.source_type values with no producer: {unclassified}"


def test_activity_can_name_every_job_this_variant_creates():
    """Activity labels a job from the frontend twin: PRODUCERS for a job that
    makes a library item, JOB_ONLY_LABELS for one that doesn't. A job type in
    neither shows up in the panel as its raw key ("batch_generate"), and a label
    for a type nothing creates is dead weight carried over from the hosted app.
    A key in both is a contradiction (no pending tile, then a link to the item
    it "didn't" make)."""
    from backend.services.library_taxonomy import normalize_producer_key

    js = (REPO / "frontend/src/components/librarynext/assetModel.js").read_text(encoding="utf-8")
    producers = _js_object_keys(js, "PRODUCERS")
    job_only = _js_object_keys(js, "JOB_ONLY_LABELS")
    assert producers and job_only, "could not parse the maps out of assetModel.js"

    emitted = {normalize_producer_key(t) for t in _emitted_job_types()}
    unnamed = sorted(t for t in emitted if t not in producers and t not in job_only)
    assert unnamed == [], f"job types Activity would show as a raw key: {unnamed}"
    stale = sorted(job_only - emitted)
    assert stale == [], f"Activity labels for job types nothing creates: {stale}"
    both = sorted(job_only & producers)
    assert both == [], f"in PRODUCERS and JOB_ONLY_LABELS at once: {both}"


def test_no_producer_claims_a_job_type_that_is_also_declared_file_less():
    """The two lists answer opposite questions; being in both is a contradiction
    that renders as one (no tile, yet a link to the item it 'didn't' make)."""
    from backend.services.library_taxonomy import NON_LIBRARY_JOB_TYPES, PRODUCERS

    both = sorted(set(PRODUCERS) & set(NON_LIBRARY_JOB_TYPES))
    assert both == [], f"declared as producing a library item AND as producing none: {both}"


def test_producer_media_matches_the_extension_its_runner_writes():
    """The index lets the file extension win over this map, so a mismatch is
    invisible on the tiles and shows up only in /api/library/taxonomy — which
    the UI renders its filters from."""
    from backend.services.library_index import _suffix_media
    from backend.services.library_taxonomy import PRODUCERS

    # producer key → the suffix its runner writes, for the runners that are
    # unambiguous. Tools that emit either media (audio_enhance, transform) are
    # deliberately absent: for those the extension is the only truth.
    KNOWN_SUFFIX = {
        "tool:captions": ".mp4",
        "tool:merge_clips": ".mp4",
        "tool:gif": ".gif",
        "tool:metadata": ".json",
        "tool:auto_chapters": ".txt",
        "tool:subtitle_export": ".srt",
        "tool:voiceover": ".mp3",
    }
    wrong = {
        key: {"declared": PRODUCERS[key].media, "from_extension": _suffix_media(suffix)}
        for key, suffix in KNOWN_SUFFIX.items()
        if _suffix_media(suffix) != PRODUCERS[key].media
    }
    assert wrong == {}, f"producer media disagrees with the artifact: {wrong}"


def test_the_frontend_taxonomy_mirror_does_not_drift():
    """One taxonomy, two files.

    library_taxonomy.py and assetModel.js both carry the producer map because
    one side classifies and the other renders. Nothing but this test compares
    them, and without it a producer can be added, relabelled or re-classified
    on one side while the other quietly disagrees — the Library would then file
    a row one way and label it another.

    The JS map is parsed as text deliberately: no node, no build step, and the
    failure quotes the literal a reviewer reads.
    """
    from backend.services.library_taxonomy import PRODUCERS

    js = (REPO / "frontend/src/components/librarynext/assetModel.js").read_text(encoding="utf-8")
    block = js.split("export const PRODUCERS = {", 1)[1].split("\n}\n", 1)[0]
    entry = re.compile(
        r'^\s*"?([A-Za-z_][\w:]*)"?:\s*\{\s*label:\s*"([^"]*)",\s*'
        r'media:\s*"(\w+)",\s*origin:\s*"(\w+)"\s*\},',
        re.M,
    )
    mirror = {k: (label, media, origin) for k, label, media, origin in entry.findall(block)}
    assert mirror, "could not parse PRODUCERS out of assetModel.js — did its shape change?"

    backend = {k: (p.label, p.media, p.origin) for k, p in PRODUCERS.items()}
    missing_in_js = sorted(set(backend) - set(mirror))
    extra_in_js = sorted(set(mirror) - set(backend))
    disagree = {
        k: {"py": backend[k], "js": mirror[k]}
        for k in sorted(set(backend) & set(mirror))
        if backend[k] != mirror[k]
    }
    assert not missing_in_js, f"producers only the backend knows: {missing_in_js}"
    assert not extra_in_js, f"producers only the frontend knows: {extra_in_js}"
    assert not disagree, f"label/media/origin disagree between the two maps: {disagree}"


def test_agent_style_hyphen_spellings_fold_onto_the_underscore_twin():
    """Endpoints are hyphenated and job types are not; both spellings have
    reached this map at different times, so they must classify identically."""
    from backend.services.library_taxonomy import classify, normalize_producer_key

    assert normalize_producer_key("tool:auto-zoom") == "tool:auto_zoom"
    assert classify("tool:auto-zoom") == classify("tool:auto_zoom")
    assert classify("tool:merge-clips").key == "tool:merge_clips"


def test_an_audio_only_download_is_audio_not_video():
    """The axis collision the whole model exists to resolve: the row is a
    `download` (video by default) and the file is genuinely audio."""
    from backend.services.library_taxonomy import classify

    p = classify("download", media_override="audio")
    assert p.media == "audio"
    assert p.origin == "imported"
    # …and the override must not leak into the shared map.
    assert classify("download").media == "video"


def test_an_unclassified_key_returns_none_rather_than_guessing():
    from backend.services.library_taxonomy import classify

    assert classify("tool:not_a_real_tool") is None
    assert classify(None) is None
    assert classify("") is None
