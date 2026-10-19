// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useEffect, useState } from "react"
import { Box, Button, Chip, CircularProgress, InputBase, Stack, Typography, alpha } from "@mui/material"
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome"
import { assistScene } from "./studioApi"

// One-tap AI help for one scene (2026-10-13 audit: once a draft was planned
// the AI was gone). Every ask is one call on your own AI key and only
// SUGGESTS: picking a line applies it with the ordinary set_line op, so undo
// and the re-voice behave exactly as for a hand edit.
const ASKS = [
  { id: "punchier", label: "Punchier" },
  { id: "shorter", label: "Shorter" },
  { id: "clearer", label: "Clearer" },
]

export default function SceneAssist({ projectId, scene, isFirst = false, onUseLine, onSearch, onReplanScene, disabled = false }) {
  const [busy, setBusy] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState("")
  const [ask, setAsk] = useState("")
  // A different scene, or the line changed under us: old suggestions no longer apply.
  useEffect(() => { setResult(null); setError(""); setBusy(null) }, [scene.uid, scene.line])

  const run = async (action, instruction) => {
    setBusy(action)
    setError("")
    setResult(null)
    try {
      const out = await assistScene(projectId, scene.uid, action, instruction)
      setResult(out)
    } catch (e) {
      setError(e.message || "The AI didn't answer — try again.")
    } finally {
      setBusy(null)
    }
  }

  const asks = isFirst ? [{ id: "hook", label: "Hook ideas" }, ...ASKS] : ASKS
  return (
    <Box data-testid="scene-assist" sx={{ mt: 1 }}>
      <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap" alignItems="center">
        <AutoAwesomeIcon sx={{ fontSize: 15, color: "primary.main", mr: 0.25 }} aria-hidden />
        {asks.map((a) => (
          <Chip
            key={a.id} size="small" variant="outlined" label={a.label} disabled={disabled || !!busy}
            icon={busy === a.id ? <CircularProgress size={11} /> : undefined}
            onClick={() => run(a.id)} sx={{ height: 24, fontSize: 12, fontWeight: 600 }}
          />
        ))}
        {onReplanScene && (
          <Chip
            size="small" variant="outlined" label="Better clip" disabled={disabled || !!busy}
            onClick={() => onReplanScene(scene.uid)} sx={{ height: 24, fontSize: 12, fontWeight: 600 }}
          />
        )}
      </Stack>
      <Box
        component="form"
        onSubmit={(e) => { e.preventDefault(); if (ask.trim() && !busy) run("custom", ask.trim()) }}
        sx={(t) => ({
          mt: 0.75, display: "flex", alignItems: "center", gap: 0.5, px: 1, py: 0.25,
          border: 1, borderColor: "divider", borderRadius: 1.5, bgcolor: alpha(t.palette.text.primary, 0.02),
        })}
      >
        <InputBase
          value={ask} onChange={(e) => setAsk(e.target.value)} disabled={disabled || !!busy}
          placeholder="Ask AI to change this scene… e.g. “add a number” or “show a city at night”"
          inputProps={{ "aria-label": "Ask AI to change this scene", maxLength: 300 }}
          sx={{ flex: 1, fontSize: 12.5 }}
        />
        <Button type="submit" size="small" disabled={disabled || !!busy || !ask.trim()}
          sx={{ textTransform: "none", fontWeight: 700, minWidth: 0 }}>
          {busy === "custom" ? <CircularProgress size={12} /> : "Ask"}
        </Button>
      </Box>
      <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mt: 0.5 }}>
        Suggestions only — nothing changes until you pick one.
      </Typography>
      {error && <Typography variant="caption" role="alert" sx={{ color: "error.main", display: "block", mt: 0.5 }}>{error}</Typography>}
      {result && (
        <Stack spacing={0.75} sx={{ mt: 1 }} data-testid="assist-options">
          {result.lines.map((l) => (
            <Box key={l} sx={(t) => ({ p: 1, borderRadius: 1.5, border: 1, borderColor: "divider", bgcolor: alpha(t.palette.primary.main, 0.04) })}>
              <Typography variant="body2" sx={{ fontSize: 13, lineHeight: 1.45 }}>{l}</Typography>
              <Button size="small" onClick={() => { onUseLine(l); setResult(null) }}
                sx={{ textTransform: "none", fontWeight: 700, mt: 0.25, px: 0.5, minWidth: 0 }}>
                Use this line
              </Button>
            </Box>
          ))}
          {result.query && (
            <Button size="small" variant="outlined" onClick={() => { onSearch(result.query); setResult(null) }}
              sx={{ textTransform: "none", fontWeight: 700, alignSelf: "flex-start" }}>
              Search footage: “{result.query}”
            </Button>
          )}
        </Stack>
      )}
    </Box>
  )
}
