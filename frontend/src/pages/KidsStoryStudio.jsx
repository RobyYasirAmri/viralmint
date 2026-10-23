// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useState, useEffect } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import {
  Box, Stack, Typography, Button, TextField, Chip, Card, CardContent,
  CircularProgress, IconButton, Tooltip, Select, MenuItem, FormControl,
  InputLabel, Grid, Divider, Alert, useTheme, alpha, LinearProgress
} from "@mui/material"
import AutoStoriesIcon from "@mui/icons-material/AutoStoriesOutlined"
import CasinoIcon from "@mui/icons-material/CasinoOutlined"
import SparklesIcon from "@mui/icons-material/AutoAwesomeOutlined"
import BrushIcon from "@mui/icons-material/BrushOutlined"
import ChildCareIcon from "@mui/icons-material/ChildCareOutlined"
import RecordVoiceOverIcon from "@mui/icons-material/RecordVoiceOverOutlined"
import MusicNoteIcon from "@mui/icons-material/MusicNoteOutlined"
import PlayCircleIcon from "@mui/icons-material/PlayCircleFilledWhiteOutlined"
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutlineOutlined"
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlineOutlined"
import CheckCircleIcon from "@mui/icons-material/CheckCircleOutline"
import LinkIcon from "@mui/icons-material/LinkOutlined"
import EditIcon from "@mui/icons-material/EditOutlined"
import AnimationIcon from "@mui/icons-material/MotionPhotosAutoOutlined"

import PageHero from "../components/PageHero"
import http from "../api/http"
import useAppStore from "../store/appStore"
import useDocumentTitle from "../hooks/useDocumentTitle"

export default function KidsStoryStudio() {
  useDocumentTitle("Kids Story Studio — ReelMimic")
  const theme = useTheme()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const loadVideoId = searchParams.get("load")
  const showSnackbar = useAppStore((s) => s.showSnackbar)
  const isDark = theme.palette.mode === "dark"

  // Presets State
  const [presets, setPresets] = useState(null)
  const [selectedCategory, setSelectedCategory] = useState("fables")
  const [targetAge, setTargetAge] = useState("preschool")
  const [drawingEngine, setDrawingEngine] = useState("crayon_picture_book")
  const [animationMode, setAnimationMode] = useState("lively")
  const [voice, setVoice] = useState("Rachel")

  // Form State
  const [prompt, setPrompt] = useState("")
  const [referenceUrl, setReferenceUrl] = useState("")
  const [deconstructingRef, setDeconstructingRef] = useState(false)
  const [refNotes, setRefNotes] = useState(null)

  // Inspiration State
  const [suggestions, setSuggestions] = useState([])
  const [loadingSuggestions, setLoadingSuggestions] = useState(false)

  // Storyboard State
  const [storyboard, setStoryboard] = useState(null)
  const [generatingStoryboard, setGeneratingStoryboard] = useState(false)
  const [refiningSceneId, setRefiningSceneId] = useState(null)
  const [renderingJob, setRenderingJob] = useState(false)
  const [loadingSavedStory, setLoadingSavedStory] = useState(false)

  // Fetch presets on mount
  useEffect(() => {
    http.get("/api/kids-story/presets")
      .then((res) => {
        setPresets(res.data)
      })
      .catch((err) => {
        console.error("Failed to load presets:", err)
      })

    // Load initial prompt inspirations
    fetchInspirations("fables", "preschool")
  }, [])

  // Load existing story from Library if ?load=<video_id> is provided
  useEffect(() => {
    if (!loadVideoId) return
    setLoadingSavedStory(true)
    http.get(`/api/kids-story/load/${loadVideoId}`)
      .then((res) => {
        if (res.data?.storyboard) {
          const sb = res.data.storyboard
          setStoryboard(sb)
          setPrompt(sb.title || "")
          if (sb.drawing_engine) setDrawingEngine(sb.drawing_engine)
          if (sb.target_age) setTargetAge(sb.target_age)
          if (sb.tts_voice) setVoice(sb.tts_voice)
          if (sb.animation_mode) setAnimationMode(sb.animation_mode)
          showSnackbar(`Loaded "${sb.title}" into studio for editing!`, "success")
        }
      })
      .catch((err) => {
        console.error("Failed to load kids story:", err)
        showSnackbar("Could not load video into studio", "error")
      })
      .finally(() => setLoadingSavedStory(false))
  }, [loadVideoId])

  const fetchInspirations = async (category, age) => {
    setLoadingSuggestions(true)
    try {
      const res = await http.post("/api/kids-story/inspire", {
        category: category || selectedCategory,
        target_age: age || targetAge,
        count: 3
      })
      if (res.data?.suggestions) {
        setSuggestions(res.data.suggestions)
      }
    } catch (e) {
      showSnackbar("Failed to load prompt ideas", "warning")
    } finally {
      setLoadingSuggestions(false)
    }
  }

  const handleCategoryChange = (catId) => {
    setSelectedCategory(catId)
    fetchInspirations(catId, targetAge)
  }

  const handleDeconstructReference = async () => {
    if (!referenceUrl.trim()) return
    setDeconstructingRef(true)
    try {
      const res = await http.post("/api/kids-story/deconstruct-ref", {
        reference_url: referenceUrl.trim()
      })
      if (res.data?.analysis) {
        setRefNotes(res.data.analysis)
        showSnackbar("Reference video rhythm deconstructed! Pacing applied to plan.", "success")
      }
    } catch (e) {
      showSnackbar("Could not analyze reference video URL", "warning")
    } finally {
      setDeconstructingRef(false)
    }
  }

  const handleApplySuggestion = (sugg) => {
    setPrompt(sugg.prompt)
    if (sugg.target_age) setTargetAge(sugg.target_age)
    showSnackbar(`Applied idea: "${sugg.title}"`, "info")
  }

  const handleGenerateStoryboard = async () => {
    if (!prompt.trim()) {
      showSnackbar("Please enter a story concept or pick an inspired prompt first.", "warning")
      return
    }

    setGeneratingStoryboard(true)
    try {
      const res = await http.post("/api/kids-story/generate-storyboard", {
        prompt: prompt.trim(),
        target_age: targetAge,
        style: drawingEngine,
        total_scenes: 6,
        reference_notes: refNotes ? JSON.stringify(refNotes) : null
      })

      if (res.data?.storyboard) {
        setStoryboard(res.data.storyboard)
        showSnackbar("Storyboard and character plan generated successfully!", "success")
      }
    } catch (e) {
      showSnackbar(e.response?.data?.detail || "Storyboard generation failed", "error")
    } finally {
      setGeneratingStoryboard(false)
    }
  }

  const handleRefineScene = async (sceneId, action) => {
    if (!storyboard?.scenes) return
    const targetScene = storyboard.scenes.find((s) => s.scene_id === sceneId)
    if (!targetScene) return

    setRefiningSceneId(`${sceneId}-${action}`)
    try {
      const res = await http.post("/api/kids-story/refine-scene", {
        scene: targetScene,
        action: action
      })
      if (res.data?.scene) {
        const updatedScenes = storyboard.scenes.map((s) =>
          s.scene_id === sceneId ? res.data.scene : s
        )
        setStoryboard({ ...storyboard, scenes: updatedScenes })
        showSnackbar(`Scene ${sceneId} updated!`, "success")
      }
    } catch (e) {
      showSnackbar("Failed to refine scene text", "warning")
    } finally {
      setRefiningSceneId(null)
    }
  }

  const handleNarrationChange = (sceneId, newText) => {
    if (!storyboard?.scenes) return
    const updatedScenes = storyboard.scenes.map((s) =>
      s.scene_id === sceneId ? { ...s, narration: newText } : s
    )
    setStoryboard({ ...storyboard, scenes: updatedScenes })
  }

  const handleDeleteScene = (sceneId) => {
    if (!storyboard?.scenes || storyboard.scenes.length <= 3) {
      showSnackbar("A short story needs at least 3 scenes.", "warning")
      return
    }
    const updated = storyboard.scenes.filter((s) => s.scene_id !== sceneId)
    setStoryboard({ ...storyboard, scenes: updated })
  }

  const handleAddScene = () => {
    if (!storyboard?.scenes) return
    const nextId = storyboard.scenes.length + 1
    const lastScene = storyboard.scenes[storyboard.scenes.length - 1]
    const newScene = {
      scene_id: nextId,
      type: "adventure",
      start_sec: lastScene ? lastScene.end_sec : 0,
      end_sec: lastScene ? lastScene.end_sec + 4 : 4,
      duration_sec: 4,
      narration: "And then, something wonderful and unexpected appeared!",
      visual_prompt: `${drawingEngine} style, joyful moment with characters, child friendly`,
      sfx_cue: "sparkle magic chime"
    }
    setStoryboard({ ...storyboard, scenes: [...storyboard.scenes, newScene] })
  }

  const handleLaunchProduction = async () => {
    if (!storyboard || !storyboard.scenes?.length) return
    setRenderingJob(true)
    try {
      const payload = {
        ...storyboard,
        tts_voice: voice,
        drawing_engine: drawingEngine,
        animation_mode: animationMode
      }
      const res = await http.post("/api/kids-story/render", {
        storyboard: payload,
        user_id: "local"
      })
      if (res.data?.job_id) {
        showSnackbar(`ReelMimic Production line queued (Job #${res.data.job_id.slice(0, 8)})! Check Library when finished.`, "success")
      }
    } catch (e) {
      showSnackbar(e.response?.data?.detail || "Failed to start production line", "error")
    } finally {
      setRenderingJob(false)
    }
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", overflowY: "auto" }}>
      {/* Hero Header */}
      <PageHero
        icon={<AutoStoriesIcon />}
        title="Kids Story Studio"
        subtitle="AI 2D Story Generator for US Kids with Consistent Characters — Powered by ReelMimic"
        chip={
          <Stack direction="row" spacing={1} alignItems="center">
            <Chip
              size="small"
              label="ReelMimic 2D Engine"
              sx={{
                bgcolor: alpha(theme.palette.secondary.main, 0.15),
                color: theme.palette.secondary.main,
                fontWeight: 700,
                fontSize: "0.75rem",
                border: `1px solid ${alpha(theme.palette.secondary.main, 0.3)}`
              }}
            />
            {loadVideoId && (
              <Chip
                size="small"
                icon={<EditIcon fontSize="small" />}
                label="Editing from Library"
                color="info"
                sx={{ fontWeight: 700, fontSize: "0.75rem" }}
              />
            )}
          </Stack>
        }
        actions={
          <Stack direction="row" spacing={1}>
            <Button
              variant="outlined"
              size="small"
              startIcon={<CasinoIcon />}
              onClick={() => fetchInspirations(selectedCategory, targetAge)}
              disabled={loadingSuggestions}
              sx={{ textTransform: "none", borderRadius: 2 }}
            >
              Surprise Me
            </Button>
          </Stack>
        }
      />

      {loadingSavedStory && <LinearProgress color="secondary" sx={{ height: 3 }} />}

      <Box sx={{ p: { xs: 2, md: 3 }, flexGrow: 1 }}>
        <Grid container spacing={3}>
          {/* LEFT COLUMN: STEP 1 - PROMPT & INSPIRATION HUB */}
          <Grid item xs={12} lg={5}>
            <Stack spacing={2.5}>
              {/* Category Filter Chips */}
              <Card sx={{ borderRadius: 3, border: 1, borderColor: "divider" }}>
                <CardContent sx={{ p: 2, "&:last-child": { pb: 2 } }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1.25, display: "flex", alignItems: "center", gap: 1 }}>
                    <SparklesIcon fontSize="small" color="primary" />
                    US Kids Trending Categories
                  </Typography>
                  <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", gap: 1 }}>
                    {presets?.categories.map((cat) => {
                      const isSelected = selectedCategory === cat.id
                      return (
                        <Chip
                          key={cat.id}
                          label={`${cat.icon} ${cat.label}`}
                          clickable
                          onClick={() => handleCategoryChange(cat.id)}
                          color={isSelected ? "primary" : "default"}
                          variant={isSelected ? "filled" : "outlined"}
                          sx={{
                            fontWeight: isSelected ? 700 : 500,
                            borderRadius: 2
                          }}
                        />
                      )
                    })}
                  </Stack>
                </CardContent>
              </Card>

              {/* AI Suggested Ideas Cards */}
              <Box>
                <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                  <Typography variant="caption" sx={{ fontWeight: 700, color: "text.secondary", textTransform: "uppercase" }}>
                    ✨ AI Suggested Ideas (Click to Apply)
                  </Typography>
                  {loadingSuggestions && <CircularProgress size={16} />}
                </Stack>
                <Stack spacing={1.2}>
                  {suggestions.map((sugg, idx) => (
                    <Card
                      key={idx}
                      onClick={() => handleApplySuggestion(sugg)}
                      sx={{
                        p: 1.5,
                        cursor: "pointer",
                        borderRadius: 2.5,
                        border: 1,
                        borderColor: prompt === sugg.prompt ? "primary.main" : "divider",
                        bgcolor: prompt === sugg.prompt ? alpha(theme.palette.primary.main, 0.08) : "background.paper",
                        transition: "all 0.2s ease-in-out",
                        "&:hover": {
                          borderColor: "primary.main",
                          transform: "translateY(-1px)",
                          boxShadow: 2
                        }
                      }}
                    >
                      <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, color: "primary.main" }}>
                          {sugg.title}
                        </Typography>
                        <Chip
                          size="small"
                          label={sugg.target_age === "preschool" ? "Preschool 2-5" : "Early Reader 6-8"}
                          sx={{ height: 20, fontSize: "0.65rem", fontWeight: 600 }}
                        />
                      </Stack>
                      <Typography variant="body2" sx={{ fontSize: "0.825rem", color: "text.secondary", mt: 0.5 }}>
                        "{sugg.hook}"
                      </Typography>
                    </Card>
                  ))}
                </Stack>
              </Box>

              {/* Custom Prompt Input */}
              <Card sx={{ borderRadius: 3, border: 1, borderColor: "divider" }}>
                <CardContent sx={{ p: 2 }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                    Story Concept or Hook
                  </Typography>
                  <TextField
                    fullWidth
                    multiline
                    rows={3}
                    placeholder="E.g., Barnaby the little bear who lost his blue boots on a rainy morning and learns to share his umbrella with a friend..."
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    sx={{ mb: 2 }}
                  />

                  {/* Optional Reference Video URL for ReelMimic */}
                  <Typography variant="caption" sx={{ fontWeight: 600, color: "text.secondary", mb: 0.5, display: "block" }}>
                    Optional Reference Video (ReelMimic Rhythm Deconstruction)
                  </Typography>
                  <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
                    <TextField
                      fullWidth
                      size="small"
                      placeholder="https://youtube.com/shorts/... or local file"
                      value={referenceUrl}
                      onChange={(e) => setReferenceUrl(e.target.value)}
                      InputProps={{
                        startAdornment: <LinkIcon fontSize="small" sx={{ mr: 1, color: "text.disabled" }} />
                      }}
                    />
                    <Button
                      variant="outlined"
                      size="small"
                      onClick={handleDeconstructReference}
                      disabled={deconstructingRef || !referenceUrl.trim()}
                      sx={{ whiteSpace: "nowrap" }}
                    >
                      {deconstructingRef ? <CircularProgress size={16} /> : "Deconstruct"}
                    </Button>
                  </Stack>

                  {refNotes && (
                    <Alert severity="success" sx={{ mb: 2, fontSize: "0.75rem", py: 0.5 }}>
                      Reference rhythm extracted: <strong>{refNotes.shot_pace_seconds}s</strong> pace, {refNotes.estimated_bpm} BPM.
                    </Alert>
                  )}

                  {/* Age, Drawing Engine & Animation Style Selection */}
                  <Grid container spacing={1.5} sx={{ mb: 2 }}>
                    <Grid item xs={12} sm={4}>
                      <FormControl fullWidth size="small">
                        <InputLabel>Target Age</InputLabel>
                        <Select
                          value={targetAge}
                          label="Target Age"
                          onChange={(e) => setTargetAge(e.target.value)}
                        >
                          <MenuItem value="preschool">Preschool (2-5)</MenuItem>
                          <MenuItem value="early_elementary">Elementary (6-8)</MenuItem>
                        </Select>
                      </FormControl>
                    </Grid>
                    <Grid item xs={12} sm={4}>
                      <FormControl fullWidth size="small">
                        <InputLabel>Drawing Engine</InputLabel>
                        <Select
                          value={drawingEngine}
                          label="Drawing Engine"
                          onChange={(e) => setDrawingEngine(e.target.value)}
                        >
                          <MenuItem value="crayon_picture_book">🖍️ Crayon Book</MenuItem>
                          <MenuItem value="paper_cutout">✂️ Paper Cut-out</MenuItem>
                          <MenuItem value="watercolor">🎨 Watercolor</MenuItem>
                          <MenuItem value="vector">📐 Vector 2D</MenuItem>
                        </Select>
                      </FormControl>
                    </Grid>
                    <Grid item xs={12} sm={4}>
                      <FormControl fullWidth size="small">
                        <InputLabel>Animation</InputLabel>
                        <Select
                          value={animationMode}
                          label="Animation"
                          onChange={(e) => setAnimationMode(e.target.value)}
                        >
                          <MenuItem value="lively">🌟 Lively 2D</MenuItem>
                          <MenuItem value="gentle">🎞️ Storybook Pan</MenuItem>
                        </Select>
                      </FormControl>
                    </Grid>
                  </Grid>

                  {/* Generate Button */}
                  <Button
                    fullWidth
                    variant="contained"
                    size="large"
                    startIcon={generatingStoryboard ? <CircularProgress size={20} color="inherit" /> : <SparklesIcon />}
                    onClick={handleGenerateStoryboard}
                    disabled={generatingStoryboard || !prompt.trim()}
                    sx={{
                      py: 1.4,
                      fontWeight: 700,
                      borderRadius: 2.5,
                      textTransform: "none",
                      fontSize: "0.95rem"
                    }}
                  >
                    {generatingStoryboard ? "Planning Storyboard & Characters..." : "Generate Storyboard Plan"}
                  </Button>
                </CardContent>
              </Card>
            </Stack>
          </Grid>

          {/* RIGHT COLUMN: STEP 2 - INTERACTIVE STORYBOARD MATRIX */}
          <Grid item xs={12} lg={7}>
            {!storyboard ? (
              <Box
                sx={{
                  border: "2px dashed",
                  borderColor: "divider",
                  borderRadius: 3,
                  p: { xs: 3, md: 6 },
                  textAlign: "center",
                  minHeight: 450,
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  bgcolor: alpha(theme.palette.background.paper, 0.4)
                }}
              >
                <ChildCareIcon sx={{ fontSize: 64, color: "primary.main", opacity: 0.5, mb: 1.5 }} />
                <Typography variant="h6" sx={{ fontWeight: 700, mb: 0.5 }}>
                  No Storyboard Generated Yet
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 420, mb: 2.5 }}>
                  Pick an AI suggested topic on the left or write your own concept to generate a 30–60s scene-by-scene storyboard plan powered by ReelMimic.
                </Typography>
                <Button
                  variant="outlined"
                  startIcon={<SparklesIcon />}
                  onClick={() => {
                    if (suggestions.length > 0) handleApplySuggestion(suggestions[0])
                  }}
                  sx={{ borderRadius: 2, textTransform: "none" }}
                >
                  Try First Suggested Idea
                </Button>
              </Box>
            ) : (
              <Stack spacing={2.5}>
                {/* Story Overview & Character Anchor Card */}
                <Card sx={{ borderRadius: 3, border: 1, borderColor: "primary.main", bgcolor: alpha(theme.palette.primary.main, 0.04) }}>
                  <CardContent sx={{ p: 2 }}>
                    <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 1 }}>
                      <Box sx={{ flexGrow: 1, mr: 2 }}>
                        <TextField
                          variant="standard"
                          value={storyboard.title || ""}
                          onChange={(e) => setStoryboard({ ...storyboard, title: e.target.value })}
                          placeholder="Story Title"
                          InputProps={{
                            disableUnderline: true,
                            sx: {
                              fontSize: "1.2rem",
                              fontWeight: 800,
                              p: 0.5,
                              borderRadius: 1,
                              "&:hover": { bgcolor: alpha(theme.palette.primary.main, 0.08) }
                            }
                          }}
                        />
                        <Typography variant="body2" color="text.secondary" sx={{ fontStyle: "italic", mt: 0.25 }}>
                          Moral: "{storyboard.moral_lesson}"
                        </Typography>
                      </Box>
                      <Stack direction="row" spacing={1} alignItems="center">
                        {loadVideoId && (
                          <Chip
                            size="small"
                            icon={<EditIcon fontSize="small" />}
                            label="Editing Video"
                            color="info"
                            sx={{ fontWeight: 700 }}
                          />
                        )}
                        <Chip
                          label={`${storyboard.scenes?.length || 0} Scenes • ~${storyboard.scenes?.reduce((acc, s) => acc + (s.duration_sec || 4), 0)}s`}
                          color="primary"
                          size="small"
                          sx={{ fontWeight: 700 }}
                        />
                      </Stack>
                    </Stack>

                    <Divider sx={{ my: 1.5 }} />

                    {/* Character Anchor Sheet */}
                    {storyboard.character_anchor && (
                      <Box sx={{ bgcolor: "background.paper", p: 1.5, borderRadius: 2, border: 1, borderColor: "divider" }}>
                        <Typography variant="caption" sx={{ fontWeight: 800, color: "secondary.main", textTransform: "uppercase", display: "block" }}>
                          🔒 ReelMimic Character Anchor (Consistent Across All Scenes)
                        </Typography>
                        <Grid container spacing={1} sx={{ mt: 0.25 }}>
                          <Grid item xs={12} sm={6}>
                            <Typography variant="body2" sx={{ fontSize: "0.8rem" }}>
                              <strong>Name:</strong> {storyboard.character_anchor.name} ({storyboard.character_anchor.species})
                            </Typography>
                            <Typography variant="body2" sx={{ fontSize: "0.8rem", color: "text.secondary" }}>
                              <strong>Features:</strong> {storyboard.character_anchor.features}
                            </Typography>
                          </Grid>
                          <Grid item xs={12} sm={6}>
                            <Typography variant="body2" sx={{ fontSize: "0.8rem" }}>
                              <strong>Drawing Engine:</strong> {storyboard.drawing_engine}
                            </Typography>
                            <Typography variant="body2" sx={{ fontSize: "0.8rem", color: "text.secondary" }}>
                              <strong>Animation Style:</strong> {animationMode === "lively" ? "🌟 Lively 2D Animation" : "🎞️ Gentle Storybook Pan"}
                            </Typography>
                          </Grid>
                        </Grid>
                      </Box>
                    )}
                  </CardContent>
                </Card>

                {/* Scene Cards Timeline */}
                <Typography variant="subtitle2" sx={{ fontWeight: 700, display: "flex", alignItems: "center", gap: 1 }}>
                  🎬 Scene-by-Scene Timeline Matrix
                </Typography>

                <Stack spacing={1.5}>
                  {storyboard.scenes?.map((scene) => (
                    <Card
                      key={scene.scene_id}
                      sx={{
                        borderRadius: 2.5,
                        border: 1,
                        borderColor: "divider",
                        transition: "box-shadow 0.2s ease-in-out",
                        "&:hover": { boxShadow: 3 }
                      }}
                    >
                      <CardContent sx={{ p: 2, "&:last-child": { pb: 2 } }}>
                        {/* Scene Header */}
                        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                          <Stack direction="row" spacing={1} alignItems="center">
                            <Chip
                              size="small"
                              label={`Scene ${scene.scene_id}`}
                              color={scene.type === "hook" ? "secondary" : "default"}
                              sx={{ fontWeight: 700 }}
                            />
                            <Typography variant="caption" sx={{ fontWeight: 600, color: "text.secondary" }}>
                              {scene.start_sec}s – {scene.end_sec}s ({scene.duration_sec}s) • {scene.type?.toUpperCase()}
                            </Typography>
                          </Stack>
                          <IconButton
                            size="small"
                            onClick={() => handleDeleteScene(scene.scene_id)}
                            color="error"
                            disabled={storyboard.scenes.length <= 3}
                          >
                            <DeleteOutlineIcon fontSize="small" />
                          </IconButton>
                        </Stack>

                        {/* Visual Prompt */}
                        <Box sx={{ bgcolor: alpha(theme.palette.action.hover, 0.5), p: 1, borderRadius: 1.5, mb: 1.25 }}>
                          <Typography variant="caption" sx={{ color: "text.secondary", display: "block", fontSize: "0.75rem" }}>
                            <strong>🎨 2D Visual Prompt:</strong> {scene.visual_prompt}
                          </Typography>
                        </Box>

                        {/* Editable Narration Script */}
                        <TextField
                          fullWidth
                          size="small"
                          label="US English Narration Script"
                          value={scene.narration}
                          onChange={(e) => handleNarrationChange(scene.scene_id, e.target.value)}
                          multiline
                          rows={2}
                          sx={{ mb: 1 }}
                        />

                        {/* SFX and Quick Refine Actions */}
                        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ flexWrap: "wrap", gap: 1 }}>
                          <Chip
                            size="small"
                            icon={<MusicNoteIcon fontSize="small" />}
                            label={`SFX: ${scene.sfx_cue || "gentle chime"}`}
                            variant="outlined"
                            sx={{ fontSize: "0.7rem" }}
                          />
                          <Stack direction="row" spacing={0.8}>
                            <Button
                              size="small"
                              variant="outlined"
                              onClick={() => handleRefineScene(scene.scene_id, "rhyme")}
                              disabled={refiningSceneId === `${scene.scene_id}-rhyme`}
                              sx={{ fontSize: "0.75rem", py: 0.25, textTransform: "none" }}
                            >
                              {refiningSceneId === `${scene.scene_id}-rhyme` ? <CircularProgress size={12} /> : "✨ Rhyme"}
                            </Button>
                            <Button
                              size="small"
                              variant="outlined"
                              onClick={() => handleRefineScene(scene.scene_id, "simplify")}
                              disabled={refiningSceneId === `${scene.scene_id}-simplify`}
                              sx={{ fontSize: "0.75rem", py: 0.25, textTransform: "none" }}
                            >
                              {refiningSceneId === `${scene.scene_id}-simplify` ? <CircularProgress size={12} /> : "✨ Simpler"}
                            </Button>
                          </Stack>
                        </Stack>
                      </CardContent>
                    </Card>
                  ))}
                </Stack>

                {/* Add Scene Button */}
                <Button
                  variant="outlined"
                  fullWidth
                  startIcon={<AddCircleOutlineIcon />}
                  onClick={handleAddScene}
                  sx={{ py: 1, borderRadius: 2, borderStyle: "dashed" }}
                >
                  Add Another Scene
                </Button>

                {/* Bottom Production Controls */}
                <Card sx={{ borderRadius: 3, border: 1, borderColor: "divider", p: 2 }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1.5 }}>
                    🔊 Audio & Animation Production Settings
                  </Typography>
                  <Grid container spacing={2} alignItems="center" sx={{ mb: 2 }}>
                    <Grid item xs={12} sm={4}>
                      <FormControl fullWidth size="small">
                        <InputLabel>US Storyteller Voice</InputLabel>
                        <Select
                          value={voice}
                          label="US Storyteller Voice"
                          onChange={(e) => setVoice(e.target.value)}
                        >
                          {presets?.voice_presets.map((v) => (
                            <MenuItem key={v.id} value={v.id}>
                              {v.name} ({v.vibe})
                            </MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                    </Grid>
                    <Grid item xs={12} sm={4}>
                      <FormControl fullWidth size="small">
                        <InputLabel>Animation Motion Mode</InputLabel>
                        <Select
                          value={animationMode}
                          label="Animation Motion Mode"
                          onChange={(e) => setAnimationMode(e.target.value)}
                        >
                          <MenuItem value="lively">🌟 Lively 2D Animation</MenuItem>
                          <MenuItem value="gentle">🎞️ Storybook Pan & Zoom</MenuItem>
                        </Select>
                      </FormControl>
                    </Grid>
                    <Grid item xs={12} sm={4}>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", lineHeight: 1.25 }}>
                        {animationMode === "lively"
                          ? "🌟 Procedural micro-animations: breathing, eye blinks, ear wiggles, falling raindrops & ripples."
                          : "🎞️ Classic storybook pan & zoom with gentle Ken Burns motion."}
                      </Typography>
                    </Grid>
                  </Grid>

                  <Stack direction="row" spacing={2} justifyContent="flex-end">
                    <Button
                      variant="contained"
                      size="large"
                      color="secondary"
                      startIcon={renderingJob ? <CircularProgress size={20} color="inherit" /> : <PlayCircleIcon />}
                      onClick={handleLaunchProduction}
                      disabled={renderingJob}
                      sx={{
                        fontWeight: 800,
                        px: 3,
                        py: 1.25,
                        borderRadius: 2.5,
                        textTransform: "none",
                        boxShadow: 3
                      }}
                    >
                      {renderingJob ? "Queueing Production Line..." : "Start ReelMimic Production Line"}
                    </Button>
                  </Stack>
                </Card>
              </Stack>
            )}
          </Grid>
        </Grid>
      </Box>
    </Box>
  )
}
