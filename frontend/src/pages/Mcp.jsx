// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useState, useEffect } from "react"
import { useSearchParams } from "react-router-dom"
import {
  Box, Typography, Stack, Tabs, Tab,
  Switch, FormControlLabel, Tooltip,
} from "@mui/material"
import { GlassCard } from "../utils/glassFx"
import HubIcon from "@mui/icons-material/HubOutlined"
import SettingsRemoteIcon from "@mui/icons-material/SettingsRemoteOutlined"
import ListAltIcon from "@mui/icons-material/ListAltOutlined"
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesomeOutlined"
import HistoryIcon from "@mui/icons-material/HistoryOutlined"
import useDocumentTitle from "../hooks/useDocumentTitle"
import McpSetupTab from "../components/mcp/McpSetupTab"
import McpToolsTab from "../components/mcp/McpToolsTab"
import McpPromptsTab from "../components/mcp/McpPromptsTab"
import McpActivityTab from "../components/mcp/McpActivityTab"
import PageHero from "../components/PageHero"

// The /mcp page — everything needed to connect an MCP client (Claude Code,
// Claude Desktop, Codex, Cursor, …) to this install, in four tabs:
//
//   - Setup:    one-click install, endpoint, token, per-client snippets,
//               test connection, rotate token
//   - Tools:    every tool the server serves, grouped by workflow stage,
//               plus the read-only resources
//   - Prompts:  the built-in workflow recipes (slash-commands)
//   - Activity: live MCP request feed (WS-pushed, with a poll fallback)
//
// The tab lives in the URL (?tab=tools) so deep links work and a reload
// doesn't snap back to Setup mid-troubleshoot. Backed by
// backend/api/mcp_settings.py.

// "Show developer details" — raw tool names and schemas on the Tools tab.
// Off by default; persisted so a developer flips it once.
const ADVANCED_KEY = "vm_mcp_advanced"
function readAdvanced() {
  try { return localStorage.getItem(ADVANCED_KEY) === "1" } catch { return false }
}
function writeAdvanced(v) {
  try { localStorage.setItem(ADVANCED_KEY, v ? "1" : "0") } catch { /* private mode */ }
}

const TAB_DEFS = [
  { key: "setup",    label: "Setup",    icon: <SettingsRemoteIcon sx={{ fontSize: 18 }} /> },
  { key: "tools",    label: "Tools",    icon: <ListAltIcon sx={{ fontSize: 18 }} /> },
  { key: "prompts",  label: "Prompts",  icon: <AutoAwesomeIcon sx={{ fontSize: 18 }} /> },
  { key: "activity", label: "Activity", icon: <HistoryIcon sx={{ fontSize: 18 }} /> },
]

export default function Mcp() {
  useDocumentTitle("MCP")
  const [searchParams, setSearchParams] = useSearchParams()
  const [advanced, setAdvanced] = useState(readAdvanced)
  useEffect(() => { writeAdvanced(advanced) }, [advanced])

  const urlTab = searchParams.get("tab")
  const activeKey = TAB_DEFS.find((t) => t.key === urlTab)?.key || "setup"

  const handleTabChange = (_, value) => {
    setSearchParams({ tab: value }, { replace: true })
  }

  return (
    <Box sx={{ height: "100%", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <PageHero
        icon={<HubIcon sx={{ fontSize: 22 }} />}
        title="MCP"
        chip="Model Context Protocol"
        subtitle="Drive ViralMint from Claude Code, OpenAI Codex, Cursor or any MCP client."
      />

      {/* ── Tab bar + Advanced toggle ── */}
      <Box sx={{
        flexShrink: 0,
        borderBottom: 1,
        borderColor: "divider",
        bgcolor: "background.paper",
        px: { xs: 1, md: 2 },
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 2,
      }}>
        <Tabs
          value={activeKey}
          onChange={handleTabChange}
          variant="scrollable"
          scrollButtons={false}
          sx={{
            minHeight: 48,
            flex: 1,
            "& .MuiTab-root": {
              textTransform: "none",
              fontWeight: 600,
              fontSize: "0.88rem",
              minHeight: 48,
              gap: 0.5,
            },
          }}
        >
          {TAB_DEFS.map((tab) => (
            <Tab
              key={tab.key}
              value={tab.key}
              label={
                <Stack direction="row" alignItems="center" sx={{ gap: 0.8 }}>
                  {/* Icons drop at phone width so every label fits beside
                      the Advanced switch. */}
                  <Box component="span" sx={{ display: { xs: "none", sm: "inline-flex" } }}>{tab.icon}</Box>
                  <span>{tab.label}</span>
                </Stack>
              }
            />
          ))}
        </Tabs>
        <Tooltip
          title="Show developer-only details — raw tool names and schemas. Off by default; flip on if you're wiring Claude Code or debugging."
          placement="bottom-end"
          arrow
        >
          <FormControlLabel
            control={
              <Switch
                size="small"
                checked={advanced}
                onChange={(e) => setAdvanced(e.target.checked)}
              />
            }
            label={
              <Typography sx={{ fontSize: "0.78rem", color: "text.secondary", fontWeight: 500 }}>
                Advanced
              </Typography>
            }
            sx={{ flexShrink: 0, mr: 0.5 }}
          />
        </Tooltip>
      </Box>

      {/* ── Tab content — one max-width for every tab so the gutter stays
          put when switching. ── */}
      <Box sx={{ flex: 1, overflow: "auto", p: { xs: 2, md: 3 } }}>
        <Box sx={{ maxWidth: 1280, mx: "auto" }}>
          <GlassCard
            // Re-keyed per tab so the fade re-fires on every switch.
            key={activeKey}
            sx={{
              p: { xs: 2, sm: 3 },
              animation: "vm-fade-in-up 0.26s cubic-bezier(0.2, 0.7, 0.2, 1)",
              "@media (prefers-reduced-motion: reduce)": { animation: "none" },
            }}
          >
            {activeKey === "setup" && <McpSetupTab />}
            {activeKey === "tools" && <McpToolsTab advanced={advanced} />}
            {activeKey === "prompts" && <McpPromptsTab />}
            {activeKey === "activity" && <McpActivityTab />}
          </GlassCard>
        </Box>
      </Box>
    </Box>
  )
}
