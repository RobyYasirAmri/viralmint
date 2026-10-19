// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useMemo, useSyncExternalStore } from "react"

// A playhead that lives OUTSIDE React state (audit 2026-09-25).
//
// Playback moves the playhead ~20×/s. Kept in a page's useState, every tick
// re-rendered the whole editor — media bin, inspector, timeline, every canvas
// swatch — for one moving line and a clock: ~20 commits/s and 50-100ms long
// tasks in the Studio, the same on Clipper's bench on every timeupdate.
//
// Here the value sits in a tiny store and only the parts that draw it
// subscribe (the playhead line, the clock, the scrub bar, the caption
// overlay). Everything else reads `get()` inside handlers, or subscribes
// through a selector that changes rarely — e.g. "which scene is under the
// playhead", which only changes at a scene boundary.

export function createPlayhead(initial = 0) {
  let value = initial
  const subs = new Set()
  return {
    get: () => value,
    set(t) {
      if (t === value || Number.isNaN(t)) return
      value = t
      for (const fn of [...subs]) fn()
    },
    subscribe(fn) {
      subs.add(fn)
      return () => subs.delete(fn)
    },
  }
}

const same = (t) => t

// Subscribe to the playhead through `select`. The component re-renders only
// when the SELECTED value changes (Object.is), so a selector that returns a
// scene index re-renders at scene boundaries, not on every tick.
export function usePlayhead(store, select = same) {
  return useSyncExternalStore(store.subscribe, () => select(store.get()), () => select(store.get()))
}

// Components take `playhead` as either a store or a plain number (tests and
// simple callers pass a number). A number becomes a fixed store, rebuilt only
// when the number changes.
export function usePlayheadStore(playhead) {
  const isStore = !!playhead && typeof playhead === "object" && typeof playhead.subscribe === "function"
  const fixed = useMemo(() => (isStore ? null : createPlayhead(Number(playhead) || 0)), [isStore, playhead])
  return isStore ? playhead : fixed
}
