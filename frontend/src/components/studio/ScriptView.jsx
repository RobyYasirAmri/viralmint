// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useEffect, useState } from "react"
import {
  Box, Button, Drawer, IconButton, Stack, TextField, Tooltip, Typography,
} from "@mui/material"
import CloseIcon from "@mui/icons-material/Close"
import ContentCutIcon from "@mui/icons-material/ContentCut"
import CallMergeIcon from "@mui/icons-material/CallMerge"
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline"
import AddIcon from "@mui/icons-material/Add"
import { LINE_MAX, VOICE_STATE } from "./studioModel"

// The full script as a document (§5.8): one paragraph per scene, edited in
// place. It is the same ops underneath — set_line (re-voices), split_scene,
// merge_scenes, remove_scene, insert_scene — so revising the writing here is
// exactly as safe as editing a scene in the inspector, just faster.

function Paragraph({ scene, isLast, onCommit, onSplit, onMerge, onRemove, canRemove }) {
  const [text, setText] = useState(scene.line)
  useEffect(() => { setText(scene.line) }, [scene.uid, scene.line])
  const trimmed = text.replace(/\s+/g, " ").trim()
  const dirty = trimmed !== scene.line
  const over = trimmed.length > LINE_MAX
  const commit = () => { if (dirty) onCommit(scene.uid, trimmed) }
  const voice = VOICE_STATE[scene.voice?.state || "none"]
  return (
    <Box data-testid="script-paragraph" sx={{ display: "grid", gridTemplateColumns: "28px 1fr auto", gap: 1, alignItems: "flex-start", py: 1, borderBottom: 1, borderColor: "divider" }}>
      <Typography variant="caption" sx={{ color: "text.disabled", fontWeight: 800, pt: 1.1, textAlign: "right" }}>{scene.index + 1}</Typography>
      <Box>
        <TextField
          fullWidth multiline minRows={1} maxRows={6} size="small" variant="standard"
          value={text} onChange={(e) => setText(e.target.value)} onBlur={commit}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); commit() } }}
          error={over || (dirty && !trimmed)}
          placeholder="Write this scene's line"
          slotProps={{ input: { sx: { fontSize: "0.95rem", lineHeight: 1.6 }, disableUnderline: !dirty }, htmlInput: { "aria-label": `Scene ${scene.index + 1} line` } }}
        />
        <Typography variant="caption" sx={{ color: over ? "error.main" : "text.disabled" }}>
          {scene.dur.toFixed(1)}s{scene.estimated ? " est." : ""} · {voice.label}
          {over ? ` · ${trimmed.length}/${LINE_MAX} — split this scene` : dirty ? " · ⌘↵ or click away to apply" : ""}
        </Typography>
      </Box>
      <Stack direction="row" spacing={0} sx={{ pt: 0.4 }}>
        <Tooltip title="Split this scene in two"><IconButton size="small" aria-label={`Split scene ${scene.index + 1}`} onClick={() => onSplit(scene.uid)}><ContentCutIcon sx={{ fontSize: 16 }} /></IconButton></Tooltip>
        <Tooltip title={isLast ? "" : "Merge with the next scene"}><span><IconButton size="small" aria-label={`Merge scene ${scene.index + 1} with the next`} disabled={isLast} onClick={() => onMerge(scene.uid)}><CallMergeIcon sx={{ fontSize: 16 }} /></IconButton></span></Tooltip>
        <Tooltip title={canRemove ? "Delete this scene" : ""}><span><IconButton size="small" aria-label={`Delete scene ${scene.index + 1}`} disabled={!canRemove} onClick={() => onRemove(scene.uid)}><DeleteOutlineIcon sx={{ fontSize: 16 }} /></IconButton></span></Tooltip>
      </Stack>
    </Box>
  )
}

export default function ScriptView({ open, onClose, timeline, onCommitLine, onSplit, onMerge, onRemove, onAppend }) {
  const scenes = timeline?.scenes || []
  const [draft, setDraft] = useState("")
  const words = scenes.reduce((a, s) => a + (s.line ? s.line.split(/\s+/).length : 0), 0)
  const add = () => {
    const line = draft.replace(/\s+/g, " ").trim()
    if (!line) return
    onAppend(line)
    setDraft("")
  }
  return (
    <Drawer anchor="right" open={open} onClose={onClose}
      slotProps={{ paper: { sx: { width: { xs: "100%", sm: 560 }, display: "flex", flexDirection: "column" }, "data-testid": "script-view" } }}>
      <Stack direction="row" alignItems="center" sx={{ px: 2.5, pt: 2, pb: 1 }}>
        <Box sx={{ flex: 1 }}>
          <Typography variant="h6" sx={{ fontWeight: 800 }}>Script</Typography>
          <Typography variant="body2" sx={{ color: "text.secondary" }}>
            {scenes.length} scenes · {words} words · {timeline.total.toFixed(0)}s. Edit any line; a changed line is re-voiced.
          </Typography>
        </Box>
        <IconButton aria-label="Close script" onClick={onClose}><CloseIcon /></IconButton>
      </Stack>
      <Box sx={{ flex: 1, overflowY: "auto", px: 2.5 }}>
        {scenes.map((sc, i) => (
          <Paragraph key={sc.uid} scene={sc} isLast={i === scenes.length - 1} canRemove={scenes.length > 1}
            onCommit={onCommitLine} onSplit={onSplit} onMerge={onMerge} onRemove={onRemove} />
        ))}
        <Stack direction="row" spacing={1} alignItems="flex-start" sx={{ py: 1.5 }}>
          <TextField fullWidth multiline minRows={1} maxRows={4} size="small" value={draft} onChange={(e) => setDraft(e.target.value)}
            placeholder="Add a line at the end…" onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); add() } }}
            slotProps={{ htmlInput: { "aria-label": "New line" } }} />
          <Button variant="outlined" startIcon={<AddIcon />} disabled={!draft.trim()} onClick={add} sx={{ textTransform: "none", fontWeight: 700, whiteSpace: "nowrap", flexShrink: 0 }}>
            Add line
          </Button>
        </Stack>
      </Box>
    </Drawer>
  )
}
