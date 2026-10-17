// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { toDate } from "../../utils/format"

// "Clip the newest upload" (Clipper's sources pane, 2026-10-15): the one
// weekly reason to come back — the channel you follow posted, cut it. These
// are the pure rules; ChannelNewest.jsx is the UI around them.

/** Channels shown in the rail — the pane is a list of sources, not of channels. */
export const MAX_CHANNELS = 5

/** When a channel video was published: ISO (YouTube `published_at`), UNIX
 *  seconds (TikTok `created_at` / `timestamp`) — the channel API's own shapes. */
export function publishedAt(video) {
  if (!video) return null
  return toDate(video.published_at || video.created_at || video.timestamp || null)
}

/** The newest video that has a URL (nothing to download otherwise), or null. */
export function newestOf(videos) {
  let best = null
  let bestAt = -Infinity
  for (const v of videos || []) {
    if (!v?.url) continue
    const d = publishedAt(v)
    const at = d ? d.getTime() : -Infinity
    if (!best || at > bestAt) { best = v; bestAt = at }
  }
  return best
}

/** The Clipper source that IS this channel video, if it was already
 *  downloaded: the stored `source_url` is the link the download was asked
 *  for, so an exact match comes first; a YouTube id inside any URL shape
 *  (`watch?v=`, `/shorts/`, `youtu.be/`) is the fallback. Null when it is
 *  not a source yet. */
export function sourceFor(sources, video) {
  if (!video?.url) return null
  const url = String(video.url)
  const exact = (sources || []).find((s) => s.source_url && String(s.source_url) === url)
  if (exact) return exact
  const id = String(video.video_id || "").trim()
  if (!id) return null
  const re = new RegExp(`(?:[?&]v=|/shorts/|youtu\\.be/|/video/)${id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?:[?&#/]|$)`)
  return (sources || []).find((s) => s.source_url && re.test(String(s.source_url))) || null
}
