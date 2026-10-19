// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
// Save a generated video (same-origin stream) as a file. A link with
// `download` saves instead of opening a playing tab — the one implementation
// for the Library detail and the Studio's finished-video card.
export const videoFileStem = (title) => String(title || "video").replace(/[^a-zA-Z0-9]/g, "_")
export const videoFileName = (title) => `${videoFileStem(title)}.mp4`

export function downloadGeneratedVideo(video) {
  if (!video?.id) return
  const a = document.createElement("a")
  a.href = `/api/videos/${video.id}/stream`
  a.download = videoFileName(video.title)
  a.click()
}
