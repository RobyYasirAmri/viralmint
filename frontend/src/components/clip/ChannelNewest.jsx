// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useCallback, useEffect, useState } from "react"
import { Box, Button, CircularProgress, Link, Stack, Typography } from "@mui/material"
import { Link as RouterLink } from "react-router-dom"
import ContentCutIcon from "@mui/icons-material/ContentCut"
import http from "../../api/http"
import useAppStore from "../../store/appStore"
import useJobWatch from "./useJobWatch"
import { formatRelativeAge } from "../../utils/format"
import { MAX_CHANNELS, newestOf, publishedAt, sourceFor } from "./newestUpload"

// How long a landed download may take to show up as a source before the row
// gives up waiting (the Library has it either way).
const APPEAR_TIMEOUT_MS = 20000

/**
 * "Clip the newest upload" — the Clipper's weekly loop (2026-10-15). One row
 * per connected channel with its newest video and ONE button: open the bench
 * on it when it is already a source, else download it (the Channels page's
 * own batch-download door), follow the job, and open the
 * bench when it lands. Rules in newestUpload.js.
 *
 *   sources       — the Clipper's source rows (video_exists only)
 *   onOpenSource  — (id) select a source and open the bench on it
 *   onRefresh     — re-read the sources (a download just landed)
 */
export default function ChannelNewest({ sources, onOpenSource, onRefresh }) {
  const showSnackbar = useAppStore((s) => s.showSnackbar)
  const [channels, setChannels] = useState(null)   // null = loading, [] = none connected
  const [newest, setNewest] = useState({})         // channel id → { video, error }
  const [pending, setPending] = useState(null)     // { jobId, channelId, url, videoId, landedAt }
  const [failed, setFailed] = useState({})         // channel id → message

  useEffect(() => {
    let live = true
    http.get("/api/channels/list")
      .then(({ data }) => { if (live) setChannels((data?.channels || []).slice(0, MAX_CHANNELS)) })
      .catch(() => { if (live) setChannels([]) })
    return () => { live = false }
  }, [])

  useEffect(() => {
    if (!channels?.length) return undefined
    let live = true
    for (const ch of channels) {
      if (newest[ch.id]) continue
      http.get(`/api/channels/videos/${ch.id}`)
        .then(({ data }) => { if (live) setNewest((m) => ({ ...m, [ch.id]: { video: newestOf(data?.videos) } })) })
        .catch(() => { if (live) setNewest((m) => ({ ...m, [ch.id]: { video: null, error: true } })) })
    }
    return () => { live = false }
  }, [channels])  // eslint-disable-line react-hooks/exhaustive-deps

  // Follow the one download this rail started.
  const watch = useJobWatch(pending?.jobId || null, {
    onDone: ({ status, error }) => {
      if (!pending) return
      if (status === "success") {
        onRefresh?.()
        setPending((p) => (p ? { ...p, jobId: null, landedAt: Date.now() } : p))
      } else {
        setFailed((f) => ({ ...f, [pending.channelId]: error || (status === "cancelled" ? "Download cancelled." : "Download failed.") }))
        setPending(null)
      }
    },
  })

  // The source appears → open the bench on it.
  useEffect(() => {
    if (!pending?.landedAt) return undefined
    const s = sourceFor(sources, { url: pending.url, video_id: pending.videoId })
    if (s) { onOpenSource?.(s.id); setPending(null); return undefined }
    const t = setTimeout(() => {
      setFailed((f) => ({ ...f, [pending.channelId]: "Downloaded, but it hasn't shown up as a source — check the Library." }))
      setPending(null)
    }, Math.max(0, APPEAR_TIMEOUT_MS - (Date.now() - pending.landedAt)))
    return () => clearTimeout(t)
  }, [sources, pending, onOpenSource])

  const clip = useCallback(async (ch, video) => {
    const existing = sourceFor(sources, video)
    if (existing) { onOpenSource?.(existing.id); return }
    setFailed((f) => { const { [ch.id]: _gone, ...rest } = f; return rest })  // eslint-disable-line no-unused-vars
    try {
      const { data } = await http.post("/api/downloaded/batch-download", { urls: [{ url: video.url, title: video.title || "" }] })
      setPending({ jobId: data.job_id, channelId: ch.id, url: video.url, videoId: video.video_id })
    } catch (e) {
      showSnackbar(e.response?.data?.detail || "Download failed", "error")
    }
  }, [sources, onOpenSource, showSnackbar])

  if (channels === null) return null
  if (!channels.length) {
    return (
      <Typography data-testid="channel-newest-empty" variant="caption" sx={{ display: "block", color: "text.secondary", px: 0.5, pb: 0.5 }}>
        Follow a channel to clip each new upload —{" "}
        <Link component={RouterLink} to="/channels" sx={{ fontWeight: 700 }}>connect a channel</Link>
      </Typography>
    )
  }
  return (
    <Box data-testid="channel-newest" sx={{ pb: 0.5 }}>
      <Typography variant="caption" sx={{ display: "block", color: "text.secondary", fontWeight: 700, letterSpacing: 0.4, textTransform: "uppercase", fontSize: "0.65rem", px: 0.5, mb: 0.5 }}>
        Newest from your channels
      </Typography>
      <Stack spacing={0.5}>
        {channels.map((ch) => {
          const entry = newest[ch.id]
          const video = entry?.video || null
          const existing = video ? sourceFor(sources, video) : null
          const mine = pending?.channelId === ch.id
          const at = video ? publishedAt(video) : null
          let label = "Clip it"
          if (existing) label = "Open bench"
          else if (mine && pending.jobId) label = watch?.pct ? `Downloading ${Math.round(watch.pct)}%` : "Downloading…"
          else if (mine) label = "Opening…"
          return (
            // Stacked, not side by side: the sources pane is ~190px wide, and a
            // row layout left the video's title as three letters and an ellipsis.
            <Stack key={ch.id} data-testid="channel-newest-row" spacing={0.5}
              sx={{ px: 0.75, py: 0.75, borderRadius: 1.5, border: 1, borderColor: "divider", bgcolor: "background.paper" }}>
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="caption" noWrap sx={{ display: "block", fontWeight: 700 }} title={ch.channel_name || ""}>
                  {ch.channel_name || ch.channel_url}
                </Typography>
                {!entry && <CircularProgress size={10} sx={{ mt: 0.25 }} />}
                {entry && !video && (
                  <Typography variant="caption" noWrap sx={{ display: "block", color: "text.secondary" }}>
                    {entry.error ? "Couldn't read this channel right now." : "No videos yet."}
                  </Typography>
                )}
                {video && (
                  <Typography variant="caption" noWrap sx={{ display: "block", color: "text.secondary" }} title={video.title || ""}>
                    {video.title || video.url}{at ? ` · ${formatRelativeAge(at)}` : ""}
                  </Typography>
                )}
                {failed[ch.id] && (
                  <Typography variant="caption" sx={{ display: "block", color: "error.main" }}>{failed[ch.id]}</Typography>
                )}
              </Box>
              {video && (
                <Button size="small" fullWidth variant={existing ? "outlined" : "contained"} disabled={mine || (!!pending && !existing)}
                  startIcon={mine ? <CircularProgress size={12} color="inherit" /> : <ContentCutIcon sx={{ fontSize: 14 }} />}
                  onClick={() => clip(ch, video)}
                  sx={{ textTransform: "none", fontWeight: 700, whiteSpace: "nowrap", minWidth: 0, px: 1 }}>
                  {label}
                </Button>
              )}
            </Stack>
          )
        })}
      </Stack>
    </Box>
  )
}
