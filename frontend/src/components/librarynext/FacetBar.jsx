// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
/**
 * FacetBar — the two axes, made visible (prototype).
 *
 * Row 1 is WHAT IT IS (media). Row 2 is WHERE IT CAME FROM (origin) plus the
 * narrowing controls. Keeping them on separate rows is the whole point: the
 * current page mixes both into one tab strip, so items with two true answers
 * have to be filed under one.
 */
import {
  Box, Typography, Stack, Select, MenuItem, IconButton, Tooltip,
  ToggleButton, ToggleButtonGroup, alpha, useTheme,
} from "@mui/material"
import ViewComfyRoundedIcon from "@mui/icons-material/ViewComfyRounded"
import ViewModuleRoundedIcon from "@mui/icons-material/ViewModuleRounded"
import GridViewRoundedIcon from "@mui/icons-material/GridViewRounded"
import AccountTreeRoundedIcon from "@mui/icons-material/AccountTreeRounded"
import MovieRoundedIcon from "@mui/icons-material/MovieRounded"
import ImageRoundedIcon from "@mui/icons-material/ImageRounded"
import GraphicEqRoundedIcon from "@mui/icons-material/GraphicEqRounded"
import DescriptionRoundedIcon from "@mui/icons-material/DescriptionRounded"
import AppsRoundedIcon from "@mui/icons-material/AppsRounded"
import { ORIGINS, ORIGIN_KEYS, MEDIA_KEYS, MEDIA, originColor, originTextColor, classify } from "./assetModel"

const MEDIA_ICON = {
  all: AppsRoundedIcon,
  video: MovieRoundedIcon,
  image: ImageRoundedIcon,
  audio: GraphicEqRoundedIcon,
  doc: DescriptionRoundedIcon,
}

export default function FacetBar({
  media, onMediaChange,
  origins, onToggleOrigin,
  producer, onProducerChange, producerOptions,
  sort, onSortChange,
  view, onViewChange,
  dense, onDenseChange,
  mediaCounts, originCounts,
}) {
  const theme = useTheme()
  const isDark = theme.palette.mode === "dark"
  const tabs = ["all", ...MEDIA_KEYS]

  return (
    <Box sx={{ px: { xs: 2, md: 3 }, pt: 1.5, pb: 1.25 }}>
      {/* ── Axis 1: media (+ the view controls, right) ──
          The view toggle used to end row 2, and at 1024 px that row wrapped it
          onto a third line of its own. Row 1 has the room. The tab strip
          scrolls sideways when it can't fit (390 px clipped "Files" off the
          edge with no way to reach it). */}
      <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 1.1, minWidth: 0 }}>
        <Box sx={{
          minWidth: 0, overflowX: "auto", scrollbarWidth: "none",
          "&::-webkit-scrollbar": { display: "none" },
          // Room for the focus ring, which the scroller would otherwise clip.
          p: "3px", m: "-3px",
          // On a phone the strip runs past the edge; a fade says "there's
          // more — scroll", where a hard cut read as a rendering bug.
          maskImage: { xs: "linear-gradient(90deg, #000 82%, transparent)", sm: "none" },
        }}>
        <Box role="tablist" aria-label="What it is" sx={{
          display: "inline-flex", gap: 0.4, p: 0.4, borderRadius: "999px",
          bgcolor: isDark ? alpha("#fff", 0.04) : alpha("#000", 0.035),
        }}>
          {tabs.map((k) => {
            const Icon = MEDIA_ICON[k]
            const active = media === k
            const count = mediaCounts[k] ?? 0
            return (
              <Box
                key={k}
                role="tab"
                aria-selected={active}
                tabIndex={0}
                onClick={() => onMediaChange(k)}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onMediaChange(k) } }}
                sx={{
                  display: "flex", alignItems: "center", gap: 0.6, flexShrink: 0, whiteSpace: "nowrap",
                  px: 1.3, height: 30, borderRadius: "999px", cursor: "pointer",
                  bgcolor: active ? "background.paper" : "transparent",
                  boxShadow: active ? theme.customShadows?.sm : "none",
                  color: active ? "text.primary" : "text.secondary",
                  transition: "all 0.12s ease",
                  "&:hover": { color: "text.primary" },
                }}
              >
                <Icon sx={{ fontSize: 16, color: active ? "primary.main" : "inherit" }} />
                <Typography sx={{ fontSize: "0.79rem", fontWeight: active ? 700 : 500, letterSpacing: "-0.01em" }}>
                  {k === "all" ? "All" : MEDIA[k].label}
                </Typography>
                <Typography sx={{
                  fontSize: "0.68rem", fontWeight: 600, fontVariantNumeric: "tabular-nums",
                  color: "text.secondary",
                }}>
                  {count}
                </Typography>
              </Box>
            )
          })}
        </Box>
        </Box>
        <Typography sx={{ fontSize: "0.7rem", color: "text.secondary", display: { xs: "none", lg: "block" }, flexShrink: 0 }}>
          what it is
        </Typography>

        <Box sx={{ flex: 1 }} />

        <ToggleButtonGroup
          size="small" exclusive value={view}
          onChange={(_, v) => v && onViewChange(v)}
          aria-label="Layout"
          sx={{
            height: 28, flexShrink: 0,
            "& .MuiToggleButton-root": { px: 1.1, fontSize: "0.72rem", textTransform: "none", gap: 0.5 },
          }}
        >
          <ToggleButton value="grid" aria-label="Grid view">
            <GridViewRoundedIcon sx={{ fontSize: 15 }} />
            <Box component="span" sx={{ display: { xs: "none", sm: "inline" } }}>Grid</Box>
          </ToggleButton>
          <ToggleButton value="tree" aria-label="Group by source">
            <AccountTreeRoundedIcon sx={{ fontSize: 15 }} />
            <Box component="span" sx={{ display: { xs: "none", sm: "inline" } }}>By source</Box>
          </ToggleButton>
        </ToggleButtonGroup>

        {/* Density only means something for the grid — the tree has its own
            fixed row heights, so the control is hidden there, not inert. */}
        {view === "grid" && (
          <Tooltip title={dense ? "Comfortable tiles" : "Dense tiles"}>
            <IconButton size="small" onClick={() => onDenseChange(!dense)}
              aria-label={dense ? "Comfortable tiles" : "Dense tiles"}
              aria-pressed={dense}
              sx={{ border: 1, borderColor: "divider", borderRadius: "8px", width: 28, height: 28, flexShrink: 0 }}>
              {dense ? <ViewModuleRoundedIcon sx={{ fontSize: 16 }} /> : <ViewComfyRoundedIcon sx={{ fontSize: 16 }} />}
            </IconButton>
          </Tooltip>
        )}
      </Stack>

      {/* ── Axis 2: origin + narrowing ── */}
      <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap" useFlexGap>
        <Typography sx={{
          fontSize: "0.62rem", fontWeight: 700, letterSpacing: "0.09em",
          textTransform: "uppercase", color: "text.secondary", mr: 0.2,
        }}>
          From
        </Typography>
        {ORIGIN_KEYS.map((k) => {
          const active = origins.includes(k)
          const oc = originColor(k, isDark)
          // Words take the readable step-down (see originTextColor); fills,
          // borders and the dot keep the brand hue.
          const ocText = originTextColor(k, isDark)
          return (
            // describeChild: the hint is a DESCRIPTION. Without it MUI makes
            // the hint the chip's accessible name, and "Created" was announced
            // as "Made in ViralMint from a prompt, script or brief".
            <Tooltip key={k} title={ORIGINS[k].hint} enterDelay={500} describeChild>
              <Box
                role="checkbox"
                aria-checked={active}
                aria-label={`${ORIGINS[k].label}, ${originCounts[k] ?? 0}`}
                tabIndex={0}
                onClick={() => onToggleOrigin(k)}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onToggleOrigin(k) } }}
                sx={{
                  display: "inline-flex", alignItems: "center", gap: 0.6,
                  height: 28, px: 1.1, borderRadius: "999px", cursor: "pointer",
                  border: 1,
                  borderColor: active ? alpha(oc, 0.5) : "divider",
                  bgcolor: active ? alpha(oc, isDark ? 0.16 : 0.09) : "transparent",
                  color: active ? ocText : "text.secondary",
                  transition: "all 0.12s ease",
                  "&:hover": { borderColor: alpha(oc, 0.5), color: ocText },
                }}
              >
                <Box sx={{
                  width: 7, height: 7, borderRadius: "50%",
                  bgcolor: active ? oc : alpha(oc, 0.4),
                }} />
                <Typography sx={{ fontSize: "0.76rem", fontWeight: active ? 700 : 500 }}>
                  {ORIGINS[k].label}
                </Typography>
                <Typography sx={{
                  fontSize: "0.66rem", fontWeight: 600, fontVariantNumeric: "tabular-nums",
                  color: active ? ocText : "text.secondary",
                }}>
                  {originCounts[k] ?? 0}
                </Typography>
              </Box>
            </Tooltip>
          )
        })}

        <Typography sx={{ fontSize: "0.7rem", color: "text.secondary", display: { xs: "none", lg: "block" }, ml: 0.3 }}>
          where it came from
        </Typography>

        <Box sx={{ width: "1px", height: 20, bgcolor: "divider", mx: 0.5, display: { xs: "none", sm: "block" } }} />

        <Select
          size="small" value={producer} onChange={(e) => onProducerChange(e.target.value)}
          aria-label="Filter by tool"
          sx={{ height: 28, fontSize: "0.76rem", "& .MuiSelect-select": { py: 0 }, minWidth: 132 }}
        >
          <MenuItem value="all" sx={{ fontSize: "0.8rem" }}>Any tool</MenuItem>
          {/* A `?tool=` from a link lands before the facets that list it (or
              filters every match away) — keep it a valid option so the Select
              shows it instead of blanking and warning "out-of-range value". */}
          {producer !== "all" && !producerOptions.some((p) => p.key === producer) && (
            <MenuItem value={producer} sx={{ fontSize: "0.8rem" }}>{classify(producer).label}</MenuItem>
          )}
          {producerOptions.map((p) => (
            <MenuItem key={p.key} value={p.key} sx={{ fontSize: "0.8rem" }}>
              {p.label} <Box component="span" sx={{ ml: 0.6, color: "text.secondary" }}>{p.count}</Box>
            </MenuItem>
          ))}
        </Select>

        <Select
          size="small" value={sort} onChange={(e) => onSortChange(e.target.value)}
          aria-label="Sort"
          sx={{ height: 28, fontSize: "0.76rem", "& .MuiSelect-select": { py: 0 }, minWidth: 116 }}
        >
          <MenuItem value="newest" sx={{ fontSize: "0.8rem" }}>Newest</MenuItem>
          <MenuItem value="oldest" sx={{ fontSize: "0.8rem" }}>Oldest</MenuItem>
          <MenuItem value="longest" sx={{ fontSize: "0.8rem" }}>Longest</MenuItem>
          <MenuItem value="title" sx={{ fontSize: "0.8rem" }}>Title A–Z</MenuItem>
        </Select>
      </Stack>
    </Box>
  )
}
