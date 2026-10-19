// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock("../../api/http", () => ({ default: { get } }))

import useTtsVoices, { _resetVoiceCache } from "./useTtsVoices"

describe("useTtsVoices — the engines' own vocabulary", () => {
  beforeEach(() => { _resetVoiceCache(); get.mockReset() })

  it("lists Edge voices first, then OpenAI, from /api/config/voices/{provider}", async () => {
    get.mockImplementation((url) => Promise.resolve({ data: { voices: url.endsWith("/edge_tts")
      ? [{ voice_id: "en-US-GuyNeural", name: "Guy", category: "Male", locale: "en-US" }]
      : [{ voice_id: "nova", name: "Nova", category: "female" }] } }))
    const { result } = renderHook(() => useTtsVoices())
    await waitFor(() => expect(result.current.voices).toHaveLength(2))
    expect(get.mock.calls.map((c) => c[0])).toEqual(["/api/config/voices/edge_tts", "/api/config/voices/openai_tts"])
    expect(result.current.voices.map((v) => [v.id, v.provider, v.country])).toEqual([
      ["en-US-GuyNeural", "edge_tts", "US"], ["nova", "openai_tts", ""],
    ])
  })

  it("keeps the providers that answered when one fails", async () => {
    get.mockImplementation((url) => (url.endsWith("/openai_tts")
      ? Promise.reject(new Error("boom"))
      : Promise.resolve({ data: { voices: [{ voice_id: "en-GB-SoniaNeural", name: "Sonia", locale: "en-GB" }] } })))
    const { result } = renderHook(() => useTtsVoices())
    await waitFor(() => expect(result.current.voices).toHaveLength(1))
    expect(result.current.error).toBe(false)
  })

  it("reports an error only when no provider answered", async () => {
    get.mockRejectedValue(new Error("offline"))
    const { result } = renderHook(() => useTtsVoices())
    await waitFor(() => expect(result.current.error).toBe(true))
  })
})
