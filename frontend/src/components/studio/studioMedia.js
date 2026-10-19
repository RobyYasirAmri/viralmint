// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
// Playable media for the Studio editor, from the project's own endpoints.
//
//   your clips          → /api/studio/media/{project}/{asset}
//   bound stock         → the preview the backend downloads once
//                         (POST …/media/preview, then /api/studio/preview/…)
//   stock picked at render → nothing to play yet
import { useEffect, useState } from "react"
import { mediaUrl, previewCandidate } from "./studioApi"

// → { url, failed, retry }. A failed preview (offline, the stock host down, a
// slow download past the client timeout) used to come back as url=null — the
// same as "still loading" — so the player spun "Loading footage…" forever with
// nothing to click (audit 2026-09-19). `failed` + `retry` let it say so.
export function useCandidateUrl(projectId, candidate) {
  const key = candidate?.provider && candidate?.provider_id ? `${candidate.provider}:${candidate.provider_id}` : null
  const [url, setUrl] = useState(null)
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    setFailed(false)
    if (!key || !projectId) { setUrl(null); return undefined }
    let alive = true
    setUrl(null)
    previewCandidate(projectId, candidate)
      .then((u) => { if (alive) setUrl(u) })
      .catch(() => { if (alive) { setUrl(null); setFailed(true) } })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, key, attempt])
  return { url, failed, retry: () => setAttempt((n) => n + 1) }
}

export function useSceneMedia(projectId, visual) {
  const kind = visual?.kind
  const asset = visual?.asset || {}
  const owned = !!asset.asset_id && kind === "user_clip"
  const candidate = !owned && kind === "stock" && asset.provider ? asset : null
  const preview = useCandidateUrl(projectId, candidate)
  return {
    url: owned ? mediaUrl(projectId, asset.asset_id) : preview.url,
    image: owned && asset.media === "image",
    failed: !owned && preview.failed,
    retry: preview.retry,
  }
}
