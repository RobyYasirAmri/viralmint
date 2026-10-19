// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useCallback, useEffect, useState } from "react"
import http from "../api/http"

/**
 * The user's music library (GET /api/music/library →
 * {tracks: [{filename, display_name, genre, stream_url}], genres}).
 * Read-only here: the Smart Video Studio picks a background track from it.
 */
export default function useMusicLibrary() {
  const [tracks, setTracks] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const { data } = await http.get("/api/music/library")
      setTracks(data?.tracks || [])
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Failed to load music library")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  return { tracks, loading, error, refresh }
}
