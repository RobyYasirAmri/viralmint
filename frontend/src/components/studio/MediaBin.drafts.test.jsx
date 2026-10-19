// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
/**
 * Every preview tile presses from the keyboard, the Stock tab searches for the
 * selected scene by itself, and your own clips can be placed and removed.
 */
import { describe, expect, it, vi } from "vitest"
import { act, fireEvent, render, screen } from "@testing-library/react"

vi.mock("../../api/http", () => ({ default: { post: vi.fn(), get: vi.fn(() => Promise.resolve({ data: {} })) } }))
import MediaBin from "./MediaBin"

const resize = { dragging: false, handleProps: { onKeyDown: () => {} } }

const scene = (i, visual) => ({
  uid: `u${i}`, index: i, line: `Line ${i} here.`, start: i * 3, dur: 3, estimated: false,
  voice: { state: "ready" }, visual,
})
const A = scene(0, { kind: "stock", state: "bound", query: "city night" })
const B = scene(1, { kind: "stock", state: "bound", query: "sunset beach" })
const scenes = [A, B]

describe("MediaBin — preview tiles press from the keyboard", () => {
  it("a stock result previews on Enter / Space", async () => {
    const c = { provider: "pexels", provider_id: "7", creator: "Jo", native_duration: 6 }
    const onSearch = vi.fn(() => Promise.resolve([c]))
    const onPreview = vi.fn()
    const { unmount } = render(
      <MediaBin selected={B} scenes={scenes} mine={[]} width={432} resize={resize}
        request={{ tab: "stock", query: "cats", n: 1 }} onSearch={onSearch}
        onPreview={onPreview} onUseStock={vi.fn()} />,
    )
    const tile = await screen.findByRole("button", { name: "Preview Pexels · Jo" })
    fireEvent.keyDown(tile, { key: "Enter" })
    fireEvent.keyDown(tile, { key: " " })
    fireEvent.keyDown(tile, { key: "Tab" })
    expect(onPreview).toHaveBeenCalledTimes(2)
    expect(onPreview).toHaveBeenCalledWith({ candidate: c, label: "Pexels · Jo", useAs: { kind: "stock", candidate: c } })
    unmount()
  })

  it("your own clip previews on Enter", async () => {
    const item = { asset_id: "as_1", title: "jar.png", media: "image", url: "/m/as_1" }
    const onPreview = vi.fn()
    await act(async () => {
      render(
        <MediaBin selected={B} scenes={scenes} mine={[item]} width={432} resize={resize}
          request={{ tab: "mine", n: 1 }} onSearch={vi.fn()} onPreview={onPreview} onUseMine={vi.fn()} />,
      )
    })
    fireEvent.keyDown(screen.getByRole("button", { name: "Preview jar.png" }), { key: "Enter" })
    expect(onPreview).toHaveBeenCalledWith({ url: "/m/as_1", image: true, label: "jar.png", useAs: { kind: "user_clip", asset: item } })
  })
})

describe("MediaBin — stock search follows the selected scene", () => {
  it("searches the scene's own query without a click", async () => {
    const onSearch = vi.fn(() => Promise.resolve([]))
    await act(async () => {
      render(<MediaBin selected={A} scenes={scenes} mine={[]} width={432} resize={resize} onSearch={onSearch} onPreview={vi.fn()} />)
    })
    expect(onSearch).toHaveBeenCalledWith("city night")
    expect(screen.getByLabelText("Search stock footage").value).toBe("city night")
  })

  it("never replaces a search the user typed", async () => {
    const onSearch = vi.fn(() => Promise.resolve([]))
    let utils
    await act(async () => {
      utils = render(<MediaBin selected={A} scenes={scenes} mine={[]} width={432} resize={resize} onSearch={onSearch} onPreview={vi.fn()} />)
    })
    fireEvent.change(screen.getByLabelText("Search stock footage"), { target: { value: "my own words" } })
    await act(async () => {
      utils.rerender(<MediaBin selected={B} scenes={scenes} mine={[]} width={432} resize={resize} onSearch={onSearch} onPreview={vi.fn()} />)
    })
    expect(screen.getByLabelText("Search stock footage").value).toBe("my own words")
    expect(onSearch).not.toHaveBeenCalledWith("sunset beach")
  })
})

describe("MediaBin — your clips", () => {
  it("offers to place unused clips on open scenes, and has no Library or AI door", async () => {
    const item = { asset_id: "as_1", title: "jar.mp4", media: "video", url: "/m/as_1" }
    const onMatchClips = vi.fn()
    const onUpload = vi.fn()
    await act(async () => {
      render(
        <MediaBin selected={null} scenes={scenes} mine={[item]} width={432} resize={resize}
          request={{ tab: "mine", n: 1 }} onSearch={vi.fn()} onPreview={vi.fn()}
          onMatchClips={onMatchClips} onUpload={onUpload} />,
      )
    })
    fireEvent.click(screen.getByRole("button", { name: "Place 1 on scenes" }))
    expect(onMatchClips).toHaveBeenCalledWith([item])
    fireEvent.click(screen.getByRole("button", { name: "Upload clips or images" }))
    expect(onUpload).toHaveBeenCalled()
    expect(screen.queryByRole("button", { name: /From Library/ })).toBeNull()
    expect(screen.queryByRole("tab", { name: "AI" })).toBeNull()
  })
})
