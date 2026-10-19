// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
// Legacy `/stock?…` links → a Studio project.
//
// These params arrive in a URL (Library "Use as inspiration", any bookmarked
// link) — every value is validated before it reaches a project. A `?script=`
// NEVER drafts (it's the script, already written); only a bare `?topic=` /
// `?source=` drafts one, with the same script call Home's desk uses.
import { STYLES } from "../components/create/SmartVideoStyles"
import { ASPECTS, TRANSITION_VALUES as TRANSITIONS } from "../components/studio/studioModel"

// The enums come from studioModel (one frontend source).
export const VALID_ASPECTS = ASPECTS
const VALID_STYLES = new Set(STYLES.map((s) => s.id))

const onOff = (v) => (v === "on" ? true : v === "off" ? false : null)

/**
 * Read a legacy query once. Returns null when it carries no handoff, else
 * { start: {script|topic|source_id}, aspect_ratio, visual_style, settings, transition }.
 */
export function parseLegacyQuery(params) {
  const get = (k) => params.get(k)
  const script = (get("script") || "").slice(0, 5000).trim()
  const topic = (get("topic") || "").slice(0, 200).trim()
  const source = (get("source") || "").trim()
  if (!script && !topic && !source && !get("aspect")) return null

  const aspect = VALID_ASPECTS.includes(get("aspect")) ? get("aspect") : null
  const style = VALID_STYLES.has(get("style")) ? get("style") : null
  const settings = {}
  const captions = onOff(get("captions"))
  const capStyle = get("caption_style")
  // "none" is the disable SENTINEL, not a style id — captions-off travels in `captions`.
  if (captions !== null || (capStyle && capStyle !== "none" && /^[a-z0-9_-]{1,32}$/.test(capStyle))) {
    settings.captions = {
      ...(captions !== null ? { enabled: captions } : {}),
      ...(capStyle && capStyle !== "none" && /^[a-z0-9_-]{1,32}$/.test(capStyle) ? { style: capStyle } : {}),
    }
  }
  const music = onOff(get("music"))
  if (music !== null) settings.music = { enabled: music }
  const transition = TRANSITIONS.includes(get("transition")) ? get("transition") : null
  return {
    // An explicit script WINS over a topic: drafting would replace a script the link already carries.
    start: script ? { script } : topic ? { topic } : source && /^[A-Za-z0-9_-]{1,64}$/.test(source) ? { source_id: source } : {},
    aspect_ratio: aspect, visual_style: style, settings, transition,
  }
}

/** The ops that apply a handoff's non-create settings to a fresh project. */
export function handoffOps(h) {
  const ops = []
  if (h.transition) ops.push({ op: "set_setting", path: "transition", value: h.transition })
  if (h.settings?.music && Object.keys(h.settings.music).length) ops.push({ op: "set_setting", path: "music", value: h.settings.music })
  return ops
}

/** A stable key for "this exact link already made a project" (10 minutes). */
export function handoffKey(search) {
  let h = 0x811c9dc5
  for (let i = 0; i < search.length; i += 1) { h ^= search.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0 }
  return `vm_studio_handoff_${h.toString(16)}`
}

// The settings a NEW project inherits from an existing project — one shape for
// every "make another" path, so none of them silently drops music or the
// transition. `source` may be a
// project document's settings, or a loose brief ({voice, captions, music, …});
// unknown or missing fields are left out (the server fills its defaults).
export function projectSettingsFrom(source) {
  const s = source || {}
  const out = {}
  const pick = (obj, keys) => {
    if (!obj || typeof obj !== "object") return null
    const o = {}
    for (const k of keys) if (obj[k] !== undefined && obj[k] !== null) o[k] = obj[k]
    return Object.keys(o).length ? o : null
  }
  const voice = pick(s.voice, ["provider", "voice", "label"])
  if (voice?.provider || voice?.voice) out.voice = voice
  // `hook` (the opening title on/off) carries; its text belongs to one video.
  const captions = pick(s.captions, ["enabled", "style", "hook"])
  if (captions) out.captions = captions
  const music = pick(s.music, ["enabled", "source", "genre", "track", "track_name", "volume_db", "offset_s", "fade_s"])
  if (music) out.music = music
  if (TRANSITIONS.includes(s.transition)) out.transition = s.transition
  return out
}
