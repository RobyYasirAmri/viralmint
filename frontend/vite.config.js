/// <reference types="vitest" />
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api":  "http://localhost:16888",
      "/ws":   { target: "ws://localhost:16888", ws: true },
    }
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
  // `npm test` (vitest): jsdom + Testing Library, set up in src/test-setup.js.
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.js"],
    css: false,
  },
})
