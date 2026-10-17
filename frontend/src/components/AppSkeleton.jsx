// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { Box, Skeleton, Stack } from "@mui/material"

/**
 * Reusable loading skeletons. The previous loading affordance across
 * the app was a single CircularProgress in the middle of a blank
 * pane — fast pages snapped through it imperceptibly, slow pages
 * felt frozen. Skeletons preserve layout, so the eye lands on roughly
 * the right structure before data arrives.
 *
 * Variants:
 *   - card-grid  — N cards in a CSS grid (matches Videos / Channels
 *                  thumbnail grids)
 *   - list       — N stacked rows (matches DownloadedListCard,
 *                  CronJobs list, Settings sections)
 *   - hero       — page-hero placeholder (rare — most pages render
 *                  the hero immediately, before data fetch returns)
 *   - studio     — left rail + main canvas, the shape every studio page
 *                  boots into (Clipper today)
 *   - text       — N lines of prose, tapering like a real paragraph
 *                  (ChannelNarrative's AI review while it streams)
 *
 * Variant-specific tweaks (count, item size) flow through props so
 * callers can match their real content's rhythm.
 *
 * NOT everything belongs here. A skeleton whose shape IS the content —
 * DailyIdeasPanel's idea cards, VariationResultStage's result tiles — reads
 * better bespoke; forcing those into a generic variant would make both worse.
 * The rule is the same one that governs EmptyState and PageHero: shared when
 * the shape recurs, local when it's this surface's own.
 */
export default function AppSkeleton({
  variant = "list",
  count = 6,
  cardWidth = 220,
  cardHeight = 180,
  rowHeight = 64,
  railWidth = 200,
  height = 400,
}) {
  if (variant === "studio") {
    return (
      <Box sx={{ p: 3, display: "flex", flexDirection: "column", gap: 2 }}>
        <Skeleton variant="rounded" height={40} width={300} animation="wave" />
        <Stack direction="row" spacing={2}>
          <Skeleton variant="rounded" width={railWidth} height={height} animation="wave" />
          <Skeleton variant="rounded" sx={{ flex: 1 }} height={height} animation="wave" />
        </Stack>
      </Box>
    )
  }

  if (variant === "text") {
    // Taper the line widths — equal-length bars read as a table, not prose.
    const widths = ["95%", "85%", "70%", "88%", "60%"]
    return (
      <Box>
        {Array.from({ length: count }).map((_, i) => (
          <Skeleton key={i} width={widths[i % widths.length]} height={18} animation="wave" />
        ))}
      </Box>
    )
  }

  if (variant === "card-grid") {
    return (
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: `repeat(auto-fill, minmax(${cardWidth}px, 1fr))`,
          gap: 1.5,
        }}
      >
        {Array.from({ length: count }).map((_, i) => (
          <Box key={i} sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
            <Skeleton
              variant="rectangular"
              height={cardHeight}
              sx={{ borderRadius: 2 }}
              animation="wave"
            />
            <Skeleton variant="text" width="80%" animation="wave" />
            <Skeleton variant="text" width="50%" animation="wave" />
          </Box>
        ))}
      </Box>
    )
  }

  if (variant === "hero") {
    return (
      <Box sx={{ px: 3, py: 2.25, borderBottom: 1, borderColor: "divider" }}>
        <Stack direction="row" spacing={1.75} alignItems="center">
          <Skeleton variant="rounded" width={40} height={40} animation="wave" />
          <Stack spacing={0.5} sx={{ flex: 1 }}>
            <Skeleton variant="text" width={140} height={28} animation="wave" />
            <Skeleton variant="text" width={260} height={14} animation="wave" />
          </Stack>
        </Stack>
      </Box>
    )
  }

  // default — list
  return (
    <Stack spacing={1.25}>
      {Array.from({ length: count }).map((_, i) => (
        <Box
          key={i}
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 1.5,
            p: 1.25,
            border: 1,
            borderColor: "divider",
            borderRadius: 2,
            bgcolor: "background.paper",
            height: rowHeight,
          }}
        >
          <Skeleton variant="rounded" width={48} height={48} animation="wave" />
          <Stack spacing={0.5} sx={{ flex: 1 }}>
            <Skeleton variant="text" width="40%" animation="wave" />
            <Skeleton variant="text" width="65%" animation="wave" />
          </Stack>
        </Box>
      ))}
    </Stack>
  )
}
