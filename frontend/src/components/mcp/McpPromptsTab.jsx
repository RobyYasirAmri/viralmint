// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useState, useEffect, useCallback } from "react"
import {
  Box, Typography, Stack, Alert, Button,
  Chip, alpha, useTheme,
  Accordion, AccordionSummary, AccordionDetails,
  IconButton, Tooltip,
} from "@mui/material"
import ExpandMoreIcon from "@mui/icons-material/ExpandMore"
import RefreshIcon from "@mui/icons-material/RefreshOutlined"
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesomeOutlined"
import ContentCopyIcon from "@mui/icons-material/ContentCopyOutlined"
import LockIcon from "@mui/icons-material/LockOutlined"
import http from "../../api/http"
import AppSkeleton from "../AppSkeleton"
import { cleanArgDescription } from "./promptArgs"
import useAppStore from "../../store/appStore"

// Prompts tab — lists the server's built-in MCP Prompts (workflow recipes
// Claude can invoke as slash-commands, viralmint:* namespace), read live
// from FastMCP via /api/settings/mcp/prompts.

const BUILT_IN_NAMESPACE = "viralmint:"

// Break long snake_case slugs only at underscores.
function breakableSlug(slug) {
  const parts = slug.split("_")
  return parts.map((p, i) => (i < parts.length - 1 ? [p, "_", <wbr key={i} />] : p))
}

export default function McpPromptsTab() {
  const theme = useTheme()
  const showSnackbar = useAppStore(s => s.showSnackbar)
  const accent = theme.palette.primary.main

  const [builtIns, setBuiltIns] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  const fetchAll = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const builtInsRes = await http.get("/api/settings/mcp/prompts")
      if (!builtInsRes.data.ok) {
        throw new Error(builtInsRes.data.detail || builtInsRes.data.error || "Built-in prompts unavailable")
      }
      setBuiltIns(builtInsRes.data)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Failed to load prompts")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchAll() }, [fetchAll])

  const copySlashCommand = async (name) => {
    const text = `/${name}`
    try {
      await navigator.clipboard.writeText(text)
      showSnackbar(`Copied "${text}" — paste into Claude Code`, "success")
    } catch {
      showSnackbar("Clipboard write failed", "warning")
    }
  }

  if (loading) return <AppSkeleton variant="list" count={5} />

  if (error || !builtIns) return (
    <Alert severity="error" action={
      <Button color="inherit" size="small" onClick={fetchAll} startIcon={<RefreshIcon />}>Retry</Button>
    }>
      {error || "Failed to load prompts"}
    </Alert>
  )

  // In the order FastMCP registered them.
  const allPrompts = builtIns.prompts.map((p) => ({ ...p, kind: "builtin", full_name: p.name }))

  return (
    <Stack spacing={2.5}>
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" useFlexGap sx={{ flexWrap: "wrap", gap: 1 }}>
        <Box sx={{ flex: "1 1 260px", minWidth: 0 }}>
          <Typography variant="body2" sx={{ color: "text.secondary", lineHeight: 1.7 }}>
            <strong>{builtIns.total}</strong> built-in workflow {builtIns.total === 1 ? "recipe" : "recipes"}. Prompts
            surface as slash-commands in your MCP client; type <code style={{ fontFamily: "JetBrains Mono, monospace" }}>/</code> in
            Claude Code to browse them.
          </Typography>
        </Box>
        <Stack direction="row" spacing={0.5} sx={{ flexShrink: 0 }}>
          <IconButton size="small" aria-label="Refresh prompts" onClick={fetchAll}>
            <RefreshIcon fontSize="small" />
          </IconButton>
        </Stack>
      </Stack>

      {/* 2-column accordion grid at desktop widths — uses the extra
          real estate the wider /mcp page wrapper gives us. Drops to
          single-column on narrow viewports. minmax(0, 1fr), not 1fr: a
          bare 1fr track has an auto MIN, so one long unbreakable line
          (a schema blob, a slash-command) widened the column past the
          panel and clipped it. */}
      <Box sx={{
        display: "grid",
        gridTemplateColumns: { xs: "minmax(0, 1fr)", md: "repeat(2, minmax(0, 1fr))" },
        gap: 1.5,
        alignItems: "start",
      }}>
        {allPrompts.map((prompt, idx) => {
          const isBuiltin = prompt.kind === "builtin"
          const fullName = prompt.full_name || prompt.name
          const prefix = BUILT_IN_NAMESPACE
          const slug = fullName.startsWith(prefix) ? fullName.slice(prefix.length) : fullName
          return (
            <Accordion
              key={`${prompt.kind}-${prompt.id || prompt.name}`}
              defaultExpanded={idx === 0}
              disableGutters
              elevation={0}
              sx={{
                border: 1,
                borderColor: alpha(accent, isBuiltin ? 0.2 : 0.35),
                borderRadius: 2,
                background: alpha(accent, isBuiltin ? 0.025 : 0.05),
                "&:before": { display: "none" },
                "&.Mui-expanded": { margin: 0 },
              }}
            >
              {/* component="div": the summary holds its own copy/edit/delete
                  buttons, and a <button> inside a <button> is invalid DOM. */}
              <AccordionSummary
                component="div"
                expandIcon={<ExpandMoreIcon />}
                sx={{ "& .MuiAccordionSummary-content": { my: 1.5 } }}
              >
                {/* Wraps: at phone width the name takes its own line and the
                    chips + actions drop below it, instead of the name being
                    squeezed into a one-word-per-line column. */}
                <Stack direction="row" alignItems="center" useFlexGap sx={{ width: "100%", flexWrap: "wrap", columnGap: 1.5, rowGap: 0.75 }}>
                  <Box sx={{
                    width: 28, height: 28, borderRadius: 1.5,
                    bgcolor: alpha(accent, 0.1), color: accent,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    flexShrink: 0,
                  }}>
                    <AutoAwesomeIcon sx={{ fontSize: 16 }} />
                  </Box>
                  <Box sx={{ flex: "1 1 180px", minWidth: 0 }}>
                    <Typography sx={{
                      fontFamily: "JetBrains Mono, monospace",
                      fontSize: "0.88rem",
                      fontWeight: 600,
                      color: "text.primary",
                      overflowWrap: "anywhere",
                    }}>
                      <span style={{ color: theme.palette.text.muted, opacity: 0.6 }}>{prefix}<wbr /></span>
                      {breakableSlug(slug)}
                    </Typography>
                  </Box>
                  <Chip
                    label={isBuiltin ? "Built-in" : "User"}
                    size="small"
                    icon={isBuiltin ? <LockIcon sx={{ fontSize: 12 }} /> : undefined}
                    sx={{
                      height: 20, fontSize: "0.68rem", fontWeight: 600,
                      bgcolor: isBuiltin
                        ? alpha(theme.palette.text.primary, 0.08)
                        : alpha(theme.palette.success.main, 0.15),
                      color: isBuiltin ? "text.muted" : "success.main",
                      "& .MuiChip-icon": { color: "text.muted", ml: 0.5 },
                    }}
                  />
                  {prompt.arguments && prompt.arguments.length > 0 && (
                    <Chip
                      label={`${prompt.arguments.length} arg${prompt.arguments.length === 1 ? "" : "s"}`}
                      size="small"
                      sx={{
                        height: 20, fontSize: "0.7rem", fontWeight: 600,
                        bgcolor: alpha(accent, 0.1),
                        color: accent,
                      }}
                    />
                  )}
                  <Tooltip title={`Copy /${fullName} — paste into Claude Code as a slash-command`}>
                    <IconButton
                      size="small"
                      aria-label={`Copy /${fullName}`}
                      onClick={(e) => { e.stopPropagation(); copySlashCommand(fullName) }}
                      sx={{ flexShrink: 0 }}
                    >
                      <ContentCopyIcon sx={{ fontSize: 16 }} />
                    </IconButton>
                  </Tooltip>
                </Stack>
              </AccordionSummary>
              <AccordionDetails sx={{ pt: 0, pb: 2 }}>
                <Stack spacing={1.5}>
                  <Typography variant="body2" sx={{ color: "text.secondary", lineHeight: 1.7, fontSize: "0.85rem" }}>
                    {prompt.description || (isBuiltin ? "(no description)" : "(user-defined)")}
                  </Typography>
                  {prompt.arguments && prompt.arguments.length > 0 && (
                    <Box>
                      <Typography variant="caption" sx={{
                        color: "text.secondary", fontWeight: 600,
                        textTransform: "uppercase", letterSpacing: 0.5,
                        display: "block", mb: 0.8,
                      }}>
                        Arguments
                      </Typography>
                      <Stack spacing={0.5}>
                        {prompt.arguments.map((arg) => {
                          const argDesc = cleanArgDescription(arg.description)
                          return (
                          <Box key={arg.name} sx={{
                            display: "flex", gap: 1, alignItems: "baseline",
                            flexWrap: "wrap", minWidth: 0,
                            fontFamily: "JetBrains Mono, monospace",
                            fontSize: "0.78rem",
                          }}>
                            <code style={{ color: theme.palette.primary.main, fontWeight: 600 }}>
                              {arg.name}
                            </code>
                            {/* "required" was error-red, which read as a
                                validation failure on a static listing. */}
                            <Chip label={arg.required ? "required" : "optional"} size="small" sx={{
                              height: 16, fontSize: "0.62rem", fontWeight: 600,
                              bgcolor: arg.required
                                ? alpha(accent, 0.1)
                                : alpha(theme.palette.text.primary, 0.06),
                              color: arg.required ? "primary.main" : "text.muted",
                            }} />
                            {argDesc && (
                              <Typography variant="caption" sx={{
                                color: "text.secondary", fontSize: "0.78rem",
                                fontFamily: "var(--font-sans)",
                                flexBasis: { xs: "100%", sm: "auto" }, minWidth: 0,
                                overflowWrap: "anywhere",
                              }}>
                                {argDesc}
                              </Typography>
                            )}
                          </Box>
                          )
                        })}
                      </Stack>
                    </Box>
                  )}
                </Stack>
              </AccordionDetails>
            </Accordion>
          )
        })}
      </Box>

    </Stack>
  )
}
