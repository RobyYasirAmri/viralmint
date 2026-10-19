import { Box, Typography, IconButton, CircularProgress } from "@mui/material"
import PlayArrowIcon from "@mui/icons-material/PlayArrow"

export function VoiceRow({ voice, selected, onClick, onPreview, isPlayingPreview }) {
  return (
    <Box
      onClick={onClick}
      sx={(theme) => ({
        cursor: "pointer",
        height: 50,
        px: 0.875,
        borderRadius: 1.5,
        display: "flex", alignItems: "center", gap: 1,
        position: "relative",
        transition: "background .12s ease, transform .12s ease",
        border: "1px solid",
        borderColor: selected ? "primary.main" : "transparent",
        background: selected
          ? (theme.palette.mode === "dark"
              ? "linear-gradient(90deg, rgba(99,179,237,0.16), rgba(99,179,237,0.04))"
              : "linear-gradient(90deg, rgba(99,179,237,0.18), rgba(99,179,237,0.05))")
          : "transparent",
        ...(selected && {
          boxShadow: "0 0 14px rgba(99,179,237,0.30), inset 0 0 8px rgba(99,179,237,0.10)",
        }),
        "&:hover": {
          background: selected ? undefined
            : (theme.palette.mode === "dark" ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.04)"),
          transform: "translateX(2px)",
        },
      })}
    >
      <IconButton
        size="small"
        onClick={(e) => { e.stopPropagation(); onPreview?.(voice) }}
        sx={{
          p: 0.25, width: 30, height: 30, flexShrink: 0,
          bgcolor: selected ? "primary.main" : "action.hover",
          color: selected ? "#fff" : "text.primary",
          "&:hover": { bgcolor: selected ? "primary.dark" : "action.selected" },
        }}
      >
        {isPlayingPreview
          ? <CircularProgress size={14} sx={{ color: "inherit" }} />
          : <PlayArrowIcon sx={{ fontSize: 17 }} />}
      </IconButton>
      <Typography
        variant="body2"
        sx={{ fontWeight: selected ? 700 : 600, fontSize: "0.85rem", lineHeight: 1.1, flexShrink: 0 }}
      >
        {voice.label}
      </Typography>
      <Typography
        variant="caption"
        sx={{ color: "text.secondary", fontSize: "0.72rem", flex: 1, minWidth: 0, lineHeight: 1.2 }}
        noWrap
      >
        {voice.tagline}
      </Typography>
      {voice.country && (
        <Box sx={{
          px: 0.5, py: 0.1,
          fontSize: "0.6rem", fontWeight: 700,
          color: "text.secondary",
          border: 1, borderColor: "divider",
          borderRadius: 0.5,
          lineHeight: 1, flexShrink: 0,
          fontVariantNumeric: "tabular-nums",
        }}>
          {voice.country}
        </Box>
      )}
    </Box>
  )
}
