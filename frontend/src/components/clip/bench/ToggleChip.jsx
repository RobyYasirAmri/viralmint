// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { Chip, alpha } from "@mui/material"
import CheckRoundedIcon from "@mui/icons-material/CheckRounded"

// An on/off setting drawn as a chip (audit 2026-09-25). Two things the plain
// clickable Chips got wrong:
//   - they were toggles without aria-pressed, so a screen reader heard
//     "Vertical 9:16, button" with no idea whether it was on;
//   - "on" was a FILLED primary chip — beside "Play clip" that read as a
//     second primary button. On is a quiet tinted outline with a check.
// The label never changes with the state; `pressed` carries it.
export default function ToggleChip({ label, pressed, onToggle, sx, ...rest }) {
  return (
    <Chip
      size="small"
      variant="outlined"
      label={label}
      icon={pressed ? <CheckRoundedIcon sx={{ fontSize: "15px !important" }} /> : undefined}
      aria-pressed={!!pressed}
      onClick={onToggle}
      sx={(t) => ({
        fontWeight: 600,
        ...(pressed
          ? {
            color: "primary.main",
            borderColor: alpha(t.palette.primary.main, 0.5),
            bgcolor: alpha(t.palette.primary.main, t.palette.mode === "dark" ? 0.16 : 0.08),
            "& .MuiChip-icon": { color: "primary.main" },
            "&&:hover": { bgcolor: alpha(t.palette.primary.main, t.palette.mode === "dark" ? 0.24 : 0.14) },
          }
          : { color: "text.secondary" }),
        ...(typeof sx === "function" ? sx(t) : sx),
      })}
      {...rest}
    />
  )
}
