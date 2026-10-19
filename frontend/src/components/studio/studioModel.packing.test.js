// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { describe, expect, it } from "vitest"
import data from "./__fixtures__/scenePacking.fixture.json"
import { critique, joinSentences, planLines, spokenUnits } from "./studioModel"

// The fixture was generated from backend/services/studio_doc.py (a copy of the
// hosted repo's portal fixture — regenerate it if the packing rules change).
// Home's live scene list must cut exactly
// like the editor's server does — it promised 14 scenes for a script the
// server built 18 from (80 vs 60 char target, 2026-10-13 audit).
describe("planLines matches studio_doc.plan_lines", () => {
  it.each(data.plans.map((f, i) => [i, f]))("case %i", (_i, f) => {
    // The desktop mirror counts UTF-16 units in splitLong (emoji/astral cases
    // are pinned by the portal port, which counts code points).
    if (/[\u{10000}-\u{10FFFF}]/u.test(f.script)) return
    expect(planLines(f.script)).toEqual(f.lines)
  })
})

describe("CJK-aware helpers", () => {
  it("weighs a CJK character as ~4.3 Latin ones", () => {
    expect(spokenUnits("abc")).toBe(3)
    expect(spokenUnits("你好")).toBeCloseTo(8.6)
  })
  it("joins CJK sentences without a space", () => {
    expect(joinSentences("你好。", "再见。")).toBe("你好。再见。")
    expect(joinSentences("Hi.", "Bye.")).toBe("Hi. Bye.")
  })
  it("the critic flags a long Chinese opening line", () => {
    const line = "冬天植物死掉，往往不是因为冷，而是因为你浇水太多了。"
    const notes = critique({ scenes: [{ uid: "a", index: 0, line, dur: 7.5, estimated: true, visual: { kind: "stock" } }] })
    expect(notes.map((n) => n.fix.kind)).toContain("split")
  })
})

describe("weak stock match note", () => {
  const scene = (asset) => ({ uid: "s", index: 2, line: "flour water salt", dur: 3, visual: { kind: "stock", weak_id: "9", query: "flour", asset } })
  it("flags the clip the planner judged a poor match", () => {
    const notes = critique({ scenes: [scene({ provider_id: "9", native_duration: 10 })] })
    expect(notes.find((n) => n.fix.kind === "search")?.message).toMatch(/may not match/)
  })
  it("clears once another clip is bound", () => {
    const notes = critique({ scenes: [scene({ provider_id: "10", native_duration: 10 })] })
    expect(notes.some((n) => /may not match/.test(n.message))).toBe(false)
  })
})
