// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
/**
 * Keyboard parity for the Library's clickable rows.
 *
 * The tree rows, the "Nothing made from these yet" toggle, the drawer's lineage
 * rows and the pager's "clear filters" were `onClick` on a <div>: no tab stop,
 * no Enter/Space, nothing for a screen reader to announce. A real <button>
 * would fight the row layouts (block content inside), so these get the button
 * contract instead — role, tab stop, Enter AND Space (a real button answers
 * both; preventDefault keeps Space from scrolling the page).
 *
 * Only keys aimed at the row itself count, so a control nested inside a row
 * keeps its own Enter.
 */
export function buttonProps(onActivate, { label, expanded } = {}) {
  return {
    role: "button",
    tabIndex: 0,
    ...(label ? { "aria-label": label } : {}),
    ...(expanded != null ? { "aria-expanded": expanded } : {}),
    onClick: onActivate,
    onKeyDown: (e) => {
      if (e.target !== e.currentTarget) return
      if (e.key !== "Enter" && e.key !== " ") return
      e.preventDefault()
      onActivate(e)
    },
  }
}

/** A focus ring drawn INSIDE the element. The theme's global ring is a
 *  box-shadow outside the box, which the rounded, overflow-hidden cards these
 *  rows sit in clip to nothing. */
export const insetFocusRing = {
  "&:focus-visible": {
    outline: "2px solid",
    outlineColor: "primary.main",
    outlineOffset: "-2px",
    boxShadow: "none",
  },
}
