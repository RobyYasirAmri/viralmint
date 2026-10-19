// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useEffect, useRef, useState } from "react"
import useAppStore from "../../store/appStore"
import { getJob } from "./studioApi"

const TERMINAL = new Set(["success", "failed", "cancelled"])

const parseOutput = (job) => {
  try { return JSON.parse(job?.output_json || "{}") || {} } catch { return {} }
}

/**
 * Follow one job until it ends — the ONE job watcher of the Studio editor
 * (the plan / first-draft banner and the render both use it).
 *
 * Live state comes from the app store first (`activeJobs`, fed by the
 * WebSocket's job_started / job_progress / job_complete / job_failed). Not
 * every runner pushes progress over the socket (render progress is written to
 * the job row only), so a slow poll of the job row fills the gaps and catches
 * an end the socket missed. When the job ends, its row is read once more for
 * the authoritative output / error, and `onDone({status, output, error})`
 * fires exactly once.
 *
 * Returns { status, pct, step } while watching, or null with no job.
 */
export default function useJobWatch(jobId, { onDone, pollMs = 2000 } = {}) {
  const storeEntry = useAppStore((s) => (jobId ? s.activeJobs[jobId] : null))
  const [polled, setPolled] = useState(null)
  const doneRef = useRef(null)
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone

  useEffect(() => {
    setPolled(null)
    doneRef.current = null
    if (!jobId) return undefined
    let alive = true
    const finish = async (row) => {
      if (doneRef.current === jobId) return
      doneRef.current = jobId
      let job = row
      try { if (!job?.output_json && !job?.error_message) job = await getJob(jobId) } catch { /* keep what we have */ }
      if (!alive) return
      onDoneRef.current?.({ status: job?.status || row?.status, output: parseOutput(job), error: job?.error_message || null })
    }
    const tick = async () => {
      try {
        const job = await getJob(jobId)
        if (!alive) return
        setPolled({ status: job.status, pct: job.progress_pct || 0, step: job.current_step || "" })
        if (TERMINAL.has(job.status)) finish(job)
      } catch (e) {
        // The job row is gone (deleted) — nothing more will happen to it.
        if (alive && e?.status === 404) finish({ status: "cancelled" })
      }
    }
    tick()
    const timer = setInterval(() => { if (doneRef.current !== jobId) tick() }, pollMs)
    return () => { alive = false; clearInterval(timer) }
  }, [jobId, pollMs])

  // The socket said it ended before the next poll: finish now.
  useEffect(() => {
    if (!jobId || doneRef.current === jobId || !storeEntry) return
    if (storeEntry.status === "success" || storeEntry.status === "failed") {
      doneRef.current = jobId
      getJob(jobId)
        .then((job) => onDoneRef.current?.({ status: job.status === "running" ? storeEntry.status : job.status, output: parseOutput(job), error: job.error_message || null }))
        .catch(() => onDoneRef.current?.({ status: storeEntry.status, output: {}, error: storeEntry.status === "failed" ? storeEntry.step : null }))
    }
  }, [jobId, storeEntry])

  if (!jobId) return null
  // The store's percent is live between polls; the job row wins when it's ahead.
  const pct = Math.max(storeEntry?.percent || 0, polled?.pct || 0)
  const step = (storeEntry?.status === "running" && storeEntry?.step) || polled?.step || ""
  return { status: polled?.status || storeEntry?.status || "running", pct, step }
}
