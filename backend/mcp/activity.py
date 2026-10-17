# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""MCP activity ring buffer — the last N requests, in memory.

Backs the Activity tab on the /mcp page, so a user can see their agent
actually calling ViralMint instead of wondering whether the wiring is alive.

Deliberately not a DB table: one agent workflow is a burst of tool calls, and
SQLite writes on that hot path would compete with the rest of the backend for
the WAL lock. Users care about what just happened, not lifetime history, and
the durable record of what was produced already lives in `jobs` and
`generated_videos`. The buffer starts empty on every restart.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

# Comfortably more than the longest single agent workflow (~8-12 calls).
MAX_ENTRIES = 50

_buffer: deque[dict[str, Any]] = deque(maxlen=MAX_ENTRIES)
# Appends happen on the event loop; the lock keeps a future caller on another
# thread from tearing a snapshot.
_lock = threading.Lock()


def record(
    *,
    method: str,
    tool: str | None,
    status_code: int,
    latency_ms: float,
    error: str | None = None,
) -> dict:
    """Append one event.

    `method` is the JSON-RPC verb ("tools/call", "tools/list", "initialize",
    "prompts/get", …); `tool` is the tool or prompt name for a call, else None.
    """
    entry = {
        "ts": time.time(),
        "method": method,
        "tool": tool,
        "status_code": status_code,
        "latency_ms": round(latency_ms, 1),
        "error": error,
    }
    with _lock:
        _buffer.append(entry)
    return entry


async def record_and_broadcast(*, user_id: str = "local", **fields) -> dict:
    """`record()` plus a `mcp_activity` WebSocket event, so the Activity tab
    updates live. The broadcast is best-effort: the buffer and the poll
    endpoint stay authoritative, and a WS failure must not fail the request
    that just completed."""
    entry = record(**fields)
    try:
        from backend.core.ws_manager import ws_manager
        await ws_manager.send({"type": "mcp_activity", "event": entry}, user_id=user_id)
    except Exception:
        pass
    return entry


def snapshot() -> list[dict[str, Any]]:
    """A copy of the buffer, newest first."""
    with _lock:
        return list(reversed(_buffer))


def clear() -> None:
    with _lock:
        _buffer.clear()
