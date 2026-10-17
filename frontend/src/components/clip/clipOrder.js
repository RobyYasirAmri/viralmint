// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
/* The clip strip's order — ONE function, used both to draw the strip and to
   pick what "All Clips" opens on. The All Clips card used to preview
   `clips[0]` (the fetch order) while the strip beside it was sorted Top
   Viral, so the inspector showed a clip that wasn't first, or highlighted,
   anywhere on screen (audit 2026-09-25). */

export function visibleClips(clips, { sourceId, query, sortBy }) {
  const all = sourceId === "all"
  const q = (query || "").toLowerCase()
  return (clips || [])
    .filter((c) => {
      if (!sourceId && !all) return false  // nothing selected → show nothing
      if (sourceId && !all && c.source_downloaded_video_id !== sourceId) return false
      if (q) {
        return (c.title || "").toLowerCase().includes(q) ||
          (c.youtube_title || "").toLowerCase().includes(q)
      }
      return true
    })
    .sort((a, b) => {
      if (sortBy === "virality") return (b.clip_virality_score || 0) - (a.clip_virality_score || 0)
      if (sortBy === "newest") return new Date(b.created_at || 0) - new Date(a.created_at || 0)
      if (sortBy === "duration") return (b.duration_seconds || 0) - (a.duration_seconds || 0)
      return 0
    })
}
