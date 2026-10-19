// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"

vi.mock("../SampleShowcase", () => ({ default: () => null }))
import StartPanel from "./StartPanel"

const scriptBox = () => screen.getByPlaceholderText(/Your script appears here once it's written|Paste or write your narration/)

describe("StartPanel — where a first video starts", () => {
  it("opens on the script desk by default", () => {
    render(<StartPanel onCreate={vi.fn()} />)
    expect(scriptBox().getAttribute("placeholder")).toMatch(/^Paste or write/)
  })

  it("opens on the topic box for a first-timer / Make another", () => {
    render(<StartPanel onCreate={vi.fn()} preferTopic />)
    expect(scriptBox().getAttribute("placeholder")).toMatch(/^Your script appears here/)
  })

  it("switches to the topic box when the hint arrives after mount (the project list loads late)", () => {
    const { rerender } = render(<StartPanel onCreate={vi.fn()} preferTopic={false} />)
    rerender(<StartPanel onCreate={vi.fn()} preferTopic />)
    expect(scriptBox().getAttribute("placeholder")).toMatch(/^Your script appears here/)
  })
})

describe("StartPanel — topic first, then build (2026-10-13)", () => {
  it("writes the script and stops for review instead of building", async () => {
    const api = await import("./studioApi")
    const draft = vi.spyOn(api, "draftScript").mockResolvedValue("Your plants are asleep. Stop watering.")
    const { fireEvent, waitFor } = await import("@testing-library/react")
    const onCreate = vi.fn()
    render(<StartPanel onCreate={onCreate} preferTopic />)
    fireEvent.change(screen.getByLabelText("What's the video about?"), { target: { value: "houseplants in winter" } })
    fireEvent.click(screen.getByRole("button", { name: /^Write my script$/ }))
    await waitFor(() => expect(scriptBox().value).toMatch(/asleep/))
    expect(draft).toHaveBeenCalledWith("houseplants in winter", "9:16")
    expect(onCreate).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole("button", { name: /Make a first draft/ }))
    expect(onCreate).toHaveBeenCalledTimes(1)
    expect(onCreate.mock.calls[0][0]).toMatchObject({ mode: "script", title: "houseplants in winter" })
  })

  it("a failed handoff puts its topic back on the desk", () => {
    render(<StartPanel onCreate={vi.fn()} prefill={{ source: "topic", topic: "why cats purr" }} />)
    expect(screen.getByLabelText("What's the video about?").value).toBe("why cats purr")
  })

  it("says what it is doing while a handoff drafts", () => {
    render(<StartPanel onCreate={vi.fn()} busy workingLabel="Writing a script about “x”…" />)
    expect(screen.getByTestId("desk-working").textContent).toMatch(/Writing a script about/)
  })
})
