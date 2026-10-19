// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { createContext, useContext } from "react"

// True while the project renders. Recording takes waits until the render is
// done, so the voice buttons are disabled meanwhile. Provided by the editor
// page.
export const StudioRenderingContext = createContext(false)

export const useStudioRendering = () => useContext(StudioRenderingContext)
