// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
/**
 * Shared caption + emoji enums for the tool pages and Clip Studio.
 *
 * The VALUES are the contract: they must match the keys of
 * backend/services/caption_service.py CAPTION_STYLES, minus `brainrot` (a look
 * applied by its own pipeline, not a general preset).
 * tests/test_caption_styles_parity.py fails if the two drift.
 *
 * They drifted once already: this list and the /api/tools/captions Literal
 * were both pinned to the original three, so the Captions tool offered 3 of
 * 10 styles — neon, karaoke, glow, urban, warm and mono were unreachable from
 * the tool built to apply them.
 *
 * Descriptions summarize the real render params (highlight colour, font,
 * words_per_group) rather than being decorative.
 *
 * `preview` mirrors the REAL render params of the matching entry in
 * caption_service.CAPTION_STYLES, so the Studio player's caption overlay
 * can't promise a look the burn-in doesn't deliver:
 *   text / highlight / outline — primary_color / highlight_color /
 *     outline_color, converted out of ASS's &H00BBGGRR byte order into CSS.
 *   font    — a CSS stack whose first family IS the style's `font`.
 *   words   — words_per_group, the pacing knob you can't see in a still.
 */
export const CAPTION_STYLES = [
  {
    value: "viral", label: "Viral", description: "Yellow highlight, ~6-word phrases",
    preview: { text: "#fff", highlight: "#ffff00", outline: "#000", font: "Arial, Helvetica, sans-serif", weight: 700, words: 6 },
  },
  {
    value: "classic", label: "Classic", description: "Full sentence, no highlight",
    preview: { text: "#fff", highlight: "#fff", outline: "#000", font: "Arial, Helvetica, sans-serif", weight: 400, words: 8 },
  },
  {
    value: "bold", label: "Bold", description: "Green highlight, ~4-word phrases",
    preview: { text: "#fff", highlight: "#00ff00", outline: "#000", font: "Impact, 'Haettenschweiler', sans-serif", weight: 400, words: 4 },
  },
  {
    value: "neon", label: "Neon", description: "Pink text, yellow highlight, ~6 words",
    preview: { text: "#ffaaff", highlight: "#ffff00", outline: "#330033", font: "Arial, Helvetica, sans-serif", weight: 700, words: 6 },
  },
  {
    value: "minimal", label: "Minimal", description: "Plain Arial, long lines, no highlight",
    preview: { text: "#fff", highlight: "#fff", outline: "#333", font: "Arial, Helvetica, sans-serif", weight: 400, words: 10 },
  },
  {
    value: "karaoke", label: "Karaoke", description: "Grey text lights up word by word",
    preview: { text: "#aaaaaa", highlight: "#ffff00", outline: "#000", font: "Arial, Helvetica, sans-serif", weight: 700, words: 7 },
  },
  {
    value: "glow", label: "Glow", description: "Soft orange glow, ~6-word phrases",
    preview: { text: "#fff", highlight: "#ffcc66", outline: "#cc6600", font: "Arial, Helvetica, sans-serif", weight: 700, words: 6 },
  },
  {
    value: "urban", label: "Bold Urban", description: "Arial Black, punchy ~3-word bursts",
    preview: { text: "#fff", highlight: "#ff8c00", outline: "#000", font: "'Arial Black', Arial, sans-serif", weight: 900, words: 3 },
  },
  {
    value: "warm", label: "Warm Glow", description: "Georgia serif, warm cream tone",
    preview: { text: "#fff5e1", highlight: "#ffc878", outline: "#3c1e0a", font: "Georgia, 'Times New Roman', serif", weight: 400, words: 5 },
  },
  {
    value: "mono", label: "Monochrome", description: "Verdana, grey highlight, understated",
    preview: { text: "#fff", highlight: "#c8c8c8", outline: "#141414", font: "Verdana, Geneva, sans-serif", weight: 400, words: 5 },
  },
]

// The label a caption style id is shown by (a saved preset's id, unknown here,
// shows as itself) — summaries never print a raw id like "urban".
export const captionStyleLabel = (id) =>
  (id && CAPTION_STYLES.find((s) => s.value === id)?.label) || id || ""

export const EMOJI_LEVELS = [
  { value: "none", label: "None" },
  { value: "minimal", label: "Minimal" },
  { value: "moderate", label: "Moderate" },
  { value: "heavy", label: "Heavy" },
]
