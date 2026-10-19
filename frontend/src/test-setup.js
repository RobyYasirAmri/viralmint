// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
import "@testing-library/jest-dom/vitest"
import { afterEach } from "vitest"
import { cleanup } from "@testing-library/react"

// jsdom doesn't ship ResizeObserver — stub it so components that use
// it (the Studio editor and toolbars measure themselves) don't
// throw on mount during tests. The stub is no-op: tests don't depend
// on resize callbacks firing.
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

// This jsdom build doesn't provide Web Storage ("localStorage is not available
// because --localstorage-file was not provided"), so anything that persists a
// preference was untestable. Minimal in-memory Storage, installed on the
// prototype so tests can still spy on / throw from getItem+setItem to simulate
// Safari private mode.
if (typeof globalThis.localStorage === "undefined") {
  class MemoryStorage {
    #data = new Map()
    get length() { return this.#data.size }
    key(i) { return [...this.#data.keys()][i] ?? null }
    getItem(k) { return this.#data.has(String(k)) ? this.#data.get(String(k)) : null }
    setItem(k, v) { this.#data.set(String(k), String(v)) }
    removeItem(k) { this.#data.delete(String(k)) }
    clear() { this.#data.clear() }
  }
  globalThis.Storage = MemoryStorage
  const store = new MemoryStorage()
  const sessionStore = new MemoryStorage()
  Object.defineProperty(globalThis, "localStorage", { value: store, configurable: true })
  Object.defineProperty(globalThis, "sessionStorage", { value: sessionStore, configurable: true })
}

afterEach(() => {
  cleanup()
})
