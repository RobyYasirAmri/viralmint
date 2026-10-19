// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import RenderDialog from "./RenderDialog"

const project = (checks) => ({
  doc: {
    aspect_ratio: "9:16",
    settings: {
      voice: { provider: "edge_tts", voice: "en-US-GuyNeural", label: "Guy" },
      captions: { enabled: true, style: "urban" },
      music: { enabled: false },
    },
  },
  checks,
})
const timeline = { total: 33, scenes: [{}, {}, {}] }

describe("RenderDialog — the server's checks decide", () => {
  it("summarises the video and renders on confirm", () => {
    const onConfirm = vi.fn()
    render(<RenderDialog open project={project({ blockers: [], warnings: [] })} timeline={timeline} onConfirm={onConfirm} onClose={vi.fn()} />)
    expect(screen.getByText("0:33 · 3 scenes · 9:16")).toBeInTheDocument()
    expect(screen.getByText("Guy · Edge voice")).toBeInTheDocument()
    expect(screen.getByText("Bold Urban")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Render" }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it("a blocker disables Render and says why; a warning does not", () => {
    render(<RenderDialog open project={project({ blockers: ["Scene 2 has no line."], warnings: ["Scene 3 isn't voiced yet."] })}
      timeline={timeline} onConfirm={vi.fn()} onClose={vi.fn()} />)
    expect(screen.getByText("Scene 2 has no line.")).toBeInTheDocument()
    expect(screen.getByText("Scene 3 isn't voiced yet.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Render" })).toBeDisabled()
  })

  it("never mentions money", () => {
    render(<RenderDialog open project={project({ blockers: [], warnings: [] })} timeline={timeline} onConfirm={vi.fn()} onClose={vi.fn()} />)
    expect(document.body.textContent).not.toMatch(/\$|charg|balance/i)
  })
})
