// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { Box, Typography, Stack, Tooltip, LinearProgress } from "@mui/material"
import { GlassPanel } from "../../utils/glassFx"
import WhatshotIcon from "@mui/icons-material/Whatshot"

// 5-factor virality scoreboard rendered in the clip detail panel. Reads:
//   clip.clip_hook_score                         → "Hook" bar
//   clip.clip_score_breakdown.flow|value|...     → other 4 bars
//
// Component renders nothing if neither hook_score nor breakdown is present
// (legacy clips, pre-2026-05-18 extractions). The 5-bar layout mirrors
// a 4-factor scorecard plus a "Shareability" factor.

const FACTOR_META = {
  hook: {
    label: "Hook",
    blurb: "Does the opening 2-3 seconds stop the scroll? Scored on the first sentence only.",
  },
  flow: {
    label: "Flow",
    blurb: "Logical narrative arc with a satisfying close — no dangling thoughts, no cliffhangers that need context.",
  },
  value: {
    label: "Value",
    blurb: "Emotional or practical resonance — \"did you know\" payoff, actionable takeaway, gut reaction.",
  },
  trend: {
    label: "Trend",
    blurb: "Alignment with what audiences are clicking on right now in this niche.",
  },
  shareability: {
    label: "Share",
    blurb: "Would a viewer quote this, screenshot it, or send it to a friend?",
  },
}

// clip_score_breakdown_json arrives as a JSON string ({flow, value, trend,
// shareability} each 1-10). Parse defensively — a legacy clip has no field,
// a malformed one must not throw. Null hides the bars.
export function parseScoreBreakdown(clip) {
  const raw = clip?.clip_score_breakdown ?? clip?.clip_score_breakdown_json
  if (!raw) return null
  if (typeof raw === "object") return raw
  try {
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === "object" ? parsed : null
  } catch {
    return null
  }
}

// Map a 1-10 score to a color. Same thresholds as viralityColor in
// clipFormat.js so the bars and the overall chip stay consistent.
function scoreColor(score) {
  if (score == null) return "grey"
  if (score >= 8) return "success.main"
  if (score >= 6) return "warning.main"
  return "text.disabled"
}

function ScoreBar({ factor, score }) {
  const meta = FACTOR_META[factor]
  if (!meta) return null
  const pct = score == null ? 0 : Math.max(0, Math.min(score, 10)) * 10
  const color = scoreColor(score)
  return (
    <Tooltip title={meta.blurb} arrow placement="top">
      <Box sx={{ cursor: "default" }}>
        <Stack direction="row" justifyContent="space-between" spacing={0.75} sx={{ mb: 0.25, whiteSpace: "nowrap" }}>
          <Typography variant="caption" sx={{ fontWeight: 600, fontSize: "0.7rem" }}>
            {meta.label}
          </Typography>
          <Typography variant="caption" sx={{ fontWeight: 700, fontSize: "0.7rem", color }}>
            {score == null ? "—" : score.toFixed(1)}
          </Typography>
        </Stack>
        <LinearProgress
          variant="determinate"
          value={pct}
          sx={{
            height: 5, borderRadius: 3,
            bgcolor: (t) => t.palette.mode === "dark" ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)",
            "& .MuiLinearProgress-bar": { bgcolor: color, borderRadius: 3 },
          }}
        />
      </Box>
    </Tooltip>
  )
}

export default function ScoreBreakdownPanel({ clip }) {
  if (!clip) return null
  const hook = clip.clip_hook_score
  const breakdown = parseScoreBreakdown(clip)
  // Hide entirely on legacy clips — neither hook nor breakdown means the
  // scoreboard would just be 5 empty bars. Vidiq does the same.
  if (hook == null && !breakdown) return null

  // Build the 5 factors. Hook lives on its own column for backward compat
  // (older clips have hook_score but no breakdown).
  const factors = [
    { key: "hook", score: hook },
    { key: "flow", score: breakdown?.flow },
    { key: "value", score: breakdown?.value },
    { key: "trend", score: breakdown?.trend },
    { key: "shareability", score: breakdown?.shareability },
  ]

  return (
    <GlassPanel sx={{ p: 2, borderRadius: 2 }}>
      {/* Wraps as a unit: "Overall" drops under the title rather than the
          overline breaking into "VIRALITY / SCOREBOARD" (audit 2026-09-25). */}
      <Stack direction="row" alignItems="center" columnGap={1} rowGap={0.25} flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ whiteSpace: "nowrap" }}>
          <WhatshotIcon sx={{ fontSize: 16, color: "primary.main" }} />
          <Typography variant="overline" sx={{ color: "text.secondary", fontWeight: 700, fontSize: "0.65rem", lineHeight: 1.6 }}>
            Virality scoreboard
          </Typography>
        </Stack>
        {clip.clip_virality_score != null && (
          <>
            <Box sx={{ flex: 1 }} />
            <Typography variant="caption" sx={{ color: "text.secondary", fontSize: "0.7rem", whiteSpace: "nowrap" }}>
              Overall: <strong>{clip.clip_virality_score.toFixed(1)}</strong>/10
            </Typography>
          </>
        )}
      </Stack>
      {/* Columns from the PANEL's width, not the window's: the panel sits in
          a side column, and a viewport breakpoint gave it 5 columns at 170px
          wide — "Value7.0" with the value cut off. */}
      <Box sx={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(78px, 1fr))",
        gap: 1.5,
      }}>
        {factors.map(({ key, score }) => (
          <ScoreBar key={key} factor={key} score={score} />
        ))}
      </Box>
      {clip.clip_virality_reason && (
        <Typography variant="caption" sx={{ display: "block", mt: 1.5, color: "text.secondary", fontStyle: "italic", fontSize: "0.78rem", lineHeight: 1.5 }}>
          {clip.clip_virality_reason}
        </Typography>
      )}
    </GlassPanel>
  )
}
