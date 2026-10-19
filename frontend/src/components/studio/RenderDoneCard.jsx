// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useState } from "react"
import { Box, Button, Chip, IconButton, Stack, Tooltip, Typography } from "@mui/material"
import DownloadIcon from "@mui/icons-material/Download"
import ContentCopyIcon from "@mui/icons-material/ContentCopy"
import VideoLibraryOutlinedIcon from "@mui/icons-material/VideoLibraryOutlined"
import ReplayIcon from "@mui/icons-material/Replay"
import CloseRoundedIcon from "@mui/icons-material/CloseRounded"
import { aspectValue } from "./studioModel"
import { downloadGeneratedVideo } from "../../utils/downloadVideo"

// The finished video, where the user is (§5.9 completion card). Finishing a
// video is the funnel event — this card keeps the moment in the studio instead
// of sending people to look for the file in the Library: watch it, download
// it, copy the drafted title + description, make another like it.
export default function RenderDoneCard({ video, onClose, onOpenLibrary, onMakeAnother, making = false }) {
  const [copied, setCopied] = useState("")
  if (!video) return null
  const title = video.youtube_title || video.title || "Your video"
  const streamUrl = `/api/videos/${video.id}/stream`
  const ratio = aspectValue(video.aspect_ratio)

  const download = () => downloadGeneratedVideo(video)
  const copy = async (which, text) => {
    try { await navigator.clipboard.writeText(text); setCopied(which); setTimeout(() => setCopied(""), 2500) } catch { /* clipboard blocked */ }
  }
  const copyMeta = () => {
    const tags = (video.youtube_tags || []).map((t) => `#${String(t).replace(/\s+/g, "")}`).join(" ")
    copy("yt", [title, video.youtube_description || "", tags].filter(Boolean).join("\n\n"))
  }
  // The phone is where people post: TikTok's own caption, ready to paste.
  const tiktokText = [video.tiktok_title, video.tiktok_description].filter(Boolean).join("\n\n")
  return (
    <Box data-testid="render-done" sx={{
      position: "absolute", inset: 0, zIndex: 5, display: "flex", flexDirection: "column",
      bgcolor: "background.paper", color: "text.primary", p: 2, gap: 1.5,
    }}>
      <Stack direction="row" alignItems="center" spacing={1}>
        <Chip size="small" color="success" label="Rendered" sx={{ fontWeight: 800 }} />
        <Typography variant="subtitle1" sx={{ fontWeight: 800, flex: 1, minWidth: 0 }} noWrap title={title}>{title}</Typography>
        <Tooltip title="Keep editing"><IconButton size="small" aria-label="Keep editing" onClick={onClose} sx={{ color: "inherit" }}><CloseRoundedIcon /></IconButton></Tooltip>
      </Stack>
      <Box sx={{ flex: 1, minHeight: 0, display: "grid", placeItems: "center", overflow: "hidden" }}>
        <Box component="video" src={streamUrl} controls autoPlay playsInline
          sx={{ maxHeight: "100%", maxWidth: "100%", aspectRatio: String(ratio), borderRadius: 1.5, bgcolor: "#000" }} />
      </Box>
      {video.youtube_description && (
        <Typography variant="caption" sx={{ opacity: 0.75, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
          {video.youtube_description}
        </Typography>
      )}
      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
        <Button variant="contained" startIcon={<DownloadIcon />} onClick={download} sx={{ textTransform: "none", fontWeight: 700 }}>Download</Button>
        <Button variant="outlined" color="inherit" startIcon={<ContentCopyIcon />} onClick={copyMeta} sx={{ textTransform: "none", fontWeight: 700 }}>
          {copied === "yt" ? "Copied" : "Copy title & description"}
        </Button>
        {tiktokText && (
          <Button variant="outlined" color="inherit" startIcon={<ContentCopyIcon />} onClick={() => copy("tt", tiktokText)} sx={{ textTransform: "none", fontWeight: 700 }}>
            {copied === "tt" ? "Copied" : "Copy TikTok caption"}
          </Button>
        )}
        <Button variant="outlined" color="inherit" startIcon={<VideoLibraryOutlinedIcon />} onClick={onOpenLibrary} sx={{ textTransform: "none", fontWeight: 700 }}>Open in Library</Button>
        <Button variant="outlined" color="inherit" startIcon={<ReplayIcon />} onClick={onMakeAnother} disabled={making} sx={{ textTransform: "none", fontWeight: 700 }}>
          {making ? "Setting up…" : "Make another like this"}
        </Button>
      </Stack>
    </Box>
  )
}
