// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { describe, it, expect, beforeEach, vi } from "vitest"
import { renderHook, act, waitFor } from "@testing-library/react"

vi.mock("./studioApi", () => ({ getJob: vi.fn() }))
import { getJob } from "./studioApi"
import useAppStore from "../../store/appStore"
import useJobWatch from "./useJobWatch"

beforeEach(() => {
  getJob.mockReset()
  useAppStore.setState({ activeJobs: {} })
})

describe("useJobWatch", () => {
  it("returns null with no job and never polls", () => {
    const { result } = renderHook(() => useJobWatch(null))
    expect(result.current).toBeNull()
    expect(getJob).not.toHaveBeenCalled()
  })

  it("follows the store's live progress and finishes once when the socket says success", async () => {
    getJob.mockResolvedValueOnce({ status: "running", progress_pct: 10, current_step: "Planning" })
    const onDone = vi.fn()
    useAppStore.getState().startJob("j1", "studio_plan", "Planning scenes")
    const { result } = renderHook(() => useJobWatch("j1", { onDone, pollMs: 60_000 }))
    await waitFor(() => expect(result.current.pct).toBe(10))
    act(() => useAppStore.getState().updateJobProgress("j1", 55, "Scenes planned"))
    expect(result.current.pct).toBe(55)
    expect(result.current.step).toBe("Scenes planned")

    getJob.mockResolvedValue({ status: "success", output_json: JSON.stringify({ project_id: "p1" }) })
    act(() => useAppStore.getState().completeJob("j1"))
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1))
    expect(onDone.mock.calls[0][0]).toEqual({ status: "success", output: { project_id: "p1" }, error: null })
  })

  it("catches an end the socket missed by polling the job row, with its error", async () => {
    vi.useFakeTimers()
    try {
      getJob.mockResolvedValueOnce({ status: "running", progress_pct: 5 })
      getJob.mockResolvedValue({ status: "failed", error_message: "Planning failed" })
      const onDone = vi.fn()
      renderHook(() => useJobWatch("j2", { onDone, pollMs: 1000 }))
      await act(async () => { await vi.advanceTimersByTimeAsync(1100) })
      await act(async () => { await vi.advanceTimersByTimeAsync(1100) })
      expect(onDone).toHaveBeenCalledTimes(1)
      expect(onDone.mock.calls[0][0]).toMatchObject({ status: "failed", error: "Planning failed" })
    } finally {
      vi.useRealTimers()
    }
  })
})
