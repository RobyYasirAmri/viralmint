// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useState } from "react"
import { Box, IconButton, Popover, Stack, Tooltip, Typography } from "@mui/material"
import KeyboardIcon from "@mui/icons-material/KeyboardOutlined"

/**
 * The keyboard-shortcut list, as a popover on a small keyboard icon.
 *
 * Clipper's cutting bench had this; the Smart Video Studio — which binds MORE
 * keys (Space, ←/→, S, M, N, Delete, ⌘Z/⇧⌘Z) — had none, and named a handful
 * of them only inside button labels. A shortcut nobody can find is a shortcut
 * nobody has.
 *
 * `shortcuts` is [[keys, description], …]. The aria-label is fixed so both
 * surfaces (and the harnesses that drive them) address it the same way.
 */
export default function ShortcutsPopover({ shortcuts, size = "small", sx }) {
  const [anchor, setAnchor] = useState(null)
  if (!shortcuts?.length) return null
  return (
    <>
      <Tooltip title="Keyboard shortcuts">
        <IconButton
          size={size} aria-label="Keyboard shortcuts"
          onClick={(e) => setAnchor(e.currentTarget)}
          sx={{ color: "text.secondary", ...sx }}
        >
          <KeyboardIcon sx={{ fontSize: 17 }} />
        </IconButton>
      </Tooltip>
      <Popover
        open={Boolean(anchor)} anchorEl={anchor} onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
        slotProps={{ paper: { "data-testid": "shortcuts-popover" } }}
      >
        <Stack spacing={0.5} sx={{ p: 1.5, minWidth: 260 }}>
          {shortcuts.map(([keys, description]) => (
            <Stack key={keys} direction="row" spacing={1.5} alignItems="center">
              <Box sx={{
                minWidth: 62, px: 0.75, py: 0.15, borderRadius: 1,
                border: "1px solid", borderColor: "divider",
                fontFamily: "ui-monospace, monospace", fontSize: "0.68rem",
                textAlign: "center", flexShrink: 0,
              }}>{keys}</Box>
              <Typography variant="caption" sx={{ color: "text.secondary" }}>{description}</Typography>
            </Stack>
          ))}
        </Stack>
      </Popover>
    </>
  )
}
