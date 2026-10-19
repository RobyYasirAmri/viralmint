// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useCallback, useEffect, useRef, useState } from "react"
import http from "../api/http"

/**
 * Voice preview playback for a voice list (the Smart Video Studio's).
 *
 *   play(provider, voiceId)  toggles: the same voice again stops it
 *   stop()                   stops and frees the audio
 *   playing / loading        the voice id currently playing / being fetched
 *
 * One shared <audio>, one blob URL at a time (revoked on stop, replace,
 * end and unmount). Each click gets a token: a response that arrives after a
 * newer click or a stop is discarded instead of playing unstoppably. The
 * sample is synthesised by POST /api/tts/preview (mp3).
 */
export default function useVoicePreview({ onError } = {}) {
  const [playing, setPlaying] = useState(null)
  const [loading, setLoading] = useState(null)
  const audioRef = useRef(null)
  const urlRef = useRef(null)
  const tokenRef = useRef(0)
  const onErrorRef = useRef(onError)
  onErrorRef.current = onError

  const stop = useCallback(() => {
    tokenRef.current += 1
    const a = audioRef.current
    if (a) {
      a.onended = null
      a.onerror = null
      a.pause()
      a.removeAttribute("src")
      try { a.load() } catch { /* detached element */ }
    }
    if (urlRef.current) { URL.revokeObjectURL(urlRef.current); urlRef.current = null }
    setPlaying(null)
    setLoading(null)
  }, [])

  useEffect(() => () => stop(), [stop])

  const play = useCallback(async (provider, voiceId) => {
    if (!voiceId) return
    if (playing === voiceId) { stop(); return }
    stop()
    const token = tokenRef.current
    setLoading(voiceId)
    try {
      const res = await http.post("/api/tts/preview", { provider, voice_id: voiceId }, { responseType: "blob" })
      if (token !== tokenRef.current) return            // superseded or stopped meanwhile
      const url = URL.createObjectURL(res.data)
      urlRef.current = url
      if (!audioRef.current) audioRef.current = new Audio()
      const audio = audioRef.current
      audio.src = url
      audio.onended = () => { if (token === tokenRef.current) stop() }
      audio.onerror = () => {
        if (token !== tokenRef.current) return
        stop()
        onErrorRef.current?.("Couldn't play preview audio")
      }
      setLoading(null)
      setPlaying(voiceId)
      await audio.play()
    } catch (err) {
      if (token !== tokenRef.current) return
      stop()
      // The error body is a Blob (responseType: "blob"): read its JSON detail
      // so "Add your OpenAI API key in Settings…" reaches the user.
      let msg = err?.message || "Preview failed"
      try {
        const data = err?.response?.data
        const body = data && typeof data.text === "function" ? JSON.parse(await data.text()) : data
        if (typeof body?.detail === "string") msg = body.detail
      } catch { /* not JSON */ }
      onErrorRef.current?.(`Voice preview failed: ${msg}`)
    }
  }, [playing, stop])

  return { play, stop, playing, loading }
}
