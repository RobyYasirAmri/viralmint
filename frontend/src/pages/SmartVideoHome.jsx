// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useEffect, useRef, useState } from "react"
import { useLocation, useNavigate, useSearchParams } from "react-router-dom"
import {
  Badge, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, Drawer, IconButton,
  Stack, TextField, Tooltip, Typography, alpha,
} from "@mui/material"
import PlayArrowRoundedIcon from "@mui/icons-material/PlayArrowRounded"
import FolderOpenOutlinedIcon from "@mui/icons-material/FolderOpenOutlined"
import CloseIcon from "@mui/icons-material/Close"
import LibraryAddIcon from "@mui/icons-material/LibraryAddOutlined"
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline"
import PageHero from "../components/PageHero"
import StartPanel from "../components/studio/StartPanel"
import { STYLES } from "../components/create/SmartVideoStyles"
import * as api from "../components/studio/studioApi"
import { aspectCss } from "../components/studio/studioModel"
import useAppStore from "../store/appStore"
import { onActivate } from "../utils/a11y"
import useDocumentTitle from "../hooks/useDocumentTitle"
import { formatClock, formatRelativeTime } from "../utils/format"
import { handoffKey, handoffOps, parseLegacyQuery } from "../utils/studioHandoff"

// Studio Home — recent projects + the start panel.
// Backed by /api/studio (components/studio/studioApi.js). Route: /stock (the editor is /stock/p/:projectId).
export default function SmartVideoHome() {
  useDocumentTitle("Smart Video Studio")
  const navigate = useNavigate()
  const location = useLocation()
  const showSnackbar = useAppStore((s) => s.showSnackbar)
  const [projects, setProjects] = useState(null)
  const [busy, setBusy] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [playing, setPlaying] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [deleteBusy, setDeleteBusy] = useState(false)

  const confirmDelete = async () => {
    const target = deleting
    setDeleteBusy(true)
    try {
      await api.deleteProject(target.id)
      showSnackbar(`Deleted “${target.title}”`, "success")
      setDeleting(null)
      refresh()
    } catch (e) {
      showSnackbar(e.message, "error")
    } finally {
      setDeleteBusy(false)
    }
  }
  const [filter, setFilter] = useState("")
  const latest = (projects || []).slice().sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")))[0] || null
  const shown = (projects || []).filter((p) => !filter.trim() || p.title.toLowerCase().includes(filter.trim().toLowerCase()))

  // A failed list is NOT "no projects yet" — that told a user whose backend
  // hiccupped that their work was gone (audit 2026-09-19).
  const [listError, setListError] = useState(null)
  const refresh = () => api.listProjects()
    .then((items) => { setListError(null); setProjects(items) })
    .catch((e) => { setListError(e?.message || "Couldn't load your projects."); })
  useEffect(() => { refresh() }, [])

  // Legacy `/stock?script=|topic=|source=…` links (Library "Use as
  // inspiration", the Videos page's create menu) become a PROJECT:
  // validated, created once (a reload or a double-invoke reuses the id stored
  // under a hash of the query for 10 min), planned, then the editor opens by
  // history.replace so Back doesn't make a second one. `?script=` never
  // drafts; a bare topic / source drafts a script with your AI provider.
  const [searchParams] = useSearchParams()
  const handoffRef = useRef(false)
  const [handingOff, setHandingOff] = useState(false)
  // What the desk shows while a handoff works (10–20 s of drafting looked
  // idle), and what it is filled with if the handoff fails — the topic or
  // script used to be lost with the error toast (2026-10-13 audit).
  const [handoffLabel, setHandoffLabel] = useState("")
  const [prefill, setPrefill] = useState(null)
  useEffect(() => {
    if (handoffRef.current) return
    const h = parseLegacyQuery(searchParams)
    if (!h || !Object.keys(h.start).length) return
    handoffRef.current = true
    const key = handoffKey(searchParams.toString())
    let reuse = null
    try {
      const saved = JSON.parse(sessionStorage.getItem(key) || "null")
      if (saved && Date.now() - saved.at < 10 * 60 * 1000) reuse = saved.id
    } catch { /* private mode */ }
    if (reuse) { navigate(`/stock/p/${reuse}`, { replace: true }); return }
    setHandingOff(true)
    setHandoffLabel(h.start.script ? "Bringing your script over…"
      : h.start.topic ? `Writing a script about “${h.start.topic}”…` : "Writing a script from that video…")
    ;(async () => {
      try {
        let script = h.start.script || ""
        let title = null
        if (!script && h.start.topic) {
          script = await api.draftScript(h.start.topic, h.aspect_ratio || "9:16")
          title = h.start.topic
        } else if (!script && h.start.source_id) {
          script = await api.draftScriptFromSource(h.start.source_id, h.aspect_ratio || "9:16")
        }
        const p = await api.createProject({
          // source_id rides along so the rendered video keeps its "created from"
          // lineage (Library) — the script alone doesn't say where it came from.
          start: { script, title, ...(h.start.source_id ? { source_id: h.start.source_id } : {}) },
          aspect_ratio: h.aspect_ratio || api.readLast("start")?.aspect || "9:16",
          visual_style: h.visual_style || api.readLast("start")?.style || "cinematic", plan: true,
          // Per-field merge (mergeRemembered): a link that says captions=on
          // keeps the remembered caption style instead of dropping it.
          settings: api.mergeRemembered(api.readLast("settings"), h.settings),
        })
        const ops = handoffOps(h)
        // No if_revision: the plan job is already writing to this brand-new
        // project, and a stale-revision 409 here would silently drop the rail's
        // choices (seen once in the harness). Nobody else has edited it yet.
        if (ops.length) await api.applyOps(p.id, null, ops).catch((e) => showSnackbar(e.message, "warning"))
        try { sessionStorage.setItem(key, JSON.stringify({ id: p.id, at: Date.now() })) } catch { /* private mode */ }
        showSnackbar(h.start.script ? "Brought your plan over — every scene is yours to change before you render"
          : "Drafted your script — every scene is yours to change before you render", "success")
        navigate(`/stock/p/${p.id}`, { replace: true, state: { planned: true, planJobId: p.planJobId } })
      } catch (e) {
        showSnackbar(e.message || "Couldn't bring that over — start below", "warning")
        setPrefill(h.start.script ? { source: "script", script: h.start.script }
          : h.start.topic ? { source: "topic", topic: h.start.topic } : null)
        setHandingOff(false)
        setHandoffLabel("")
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const create = async (start, opts) => {
    setBusy(true)
    try {
      // Build storyboard → plan the visuals; Make a first draft → plan, then
      // voice every scene. Both run on the server.
      const create = () => api.createProject({
        start, aspect_ratio: opts.aspect_ratio, visual_style: opts.visual_style,
        firstDraft: !!opts.firstDraft, plan: !opts.firstDraft,
        settings: api.readLast("settings"),        // the last video's voice and caption style
      })
      let p
      try {
        p = await create()
      } catch (e) {
        // The remembered caption style was deleted since (a custom preset):
        // forget it and start from the default instead of refusing forever.
        if (e.detail?.field !== "captions.style") throw e
        api.forgetLastCaptionStyle()
        p = await create()
      }
      navigate(`/stock/p/${p.id}`, { state: { firstDraft: !!opts.firstDraft, planned: !opts.firstDraft, planJobId: p.planJobId } })
    } catch (e) {
      showSnackbar(e.message, "warning")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Box sx={{ height: "100%", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <PageHero
        icon={<LibraryAddIcon sx={{ fontSize: 22 }} />}
        title="Smart Video Studio"
        subtitle="Plan every scene, watch every clip, hear every line — then render"
        accentColor="#388e3c"
        actions={
          <Stack direction="row" spacing={1} alignItems="center">
            {/* A returning user's way back to the video they were working on
                — it used to sit behind the drawer (2026-10-13 audit). */}
            {latest && (
              <Tooltip title={`${latest.scenes} scenes · ${formatClock(latest.duration_seconds)}`} describeChild>
                <Chip
                  data-testid="continue-latest" color="primary" variant="outlined" icon={<PlayArrowRoundedIcon />}
                  label={`Continue “${latest.title.length > 28 ? `${latest.title.slice(0, 27)}…` : latest.title}” · ${formatRelativeTime(latest.updated_at)}`}
                  onClick={() => navigate(`/stock/p/${latest.id}`)}
                  sx={{ display: { xs: "none", md: "inline-flex" }, fontWeight: 600, maxWidth: 380 }}
                />
              </Tooltip>
            )}
            <Badge badgeContent={projects?.length || 0} color="primary" max={99}>
              <Button
                size="small" variant="outlined" startIcon={<FolderOpenOutlinedIcon />}
                onClick={() => setDrawerOpen(true)} sx={{ textTransform: "none", fontWeight: 700 }}
              >
                Your projects
              </Button>
            </Badge>
          </Stack>
        }
      />
      <Box sx={{ flex: 1, overflow: "auto", px: { xs: 2, md: 3 }, py: 2.5 }}>
        <Box sx={{ maxWidth: 1480, mx: "auto" }}>
          {/* The script is the main event (owner, 2026-09-15: the 480px start
              card's 6-row textarea was too small) — full width, projects below. */}
          <StartPanel onCreate={create} busy={busy || handingOff} workingLabel={handingOff ? handoffLabel : ""} prefill={prefill}
            preferTopic={location.state?.start === "topic" || (Array.isArray(projects) && projects.length === 0 && !listError)} />
        </Box>
      </Box>

      {/* Projects live in a drawer (owner, 2026-09-15: a grid under the desk
          read as a stray bottom row). Autosaved, so nothing is lost by hiding it. */}
      <Drawer
        anchor="right" open={drawerOpen} onClose={() => setDrawerOpen(false)}
        slotProps={{ paper: { sx: { width: { xs: "100%", sm: 460 }, display: "flex", flexDirection: "column" } } }}
      >
        <Stack direction="row" alignItems="center" sx={{ px: 2.5, pt: 2, pb: 1 }}>
          <Box sx={{ flex: 1 }}>
            <Typography variant="h6" sx={{ fontWeight: 800 }}>Your projects</Typography>
            <Typography variant="body2" sx={{ color: "text.secondary" }}>Saved automatically. Open one to keep editing.</Typography>
          </Box>
          <IconButton aria-label="Close projects" onClick={() => setDrawerOpen(false)}><CloseIcon /></IconButton>
        </Stack>
        {(projects?.length || 0) > 4 && (
          <Box sx={{ px: 2.5, pb: 1 }}>
            <TextField size="small" fullWidth placeholder="Search projects" value={filter} onChange={(e) => setFilter(e.target.value)} />
          </Box>
        )}
        <Box sx={{ flex: 1, overflowY: "auto", px: 2.5, pb: 2.5, pt: 1 }}>
          {listError && !projects?.length && (
            <Box sx={{ border: "1.5px dashed", borderColor: "error.main", borderRadius: 2, p: 3, textAlign: "center" }}>
              <Typography variant="body2" sx={{ fontWeight: 700 }}>Couldn't load your projects</Typography>
              <Typography variant="body2" sx={{ color: "text.secondary", mb: 1 }}>{listError}</Typography>
              <Button size="small" variant="outlined" onClick={refresh}>Try again</Button>
            </Box>
          )}
          {!listError && projects && projects.length === 0 && (
            <Box sx={{ border: "1.5px dashed", borderColor: "divider", borderRadius: 2, p: 4, textAlign: "center" }}>
              <Typography variant="body2" sx={{ fontWeight: 700 }}>No projects yet</Typography>
              <Typography variant="body2" sx={{ color: "text.secondary" }}>
                Write a script and build a storyboard. It shows up here and saves as you work.
              </Typography>
            </Box>
          )}
          {projects?.length > 0 && shown.length === 0 && (
            <Typography variant="body2" sx={{ color: "text.secondary" }}>No project titles match “{filter}”.</Typography>
          )}
          <Box sx={{ display: "grid", gap: 1.5, gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
            {shown.map((p) => (
              <ProjectCard
                key={p.id} project={p}
                onOpen={() => navigate(`/stock/p/${p.id}`)}
                onPlay={() => setPlaying(p)}
                onDelete={() => setDeleting(p)}
              />
            ))}
          </Box>
        </Box>
      </Drawer>

      <PlayDialog
        project={playing} onClose={() => setPlaying(null)}
        onEdit={() => { const id = playing.id; setPlaying(null); navigate(`/stock/p/${id}`) }}
      />

      <Dialog open={!!deleting} onClose={() => !deleteBusy && setDeleting(null)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 800 }}>Delete this project?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            “{deleting?.title}” and its scenes, voice takes and uploaded clips will be deleted. This can't be undone.
          </Typography>
          {deleting?.status === "rendered" && (
            <Typography variant="body2" sx={{ color: "text.secondary", mt: 1.5 }}>
              Videos you already rendered stay in your Library.
            </Typography>
          )}
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setDeleting(null)} disabled={deleteBusy} sx={{ textTransform: "none" }}>Cancel</Button>
          <Button
            variant="contained" color="error" onClick={confirmDelete} disabled={deleteBusy}
            startIcon={deleteBusy ? <CircularProgress size={14} color="inherit" /> : <DeleteOutlineIcon />}
            sx={{ textTransform: "none", fontWeight: 700 }}
          >
            Delete project
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

// Plays a project's last rendered video (GeneratedVideo `last_video_id`).
function PlayDialog({ project, onClose, onEdit }) {
  const url = project?.last_video_id ? `/api/videos/${project.last_video_id}/stream` : null
  const ratio = aspectCss(project?.aspect_ratio)
  const portrait = (project?.aspect_ratio || "9:16") === "9:16"
  return (
    <Dialog open={!!project} onClose={onClose} maxWidth={portrait ? "xs" : "md"} fullWidth>
      <DialogTitle sx={{ fontWeight: 800, pr: 6 }}>
        {project?.title}
        <IconButton aria-label="Close player" onClick={onClose} sx={{ position: "absolute", right: 12, top: 12 }}><CloseIcon /></IconButton>
      </DialogTitle>
      <DialogContent>
        <Box sx={{ aspectRatio: ratio, maxHeight: "70vh", mx: "auto", bgcolor: "common.black", borderRadius: 1.5, overflow: "hidden", display: "grid", placeItems: "center" }}>
          {/* contain: the box is locked to the project's RECORDED ratio, so any
              drift between that and the real render silently cut the frame. */}
          {url ? (
            <Box component="video" src={url} controls autoPlay playsInline sx={{ width: "100%", height: "100%", objectFit: "contain" }} />
          ) : (
            <CircularProgress size={28} sx={{ color: "grey.500" }} />
          )}
        </Box>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onEdit} sx={{ textTransform: "none", fontWeight: 700 }}>Open in editor</Button>
      </DialogActions>
    </Dialog>
  )
}

function ProjectCard({ project, onOpen, onPlay, onDelete }) {
  const style = STYLES.find((st) => st.id === project.visual_style) || STYLES[0]
  const rendered = project.status === "rendered"
  return (
    <Box
      role="button" tabIndex={0} onClick={onOpen} aria-label={`Open ${project.title}`}
      onKeyDown={(e) => { if (e.target === e.currentTarget) onActivate(onOpen)(e) }}
      sx={(t) => ({
        cursor: "pointer", borderRadius: 2, overflow: "hidden", border: 1, borderColor: "divider",
        bgcolor: "background.paper", transition: "border-color .15s",
        "&:hover": { borderColor: t.palette.primary.main },
        "&:focus-visible": { outline: `2px solid ${t.palette.primary.main}`, outlineOffset: 2 },
      })}
    >
      <Box sx={{
        height: 112, position: "relative", display: "grid", placeItems: "center",
        // A rendered project has a real cover; the style gradient is the
        // fallback for drafts (and stays underneath, so a thumbnail that
        // 404s degrades to what this card always showed).
        background: `linear-gradient(135deg, ${style.cA}, ${style.cB})`,
      }}>
        {rendered && project.last_video_id && (
          <Box
            component="img" alt="" loading="lazy" decoding="async"
            src={`/api/videos/${project.last_video_id}/thumbnail?w=400&v=${encodeURIComponent(project.updated_at || "1")}`}
            onError={(e) => { e.currentTarget.style.display = "none" }}
            sx={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" }}
          />
        )}
        <Chip
          size="small" label={rendered ? "rendered" : "draft"}
          color={rendered ? "success" : "default"}
          sx={(t) => ({ position: "absolute", top: 8, left: 8, height: 20, fontSize: 11, fontWeight: 700,
            bgcolor: rendered ? undefined : alpha(t.palette.background.paper, 0.85) })}
        />
        <Chip
          size="small" label={project.aspect_ratio}
          sx={(t) => ({ position: "absolute", top: 8, right: 8, height: 20, fontSize: 11, fontWeight: 700,
            bgcolor: alpha(t.palette.background.paper, 0.85) })}
        />
        {rendered && (
          <IconButton
            aria-label={`Play ${project.title}`}
            onClick={(e) => { e.stopPropagation(); onPlay() }}
            sx={(t) => ({
              // Positioned, so it paints above the absolutely-positioned
              // cover image rather than under it.
              position: "relative", zIndex: 1,
              width: 44, height: 44, color: "common.white",
              bgcolor: alpha(t.palette.common.black, 0.55),
              "&:hover": { bgcolor: alpha(t.palette.common.black, 0.75) },
            })}
          >
            <PlayArrowRoundedIcon sx={{ fontSize: 30 }} />
          </IconButton>
        )}
      </Box>
      <Stack direction="row" alignItems="flex-start" sx={{ p: 1.25, pr: 0.5 }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="body2" noWrap sx={{ fontWeight: 700 }}>{project.title}</Typography>
          <Typography variant="caption" sx={{ color: "text.secondary", display: "block" }} noWrap>
            {project.scenes} scenes · {formatClock(project.duration_seconds)} · {formatRelativeTime(project.updated_at)}
          </Typography>
        </Box>
        <Tooltip title="Delete project">
          <IconButton
            size="small" aria-label={`Delete ${project.title}`}
            onClick={(e) => { e.stopPropagation(); onDelete() }}
            sx={{ "&:hover": { color: "error.main" } }}
          >
            <DeleteOutlineIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>
    </Box>
  )
}
