// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { Box, ButtonBase, Tooltip } from "@mui/material"
import { CAPTION_STYLES } from "./captionOptions"

// Caption style picker — inline pills for a narrow rail (the Smart Video
// Studio's Project panel). Each label carries the style's own face and text
// colour over a dark chip, with the highlight colour as the rule underneath,
// so the colour — the thing you actually pick on — is visible before you pick.
// The colours come from captionOptions.preview (derived from
// caption_service.CAPTION_STYLES).
function StyleChip({ style, selected, onSelect }) {
  const p = style.preview
  return (
    <Tooltip title={style.description} placement="top" arrow>
      <ButtonBase
        onClick={() => onSelect(style.value)}
        aria-label={`${style.label} caption style — ${style.description}`}
        aria-pressed={selected}
        sx={(t) => ({
          px: 1, py: 0.35, borderRadius: 1,
          bgcolor: "#101014",
          border: 2,
          borderColor: selected ? "primary.main" : "transparent",
          boxShadow: `inset 0 -3px 0 ${p.highlight}`,
          fontFamily: p.font, fontWeight: p.weight,
          fontSize: "0.74rem", lineHeight: 1.5, letterSpacing: 0.2,
          color: p.text,
          transition: "border-color 140ms",
          "&:hover": { borderColor: selected ? "primary.main" : t.palette.primary.light },
          "&:focus-visible": { outline: `2px solid ${t.palette.primary.main}`, outlineOffset: 2 },
        })}
      >
        {style.label}
      </ButtonBase>
    </Tooltip>
  )
}

/**
 * @param value     selected style value
 * @param onChange  (value) => void
 */
export default function CaptionStylePicker({ value, onChange }) {
  return (
    <Box role="group" aria-label="Caption style" sx={{ display: "flex", flexWrap: "wrap", gap: 0.6 }}>
      {CAPTION_STYLES.map((s) => (
        <StyleChip key={s.value} style={s} selected={value === s.value} onSelect={onChange} />
      ))}
    </Box>
  )
}
