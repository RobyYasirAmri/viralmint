// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useState } from "react"
import { Box, Typography, Stack, Chip, IconButton, Tooltip } from "@mui/material"
import ContentCutIcon from "@mui/icons-material/ContentCut"
import PlayCircleOutlineIcon from "@mui/icons-material/PlayCircleOutline"
import VideocamIcon from "@mui/icons-material/Videocam"
import { GlassCard } from "../../utils/glassFx"
import { formatTime } from "./clipFormat"

/* ── Source Video Sidebar Item ──────────────────────────────── */

/**
 * The poster ladder, cheapest first, ONE request at a time and only on
 * failure of the previous rung (the <img> is lazy, so an off-screen card asks
 * for nothing):
 *   1. /downloaded/{id}/thumbnail — the cached thumbnail, or one the server
 *      extracts from the video (t=2s) and caches. Only when the server says it
 *      can serve one (`thumbnail_available`); keying off `video_path` meant a
 *      purged row 404'd AND skipped the scout thumbnail it still had.
 *   2. /downloaded/{id}/frame at ~10% of the duration — a local import has no
 *      thumbnail, and a source shorter than 2s, or one whose first seconds are
 *      black, fails rung 1 while still having frames.
 *   3. the scout's remote thumbnail_url, when there is one.
 * When every rung fails the card SAYS so ("No preview"), never a bare black box.
 */
export function posterLadder(video) {
  const canServe = video.thumbnail_available ?? (video.video_exists ?? Boolean(video.video_path))
  const rungs = []
  if (canServe) {
    rungs.push(`/api/downloaded/${video.id}/thumbnail`)
    if (video.video_exists !== false) {
      const t = Math.max(0, (video.duration_seconds || 0) * 0.1).toFixed(1)
      rungs.push(`/api/downloaded/${video.id}/frame?t=${t}&w=320`)
    }
  }
  if (video.thumbnail_url) rungs.push(video.thumbnail_url)
  return rungs
}

export default function SourceVideoCard({ video, clipCount, isSelected, onClick, onPreview }) {
  const rungs = posterLadder(video)
  const [rung, setRung] = useState(0)
  const poster = rungs[rung] || null
  return (
    <GlassCard
      onClick={onClick}
      selected={isSelected}
      sx={{ p: 1.5, cursor: "pointer", borderRadius: 2.5 }}
    >
      {/* Thumbnail */}
      <Box sx={{
        width: "100%", aspectRatio: "16/9", borderRadius: 2, overflow: "hidden",
        // Black, because the image is CONTAINed below rather than cropped: a
        // portrait source was centre-cropped to a letterbox strip in the one
        // place you pick between sources.
        bgcolor: "#000", mb: 1, position: "relative",
      }}>
        {poster ? (
          <Box component="img"
            key={poster}
            src={poster}
            alt=""
            loading="lazy" decoding="async"
            sx={{ width: "100%", height: "100%", objectFit: "contain" }}
            onError={() => setRung((r) => r + 1)} />
        ) : (
          <Stack data-testid="source-no-preview" alignItems="center" justifyContent="center" spacing={0.25}
            sx={{ width: "100%", height: "100%" }}>
            <VideocamIcon sx={{ color: "grey.500", fontSize: 24 }} />
            <Typography variant="caption" sx={{ color: "grey.400", fontSize: "0.62rem" }}>
              No preview
            </Typography>
          </Stack>
        )}
        {/* Duration badge */}
        {video.duration_seconds > 0 && (
          <Chip
            label={formatTime(video.duration_seconds)}
            size="small"
            sx={{
              position: "absolute", bottom: 4, right: 4,
              height: 20, fontSize: "0.65rem", fontWeight: 700,
              bgcolor: "rgba(0,0,0,0.75)", color: "#fff",
              "& .MuiChip-label": { px: 0.75 },
            }}
          />
        )}
        {/* Preview button — top-right; stopPropagation so it doesn't
            also trigger card selection. Only for a source whose video is on
            disk and therefore streamable. */}
        {onPreview && (video.video_exists ?? Boolean(video.video_path)) && (
          <Tooltip title="Preview video">
            <IconButton
              size="small"
              aria-label="Preview video"
              onClick={(e) => { e.stopPropagation(); onPreview(video) }}
              sx={{
                position: "absolute", top: 4, right: 4,
                bgcolor: "rgba(0,0,0,0.6)", color: "#fff",
                "&:hover": { bgcolor: "rgba(0,0,0,0.8)" },
                p: 0.5,
              }}
            >
              <PlayCircleOutlineIcon sx={{ fontSize: 20 }} />
            </IconButton>
          </Tooltip>
        )}
      </Box>

      <Typography variant="body2" sx={{ fontWeight: 600, fontSize: "0.8rem", lineHeight: 1.3 }} noWrap>
        {video.title || "Untitled"}
      </Typography>
      <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.5 }}>
        <ContentCutIcon sx={{ fontSize: 13, color: clipCount > 0 ? "primary.main" : "text.disabled" }} />
        <Typography variant="caption" sx={{ color: clipCount > 0 ? "primary.main" : "text.secondary", fontWeight: clipCount > 0 ? 700 : 400 }}>
          {clipCount} clip{clipCount !== 1 ? "s" : ""}
        </Typography>
      </Stack>
    </GlassCard>
  )
}

/* ── A source whose file is gone ────────────────────────────────
   Listed, not hidden and not auto-deleted (a read must not mutate): the user
   sees which rows are dead and removes them, or downloads them again when the
   row remembers where it came from. Never selectable — there is nothing to
   put on the bench. */
export function MissingSourceRow({ video, busy, onRemove, onRedownload }) {
  return (
    <Box data-testid="missing-source" sx={{
      px: 1, py: 0.75, borderRadius: 1.5, border: 1, borderColor: "divider",
      bgcolor: "background.paper",
    }}>
      <Typography variant="caption" noWrap title={video.title || ""}
        sx={{ display: "block", fontWeight: 700 }}>
        {video.title || "Untitled"}
      </Typography>
      <Typography variant="caption" sx={{ display: "block", color: "warning.main", fontSize: "0.66rem" }}>
        File missing from disk
      </Typography>
      <Stack direction="row" spacing={0.5} sx={{ mt: 0.5 }}>
        {onRedownload && (
          <Chip size="small" variant="outlined" label="Download again" disabled={busy}
            onClick={() => onRedownload(video)} sx={{ fontSize: "0.66rem", height: 22 }} />
        )}
        <Chip size="small" variant="outlined" color="error" label="Remove" disabled={busy}
          onClick={() => onRemove(video)} sx={{ fontSize: "0.66rem", height: 22 }} />
      </Stack>
    </Box>
  )
}
