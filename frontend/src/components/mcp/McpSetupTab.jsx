// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useState, useEffect, useCallback } from "react"
import {
  Box, Typography, Stack, Button, Chip, Alert,
  TextField, IconButton, Tooltip, Dialog, DialogTitle, DialogContent,
  DialogActions, CircularProgress, alpha, useTheme, Tabs, Tab,
  Link,
} from "@mui/material"
import ContentCopyIcon from "@mui/icons-material/ContentCopyOutlined"
import CheckCircleIcon from "@mui/icons-material/CheckCircleOutlined"
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutlineOutlined"
import RotateLeftIcon from "@mui/icons-material/RotateLeftOutlined"
import RefreshIcon from "@mui/icons-material/RefreshOutlined"
import OpenInNewIcon from "@mui/icons-material/OpenInNewOutlined"
import InstallDesktopIcon from "@mui/icons-material/InstallDesktopOutlined"
import VisibilityIcon from "@mui/icons-material/VisibilityOutlined"
import VisibilityOffIcon from "@mui/icons-material/VisibilityOffOutlined"
import http from "../../api/http"
import AppSkeleton from "../AppSkeleton"
import useAppStore from "../../store/appStore"

// Setup tab on /mcp page — surfaces the MCP token + ready-to-paste config
// snippets for the user's MCP client of choice.
//
// Previously lived as components/settings/McpIntegration.jsx; moved here
// 2026-05-11 when MCP got promoted to a dedicated page. Settings keeps
// only a small "MCP enabled — Manage →" tile that links here.
//
// Two snippet flavors covered:
//   1. Claude Code CLI (single-line `claude mcp add ...`)
//   2. Claude Desktop / any JSON-config client (mcp-remote proxy form)
//
// "Test connection" calls the backend's self-test endpoint (which itself
// runs initialize → list_tools against /mcp) and surfaces the tool count
// so the user knows the bridge is alive end-to-end.
//
// "Rotate token" generates a fresh token server-side and refreshes the
// snippet in place. A confirmation dialog prevents accidental rotation
// since the existing Claude Code config breaks until the user re-pastes
// the new snippet.

// What the "copied" toast calls the snippet, per client config format.
// Codex is TOML, not JSON — the old shell-or-JSON ternary told Codex users
// they'd copied a "JSON config".
const SNIPPET_COPY_LABEL = {
  shell: "command",
  json: "JSON config",
  toml: "TOML config",
}

// The snippet carries the live bearer token. On screen it is masked (first
// and last four characters kept so the user can tell tokens apart) until
// they ask to reveal it — screenshots and screen-shares of this page were
// leaking it. Copy always copies the real snippet.
export function maskToken(token) {
  if (!token) return ""
  if (token.length <= 10) return "•".repeat(token.length)
  return `${token.slice(0, 4)}${"•".repeat(12)}${token.slice(-4)}`
}

export function maskSnippet(snippet, token) {
  if (!snippet || !token) return snippet || ""
  return snippet.split(token).join(maskToken(token))
}

export default function McpSetupTab() {
  const showSnackbar = useAppStore(s => s.showSnackbar)
  const theme = useTheme()

  const [config, setConfig] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  // Which client's tab is selected in the config-snippet section. Null until
  // the user picks one — we fall back to the first client (Claude Code) the
  // backend returns, so there's no flash of an empty selection on load.
  const [clientId, setClientId] = useState(null)

  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState(null)

  const [rotateOpen, setRotateOpen] = useState(false)
  const [rotating, setRotating] = useState(false)

  // One-click install targets (detected MCP clients).
  const [targets, setTargets] = useState([])
  const [installing, setInstalling] = useState("")        // client id in flight
  const [installResult, setInstallResult] = useState(null)
  const [copied, setCopied] = useState(null)   // which copy button just fired (icon→check)
  const [revealToken, setRevealToken] = useState(false)

  const fetchConfig = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const { data } = await http.get("/api/settings/mcp")
      setConfig(data)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Failed to load MCP config")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchConfig() }, [fetchConfig])

  useEffect(() => {
    http.get("/api/settings/mcp/install/targets")
      .then(({ data }) => setTargets(data.targets || []))
      .catch(() => { /* one-click section just won't render */ })
  }, [])

  const handleInstall = async (client, label) => {
    setInstalling(client)
    setInstallResult(null)
    try {
      const { data } = await http.post(`/api/settings/mcp/install/${client}`)
      setInstallResult({ ...data, label })
      showSnackbar(data.message || `Installed for ${label}`, "success")
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || "Install failed"
      setInstallResult({ ok: false, client, label, message: detail })
      showSnackbar(detail, "error")
    } finally {
      setInstalling("")
    }
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const { data } = await http.post("/api/settings/mcp/test")
      setTestResult(data)
      if (data.ok) {
        showSnackbar(`MCP connection OK — ${data.tools_count} tools available`, "success")
      } else {
        showSnackbar(`MCP test failed: ${data.error}`, "error")
      }
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || "Request failed"
      setTestResult({ ok: false, error: "request", detail })
      showSnackbar(`MCP test failed: ${detail}`, "error")
    } finally {
      setTesting(false)
    }
  }

  const handleRotate = async () => {
    setRotating(true)
    try {
      const { data } = await http.post("/api/settings/mcp/rotate")
      setConfig(data)  // snippets below now carry the new token
      setRotateOpen(false)
      setTestResult(null)  // old test result is no longer meaningful
      showSnackbar(
        "New MCP token generated — re-copy the snippet for your client and re-paste it.",
        "warning",
      )
    } catch (err) {
      showSnackbar(
        err.response?.data?.detail || err.message || "Token rotation failed",
        "error",
      )
    } finally {
      setRotating(false)
    }
  }

  const copyToClipboard = async (text, what = "snippet", key = null) => {
    try {
      await navigator.clipboard.writeText(text)
      showSnackbar(`Copied ${what} to clipboard`, "success")
      // Transient icon→checkmark at the button (point-of-action feedback in
      // addition to the toast).
      if (key) {
        setCopied(key)
        setTimeout(() => setCopied((c) => (c === key ? null : c)), 1500)
      }
    } catch {
      showSnackbar("Clipboard write failed — select and copy manually", "warning")
    }
  }

  if (loading) return <AppSkeleton variant="list" count={5} />

  if (error || !config) return (
    <Alert severity="error" action={
      <Button color="inherit" size="small" onClick={fetchConfig} startIcon={<RefreshIcon />}>Retry</Button>
    }>
      {error || "Failed to load MCP config"}
    </Alert>
  )

  // Per-client config snippets come pre-rendered from the backend (token
  // already interpolated, JSON already pretty-printed) as an ordered list —
  // one tab per MCP client. Resolve the active tab, falling back to the
  // first client when nothing's selected yet or a stale id no longer
  // matches. `clients` is guaranteed non-empty by the backend, but guard
  // anyway so an older backend response can't blank the section.
  const clients = config.clients || []
  const activeClient = clients.find((c) => c.id === clientId) || clients[0] || null
  const snippet = activeClient?.snippet || ""
  const shownSnippet = revealToken ? snippet : maskSnippet(snippet, config.token)
  const hasToken = !!config.token && snippet.includes(config.token)

  return (
    <Stack spacing={2.5}>
      {/* ─ Intro ─ */}
      <Box>
        <Typography variant="body2" sx={{ color: "text.secondary", lineHeight: 1.7 }}>
          Drive ViralMint from <strong>Claude Code</strong>, OpenAI Codex, Cursor or any{" "}
          <Link
            href="https://modelcontextprotocol.io"
            target="_blank"
            rel="noopener"
            underline="hover"
            sx={{ display: "inline-flex", alignItems: "center", gap: 0.3 }}
          >
            MCP client <OpenInNewIcon sx={{ fontSize: 12 }} />
          </Link>
          . Paste the snippet below into your client's config — ViralMint
          exposes the full scout → download → analyze → generate pipeline
          plus the Tools utilities as callable MCP tools.
        </Typography>
      </Box>

      {/* ─ One-click install (recommended) ─ */}
      {targets.length > 0 && (
        <Box sx={{
          p: 2, borderRadius: 2, border: 1, borderColor: "divider",
          bgcolor: (t) => alpha(t.palette.primary.main, t.palette.mode === "dark" ? 0.06 : 0.04),
        }}>
          <Typography variant="caption" sx={{ color: "text.secondary", fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 }}>
            One-click setup — recommended
          </Typography>
          <Typography variant="caption" sx={{ display: "block", color: "text.secondary", mt: 0.25, mb: 1.25, fontSize: "0.74rem", lineHeight: 1.6 }}>
            Writes the MCP config into your client for you — no editing JSON or running terminal commands.
            Clients marked <strong>Detected</strong> were found on this machine; the others still work if you have them.
          </Typography>
          {/* All clients on ONE row, all outlined — a wall of five solid
              orange buttons shouted, and "filled = detected" was a code the
              user had to be told. Detection is a small labelled chip inside
              the button now. flexWrap stays as the narrow-window fallback. */}
          <Stack direction="row" sx={{ flexWrap: "wrap", gap: 1 }}>
            {targets.map((t) => (
              <Tooltip
                key={t.id}
                title={t.detected
                  ? `Install the ViralMint MCP config for ${t.label}`
                  : `${t.label} wasn't detected here — install anyway if you have it`}
              >
                <span>
                  <Button
                    variant="outlined"
                    size="small"
                    startIcon={installing === t.id
                      ? <CircularProgress size={14} color="inherit" />
                      : <InstallDesktopIcon />}
                    onClick={() => handleInstall(t.id, t.label)}
                    disabled={!!installing}
                    aria-label={`Install for ${t.label}${t.detected ? " (detected)" : ""}`}
                    sx={{ textTransform: "none", whiteSpace: "nowrap", bgcolor: "background.paper", gap: 0.25 }}
                  >
                    {t.label}
                    {t.detected && (
                      <Box component="span" aria-hidden sx={{
                        ml: 0.75, px: 0.6, py: 0.1, borderRadius: 1,
                        fontSize: "0.62rem", fontWeight: 700, letterSpacing: 0.3,
                        lineHeight: 1.5, textTransform: "uppercase",
                        color: "success.main",
                        bgcolor: (th) => alpha(th.palette.success.main, 0.12),
                      }}>
                        Detected
                      </Box>
                    )}
                  </Button>
                </span>
              </Tooltip>
            ))}
          </Stack>
          {installResult && (
            <Alert
              severity={installResult.ok ? "success" : "error"}
              icon={installResult.ok ? <CheckCircleIcon /> : <ErrorOutlineIcon />}
              sx={{ mt: 1.5 }}
            >
              <Typography variant="body2" sx={{ fontWeight: 600 }}>{installResult.message}</Typography>
              {installResult.ok && installResult.needs_restart && (
                <Typography variant="caption" sx={{ display: "block", mt: 0.3, color: "text.secondary" }}>
                  Restart {installResult.label}, then hit “Test connection” below.
                </Typography>
              )}
              {installResult.config_path && (
                <Typography variant="caption" sx={{ display: "block", mt: 0.3, color: "text.secondary", fontFamily: "JetBrains Mono, monospace", fontSize: "0.7rem", wordBreak: "break-all" }}>
                  {installResult.config_path}
                </Typography>
              )}
            </Alert>
          )}
        </Box>
      )}

      {/* ─ Endpoint URL ─ */}
      <Box>
        <Typography variant="caption" sx={{ color: "text.secondary", fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 }}>
          Endpoint
        </Typography>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5 }}>
          <TextField
            value={config.endpoint_url}
            size="small"
            fullWidth
            InputProps={{ readOnly: true, sx: { fontFamily: "JetBrains Mono, monospace", fontSize: "0.85rem" } }}
          />
          <Tooltip title="Copy endpoint URL">
            <IconButton aria-label="Copy endpoint URL" onClick={() => copyToClipboard(config.endpoint_url, "endpoint URL", "endpoint")} size="small">
              {copied === "endpoint"
                ? <CheckCircleIcon fontSize="small" color="success" />
                : <ContentCopyIcon fontSize="small" />}
            </IconButton>
          </Tooltip>
        </Stack>
      </Box>

      {/* The bearer token isn't shown on its own — it's already baked into
          every config snippet below, masked until revealed. It lives at
          ~/ViralMint/mcp_token (mode 0o600); use the Rotate button if you
          suspect it's been exposed. */}

      {/* ─ Snippet picker — one tab per MCP client ─ */}
      <Box>
        <Typography variant="caption" sx={{ color: "text.secondary", fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 }}>
          {targets.length > 0 ? "Or configure manually" : "Config snippet"}
        </Typography>
        <Tabs
          value={activeClient?.id || false}
          onChange={(_, v) => setClientId(v)}
          variant="scrollable"
          scrollButtons="auto"
          allowScrollButtonsMobile
          sx={{
            mt: 0.5, mb: 1.5, minHeight: 36,
            borderBottom: 1, borderColor: "divider",
            "& .MuiTab-root": { textTransform: "none", minHeight: 36, py: 0.5, fontSize: "0.8rem", fontWeight: 600 },
          }}
        >
          {clients.map((c) => (
            <Tab key={c.id} value={c.id} label={c.label} />
          ))}
        </Tabs>
        {/* pre-wrap + overflow-wrap:anywhere: the one-line `claude mcp add …`
            command used to run past the panel edge at phone width. JSON/TOML
            keep their indentation. The action buttons sit in their own
            column so wrapped text never slides under them. */}
        <Box sx={{
          display: "flex", alignItems: "flex-start", gap: 1,
          bgcolor: (t) => t.palette.mode === "dark" ? "#0f1011" : "#f6f8fa",
          border: 1, borderColor: "divider", borderRadius: 2,
          p: 2, pr: 1, minWidth: 0,
        }}>
          <Box
            component="pre"
            data-testid="mcp-snippet"
            sx={{
              m: 0, flex: 1, minWidth: 0,
              fontFamily: "JetBrains Mono, monospace",
              fontSize: "0.78rem", lineHeight: 1.65,
              overflow: "auto", maxHeight: 280,
              whiteSpace: "pre-wrap", overflowWrap: "anywhere",
            }}
          >
            {shownSnippet}
          </Box>
          <Stack spacing={0.5} sx={{ flexShrink: 0, mt: -0.75 }}>
            <Tooltip title="Copy snippet (includes your token)">
              <IconButton
                aria-label="Copy config snippet"
                onClick={() => copyToClipboard(snippet, SNIPPET_COPY_LABEL[activeClient?.format] || "config", "snippet")}
                size="small"
                sx={{ bgcolor: alpha(theme.palette.background.paper, 0.7) }}
              >
                {copied === "snippet"
                  ? <CheckCircleIcon fontSize="small" color="success" />
                  : <ContentCopyIcon fontSize="small" />}
              </IconButton>
            </Tooltip>
            {hasToken && (
              <Tooltip title={revealToken ? "Hide token" : "Show token"}>
                <IconButton
                  aria-label={revealToken ? "Hide token" : "Show token"}
                  aria-pressed={revealToken}
                  onClick={() => setRevealToken((v) => !v)}
                  size="small"
                  sx={{ bgcolor: alpha(theme.palette.background.paper, 0.7) }}
                >
                  {revealToken ? <VisibilityOffIcon fontSize="small" /> : <VisibilityIcon fontSize="small" />}
                </IconButton>
              </Tooltip>
            )}
          </Stack>
        </Box>
        {activeClient && (
          <Stack direction="row" spacing={1} alignItems="baseline" sx={{ mt: 1, flexWrap: "wrap" }}>
            <Typography variant="caption" sx={{ color: "text.muted", fontSize: "0.72rem", lineHeight: 1.6, flex: 1, minWidth: 200 }}>
              {activeClient.instructions}
            </Typography>
            {activeClient.docs_url && (
              <Link
                href={activeClient.docs_url}
                target="_blank"
                rel="noopener"
                underline="hover"
                variant="caption"
                sx={{ display: "inline-flex", alignItems: "center", gap: 0.3, fontSize: "0.72rem", whiteSpace: "nowrap" }}
              >
                {activeClient.label} MCP docs <OpenInNewIcon sx={{ fontSize: 12 }} />
              </Link>
            )}
          </Stack>
        )}
      </Box>

      {/* ─ Test + Rotate actions ─ */}
      <Stack direction="row" sx={{ pt: 0.5, alignItems: "center", flexWrap: "wrap", gap: 1 }}>
        <Typography variant="caption" sx={{
          color: "text.secondary", fontSize: "0.72rem",
          fontWeight: 600, mr: 0.5, letterSpacing: 0.3,
        }}>
          NEXT →
        </Typography>
        <Button
          variant="contained"
          startIcon={testing ? <CircularProgress size={14} color="inherit" /> : <CheckCircleIcon />}
          onClick={handleTest}
          disabled={testing}
        >
          {testing ? "Testing…" : "Test connection"}
        </Button>
        <Button
          variant="outlined"
          startIcon={<RotateLeftIcon />}
          onClick={() => setRotateOpen(true)}
          color="warning"
        >
          Rotate token
        </Button>
      </Stack>

      {/* ─ Test result banner ─ */}
      {testResult && (
        testResult.ok ? (
          <Alert
            severity="success"
            icon={<CheckCircleIcon />}
            sx={{ alignItems: "center" }}
          >
            <Stack direction="row" alignItems="center" spacing={1.5}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                Connected.
              </Typography>
              <Chip
                label={`${testResult.tools_count} tools available`}
                size="small"
                sx={{ height: 22, fontWeight: 600 }}
              />
            </Stack>
            <Typography variant="caption" sx={{ display: "block", mt: 0.5, color: "text.secondary" }}>
              {testResult.tool_names?.slice(0, 8).join(" · ")}{testResult.tool_names && testResult.tool_names.length > 8 ? ` · +${testResult.tool_names.length - 8} more` : ""}
            </Typography>
          </Alert>
        ) : (
          <Alert severity="error" icon={<ErrorOutlineIcon />}>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>{testResult.error}</Typography>
            {testResult.detail && (
              <Typography variant="caption" sx={{ display: "block", mt: 0.3, color: "text.secondary", fontFamily: "JetBrains Mono, monospace", fontSize: "0.72rem" }}>
                {testResult.detail}
              </Typography>
            )}
          </Alert>
        )
      )}

      {/* ─ Rotate confirmation dialog ─ */}
      <Dialog open={rotateOpen} onClose={() => !rotating && setRotateOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ pb: 1 }}>Rotate MCP token?</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ color: "text.secondary", mb: 1.5 }}>
            Generates a new Bearer token immediately. Your <strong>current Claude Code config</strong> stops
            working until you re-paste the new snippet.
          </Typography>
          <Typography variant="body2" sx={{ color: "text.secondary" }}>
            Rotate when you suspect the token has been exposed (committed to a public repo,
            shared in a screenshot, etc.).
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRotateOpen(false)} disabled={rotating}>Cancel</Button>
          <Button
            onClick={handleRotate}
            variant="contained"
            color="warning"
            disabled={rotating}
            startIcon={rotating ? <CircularProgress size={14} color="inherit" /> : <RotateLeftIcon />}
          >
            {rotating ? "Rotating…" : "Rotate"}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  )
}
