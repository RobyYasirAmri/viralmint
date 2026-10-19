// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { memo } from "react"
import { Box } from "@mui/material"
import { SceneTab } from "./Inspector"
import { SCENE_PANEL_MIN, SCENE_PANEL_WIDTH } from "./editorLayout"

// The selected scene's panel, beside the player (owner, 2026-09-16: the scene
// is edited next to what it looks like, and only exists while a scene is
// selected in the timeline — it is not a tab next to Project).
//
// Beside the player it shrinks from 360 to 300px (the player keeps its own
// minimum). `drawer`: a window too small for both — it fills the Project
// column instead, never covering the player.
// `findings` are this scene's critic notes — computed once by the editor.
function ScenePanel({ scene, timeline, project, findings = [], drawer = false, onClose, ...handlers }) {
  return (
    <Box
      role="region" aria-label={`Scene ${scene.index + 1}`} data-testid="scene-panel"
      sx={drawer ? {
        position: "absolute", inset: 0, zIndex: 3, overflowY: "auto", bgcolor: "background.paper",
      } : {
        flex: `0 1 ${SCENE_PANEL_WIDTH}px`, minWidth: SCENE_PANEL_MIN, minHeight: 0, overflowY: "auto",
        bgcolor: "background.paper", borderLeft: 1, borderColor: "divider",
      }}
    >
      <SceneTab
        // Remount per scene: an unsaved line draft and open menus belong to
        // the scene they were made on.
        key={scene.uid}
        scene={scene} total={timeline.total} settings={project.doc.settings}
        findings={findings}
        isLast={scene.index === timeline.scenes.length - 1}
        sceneCount={timeline.scenes.length} projectId={project.id}
        onClose={onClose}
        {...handlers}
      />
    </Box>
  )
}

export default memo(ScenePanel)
