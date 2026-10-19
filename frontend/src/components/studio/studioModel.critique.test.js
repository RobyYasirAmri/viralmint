// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { describe, it, expect } from "vitest"
import {
  LINE_MAX, SCENE_MAX, aspectValue, critique, estimateSeconds, isFixedVisual,
  isShortVisual, planLines, providerLabel, sceneAt, sceneDuration, splitSentences,
  visualSourceLabel, voiceProvider, withTimeline,
} from "./studioModel"

const LONG_LINE = "This opening line goes on and on for a very long time indeed."

const scene = (over = {}) => ({
  uid: "s", index: 0, start: 0, dur: 2, line: "a short line here", estimated: false,
  visual: { kind: "stock" }, ...over,
})

describe("critique — says whether a duration is measured or estimated", () => {
  it("an unvoiced long opening line is labelled (estimated)", () => {
    const notes = critique({ scenes: [scene({ uid: "a", dur: 4.26, line: LONG_LINE, estimated: true })] })
    expect(notes).toHaveLength(1)
    expect(notes[0]).toMatchObject({ uid: "a", severity: "high", fix: { kind: "split" } })
    expect(notes[0].message).toBe(
      "The opening line runs 4.3s (estimated) — most viewers decide in the first 3. Split it or shorten the hook.",
    )
  })

  it("a voiced opening line states the measured number without the qualifier", () => {
    const [note] = critique({ scenes: [scene({ dur: 4.26, line: LONG_LINE, estimated: false })] })
    expect(note.message).toContain("runs 4.3s —")
    expect(note.message).not.toContain("estimated")
  })

  it("a long-held later scene is flagged with the same qualifier rule", () => {
    const notes = critique({
      scenes: [
        scene({ uid: "a", dur: 1 }),
        scene({ uid: "b", index: 1, dur: 7.5, line: LONG_LINE, estimated: true }),
        scene({ uid: "c", index: 2, dur: 8, line: LONG_LINE, estimated: false }),
      ],
    })
    const msgs = notes.map((n) => n.message)
    expect(msgs).toContain("Scene 2 holds one visual for 7.5s (estimated). Splitting it adds a cut.")
    expect(msgs).toContain("Scene 3 holds one visual for 8.0s. Splitting it adds a cut.")
    expect(notes.every((n) => n.severity === "medium" && n.fix.label === "Split (S)")).toBe(true)
  })

  it("does not nag about a long line with fewer than four words", () => {
    expect(critique({ scenes: [scene({ dur: 9, line: "Hi there friend" })] })).toEqual([])
  })

  it("short visuals and failed visuals carry their fixes", () => {
    const notes = critique({
      scenes: [
        scene({ uid: "a", dur: 1 }),
        scene({ uid: "b", index: 1, dur: 5, visual: { kind: "stock", query: "q", asset: { native_duration: 3 } } }),
        scene({ uid: "c", index: 2, dur: 5, visual: { kind: "user_clip", fit: "freeze", asset: { native_duration: 2, query: "aq" } } }),
        scene({ uid: "d", index: 3, dur: 1, visual: { kind: "user_clip", state: "failed" } }),
      ],
    })
    expect(notes).toEqual([
      { uid: "b", severity: "low", message: "Scene 2's clip is 2.0s shorter than its line — it will loop.",
        fix: { kind: "search", label: "Find a longer clip", query: "q" } },
      { uid: "c", severity: "low", message: "Scene 3's clip is 3.0s shorter than its line — it will freeze.",
        fix: { kind: "search", label: "Find a longer clip", query: "aq" } },
      { uid: "d", severity: "high", message: "Scene 4 has no usable visual.", fix: { kind: "stock", label: "Use stock instead" } },
    ])
  })

  it("empty / missing timelines produce no notes", () => {
    expect(critique(null)).toEqual([])
    expect(critique({ scenes: [] })).toEqual([])
  })

  it("end-to-end: an unvoiced scene from withTimeline is critiqued as estimated", () => {
    const line = "word ".repeat(30).trim() + "."
    const t = withTimeline({ settings: {}, scenes: [{ uid: "x", line, voice: { state: "none" }, visual: {} }] })
    const [note] = critique(t)
    expect(note.message).toMatch(/\(estimated\)/)
    const voiced = withTimeline({ settings: {}, scenes: [{ uid: "x", line, voice: { state: "ready", duration: 5 }, visual: {} }] })
    expect(critique(voiced)[0].message).toContain("runs 5.2s —")
  })
})

describe("isShortVisual", () => {
  it("only stock/user clips shorter than the line (with a 50 ms tolerance)", () => {
    expect(isShortVisual(scene({ dur: 3, visual: { kind: "stock", asset: { native_duration: 2.96 } } }))).toBe(false)
    expect(isShortVisual(scene({ dur: 3, visual: { kind: "stock", asset: { native_duration: 2.9 } } }))).toBe(true)
    expect(isShortVisual(scene({ dur: 3, visual: { kind: "other", asset: { native_duration: 1 } } }))).toBe(false)
    expect(isShortVisual(scene({ dur: 3, visual: { kind: "stock" } }))).toBe(false)
    expect(isShortVisual(null)).toBe(false)
  })
})

describe("visualSourceLabel", () => {
  it("names each kind and state", () => {
    expect(visualSourceLabel(null)).toBe("—")
    expect(visualSourceLabel({ kind: "stock", asset: { query: "cats" } })).toBe("Stock · “cats”")
    expect(visualSourceLabel({ kind: "stock", query: "dogs" })).toBe("Stock · “dogs”")
    expect(visualSourceLabel({ kind: "stock" })).toBe("Stock · “”")
    expect(visualSourceLabel({ kind: "user_clip", asset: { title: "Mine" } })).toBe("Mine")
    expect(visualSourceLabel({ kind: "user_clip" })).toBe("Your clip")
    expect(visualSourceLabel({ kind: "motion_block" })).toBe("motion_block")
  })
})

describe("script → scene lines", () => {
  it("splits on Latin and CJK sentence ends and normalises whitespace", () => {
    expect(splitSentences("  Hello   world. How are you?Fine!  ")).toEqual(["Hello world.", "How are you?", "Fine!"])
    expect(splitSentences("你好。再见！")).toEqual(["你好。", "再见！"])
    expect(splitSentences("")).toEqual([])
  })

  it("packs short sentences two per scene", () => {
    expect(planLines("One. Two. Three. Four. Five.")).toEqual(["One. Two.", "Three. Four.", "Five."])
  })

  it("never lets a line exceed LINE_MAX — long sentences split on words, spaceless text hard-splits", () => {
    const words = Array.from({ length: 150 }, (_, i) => `word${i}`).join(" ") + "."
    const lines = planLines(words)
    expect(lines.length).toBeGreaterThan(1)
    expect(lines.every((l) => l.length <= LINE_MAX)).toBe(true)
    expect(lines.join(" ")).toBe(words)

    const blob = "x".repeat(LINE_MAX * 2 + 10)
    const parts = planLines(blob)
    expect(parts.every((l) => l.length <= LINE_MAX)).toBe(true)
    expect(parts.join("")).toBe(blob)
  })

  it("a long script grows the target so it fits in SCENE_MAX scenes", () => {
    const script = Array.from({ length: 60 }, (_, i) => `Sentence number ${i} is here with some words.`).join(" ")
    const lines = planLines(script)
    expect(lines.length).toBeLessThanOrEqual(SCENE_MAX)
    expect(lines.every((l) => l.length <= LINE_MAX)).toBe(true)
  })
})

describe("scene timing helpers", () => {
  it("estimateSeconds floors at 1.2s", () => {
    expect(estimateSeconds("")).toBe(1.2)
    expect(estimateSeconds(null)).toBe(1.2)
    expect(estimateSeconds("word ".repeat(40))).toBeGreaterThan(1.2)
  })

  it("sceneDuration: a ready take is exact, a stale one is re-estimated", () => {
    expect(sceneDuration({ voice: { state: "ready", duration: 2 } }, { tail_gap_s: 0.5 })).toBe(2.5)
    expect(sceneDuration({ line: "", voice: { state: "stale", duration: 9 } })).toBeCloseTo(1.35)
  })

  it("sceneAt returns the scene covering t", () => {
    const scenes = [{ start: 0 }, { start: 2 }, { start: 5 }]
    expect(sceneAt(scenes, 0)).toBe(scenes[0])
    expect(sceneAt(scenes, 2)).toBe(scenes[1])
    expect(sceneAt(scenes, 4.9)).toBe(scenes[1])
    expect(sceneAt(scenes, 99)).toBe(scenes[2])
    expect(sceneAt([], 1)).toBeNull()
  })

  it("isFixedVisual", () => {
    expect(isFixedVisual({ visual: { pinned: true } })).toBe(true)
    expect(isFixedVisual({ visual: { kind: "user_clip" } })).toBe(true)
    expect(isFixedVisual({ visual: { state: "ready" } })).toBe(true)
    expect(isFixedVisual({ visual: { state: "generating" } })).toBe(true)
    expect(isFixedVisual({ visual: { kind: "stock" } })).toBe(false)
    expect(isFixedVisual(null)).toBe(false)
  })

  it("misc presentation", () => {
    expect(aspectValue("16:9")).toBeCloseTo(16 / 9)
    expect(aspectValue("bogus")).toBeCloseTo(9 / 16)
    expect(providerLabel(undefined)).toBe("Pexels")
    expect(voiceProvider(undefined)).toBe("edge_tts")
    expect(voiceProvider({ voice: { provider: "openai_tts" } })).toBe("openai_tts")
  })
})
