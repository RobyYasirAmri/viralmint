// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useEffect, useState } from "react"
import { readRaw, writeRaw } from "../utils/storage"

/**
 * A boolean UI preference that survives a reload.
 *
 * Collapses the "read localStorage in a lazy initialiser, write it in an
 * effect, wrap both in try/catch because private mode throws" block that
 * ClipStudio and Merge Clips each carried a copy of — with the two keys
 * (`clipstudio_filmstrip_collapsed`, `mergeclips_filmstrip_collapsed`) being
 * the only two in the whole app with no `vm` prefix, so a "clear ViralMint
 * state" sweep matching on `vm` left them behind (2026-08-17 audit, D2).
 *
 * @param {string} key         Canonical key — build it with storageKey(scope, name).
 * @param {boolean} [initial]  Value when nothing is stored.
 * @param {object} [opts]
 * @param {string} [opts.legacyKey]  Older key to migrate from, read once when
 *                                   `key` is absent. Renaming a key otherwise
 *                                   silently discards the user's saved state.
 * @returns {[boolean, Function]} `[value, setValue]`, same shape as useState.
 */
export default function usePersistentFlag(key, initial = false, opts = {}) {
  const { legacyKey } = opts

  const [value, setValue] = useState(() => {
    const stored = readRaw(key)
    if (stored != null) return stored === "1"
    if (legacyKey) {
      const legacy = readRaw(legacyKey)
      if (legacy != null) return legacy === "1"
    }
    return initial
  })

  useEffect(() => {
    writeRaw(key, value ? "1" : "0")
  }, [key, value])

  return [value, setValue]
}
