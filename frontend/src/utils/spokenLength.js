// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
// CJK-aware narration length estimation (2026-07-18).
//
// Every "split on whitespace ÷ 2.5 words/sec" heuristic breaks on
// whitespace-free scripts: a 244-second Chinese narration (881 chars) counted
// as ~1 "word", so the est-cost chip and "~Ns spoken" label showed a near-$0,
// near-0s video that actually billed ~44¢ and ran 4 minutes. Ideographic
// scripts narrate per CHARACTER — the rate is calibrated from that real
// render (≈3.6 chars/sec incl. punctuation).
//
// Keep the formula in sync with backend tts_service.estimate_spoken_seconds.
const CJK_RE = /[぀-ヿ㐀-䶿一-鿿豈-﫿가-힯]/g
const LATIN_WORDS_PER_SEC = 2.5
const CJK_CHARS_PER_SEC = 3.5

/**
 * narrationStats(text) → {
 *   words:     Latin word count,
 *   cjkChars:  ideographic character count,
 *   units:     what to DISPLAY as the count (words + cjk chars),
 *   unitLabel: "words" | "chars" (chars when the text is CJK-dominant),
 *   seconds:   estimated spoken seconds (rounded up, for display),
 *   secondsExact: the same estimate UNROUNDED.
 * }
 *
 * `secondsExact` exists for cumulative use. Rounding each line up before
 * summing inflates a running timestamp by up to half a second per line, which
 * on a 40-line dialogue is twenty seconds of invented time — so anything that
 * ACCUMULATES must take the exact value and round once at the end.
 */
export function narrationStats(text) {
  const t = (text || "").trim()
  if (!t) return { words: 0, cjkChars: 0, units: 0, unitLabel: "words", seconds: 0, secondsExact: 0 }
  const cjkChars = (t.match(CJK_RE) || []).length
  const words = t.replace(CJK_RE, " ").split(/\s+/).filter(Boolean).length
  const secondsExact = words / LATIN_WORDS_PER_SEC + cjkChars / CJK_CHARS_PER_SEC
  return {
    words,
    cjkChars,
    units: words + cjkChars,
    unitLabel: cjkChars > words ? "chars" : "words",
    seconds: Math.ceil(secondsExact),
    secondsExact,
  }
}
