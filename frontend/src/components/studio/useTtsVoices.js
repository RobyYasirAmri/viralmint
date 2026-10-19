// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useEffect, useState } from "react"
import http from "../../api/http"

// Flat voice list for the Studio's Project → Voice section: the engine's own
// vocabulary from /api/config/voices/{provider} (Edge TTS first — no key
// needed — then OpenAI TTS, which runs on the user's own key). Module-cached so
// reopening the section doesn't refetch. A provider that fails to answer is
// left out rather than failing the whole list.
const PROVIDERS = [
  { id: "edge_tts", hint: "Edge TTS" },
  { id: "openai_tts", hint: "OpenAI TTS · your API key" },
]

let _cache = null
let _inflight = null

export function _resetVoiceCache() { _cache = null; _inflight = null }

function fetchVoices() {
  if (_cache) return Promise.resolve(_cache)
  if (_inflight) return _inflight
  _inflight = Promise.all(PROVIDERS.map((p) => http.get(`/api/config/voices/${p.id}`)
    .then((res) => ({ p, list: res.data?.voices || [] }))
    .catch(() => ({ p, list: null }))))
    .then((answers) => {
      if (answers.every((a) => a.list === null)) throw new Error("no voices")
      const flat = []
      for (const { p, list } of answers) {
        for (const v of list || []) {
          const id = v.voice_id || v.id
          if (!id) continue
          flat.push({
            id,
            label: v.name || id,
            tagline: [v.category, p.hint].filter(Boolean).join(" · "),
            provider: p.id,
            // "en-US" → "US": the badge VoiceRow shows beside the name.
            country: String(v.locale || "").split("-")[1] || "",
          })
        }
      }
      _cache = flat
      return flat
    })
    .finally(() => { _inflight = null })
  return _inflight
}

export default function useTtsVoices() {
  const [voices, setVoices] = useState(_cache || [])
  const [error, setError] = useState(false)
  useEffect(() => {
    let alive = true
    fetchVoices()
      .then((v) => { if (alive) setVoices(v) })
      .catch(() => { if (alive) setError(true) })
    return () => { alive = false }
  }, [])
  return { voices, error }
}
