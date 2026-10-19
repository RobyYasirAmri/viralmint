// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { afterEach, describe, expect, it, vi } from "vitest"
import { act, render, screen } from "@testing-library/react"
import { useRef } from "react"
import useLiveAnimation from "./useLiveAnimation"

// Decorative canvases animate only when wanted AND on screen AND the tab is
// visible AND motion is welcome (audit 2026-09-25: ~26 idle rAF loops on /stock).

let ioCb = null
class FakeIO {
  constructor(cb) { ioCb = cb }
  observe() {}
  disconnect() {}
}

function Probe({ want }) {
  const ref = useRef(null)
  const live = useLiveAnimation(ref, want)
  return <div ref={ref} data-testid="probe" data-live={String(live)} />
}
const live = () => screen.getByTestId("probe").dataset.live

afterEach(() => {
  vi.unstubAllGlobals()
  ioCb = null
  delete document.visibilityState
})

describe("useLiveAnimation", () => {
  it("off until the element is on screen, and only while wanted", () => {
    vi.stubGlobal("IntersectionObserver", FakeIO)
    const { rerender } = render(<Probe want />)
    expect(live()).toBe("false")
    act(() => ioCb([{ isIntersecting: true }]))
    expect(live()).toBe("true")
    rerender(<Probe want={false} />)
    expect(live()).toBe("false")
    rerender(<Probe want />)
    act(() => ioCb([{ isIntersecting: false }]))
    expect(live()).toBe("false")
  })

  it("stops while the tab is hidden", () => {
    render(<Probe want />)
    expect(live()).toBe("true")
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "hidden" })
    act(() => { document.dispatchEvent(new Event("visibilitychange")) })
    expect(live()).toBe("false")
  })

  it("never animates under prefers-reduced-motion", () => {
    vi.stubGlobal("matchMedia", (q) => ({
      matches: q.includes("reduce"), addEventListener() {}, removeEventListener() {},
    }))
    render(<Probe want />)
    expect(live()).toBe("false")
  })
})
