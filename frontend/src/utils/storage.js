// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
/**
 * Browser-storage keys: one namespace, one convention.
 *
 * `vm.<scope>.<name>` — scope is the surface, name is the setting. Keeping
 * every key under one prefix is what makes "clear ViralMint's local state" a
 * thing a user (or a support answer) can actually do; an unprefixed key is
 * invisible to any such sweep and gets left behind.
 *
 * Existing unprefixed keys are deliberately NOT renamed — a rename silently
 * discards whatever the user had saved. This is what a NEW key looks like.
 */
export function storageKey(scope, name) {
  if (!scope || !name) throw new Error("storageKey(scope, name): both required")
  return `vm.${scope}.${name}`
}

/**
 * Read + JSON.parse a key, returning `fallback` on absent/corrupt/blocked.
 *
 * localStorage throws in Safari private mode and when a page is sandboxed, and
 * a half-written value throws in JSON.parse — several call sites already
 * wrapped one or the other in try/catch, and the ones that didn't would take
 * the whole page down with them.
 */
export function readJson(key, fallback = null) {
  try {
    const raw = localStorage.getItem(key)
    return raw == null ? fallback : JSON.parse(raw)
  } catch {
    return fallback
  }
}

/** JSON.stringify + write. Silently no-ops when storage is unavailable. */
export function writeJson(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
    return true
  } catch {
    return false
  }
}

/** Read a raw string value. Returns `fallback` when storage is unavailable
 *  (private mode, blocked site data) — the accessor can throw. */
export function readRaw(key, fallback = null) {
  try {
    return localStorage.getItem(key) ?? fallback
  } catch {
    return fallback
  }
}

/** Write a raw string value. Silently no-ops when storage is unavailable. */
export function writeRaw(key, value) {
  try {
    localStorage.setItem(key, value)
    return true
  } catch {
    return false
  }
}
