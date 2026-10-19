// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import StudioTimeline from "./StudioTimeline"

const timeline = {
  total: 5,
  scenes: [
    { uid: "a", index: 0, start: 0, dur: 2.5, line: "One line.", voice: { state: "ready" }, visual: { kind: "stock", query: "x" } },
    { uid: "b", index: 1, start: 2.5, dur: 2.5, line: "Two line.", voice: { state: "none" }, visual: { kind: "user_clip", asset: { asset_id: "as_1", title: "mine.mp4" } } },
  ],
}

const renderTl = (props = {}) => render(
  <StudioTimeline
    timeline={timeline} settings={{ captions: { enabled: true }, music: { enabled: false } }}
    playhead={0} playing={false} selectedUid={null}
    onSelect={vi.fn()} onSeek={vi.fn()} onReorder={vi.fn()} {...props}
  />,
)

describe("StudioTimeline — 'Add scene' is a real keyboard button", () => {
  it("is focusable and adds a scene on Enter and Space, not on other keys", () => {
    const onAddScene = vi.fn()
    renderTl({ onAddScene })
    const add = screen.getByRole("button", { name: "Add scene" })
    expect(add).toHaveAttribute("tabindex", "0")
    add.focus()
    expect(add).toHaveFocus()
    fireEvent.keyDown(add, { key: "Enter" })
    fireEvent.keyDown(add, { key: " " })
    fireEvent.keyDown(add, { key: "a" })
    expect(onAddScene).toHaveBeenCalledTimes(2)
    fireEvent.click(add)
    expect(onAddScene).toHaveBeenCalledTimes(3)
  })

  it("no handler → pressing it is a no-op, not a crash", () => {
    renderTl()
    expect(() => fireEvent.keyDown(screen.getByRole("button", { name: "Add scene" }), { key: "Enter" })).not.toThrow()
  })
})
