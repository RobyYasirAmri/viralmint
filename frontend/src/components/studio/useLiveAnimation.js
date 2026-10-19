// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useEffect, useState } from "react"

// Should a decorative canvas animate right now? (audit 2026-09-25)
//
// /stock ran ~26 requestAnimationFrame loops forever — every sample card's
// caption canvas and every style swatch — ~1,600 callbacks a second on an idle
// page, and the Studio's Project panel another 16. Each canvas now draws ONE
// static frame, and loops only while ALL of these hold:
//   · `want`            — the caller's reason to move (hovered, selected, …)
//   · on screen         — IntersectionObserver
//   · the tab is shown  — document.visibilityState
//   · motion is welcome — prefers-reduced-motion is not "reduce"

function reducedMotionQuery() {
  try { return window.matchMedia?.("(prefers-reduced-motion: reduce)") || null } catch { return null }
}

export function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(() => !!reducedMotionQuery()?.matches)
  useEffect(() => {
    const mq = reducedMotionQuery()
    if (!mq) return undefined
    const on = () => setReduced(mq.matches)
    mq.addEventListener?.("change", on)
    return () => mq.removeEventListener?.("change", on)
  }, [])
  return reduced
}

export function useDocumentVisible() {
  const [visible, setVisible] = useState(() => typeof document === "undefined" || document.visibilityState !== "hidden")
  useEffect(() => {
    const on = () => setVisible(document.visibilityState !== "hidden")
    document.addEventListener("visibilitychange", on)
    return () => document.removeEventListener("visibilitychange", on)
  }, [])
  return visible
}

export function useInView(ref, { threshold = 0.1 } = {}) {
  // No IntersectionObserver (jsdom, very old engines): treat as visible.
  const [inView, setInView] = useState(() => typeof IntersectionObserver === "undefined")
  useEffect(() => {
    const el = ref.current
    if (!el || typeof IntersectionObserver === "undefined") return undefined
    const io = new IntersectionObserver(([e]) => setInView(e.isIntersecting), { threshold })
    io.observe(el)
    return () => io.disconnect()
  }, [ref, threshold])
  return inView
}

export default function useLiveAnimation(ref, want = true) {
  const inView = useInView(ref)
  const visible = useDocumentVisible()
  const reduced = usePrefersReducedMotion()
  return !!want && inView && visible && !reduced
}
