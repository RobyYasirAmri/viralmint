// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { act, fireEvent, render, screen } from "@testing-library/react"

const { media } = vi.hoisted(() => ({ media: { url: null, image: false, failed: false } }))
vi.mock("./studioMedia", () => ({
  useSceneMedia: () => ({ ...media, retry: vi.fn() }),
  useCandidateUrl: () => ({ url: null, failed: false, retry: vi.fn() }),
}))
vi.mock("./studioApi", () => ({
  mediaUrl: (p, a) => `/media/${p}/${a}`,
  voiceUrl: (k) => `/voice/${k}`,
  takeMeta: vi.fn(() => Promise.resolve({ words: null })),
}))

import SequencePlayer from "./SequencePlayer"

const timeline = {
  total: 4,
  scenes: [
    { uid: "a", index: 0, start: 0, dur: 2, line: "Hello there world friend", voice: { state: "none" }, visual: { kind: "stock", query: "cats" } },
    { uid: "b", index: 1, start: 2, dur: 2, line: "Second line", voice: { state: "none" }, visual: { kind: "stock", query: "dogs" } },
  ],
}

const props = (over = {}) => ({
  timeline, settings: { captions: { enabled: true, style: "viral" } }, aspectRatio: "9:16",
  playhead: 0.5, playing: false, onTick: vi.fn(), onPlayingChange: vi.fn(), onSeek: vi.fn(),
  preview: null, onClosePreview: vi.fn(), onUsePreview: vi.fn(), selectedIndex: 0,
  voiceMuted: false, onToggleVoice: vi.fn(), musicMuted: false, onToggleMusic: vi.fn(),
  loopScene: false, onToggleLoop: vi.fn(), onPrev: vi.fn(), onNext: vi.fn(), onTogglePlay: vi.fn(),
  projectId: "p1", ...over,
})

let fsEl = null
beforeEach(() => {
  fsEl = null
  Object.defineProperty(document, "fullscreenElement", { configurable: true, get: () => fsEl })
  // useFitBox measures the container; jsdom lays nothing out, so give it a size.
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({
    width: 360, height: 640, top: 0, left: 0, right: 360, bottom: 640, x: 0, y: 0,
  })
})
afterEach(() => {
  vi.restoreAllMocks()
  delete document.fullscreenElement
  delete HTMLElement.prototype.requestFullscreen
  delete document.exitFullscreen
})

describe("SequencePlayer — fullscreen takes the whole player", () => {
  it("fullscreens the player root (picture + transport), not just the frame", () => {
    const req = vi.fn(function () { fsEl = this })
    HTMLElement.prototype.requestFullscreen = req
    render(<SequencePlayer {...props()} />)
    const btn = screen.getByRole("button", { name: "Fullscreen" })
    fireEvent.click(btn)
    expect(req).toHaveBeenCalledOnce()
    const target = req.mock.contexts[0]
    // The transport controls live INSIDE the fullscreened element.
    expect(target.contains(btn)).toBe(true)
    expect(target.contains(screen.getByRole("button", { name: "Play" }))).toBe(true)
    expect(target.contains(screen.getByTestId("caption-overlay"))).toBe(true)
  })

  it("flips to 'Exit fullscreen' on fullscreenchange, and exits on the next press", () => {
    let root = null
    HTMLElement.prototype.requestFullscreen = function () { root = this }
    document.exitFullscreen = vi.fn()
    render(<SequencePlayer {...props()} />)
    fireEvent.click(screen.getByRole("button", { name: "Fullscreen" }))
    act(() => { fsEl = root; document.dispatchEvent(new Event("fullscreenchange")) })
    const exit = screen.getByRole("button", { name: "Exit fullscreen" })
    fireEvent.click(exit)
    expect(document.exitFullscreen).toHaveBeenCalledOnce()
    // Esc (the browser leaves fullscreen itself) resets the label.
    act(() => { fsEl = null; document.dispatchEvent(new Event("fullscreenchange")) })
    expect(screen.getByRole("button", { name: "Fullscreen" })).toBeInTheDocument()
  })

  it("some OTHER element going fullscreen doesn't mark the player as fullscreen", () => {
    render(<SequencePlayer {...props()} />)
    act(() => { fsEl = document.body; document.dispatchEvent(new Event("fullscreenchange")) })
    expect(screen.getByRole("button", { name: "Fullscreen" })).toBeInTheDocument()
  })

  it("is harmless where the Fullscreen API is missing", () => {
    render(<SequencePlayer {...props()} />)
    expect(() => fireEvent.click(screen.getByRole("button", { name: "Fullscreen" }))).not.toThrow()
  })

  it("stops listening once unmounted", () => {
    const remove = vi.spyOn(document, "removeEventListener")
    const { unmount } = render(<SequencePlayer {...props()} />)
    unmount()
    expect(remove).toHaveBeenCalledWith("fullscreenchange", expect.any(Function))
  })
})

describe("SequencePlayer — overlay + transport", () => {
  it("draws the caption overlay only when captions are on", () => {
    const { rerender } = render(<SequencePlayer {...props()} />)
    expect(screen.getByTestId("caption-overlay")).toHaveTextContent("Hello")
    rerender(<SequencePlayer {...props({ settings: { captions: { enabled: false } } })} />)
    expect(screen.queryByTestId("caption-overlay")).toBeNull()
  })

  it("names the scene and why it plays silent", () => {
    render(<SequencePlayer {...props()} />)
    expect(screen.getByText("Scene 1 / 2")).toBeInTheDocument()
    expect(screen.getByText("Not voiced yet — plays silent")).toBeInTheDocument()
    expect(screen.getByText(/Footage for “cats” is picked at render/)).toBeInTheDocument()
  })

  it("play button + clicking the picture toggle play", () => {
    const p = props()
    render(<SequencePlayer {...p} />)
    fireEvent.click(screen.getByRole("button", { name: "Play" }))
    expect(p.onTogglePlay).toHaveBeenCalledTimes(1)
  })
})

describe("SequencePlayer — the centre play glyph never covers a message", () => {
  afterEach(() => { Object.assign(media, { url: null, image: false, failed: false }) })

  it("hidden over 'Loading footage…'", () => {
    Object.assign(media, { url: null, failed: false })
    const t = { ...timeline, scenes: timeline.scenes.map((s) => ({ ...s, visual: { kind: "stock", asset: { provider_id: "1" } } })) }
    render(<SequencePlayer {...props({ timeline: t })} />)
    expect(screen.getByText("Loading footage…")).toBeInTheDocument()
    expect(screen.queryByTestId("play-hint")).toBeNull()
  })

  it("hidden over 'Couldn't load… / Try again'", () => {
    Object.assign(media, { url: null, failed: true })
    const t = { ...timeline, scenes: timeline.scenes.map((s) => ({ ...s, visual: { kind: "stock", asset: { provider_id: "1" } } })) }
    render(<SequencePlayer {...props({ timeline: t })} />)
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument()
    expect(screen.queryByTestId("play-hint")).toBeNull()
  })

  it("hidden while a stock scene waits for the render to pick its footage", () => {
    Object.assign(media, { url: null, failed: false })
    const t = { ...timeline, scenes: timeline.scenes.map((s) => ({ ...s, visual: { kind: "stock", query: "rain" } })) }
    render(<SequencePlayer {...props({ timeline: t })} />)
    expect(screen.getByText(/is picked at render/)).toBeInTheDocument()
    expect(screen.queryByTestId("play-hint")).toBeNull()
  })

  it("shown over real footage while paused, gone while playing", () => {
    Object.assign(media, { url: "/clip.mp4", image: false })
    vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(() => Promise.resolve())
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {})
    const { rerender } = render(<SequencePlayer {...props()} />)
    expect(screen.getAllByTestId("play-hint")).toHaveLength(1)   // the current scene only, not the preloaded next
    rerender(<SequencePlayer {...props({ playing: true })} />)
    expect(screen.queryByTestId("play-hint")).toBeNull()
  })
})

describe("SequencePlayer — the playhead is a store", () => {
  it("moves the caption and clock without the parent re-rendering, and scene boundaries swap the chip", async () => {
    const { createPlayhead } = await import("./playheadStore")
    const clock = createPlayhead(0.1)
    render(<SequencePlayer {...props({ playhead: clock })} />)
    expect(screen.getByText("Scene 1 / 2")).toBeInTheDocument()
    expect(screen.getByText(/^0:00\.1 \//)).toBeInTheDocument()
    act(() => clock.set(1.5))
    expect(screen.getByText(/^0:01\.5 \//)).toBeInTheDocument()
    act(() => clock.set(2.5))
    expect(screen.getByText("Scene 2 / 2")).toBeInTheDocument()
    expect(screen.getByTestId("caption-overlay")).toHaveTextContent("Second")
  })
})

describe("SequencePlayer — the scrub bar is a slider", () => {
  it("is focusable, announces its position and seeks with the keyboard", () => {
    const p = props({ playhead: 1.5 })
    render(<SequencePlayer {...p} />)
    const s = screen.getByRole("slider", { name: "Playback position" })
    expect(s).toHaveAttribute("tabindex", "0")
    expect(s).toHaveAttribute("aria-valuemin", "0")
    expect(s).toHaveAttribute("aria-valuemax", "4")
    expect(s).toHaveAttribute("aria-valuenow", "1.5")
    expect(s).toHaveAttribute("aria-valuetext", "0:02 of 0:04")
    fireEvent.keyDown(s, { key: "ArrowRight" })
    expect(p.onSeek).toHaveBeenLastCalledWith(2.5)
    fireEvent.keyDown(s, { key: "ArrowLeft" })
    expect(p.onSeek).toHaveBeenLastCalledWith(0.5)
    fireEvent.keyDown(s, { key: "End" })
    expect(p.onSeek).toHaveBeenLastCalledWith(4)
    fireEvent.keyDown(s, { key: "Home" })
    expect(p.onSeek).toHaveBeenLastCalledWith(0)
    fireEvent.keyDown(s, { key: "PageUp" })
    expect(p.onSeek).toHaveBeenLastCalledWith(4)   // clamped to the end
  })

  it("stops the arrow keys reaching the editor's scene-step shortcut", () => {
    const onWindowKey = vi.fn()
    window.addEventListener("keydown", onWindowKey)
    render(<SequencePlayer {...props()} />)
    fireEvent.keyDown(screen.getByRole("slider"), { key: "ArrowRight" })
    window.removeEventListener("keydown", onWindowKey)
    expect(onWindowKey).not.toHaveBeenCalled()
  })

  it("drags: pointer down seeks, moves keep seeking, up ends the drag", () => {
    const p = props()
    render(<SequencePlayer {...p} />)
    const s = screen.getByRole("slider")
    // getBoundingClientRect is mocked to 360px wide at left 0 (beforeEach).
    fireEvent.pointerDown(s, { button: 0, clientX: 90, pointerId: 1 })
    expect(p.onSeek).toHaveBeenLastCalledWith(1)
    fireEvent.pointerMove(s, { clientX: 270, pointerId: 1 })
    expect(p.onSeek).toHaveBeenLastCalledWith(3)
    fireEvent.pointerUp(s, { pointerId: 1 })
    const n = p.onSeek.mock.calls.length
    fireEvent.pointerMove(s, { clientX: 180, pointerId: 1 })
    expect(p.onSeek).toHaveBeenCalledTimes(n)
  })
})

describe("SequencePlayer — the transport never wraps", () => {
  it("narrow: the secondary toggles fold into a More menu; play + fullscreen stay", () => {
    const p = props()
    render(<SequencePlayer {...p} />)   // 360px wide (mocked)
    expect(screen.queryByRole("button", { name: "Mute voice" })).toBeNull()
    expect(screen.getByRole("button", { name: "Fullscreen" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "More player controls" }))
    fireEvent.click(screen.getByRole("menuitem", { name: "Mute voice" }))
    expect(p.onToggleVoice).toHaveBeenCalledOnce()
    fireEvent.click(screen.getByRole("menuitem", { name: "Loop the current scene" }))
    expect(p.onToggleLoop).toHaveBeenCalledOnce()
  })

  it("wide: every toggle is inline, no More menu", () => {
    Element.prototype.getBoundingClientRect.mockReturnValue({
      width: 900, height: 640, top: 0, left: 0, right: 900, bottom: 640, x: 0, y: 0,
    })
    render(<SequencePlayer {...props()} />)
    expect(screen.getByRole("button", { name: "Mute voice" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "About the preview" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "More player controls" })).toBeNull()
  })
})
