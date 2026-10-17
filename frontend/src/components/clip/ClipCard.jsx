// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { memo } from "react"
import { Box, Typography, Stack, Chip, Tooltip, Checkbox, alpha } from "@mui/material"
import ContentCutIcon from "@mui/icons-material/ContentCut"
import WhatshotIcon from "@mui/icons-material/Whatshot"
import PlayCircleOutlineIcon from "@mui/icons-material/PlayCircleOutline"
import WarningAmberIcon from "@mui/icons-material/WarningAmber"
import { GlassCard } from "../../utils/glassFx"
import { formatTime, viralityColor, hookTypeLabel, clipAspectCss } from "./clipFormat"

/* ── Clip Filmstrip Card ───────────────────────────────────── */

// ?v= is the cache-bust signal: created_at normally, thumb_v after an
// in-place regeneration (same URL otherwise = the browser never shows the new
// image).
const thumbSrc = (clip) =>
  `/api/videos/${clip.id}/thumbnail?v=${encodeURIComponent(clip.thumb_v || clip.created_at || "1")}`

// Two layout modes:
//   - Expanded (default): a 112px-tall thumbnail frame (width by aspect,
//     ≥140px) over a title block — every card the same height, so the strip
//     never reserves room for an off-screen portrait card.
//   - Collapsed: 260px-wide horizontal row (~52px tall) — tiny 9:16 thumb +
//     1-line title + score/duration chips. Lets the user keep the clip
//     filmstrip visible while the preview area gets most of the height.
// Toggled by the user via the unfold icon in the filmstrip toolbar;
// preference persists to localStorage.

export const EXPANDED_THUMB_H = 112
const EXPANDED_MIN_W = 140

function ClipCard({ clip, isSelected, onClick, checked, onCheck, collapsed = false }) {
  const score = clip.clip_virality_score
  const hookLabel = hookTypeLabel(clip.clip_hook_type)
  // Tooltip body — combines reasoning + hook type if present. Keeps the
  // card itself uncluttered while making the AI's "why" one hover away.
  const reason = clip.clip_virality_reason
  const tooltipBody = reason
    ? (hookLabel ? `${hookLabel} — ${reason}` : reason)
    : (hookLabel || null)

  const baseSx = {
    flexShrink: 0,
    cursor: "pointer",
    border: 2,
    borderColor: isSelected ? "primary.main" : "transparent",
    borderRadius: 1.5,
    overflow: "hidden",
    transition: "all 0.2s ease",
    boxShadow: isSelected ? (t) => `0 4px 16px ${alpha(t.palette.primary.main, 0.25)}` : "none",
    "&:hover": {
      borderColor: isSelected ? "primary.main" : "divider",
      boxShadow: (t) => `0 4px 12px ${alpha(t.palette.common.black, 0.1)}`,
    },
  }

  // ── Collapsed row variant ───────────────────────────────────────────
  if (collapsed) {
    return (
      <Tooltip title={tooltipBody || ""} arrow placement="top" disableHoverListener={!tooltipBody}>
        <GlassCard
          onClick={onClick}
          selected={isSelected}
          hover={false}
          cheap
          sx={{
            ...baseSx,
            width: 280, minWidth: 280,
            display: "flex", alignItems: "stretch",
            // No translateY on hover for the row variant — would be visually
            // jumpy inside the dense horizontal scrollbar.
          }}
        >
          {/* Tiny thumb on the left — width follows the clip's aspect at
              the fixed row height (30px portrait, ~92px landscape), so a
              16:9 clip isn't centre-cropped to a vertical sliver. */}
          <Box sx={{
            width: clip.aspect_ratio === "16:9" ? 92 : clip.aspect_ratio === "1:1" ? 52 : 30,
            minWidth: 30, height: 52,
            position: "relative", bgcolor: "#000", flexShrink: 0,
          }}>
            {clip.thumbnail_path ? (
              <Box component="img" src={thumbSrc(clip)} alt=""
                loading="lazy" decoding="async"
                sx={{ width: "100%", height: "100%", objectFit: "cover" }} />
            ) : (
              <Box sx={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <ContentCutIcon sx={{ color: "rgba(255,255,255,0.3)", fontSize: 14 }} />
              </Box>
            )}
            {clip.caption_status === "failed" && (
              <WarningAmberIcon sx={{
                position: "absolute", top: 1, right: 1,
                fontSize: 11, color: "warning.main",
                filter: "drop-shadow(0 0 2px rgba(0,0,0,0.8))",
              }} />
            )}
          </Box>

          {/* Title + meta — flex column with 1-line title and an inline
              chip row underneath. Padding kept tight to fit ~52px height. */}
          <Box sx={{ flex: 1, minWidth: 0, px: 1, py: 0.5, display: "flex", flexDirection: "column", justifyContent: "center" }}>
            <Typography variant="caption" sx={{
              fontWeight: 600, fontSize: "0.72rem", lineHeight: 1.25,
              whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
            }}>
              {clip.title || "Untitled Clip"}
            </Typography>
            <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.25 }}>
              {score != null && (
                <Chip
                  icon={<WhatshotIcon sx={{ fontSize: "11px !important" }} />}
                  label={score.toFixed(1)}
                  size="small"
                  color={viralityColor(score)}
                  sx={{ height: 16, fontWeight: 700, fontSize: "0.6rem", "& .MuiChip-icon": { ml: 0.3 }, "& .MuiChip-label": { px: 0.4 } }}
                />
              )}
              <Typography variant="caption" sx={{ color: "text.secondary", fontSize: "0.62rem" }}>
                {formatTime(clip.duration_seconds)}
              </Typography>
              {hookLabel && (
                <Typography variant="caption" sx={{
                  color: "primary.main", fontSize: "0.6rem", fontWeight: 600,
                  whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", minWidth: 0,
                }}>
                  · {hookLabel}
                </Typography>
              )}
            </Stack>
          </Box>

          {/* Export checkbox — right side, vertically centered */}
          {onCheck && (
            <Box sx={{ display: "flex", alignItems: "center", pr: 0.5 }}>
              <Checkbox
                size="small"
                checked={!!checked}
                onClick={e => { e.stopPropagation(); onCheck(clip.id) }}
                sx={{ p: 0.25, "& .MuiSvgIcon-root": { fontSize: 18 } }}
              />
            </Box>
          )}
        </GlassCard>
      </Tooltip>
    )
  }

  // ── Expanded variant ────────────────────────────────────────────────
  // One thumbnail HEIGHT for every card, width by aspect. The frame used to
  // be 140px wide at the clip's aspect, so a portrait clip stood 249px tall
  // beside 79px landscape ones — and the strip is as tall as its TALLEST card,
  // on screen or not: ~200px of empty panel under a row of landscape cards
  // (audit 2026-09-25). A portrait clip now sits in a 140×112 frame on black
  // (contain — never cropped), a landscape one fills a 199×112 frame.
  const [aw, ah] = clipAspectCss(clip.aspect_ratio).split("/").map(Number)
  const frameW = Math.max(EXPANDED_MIN_W, Math.round(EXPANDED_THUMB_H * (aw / ah)))
  return (
    <GlassCard
      onClick={onClick}
      selected={isSelected}
      hover={false}
      cheap
      data-testid="clip-card"
      sx={{
        ...baseSx,
        width: frameW, minWidth: frameW,
        transform: isSelected ? "translateY(-2px)" : "none",
        "&:hover": {
          ...baseSx["&:hover"],
          transform: "translateY(-2px)",
        },
      }}
    >
      {/* Thumbnail */}
      <Box sx={{ width: "100%", height: EXPANDED_THUMB_H, position: "relative", bgcolor: "#000" }}>
        {clip.thumbnail_path ? (
          <Box component="img" src={thumbSrc(clip)} alt=""
            loading="lazy" decoding="async"
            sx={{ width: "100%", height: "100%", objectFit: "contain" }} />
        ) : (
          <Box sx={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <ContentCutIcon sx={{ color: "rgba(255,255,255,0.3)", fontSize: 28 }} />
          </Box>
        )}
        {/* Export checkbox */}
        {onCheck && (
          <Checkbox
            size="small"
            checked={!!checked}
            onClick={e => { e.stopPropagation(); onCheck(clip.id) }}
            sx={{
              position: "absolute", top: 0, right: 0, zIndex: 2, p: 0.25,
              color: "rgba(255,255,255,0.7)",
              "&.Mui-checked": { color: "#fff" },
              "& .MuiSvgIcon-root": { fontSize: 20, filter: "drop-shadow(0 1px 2px rgba(0,0,0,0.6))" },
            }}
          />
        )}
        {/* Virality badge — wrapped in a Tooltip when the AI returned a
            reason / hook_type, so users get the "why" on hover without
            cluttering the small card. Falls back to no tooltip on legacy
            clips where the AI response didn't carry these fields. */}
        {score != null && (
          tooltipBody ? (
            <Tooltip title={tooltipBody} arrow placement="top">
              <Chip
                icon={<WhatshotIcon sx={{ fontSize: "14px !important" }} />}
                label={score.toFixed(1)}
                size="small"
                color={viralityColor(score)}
                sx={{
                  position: "absolute", top: 4, left: 4,
                  height: 22, fontWeight: 700, fontSize: "0.7rem",
                  "& .MuiChip-icon": { ml: 0.3 },
                }}
              />
            </Tooltip>
          ) : (
            <Chip
              icon={<WhatshotIcon sx={{ fontSize: "14px !important" }} />}
              label={score.toFixed(1)}
              size="small"
              color={viralityColor(score)}
              sx={{
                position: "absolute", top: 4, left: 4,
                height: 22, fontWeight: 700, fontSize: "0.7rem",
                "& .MuiChip-icon": { ml: 0.3 },
              }}
            />
          )
        )}
        {/* Duration badge */}
        <Chip
          label={formatTime(clip.duration_seconds)}
          size="small"
          sx={{
            position: "absolute", bottom: 4, right: 4,
            height: 18, fontSize: "0.6rem", fontWeight: 700,
            bgcolor: "rgba(0,0,0,0.75)", color: "#fff",
            "& .MuiChip-label": { px: 0.5 },
          }}
        />
        {/* Caption warning */}
        {clip.caption_status === "failed" && (
          <Tooltip title="Captions failed to apply">
            <WarningAmberIcon sx={{ position: "absolute", top: 4, right: 4, fontSize: 18, color: "warning.main" }} />
          </Tooltip>
        )}
        {/* Play overlay */}
        <Box sx={{
          position: "absolute", inset: 0,
          display: "flex", alignItems: "center", justifyContent: "center",
          opacity: 0, transition: "opacity 0.2s",
          bgcolor: "rgba(0,0,0,0.3)",
          "&:hover": { opacity: 1 },
        }}>
          <PlayCircleOutlineIcon sx={{ fontSize: 36, color: "#fff" }} />
        </Box>
      </Box>

      {/* Title + optional hook type tag — keeps the card compact. Tag is
          rendered as a tiny outlined pill at the bottom so it visually
          tags the clip without competing with the title. */}
      <Box sx={{ p: 1 }}>
        <Typography variant="caption" sx={{ fontWeight: 600, fontSize: "0.7rem", lineHeight: 1.2, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
          {clip.title || "Untitled Clip"}
        </Typography>
        {hookLabel && (
          <Chip
            label={hookLabel}
            size="small"
            variant="outlined"
            sx={{
              mt: 0.5, height: 16, fontSize: "0.6rem", fontWeight: 600,
              borderColor: "primary.light", color: "primary.main",
              "& .MuiChip-label": { px: 0.6 },
            }}
          />
        )}
      </Box>
    </GlassCard>
  )
}

// Memoized: the page re-renders per pointermove while a bench handle drags,
// and 120 of these re-rendering per mouse event is the difference between a
// smooth drag and a stutter. Props are all primitives + stable callbacks.
export default memo(ClipCard)
