// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useState, useEffect, useCallback, useMemo } from "react"
import {
  Box, Typography, Stack, Alert, Button,
  Chip, alpha, useTheme,
  TextField, InputAdornment, IconButton, Collapse,
} from "@mui/material"
import RefreshIcon from "@mui/icons-material/RefreshOutlined"
import ContentCopyIcon from "@mui/icons-material/ContentCopyOutlined"
import SearchIcon from "@mui/icons-material/SearchOutlined"
import ClearIcon from "@mui/icons-material/ClearOutlined"
import ExpandMoreIcon from "@mui/icons-material/ExpandMoreOutlined"
import StorageOutlinedIcon from "@mui/icons-material/StorageOutlined"
import http from "../../api/http"
import AppSkeleton from "../AppSkeleton"
import useAppStore from "../../store/appStore"

// Tool Inventory tab on /mcp — browse every callable tool grouped by
// workflow stage, with full descriptions. Source of truth is the live
// FastMCP instance, surfaced via GET /api/settings/mcp/tools so the
// descriptions stay in sync with the Python docstrings.
//
// UX: each group renders as an MUI Accordion (collapsed by default
// except the first) so users can scan the surface without scrolling
// through 22 expanded tiles. Clicking a tool exposes its full
// description and a "Copy name" button that lets users drop the tool
// name into a Claude Code prompt without hunting through docs.
//

// Workflow-stage accents — a THEME TONE per group, not a hex. The old
// rainbow of hand-picked hexes put "Output" in the error red (read as a
// failure) and "Orchestration" in grey (read as disabled). Tones cycle
// through the calm semantic set; the label itself stays text.primary and the
// tone only tints the rail, chevron and count chip. New group → pick a tone.
const GROUP_META = {
  macros:        { label: "Macros",         tone: "primary", desc: "Workflow shortcuts — one call composes several primitives" },
  research:      { label: "Research",       tone: "info", desc: "Discover what's worth making" },
  intelligence:  { label: "Intelligence",   tone: "warning", desc: "AI-grounded advice — channel coaching, keyword/trend intel, your profile" },
  acquire:       { label: "Acquire",        tone: "info", desc: "Pull source content into the local library" },
  generate:      { label: "Generate",       tone: "primary", desc: "Build new videos with AI" },
  output:        { label: "Output",         tone: "success", desc: "Inspect and export the finished work" },
  tools:         { label: "Tools",          tone: "primary", desc: "Single-purpose utilities (captions / reframe / audio enhance / ...)" },
  orchestration: { label: "Orchestration",  tone: "info", desc: "Job status, polling, cancellation" },
  discovery:     { label: "Discovery",      tone: "success", desc: "Look up the values the other tools take — caption styles, TTS voices, music tracks, curated prompt packs, your past assets" },
  other:         { label: "Other",          tone: "secondary", desc: "Tools not yet mapped to a workflow group" },
}

function toneColor(theme, tone) {
  return (theme.palette[tone] || theme.palette.secondary).main
}
// Readable text on a 10% tint of the tone: the darker shade in light mode,
// the lighter one in dark mode.
function toneText(theme, tone) {
  const p = theme.palette[tone] || theme.palette.secondary
  return theme.palette.mode === "dark" ? (p.light || p.main) : (p.dark || p.main)
}

export default function McpToolsTab({ advanced = false }) {
  const showSnackbar = useAppStore(s => s.showSnackbar)
  const theme = useTheme()

  const [data, setData] = useState(null)
  const [resources, setResources] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [query, setQuery] = useState("")

  // Resources block at the bottom is collapsed by default to match every
  // other group on this tab (it used to render always-expanded).
  const [resourcesOpen, setResourcesOpen] = useState(false)

  // Per-group expand state. Default: every group collapsed when the
  // page is in friendly mode (advanced=false) — group cards alone are
  // a much calmer browse surface than 50+ tool rows. Searching auto-
  // expands matches (see effect below). Advanced mode opens every
  // group on mount so devs see the full surface immediately.
  const [expanded, setExpanded] = useState({})
  useEffect(() => {
    if (!data) return
    // All groups collapsed by default — even in advanced mode. Users
    // open the blocks they care about; searching still auto-expands
    // matching groups (effect below). Previously advanced mode opened
    // every group on mount which was overwhelming once the surface
    // grew past ~60 tools.
    const next = {}
    for (const g of data.groups) next[g.name] = false
    setExpanded(next)
  }, [data])

  const fetchTools = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      // Fetch tools and resources in parallel — both feed the same
      // page render. Resources surfacing was added 2026-05-18 so
      // users discover the read-only data sources (recent_videos,
      // channels, etc.) that Claude can pull at session start.
      const [toolsRes, resourcesRes] = await Promise.all([
        http.get("/api/settings/mcp/tools"),
        http.get("/api/settings/mcp/resources").catch(() => null),
      ])
      const td = toolsRes.data
      if (!td.ok) {
        throw new Error(td.detail || td.error || "Tool listing failed")
      }
      setData(td)
      // Resources endpoint failure is non-fatal — older backends or a
      // transient MCP build error shouldn't blank the whole tab.
      if (resourcesRes?.data?.ok) {
        setResources(resourcesRes.data.resources || [])
      } else {
        setResources([])
      }
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Failed to load tools")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchTools() }, [fetchTools])

  const copyName = async (name) => {
    try {
      await navigator.clipboard.writeText(name)
      showSnackbar(`Copied "${name}" to clipboard`, "success")
    } catch {
      showSnackbar("Clipboard write failed", "warning")
    }
  }

  // Filter groups by query — case-insensitive match on tool name OR
  // first-line description. Empty groups disappear; non-empty groups
  // surface only the matching tools.
  //
  // IMPORTANT: this useMemo must run on EVERY render — putting it
  // below the early-return blocks below tripped React error #310
  // (rules-of-hooks: hooks called conditionally between renders).
  // Keep it above the loading / error returns even though `data` is
  // null on the first render.
  const filteredGroups = useMemo(() => {
    if (!data) return []
    const q = query.trim().toLowerCase()
    if (!q) return data.groups
    return data.groups
      .map((g) => ({
        ...g,
        tools: g.tools.filter((t) =>
          t.name.toLowerCase().includes(q) ||
          (t.summary || "").toLowerCase().includes(q)
        ),
      }))
      .filter((g) => g.tools.length > 0)
  }, [data, query])

  // Auto-expand any group that has search hits so users see the
  // matching tool names without clicking. Resets to the
  // advanced-driven default when the query clears.
  useEffect(() => {
    if (!data) return
    if (!query.trim()) return
    setExpanded((prev) => {
      const next = { ...prev }
      for (const g of filteredGroups) next[g.name] = true
      return next
    })
  }, [query, filteredGroups, data])

  const toggleGroup = (name) => {
    setExpanded((prev) => ({ ...prev, [name]: !prev[name] }))
  }

  if (loading) return <AppSkeleton variant="list" count={5} />

  if (error || !data) return (
    <Alert severity="error" action={
      <Button color="inherit" size="small" onClick={fetchTools} startIcon={<RefreshIcon />}>Retry</Button>
    }>
      {error || "Failed to load tools"}
    </Alert>
  )

  const matchedToolCount = filteredGroups.reduce((n, g) => n + g.tools.length, 0)

  return (
    <Stack spacing={2.5}>
      {/* Filter box — first row of the tab. Case-insensitive match on tool
          name or description first-line; auto-expands every matching group
          so users see hits without manually opening accordions. */}
      <TextField
        size="small"
        placeholder="Filter by name or description…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        InputProps={{
          startAdornment: (
            <InputAdornment position="start">
              <SearchIcon sx={{ fontSize: 18, color: "text.muted" }} />
            </InputAdornment>
          ),
          endAdornment: query ? (
            <InputAdornment position="end">
              <IconButton size="small" aria-label="Clear search" onClick={() => setQuery("")} sx={{ p: 0.5 }}>
                <ClearIcon sx={{ fontSize: 16 }} />
              </IconButton>
            </InputAdornment>
          ) : null,
          sx: { fontSize: "0.88rem" },
        }}
      />
      {query && (
        <Typography variant="caption" sx={{ color: "text.muted", mt: -1.5, ml: 0.5 }}>
          {matchedToolCount === 0
            ? `No tools match "${query}".`
            : `${matchedToolCount} of ${data.total} tools match "${query}".`}
        </Typography>
      )}

      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Box>
          <Typography variant="body2" sx={{ color: "text.secondary", lineHeight: 1.7 }}>
            {advanced ? (
              <>
                <strong>{data.total}</strong> tools across <strong>{data.groups.length}</strong> workflow groups.
                Browse the surface before wiring Claude Code, or copy a tool name to drop into a prompt.
              </>
            ) : (
              <>
                <strong>{data.groups.length}</strong> workflow groups available to Claude clients. Click a
                group to see what it can do — flip <em>Advanced</em> on for tool names + schemas.
              </>
            )}
          </Typography>
        </Box>
        <Button size="small" onClick={fetchTools} startIcon={<RefreshIcon fontSize="small" />} sx={{ flexShrink: 0 }}>
          Refresh
        </Button>
      </Box>

      {/* Workflow-group sections. Group header is a clickable row
          (chevron rotates on open). Default: collapsed unless
          Advanced is on or a search auto-expands a match — keeps
          the page calm for product users while devs flip Advanced
          once to see the full surface. */}
      <Stack spacing={1.5}>
        {filteredGroups.map((group) => {
          const meta = GROUP_META[group.name] || GROUP_META.other
          const color = toneColor(theme, meta.tone)
          const textColor = toneText(theme, meta.tone)
          const isOpen = !!expanded[group.name]
          return (
            <Box
              key={group.name}
              sx={{
                borderLeft: 3,
                borderColor: alpha(color, isOpen ? 0.7 : 0.4),
                pl: 2,
                transition: "border-color 0.18s",
              }}
            >
              <Stack
                direction="row"
                spacing={1.5}
                alignItems="center"
                onClick={() => toggleGroup(group.name)}
                role="button"
                tabIndex={0}
                aria-expanded={isOpen}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleGroup(group.name) }
                }}
                sx={{
                  mb: isOpen ? 1.25 : 0,
                  "&:focus-visible": { outline: `2px solid ${theme.palette.primary.main}`, outlineOffset: 2 },
                  cursor: "pointer",
                  py: 0.5,
                  userSelect: "none",
                  borderRadius: 1,
                  "&:hover": {
                    bgcolor: alpha(color, 0.04),
                  },
                }}
              >
                <ExpandMoreIcon
                  sx={{
                    fontSize: 20,
                    color: alpha(color, 0.8),
                    transform: isOpen ? "rotate(0deg)" : "rotate(-90deg)",
                    transition: "transform 0.18s ease",
                  }}
                />
                <Typography sx={{ fontWeight: 700, fontSize: "0.95rem", color: "text.primary" }}>
                  {meta.label}
                </Typography>
                <Chip
                  label={`${group.tools.length} tool${group.tools.length === 1 ? "" : "s"}`}
                  size="small"
                  sx={{
                    height: 20, fontSize: "0.7rem", fontWeight: 600,
                    bgcolor: alpha(color, 0.1),
                    color: textColor,
                  }}
                />
                <Typography variant="caption" sx={{ color: "text.muted", ml: 1 }}>
                  {meta.desc}
                </Typography>
              </Stack>
              <Collapse in={isOpen} timeout={220} unmountOnExit>
              <Box sx={{
                display: "grid",
                // Auto-fit columns: card minimum 280px, expand to
                // fill available width. At 1280px page width we get
                // ~4 cards/row for tool-name-only cards, ~3 for ones
                // with longer descriptions. Down-shifts gracefully
                // on narrower viewports.
                gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
                gap: 1.5,
              }}>
                {group.tools.map((tool) => (
                    <Box key={tool.name} sx={{
                      p: 1.5,
                      borderRadius: 1.5,
                      bgcolor: "background.paper",
                      border: 1, borderColor: "divider",
                      transition: "border-color 0.15s, transform 0.15s",
                      "&:hover": {
                        borderColor: alpha(color, 0.5),
                        transform: "translateY(-1px)",
                      },
                    }}>
                      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
                        <Box sx={{ flex: 1, minWidth: 0 }}>
                          <Typography sx={{
                            fontFamily: "JetBrains Mono, monospace",
                            fontSize: "0.85rem",
                            fontWeight: 600,
                            color: "text.primary",
                            mb: 0.5,
                          }}>
                            {tool.name}
                          </Typography>
                          <Typography variant="caption" sx={{
                            color: "text.secondary",
                            fontSize: "0.8rem",
                            lineHeight: 1.6,
                            display: "block",
                          }}>
                            {tool.summary}
                          </Typography>
                        </Box>
                        <Button
                          size="small"
                          startIcon={<ContentCopyIcon sx={{ fontSize: 14 }} />}
                          onClick={() => copyName(tool.name)}
                          sx={{ flexShrink: 0, minWidth: "auto", textTransform: "none", fontSize: "0.72rem" }}
                        >
                          Copy
                        </Button>
                      </Stack>
                    </Box>
                  ))}
              </Box>
              </Collapse>
            </Box>
          )
        })}
      </Stack>

      {/* Resources — MCP's third capability surface alongside Tools and
          Prompts. Read-only URIs Claude can pull at session start to
          ground itself in user state (recent videos, channels, etc.).
          Rendered as a small inline list at the bottom of the page so
          users discover they exist; before 2026-05-18 there was no UI
          surface for them at all. Hidden when the resources fetch
          returned nothing (older backend, or transient build error). */}
      {resources && resources.length > 0 && (
        <Box sx={{
          borderLeft: 3,
          borderColor: alpha(theme.palette.text.secondary, 0.4),
          pl: 2,
        }}>
          <Stack
            direction="row"
            spacing={1.5}
            alignItems="center"
            onClick={() => setResourcesOpen((v) => !v)}
            sx={{
              py: 0.5,
              mb: resourcesOpen ? 1.25 : 0,
              cursor: "pointer",
              userSelect: "none",
              borderRadius: 1,
              "&:hover": { bgcolor: alpha(theme.palette.text.secondary, 0.04) },
            }}
          >
            <ExpandMoreIcon
              sx={{
                fontSize: 20,
                color: alpha(theme.palette.text.secondary, 0.8),
                transform: resourcesOpen ? "rotate(0deg)" : "rotate(-90deg)",
                transition: "transform 0.18s ease",
              }}
            />
            <StorageOutlinedIcon sx={{ fontSize: 20, color: "text.secondary" }} />
            <Typography sx={{ fontWeight: 700, fontSize: "0.95rem" }}>Resources</Typography>
            <Chip
              label={`${resources.length} resource${resources.length === 1 ? "" : "s"}`}
              size="small"
              sx={{
                height: 20, fontSize: "0.7rem", fontWeight: 600,
                bgcolor: alpha(theme.palette.text.secondary, 0.1),
                color: "text.secondary",
              }}
            />
            <Typography variant="caption" sx={{ color: "text.muted", ml: 1 }}>
              Read-only data Claude can pull at session start to ground itself
            </Typography>
          </Stack>
          <Collapse in={resourcesOpen} timeout={220} unmountOnExit>
          <Box sx={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
            gap: 1.5,
          }}>
            {resources.map((r) => (
              <Box key={r.uri} sx={{
                p: 1.5,
                borderRadius: 1.5,
                bgcolor: "background.paper",
                border: 1, borderColor: "divider",
                transition: "border-color 0.15s",
                "&:hover": { borderColor: alpha(theme.palette.text.secondary, 0.5) },
              }}>
                <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography sx={{
                      fontFamily: "JetBrains Mono, monospace",
                      fontSize: "0.85rem",
                      fontWeight: 600,
                      color: "text.primary",
                      mb: 0.5,
                      wordBreak: "break-all",
                    }}>
                      {r.uri}
                    </Typography>
                    <Typography variant="caption" sx={{
                      color: "text.secondary",
                      fontSize: "0.8rem",
                      lineHeight: 1.55,
                      display: "block",
                    }}>
                      {r.description || r.name}
                    </Typography>
                  </Box>
                  <Button
                    size="small"
                    startIcon={<ContentCopyIcon sx={{ fontSize: 14 }} />}
                    onClick={() => copyName(r.uri)}
                    sx={{ flexShrink: 0, minWidth: "auto", textTransform: "none", fontSize: "0.72rem" }}
                  >
                    Copy
                  </Button>
                </Stack>
              </Box>
            ))}
          </Box>
          </Collapse>
        </Box>
      )}
    </Stack>
  )
}
