// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useCallback, useEffect, useRef, useState } from "react"

const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi)

// Pointer travel before a press counts as a drag. Below it the press stays a
// plain click, so the double-click reset survives — the caller's drag overlay
// would otherwise cover the handle from the first mousedown and swallow every
// following pointerup/click/dblclick.
const DRAG_THRESHOLD_PX = 3

/**
 * Drag-to-resize width for a panel, persisted per `storageKey`. `anchor`:
 * "right" (default) — the panel is docked on the right and its handle sits on
 * its LEFT edge, so dragging left widens it; "left" — docked on the left with
 * the handle on its RIGHT edge, so dragging right widens it.
 *
 * Returns `handleProps` to spread onto the grab strip: pointer drag, double-click
 * to reset, and arrow-key resizing so the control is reachable without a mouse
 * (it's a real `separator` role, not a decorative div).
 *
 * Uses POINTER CAPTURE rather than window listeners. The panel floats over an
 * <iframe> (the HyperFrames studio), and an iframe swallows pointer events the
 * parent document never sees — so a window-listener drag dies the instant the
 * cursor crosses the frame. Capture routes every event for that pointer to the
 * handle regardless of what's underneath, which also means the drag can't be
 * lost mid-gesture. The caller's `dragging` overlay is then purely cosmetic
 * (global col-resize cursor, no hover states bleeding through).
 */
export default function useResizableWidth({
  storageKey, initial = 400, min = 320, max = 900,
  // What the separator announces. It used to be hardcoded to "the AI Compose
  // panel", which was already a lie on /motion and would be a second one on
  // the Plan drawer — a screen-reader user resizing the plan should not be
  // told they are resizing Compose.
  label = "panel",
  anchor = "right",
}) {
  const dir = anchor === "left" ? -1 : 1
  const [width, setWidthRaw] = useState(() => {
    try {
      const saved = parseInt(window.localStorage.getItem(storageKey), 10)
      // Same viewport clamp the resize listener applies — a width saved on a
      // wide monitor must not mount wider than a narrow window on first paint
      // (the handle sits on the LEFT edge, so an oversized panel hides it).
      if (Number.isFinite(saved)) {
        return clamp(saved, min, Math.min(max, Math.max(min, window.innerWidth - 160)))
      }
    } catch { /* private mode / disabled storage — fall through to the default */ }
    return initial
  })
  const [dragging, setDragging] = useState(false)  // past the threshold — really dragging
  const startRef = useRef(null)                    // {x, w, id} while a pointer is down
  const draggingRef = useRef(false)                // read synchronously inside onPointerMove

  const setWidth = useCallback((w) => {
    const next = clamp(Math.round(w), min, max)
    setWidthRaw(next)
    try { window.localStorage.setItem(storageKey, String(next)) } catch { /* ignore */ }
  }, [storageKey, min, max])

  // A width saved on a wide monitor must not eat a narrow window whole.
  useEffect(() => {
    const onResize = () =>
      setWidthRaw((w) => clamp(w, min, Math.max(min, window.innerWidth - 160)))
    window.addEventListener("resize", onResize)
    return () => window.removeEventListener("resize", onResize)
  }, [min])

  const disarm = useCallback(() => {
    startRef.current = null
    draggingRef.current = false
    setDragging(false)
  }, [])

  const onPointerDown = useCallback((e) => {
    e.preventDefault()
    try { e.currentTarget.setPointerCapture(e.pointerId) } catch { /* older engines */ }
    startRef.current = { x: e.clientX, w: width, id: e.pointerId }
  }, [width])

  const onPointerMove = useCallback((e) => {
    const s = startRef.current
    if (!s || s.id !== e.pointerId) return
    // Right-anchored: dragging the handle LEFT makes the panel wider (mirrored for left).
    const dx = (s.x - e.clientX) * dir
    if (!draggingRef.current) {
      if (Math.abs(dx) < DRAG_THRESHOLD_PX) return
      draggingRef.current = true
      setDragging(true)
    }
    setWidth(s.w + dx)
  }, [setWidth, dir])

  const onPointerUp = useCallback((e) => {
    try {
      if (e.currentTarget.hasPointerCapture?.(e.pointerId)) {
        e.currentTarget.releasePointerCapture(e.pointerId)
      }
    } catch { /* already released */ }
    disarm()
  }, [disarm])

  const reset = useCallback(() => {
    disarm()                       // a trailing pointermove must not undo this
    setWidth(initial)
  }, [disarm, setWidth, initial])

  const onKeyDown = useCallback((e) => {
    const step = e.shiftKey ? 64 : 16
    const actions = {
      ArrowLeft: () => setWidth(width + step * dir),
      ArrowRight: () => setWidth(width - step * dir),
      Home: () => setWidth(max),
      End: () => setWidth(min),
      Enter: reset,
    }
    const fn = actions[e.key]
    if (fn) { e.preventDefault(); fn() }
  }, [width, setWidth, min, max, reset, dir])

  return {
    width,
    dragging,
    reset,
    handleProps: {
      onPointerDown,
      onPointerMove,
      onPointerUp,
      onPointerCancel: disarm,
      onKeyDown,
      onDoubleClick: reset,
      role: "separator",
      tabIndex: 0,
      "aria-orientation": "vertical",
      "aria-label": `Resize ${label}`,
      "aria-valuenow": width,
      "aria-valuemin": min,
      "aria-valuemax": max,
    },
  }
}
