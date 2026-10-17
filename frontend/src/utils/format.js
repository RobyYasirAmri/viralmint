// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
/**
 * Shared formatters. One implementation each, so the same value never renders
 * two different ways on two screens.
 */

const NAIVE_DATETIME = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/

/**
 * Coerce the timestamp shapes this app receives into a Date.
 *
 * A bare number is UNIX SECONDS. Returns null when the input can't be read as
 * a time, so callers render their own blank rather than "Invalid Date".
 *
 * ⚠️ A NAIVE datetime string is read as UTC, not local. Every timestamp the
 * backend stores is `datetime.utcnow()` — naive UTC — and FastAPI serializes it
 * with `.isoformat()`, which appends no offset. ECMAScript says a date-TIME
 * form without a designator is LOCAL time, so `new Date(raw)` shifts every
 * relative age by the viewer's UTC offset: at UTC+2, a job that started five
 * minutes ago renders as "2h ago". Reading it as UTC is what the producer meant.
 *
 * The space-separated SQLite form is normalized to "T" in the same step —
 * engines are not required to parse it, and Safari does not.
 */
export function toDate(input) {
  if (input == null || input === "") return null
  if (typeof input === "number") {
    const n = new Date(input * 1000)
    return Number.isNaN(n.getTime()) ? null : n
  }
  let raw = input
  if (typeof raw === "string" && NAIVE_DATETIME.test(raw.trim())) {
    raw = raw.trim().replace(" ", "T") + "Z"
  }
  const d = new Date(raw)
  return Number.isNaN(d.getTime()) ? null : d
}

/**
 * Abbreviated relative-age formatter used where we never want to fall
 * back to a calendar date. Ladders d → w → mo → y. Channels uses this
 * for "video uploaded X ago" badges.
 *
 * @param {string|number|Date} input  ISO string, Date, or UNIX seconds (the channel API shape).
 * @returns {string}
 */
export function formatRelativeAge(input) {
  const d = toDate(input)
  if (!d) return ""
  const diff = Date.now() - d.getTime()
  const days = Math.floor(diff / 86400000)
  if (days < 1) return "Today"
  if (days === 1) return "1d ago"
  if (days < 7) return `${days}d ago`
  if (days < 30) return `${Math.floor(days / 7)}w ago`
  if (days < 365) return `${Math.floor(days / 30)}mo ago`
  return `${Math.floor(days / 365)}y ago`
}

/**
 * Seconds → a clock badge: "1:05", "1:02:03".
 *
 * Quantised to the requested precision BEFORE splitting into fields, so a value
 * that rounds up across a boundary carries into the minute rather than
 * rendering "0:60". Clamped at zero: a negative duration is a bug upstream and
 * a badge is not the place to surface it.
 */
export function formatClock(seconds, { fallback = "", padMinutes = false, decimals = 0 } = {}) {
  const n = Number(seconds)
  if (seconds == null || !Number.isFinite(n)) return fallback
  const factor = 10 ** decimals
  const total = Math.max(0, Math.round(n * factor) / factor)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total - h * 3600 - m * 60
  const ss = s.toFixed(decimals).padStart(decimals ? decimals + 3 : 2, "0")
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${ss}`
  return `${padMinutes ? String(m).padStart(2, "0") : m}:${ss}`
}

/**
 * Seconds → compact prose: "1h 30m" / "2m 51s" / "45s" / "<1s".
 *
 * Rounds first so float durations never leak floating-point noise into the UI.
 * Seconds are dropped once an hour is involved — "1h 30m 12s" is noise in a
 * meta line. Sub-second clips are real (a trimmed frame), and "0s" would read
 * as an empty or failed asset, so they are named as short instead.
 */
export function formatDuration(seconds) {
  const n = Number(seconds)
  const raw = Number.isFinite(n) ? Math.max(0, n) : 0
  const total = Math.round(raw)
  if (total === 0) return raw > 0 ? "<1s" : "0s"
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0) return m > 0 ? `${h}h ${m}m` : `${h}h`
  if (m > 0) return s > 0 ? `${m}m ${s}s` : `${m}m`
  return `${s}s`
}

/**
 * Format a timestamp as "just now" / "Nm ago" / "Nh ago" / "Nd ago", falling
 * back to a localized short date once `fullDateAfterDays` has elapsed.
 *
 * @param {string|number|Date} iso     ISO string, Date, or UNIX seconds.
 * @param {object} [opts]
 * @param {number}  [opts.fullDateAfterDays=30]    Switch to a calendar date past this many days.
 * @param {boolean} [opts.includeYear=false]       Include the year in the calendar fallback.
 * @param {boolean} [opts.useYesterday=false]      Render exactly 1 day ago as "Yesterday".
 * @param {boolean} [opts.verbose=false]           "5 min ago" / "2 hours ago" instead of "5m" / "2h".
 * @param {boolean} [opts.secondsGranularity=false] Tick in seconds under a minute ("12s ago").
 * @returns {string}
 */
export function formatRelativeTime(iso, opts = {}) {
  const d = toDate(iso)
  if (!d) return ""
  const fullDateAfterDays = opts.fullDateAfterDays ?? 30
  const includeYear = opts.includeYear ?? false
  const useYesterday = opts.useYesterday ?? false
  const verbose = opts.verbose ?? false
  const secondsGranularity = opts.secondsGranularity ?? false

  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"} ago`

  const secs = Math.floor((Date.now() - d.getTime()) / 1000)
  if (secs < (secondsGranularity ? 5 : 60)) return verbose ? "Just now" : "just now"
  if (secondsGranularity && secs < 60) return `${secs}s ago`
  const mins = Math.floor(secs / 60)
  if (mins < 60) return verbose ? `${mins} min ago` : `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return verbose ? plural(hrs, "hour") : `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  if (useYesterday && days === 1) return "Yesterday"
  if (days < fullDateAfterDays) return verbose ? plural(days, "day") : `${days}d ago`

  const dateOpts = { month: "short", day: "numeric" }
  if (includeYear) dateOpts.year = "numeric"
  return d.toLocaleDateString(undefined, dateOpts)
}
