// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { describe, it, expect } from "vitest"
import { mergeRemembered } from "./studioApi"
import { renderInProgress } from "./useStudioProject"

describe("mergeRemembered", () => {
  it("keeps remembered fields the new value doesn't know (an older render has no voice)", () => {
    const prev = { voice: { provider: "openai_tts", voice: "nova" }, captions: { enabled: true, style: "bold" } }
    expect(mergeRemembered(prev, { voice: undefined, captions: { enabled: false, style: "neon" } }))
      .toEqual({ voice: { provider: "openai_tts", voice: "nova" }, captions: { enabled: false, style: "neon" } })
  })

  it("replaces a given field whole — two voices' keys never mix", () => {
    const prev = { voice: { provider: "openai_tts", voice: "nova", label: "Nova" } }
    expect(mergeRemembered(prev, { voice: { provider: "edge_tts", voice: "en-US-Guy" } }).voice)
      .toEqual({ provider: "edge_tts", voice: "en-US-Guy" })
  })

  it("merges settings groups per field — a link that only says captions=on keeps the style", () => {
    const prev = { captions: { enabled: false, style: "bold" }, music: { enabled: true, genre: "lofi", track: "a.mp3" } }
    expect(mergeRemembered(prev, { captions: { enabled: true }, music: { genre: "cinematic" } }))
      .toEqual({ captions: { enabled: true, style: "bold" }, music: { enabled: true, genre: "cinematic", track: "a.mp3" } })
  })

  it("starts from nothing when nothing (or junk) is remembered", () => {
    expect(mergeRemembered(null, { a: 1 })).toEqual({ a: 1 })
    expect(mergeRemembered([1], { a: 1 })).toEqual({ a: 1 })
  })
})

describe("renderInProgress", () => {
  it("a rendering claim counts only while its job is alive", () => {
    expect(renderInProgress({ status: "rendering", render_alive: true })).toBe(true)
    expect(renderInProgress({ status: "rendering", render_alive: false })).toBe(false)
    expect(renderInProgress({ status: "rendering" })).toBe(true)      // older backend: trust the status
    expect(renderInProgress({ status: "draft", render_alive: true })).toBe(false)
    expect(renderInProgress(null)).toBe(false)
  })
})
