// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2025-2026 ViralMint Contributors
// fastmcp appends its own boilerplate to every prompt argument's
// description — "Provide as a JSON string matching the following schema:
// {"type":"string"}" — because MCP prompt arguments are always strings on
// the wire. It is noise for a person reading the Prompts tab (and was the
// longest, unbreakable line in the card), so strip it for display.
const SCHEMA_BOILERPLATE = /\s*Provide as a JSON string matching the following schema:[\s\S]*$/i

export function cleanArgDescription(desc) {
  if (!desc || typeof desc !== "string") return ""
  return desc.replace(SCHEMA_BOILERPLATE, "").trim()
}
