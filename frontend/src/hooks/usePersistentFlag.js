// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import { useEffect, useState } from "react"
import { readRaw, writeRaw } from "../utils/storage"

/**
 * A boolean UI preference that survives a reload.
 *
 * The "read localStorage in a lazy initialiser, write it in an effect, wrap
 * both in try/catch because private mode throws" block, once. Build the key
 * with storageKey(scope, name) so it sits under the app's `vm.` prefix.
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
