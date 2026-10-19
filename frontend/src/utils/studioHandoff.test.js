// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { describe, it, expect } from "vitest"
import { handoffKey, handoffOps, parseLegacyQuery, projectSettingsFrom } from "./studioHandoff"

const q = (s) => new URLSearchParams(s)

describe("parseLegacyQuery", () => {
  it("returns null for a plain visit", () => {
    expect(parseLegacyQuery(q(""))).toBeNull()
  })
  it("an explicit script wins over a topic, so the link never re-drafts a written script", () => {
    const h = parseLegacyQuery(q("script=Hello%20world.&topic=money&aspect=16:9&style=neon"))
    expect(h.start).toEqual({ script: "Hello world." })
    expect(h.aspect_ratio).toBe("16:9")
    expect(h.visual_style).toBe("neon")
  })
  it("a bare topic drafts; a Library source drafts from the source", () => {
    expect(parseLegacyQuery(q("topic=5%20money%20habits")).start).toEqual({ topic: "5 money habits" })
    // The Library / Videos menu link: /stock?source=<downloaded id>
    expect(parseLegacyQuery(q("source=abc-123")).start).toEqual({ source_id: "abc-123" })
    expect(parseLegacyQuery(q("source=..%2F..%2Fetc")).start).toEqual({})
  })
  it("rejects an unknown style, aspect and hostile params", () => {
    const h = parseLegacyQuery(q("script=x.&style=<b>&aspect=4:3&caption_style=none&transition=fade"))
    expect(h.visual_style).toBeNull()
    expect(h.aspect_ratio).toBeNull()
    expect(h.settings.captions).toBeUndefined()
    expect(h.settings.voice).toBeUndefined()
    expect(h.transition).toBeNull()
  })
  it("applies captions, music and transition", () => {
    const h = parseLegacyQuery(q("script=x.&captions=on&caption_style=bold&music=off&transition=smooth"))
    expect(h.settings.captions).toEqual({ enabled: true, style: "bold" })
    expect(h.settings.music).toEqual({ enabled: false })
    expect(handoffOps(h)).toEqual([
      { op: "set_setting", path: "transition", value: "smooth" },
      { op: "set_setting", path: "music", value: { enabled: false } },
    ])
  })
})

describe("handoffKey", () => {
  it("is stable per query and differs between queries", () => {
    expect(handoffKey("source=a")).toBe(handoffKey("source=a"))
    expect(handoffKey("source=a")).not.toBe(handoffKey("source=b"))
    expect(handoffKey("source=a")).toMatch(/^vm_studio_handoff_[0-9a-f]+$/)
  })
})

describe("projectSettingsFrom — one shape for every 'make another'", () => {
  it("carries voice, captions, music and transition", () => {
    const settings = {
      voice: { provider: "openai_tts", voice: "nova", label: "Nova" },
      captions: { enabled: true, style: "bold" },
      music: { enabled: true, source: "library", track: "lofi_a.mp3", track_name: "a", volume_db: -12 },
      transition: "smooth", visual_style: "neon",
    }
    expect(projectSettingsFrom(settings)).toEqual({
      voice: { provider: "openai_tts", voice: "nova", label: "Nova" },
      captions: { enabled: true, style: "bold" },
      music: { enabled: true, source: "library", track: "lofi_a.mp3", track_name: "a", volume_db: -12 },
      transition: "smooth",
    })
  })
  it("leaves out what it doesn't know (the server fills its defaults)", () => {
    expect(projectSettingsFrom({ voice: {}, captions: { style: "viral" }, transition: "fade" }))
      .toEqual({ captions: { style: "viral" } })
    expect(projectSettingsFrom(null)).toEqual({})
  })
})
