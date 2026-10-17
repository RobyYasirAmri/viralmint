// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useState, useEffect, useCallback, useRef } from "react"
import {
  Box, Typography, Stack, Alert, Button,
  Chip, Table, TableHead, TableBody, TableRow, TableCell,
  IconButton, Tooltip, alpha, useTheme, ToggleButton, ToggleButtonGroup,
} from "@mui/material"
import RefreshIcon from "@mui/icons-material/RefreshOutlined"
import HistoryIcon from "@mui/icons-material/HistoryOutlined"
import PlayCircleIcon from "@mui/icons-material/PlayCircleOutlined"
import PauseCircleIcon from "@mui/icons-material/PauseCircleOutlined"
import BoltIcon from "@mui/icons-material/BoltOutlined"
import DeleteSweepIcon from "@mui/icons-material/DeleteSweepOutlined"
import http from "../../api/http"
import AppSkeleton from "../AppSkeleton"
import useAppStore from "../../store/appStore"
import { ws } from "../../api/websocket"
import { formatRelativeTime } from "../../utils/format"

// Activity tab — newest-first table of MCP requests, refreshed on
// demand or via the auto-refresh toggle (3-second polling). Data is a
// process-local ring buffer; resets on backend restart.
//
// Why this exists: when the integration is wired up correctly the
// /mcp page is otherwise quiet — users wire Claude Code, run a
// workflow, and never come back. The Activity tab is the "did
// anything happen?" surface. Especially valuable during launch when
// users are skeptical that every tool really works end-to-end.

// Polling is ONLY the fallback for a dropped WebSocket: it runs while the
// socket is disconnected and the page is visible, and a reconnect triggers
// one catch-up fetch. It used to tick every 8 s regardless — on top of the
// WS pushes, and in a hidden tab.
const POLL_INTERVAL_MS = 8000

function useDocumentVisible() {
  const [visible, setVisible] = useState(() => typeof document === "undefined" || !document.hidden)
  useEffect(() => {
    const onChange = () => setVisible(!document.hidden)
    document.addEventListener("visibilitychange", onChange)
    return () => document.removeEventListener("visibilitychange", onChange)
  }, [])
  return visible
}

// Max entries we render — matches the backend ring buffer cap, but
// computed locally because WS-pushed events are prepended without
// re-fetching the full list. Trim when we cross the threshold.
const MAX_LOCAL_ENTRIES = 50

// Method labels — turn JSON-RPC method strings into something
// human-scannable in the table. Anything not in this map renders
// as-is, which is fine for unknown methods.
const METHOD_LABELS = {
  "tools/list": "List tools",
  "tools/call": "Tool call",
  "prompts/list": "List prompts",
  "prompts/get": "Get prompt",
  initialize: "Initialize",
  ping: "Ping",
  // WebSocket-emitted (synced into the buffer via ws_manager).
  // Rendered with yellow row styling — see row sx below.
  constraint_warning: "Constraint warning",
}

// The activity feed ticks in seconds and never wants a calendar fallback — an
// entry older than the 50-deep ring buffer simply isn't there any more. `ts` is
// UNIX seconds, which the shared helper reads natively.
const relativeTime = (ts) =>
  formatRelativeTime(ts, { secondsGranularity: true, fullDateAfterDays: Infinity })

function formatLatency(ms) {
  if (ms < 1) return "<1 ms"
  if (ms < 1000) return `${Math.round(ms)} ms`
  return `${(ms / 1000).toFixed(2)} s`
}

// Cost column removed 2026-05-16: the desktop-side estimate covered
// only the small slice of tools with a `tool_cost_estimate` entry,
// so summing the column never matched the cloud-side actual spend.
// Real per-action spend is authoritative in the Account page balance.

export default function McpActivityTab() {
  const theme = useTheme()
  const showSnackbar = useAppStore((s) => s.showSnackbar)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [clearing, setClearing] = useState(false)
  const [wsConnected, setWsConnected] = useState(() => ws.connected)
  const pageVisible = useDocumentVisible()
  const timerRef = useRef(null)
  const autoRefreshRef = useRef(autoRefresh)
  autoRefreshRef.current = autoRefresh

  const fetchActivity = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    setError("")
    try {
      const { data } = await http.get("/api/settings/mcp/activity")
      if (!data.ok) {
        throw new Error(data.error || "Activity unavailable")
      }
      setData(data)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Failed to load activity")
    } finally {
      if (!silent) setLoading(false)
    }
  }, [])

  useEffect(() => { fetchActivity() }, [fetchActivity])

  // Empty the server-side ring buffer + the local view. Useful after
  // a heavy workflow when the user wants to see only NEW events. The
  // buffer is process-local so a backend restart also clears it, but
  // most users won't restart just for a tidy log.
  const handleClear = useCallback(async () => {
    setClearing(true)
    try {
      const { data: resp } = await http.post("/api/settings/mcp/activity/clear")
      if (resp.ok) {
        setData((prev) => ({ ...(prev || {}), total: 0, events: [] }))
        showSnackbar?.("Activity log cleared", "success")
      } else {
        showSnackbar?.(resp.error || "Could not clear activity", "warning")
      }
    } catch (err) {
      showSnackbar?.(err.response?.data?.detail || err.message || "Clear failed", "error")
    } finally {
      setClearing(false)
    }
  }, [showSnackbar])

  // Real-time WebSocket subscription — backend pushes a `mcp_activity`
  // event on every MCP request (also on constraint_warning broadcasts
  // recorded into the buffer). Prepend to local state so the table
  // updates within milliseconds instead of waiting on the next poll.
  //
  // Polling stays as a fallback for WS-disconnect windows. When both
  // arrive for the same event, the dedupe on `ts` below keeps state
  // clean — a freshly-pushed event has the same timestamp the poll
  // would later see.
  useEffect(() => {
    const unsub = ws.on("mcp_activity", (msg) => {
      const event = msg?.event
      // Paused means paused — a resume re-fetches the whole buffer.
      if (!event || !autoRefreshRef.current) return
      setData((prev) => {
        const prevEvents = prev?.events || []
        // Dedupe: if we already have an event at this exact ts +
        // method + status, skip — the poll fallback may also be
        // delivering it shortly. Floating-point ts is fine here
        // because record() writes the same value to both paths.
        const dupe = prevEvents.some(
          (e) =>
            e.ts === event.ts &&
            e.method === event.method &&
            e.status_code === event.status_code,
        )
        if (dupe) return prev
        const nextEvents = [event, ...prevEvents].slice(0, MAX_LOCAL_ENTRIES)
        return {
          ...(prev || { max_entries: MAX_LOCAL_ENTRIES }),
          total: nextEvents.length,
          events: nextEvents,
        }
      })
    })
    return unsub
  }, [])

  // Track the socket so the poll only runs while it is down; a reconnect
  // fetches once to pick up whatever was pushed while it was away.
  useEffect(() => ws.on("_connection_state", ({ connected }) => {
    setWsConnected(connected)
    if (connected && autoRefreshRef.current) fetchActivity(true)
  }), [fetchActivity])

  // Resuming from Paused catches up in one fetch.
  const firstRunRef = useRef(true)
  useEffect(() => {
    if (firstRunRef.current) { firstRunRef.current = false; return }
    if (autoRefresh) fetchActivity(true)
  }, [autoRefresh, fetchActivity])

  // Fallback poll: silent fetches every POLL_INTERVAL_MS, only while Live,
  // the WS is down and the tab is visible.
  useEffect(() => {
    if (!autoRefresh || wsConnected || !pageVisible) {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
      return
    }
    timerRef.current = setInterval(() => fetchActivity(true), POLL_INTERVAL_MS)
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
  }, [autoRefresh, wsConnected, pageVisible, fetchActivity])

  if (loading) return <AppSkeleton variant="list" count={5} />

  if (error || !data) return (
    <Alert severity="error" action={
      <Button color="inherit" size="small" onClick={() => fetchActivity()} startIcon={<RefreshIcon />}>Retry</Button>
    }>
      {error || "Failed to load activity"}
    </Alert>
  )

  const events = data.events || []

  return (
    <Stack spacing={2.5}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <Box>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.3 }}>
            <Typography variant="body2" sx={{ color: "text.secondary", lineHeight: 1.7 }}>
              <strong>{data.total}</strong> of <strong>{data.max_entries}</strong> recent MCP requests
            </Typography>
            {autoRefresh && (
              <Chip
                label="LIVE"
                size="small"
                icon={<BoltIcon sx={{ fontSize: 12 }} />}
                sx={{
                  height: 18, fontSize: "0.62rem", fontWeight: 800,
                  letterSpacing: 0.5,
                  bgcolor: alpha(theme.palette.success.main, 0.15),
                  color: "success.main",
                  "& .MuiChip-icon": { color: "success.main", ml: 0.5 },
                  "& .MuiChip-label": { px: 0.7 },
                  // Subtle pulse animation while live — the WebSocket
                  // delivers events to setData on push, so this chip
                  // is the user's visual confirmation that the page is
                  // wired up correctly even when no events are firing
                  // (no events = quiet pulse, not a frozen UI).
                  animation: "live-pulse 2s ease-in-out infinite",
                  "@keyframes live-pulse": {
                    "0%, 100%": { opacity: 1 },
                    "50%": { opacity: 0.55 },
                  },
                }}
              />
            )}
          </Stack>
          <Typography variant="caption" sx={{ color: "text.muted", fontSize: "0.72rem" }}>
            {!autoRefresh
              ? "Updates paused. Press Live to resume."
              : wsConnected
                ? "Live updates via WebSocket — tool calls land within milliseconds"
                : "Live connection not available — checking every few seconds instead"}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} alignItems="center">
          <ToggleButtonGroup
            value={autoRefresh ? "on" : "off"}
            exclusive
            size="small"
            onChange={(_, v) => v && setAutoRefresh(v === "on")}
          >
            <ToggleButton value="on" sx={{ textTransform: "none", px: 1.5, py: 0.4, fontSize: "0.75rem" }}>
              <PlayCircleIcon sx={{ fontSize: 14, mr: 0.5 }} /> Live
            </ToggleButton>
            <ToggleButton value="off" sx={{ textTransform: "none", px: 1.5, py: 0.4, fontSize: "0.75rem" }}>
              <PauseCircleIcon sx={{ fontSize: 14, mr: 0.5 }} /> Paused
            </ToggleButton>
          </ToggleButtonGroup>
          <Tooltip title="Refresh now">
            <IconButton size="small" aria-label="Refresh activity" onClick={() => fetchActivity()}>
              <RefreshIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Clear activity log">
            {/* The <span> is MUI's required wrapper for a DISABLED button
                (disabled elements don't fire the events Tooltip listens for) —
                but it also means the tooltip's title lands on the span, not the
                button, so the button needs its own label. */}
            <span>
              <IconButton
                size="small"
                aria-label="Clear activity log"
                onClick={handleClear}
                disabled={clearing || events.length === 0}
              >
                <DeleteSweepIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
        </Stack>
      </Stack>

      {events.length === 0 ? (
        <Box sx={{
          p: 4, textAlign: "center",
          border: 1, borderColor: "divider", borderRadius: 2,
          background: (t) => t.palette.mode === "dark" ? "rgba(255,255,255,0.02)" : "rgba(0,0,0,0.02)",
        }}>
          <HistoryIcon sx={{ fontSize: 40, color: "text.muted", mb: 1 }} />
          <Typography variant="body2" sx={{ color: "text.secondary", fontWeight: 600 }}>
            No activity yet
          </Typography>
          <Typography variant="caption" sx={{ color: "text.muted", display: "block", mt: 0.5 }}>
            Once an MCP client connects and starts calling tools, requests will appear here.
          </Typography>
          <Typography variant="caption" sx={{
            color: "text.secondary", display: "block", mt: 1.5,
            fontSize: "0.72rem",
          }}>
            Quickest way to see this fill up: press <strong>Test connection</strong> on the
            Setup tab — its handshake appears here within milliseconds.
          </Typography>
        </Box>
      ) : (
        <Box sx={{
          border: 1, borderColor: "divider", borderRadius: 2,
          overflow: "auto",
        }}>
          <Table size="small">
            <TableHead>
              <TableRow sx={{
                bgcolor: (t) => t.palette.mode === "dark" ? "rgba(255,255,255,0.03)" : "rgba(0,0,0,0.02)",
                "& th": { fontWeight: 700, fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: 0.5, color: "text.secondary" },
              }}>
                <TableCell>When</TableCell>
                <TableCell>Action</TableCell>
                <TableCell>Tool / Prompt</TableCell>
                <TableCell align="right">Latency</TableCell>
                <TableCell align="right">Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {events.map((e, i) => {
                const isWarning = e.method === "constraint_warning"
                const ok = e.status_code < 400
                const methodLabel = METHOD_LABELS[e.method] || e.method
                // constraint_warning rows get yellow tinting so users
                // can scan partial-failure events at a glance. They
                // also have no real latency (instant WS event) so the
                // tabular numbers show "—" rather than "0 ms".
                const rowBg = isWarning
                  ? alpha(theme.palette.warning.main, 0.06)
                  : "transparent"
                return (
                  <TableRow key={`${e.ts}-${i}`} sx={{
                    bgcolor: rowBg,
                    "& td": { fontSize: "0.82rem", py: 1 },
                    "&:hover": { bgcolor: isWarning
                      ? alpha(theme.palette.warning.main, 0.1)
                      : alpha(theme.palette.primary.main, 0.03)
                    },
                  }}>
                    <TableCell sx={{ color: "text.secondary", whiteSpace: "nowrap" }}>
                      {relativeTime(e.ts)}
                    </TableCell>
                    <TableCell>
                      {methodLabel}
                      {/* For constraint_warning rows, the note (the
                          warning message) is the most actionable
                          field. Inline it under the method label so
                          users see "TikHub credit exhausted" without
                          hovering. */}
                      {isWarning && e.note && (
                        <Box sx={{
                          mt: 0.25,
                          fontSize: "0.72rem",
                          color: "warning.main",
                          fontWeight: 500,
                          maxWidth: 380,
                        }}>
                          {e.note}
                        </Box>
                      )}
                    </TableCell>
                    <TableCell sx={{
                      fontFamily: e.tool ? "JetBrains Mono, monospace" : undefined,
                      fontSize: e.tool ? "0.78rem" : undefined,
                      color: e.tool ? "text.primary" : "text.muted",
                    }}>
                      {e.tool || "—"}
                    </TableCell>
                    <TableCell align="right" sx={{ color: "text.secondary", fontVariantNumeric: "tabular-nums" }}>
                      {isWarning ? "—" : formatLatency(e.latency_ms)}
                    </TableCell>
                    <TableCell align="right">
                      <Chip
                        label={isWarning ? (e.error ? "Error" : "Warn") : e.status_code}
                        size="small"
                        sx={{
                          height: 20, fontSize: "0.7rem", fontWeight: 700,
                          bgcolor: isWarning
                            ? alpha(theme.palette.warning.main, 0.16)
                            : ok
                              ? alpha(theme.palette.success.main, 0.12)
                              : alpha(theme.palette.error.main, 0.12),
                          color: isWarning
                            ? "warning.main"
                            : ok ? "success.main" : "error.main",
                        }}
                      />
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </Box>
      )}
    </Stack>
  )
}
