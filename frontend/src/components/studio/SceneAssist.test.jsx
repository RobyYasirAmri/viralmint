// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import * as api from "./studioApi"
import SceneAssist from "./SceneAssist"

const scene = { uid: "u1", index: 0, line: "Plants sleep in winter." }

describe("SceneAssist — AI suggestions for one scene", () => {
  it("offers hook ideas on the opening scene and applies a picked line", async () => {
    const spy = vi.spyOn(api, "assistScene").mockResolvedValue({ lines: ["Your plants aren't dying. They're asleep."], query: null })
    const onUseLine = vi.fn()
    render(<SceneAssist projectId="p" scene={scene} isFirst onUseLine={onUseLine} onSearch={vi.fn()} />)
    fireEvent.click(screen.getByRole("button", { name: "Hook ideas" }))
    await waitFor(() => expect(screen.getByTestId("assist-options")).toBeTruthy())
    expect(spy).toHaveBeenCalledWith("p", "u1", "hook", undefined)
    fireEvent.click(screen.getByRole("button", { name: "Use this line" }))
    expect(onUseLine).toHaveBeenCalledWith("Your plants aren't dying. They're asleep.")
  })

  it("a custom ask can bring a footage search", async () => {
    vi.spyOn(api, "assistScene").mockResolvedValue({ lines: [], query: "snowy window plant" })
    const onSearch = vi.fn()
    render(<SceneAssist projectId="p" scene={{ ...scene, index: 2 }} onUseLine={vi.fn()} onSearch={onSearch} />)
    expect(screen.queryByRole("button", { name: "Hook ideas" })).toBeNull()
    fireEvent.change(screen.getByLabelText("Ask AI to change this scene"), { target: { value: "show snow" } })
    fireEvent.click(screen.getByRole("button", { name: "Ask" }))
    await waitFor(() => screen.getByRole("button", { name: /Search footage/ }))
    fireEvent.click(screen.getByRole("button", { name: /Search footage/ }))
    expect(onSearch).toHaveBeenCalledWith("snowy window plant")
  })

  it("says why when the AI fails", async () => {
    vi.spyOn(api, "assistScene").mockRejectedValue(new Error("The AI didn't answer — try again in a moment."))
    render(<SceneAssist projectId="p" scene={scene} onUseLine={vi.fn()} onSearch={vi.fn()} />)
    fireEvent.click(screen.getByRole("button", { name: "Shorter" }))
    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/didn't answer/))
  })
})
