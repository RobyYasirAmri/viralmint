# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""MCP server entry point — mounts onto the existing FastAPI app.

Wire-up:

  1. Create a FastMCP instance and register the tool / prompt / resource
     modules (memoized — the /mcp page and the mount share one instance).
  2. Fetch (or generate on first run) the Bearer token from DATA_DIR/mcp_token.
  3. Wrap the streamable-HTTP ASGI app with a Bearer-auth middleware.
  4. backend/main.py mounts it at /mcp and enters its lifespan.

Security layering, in request order:

  request → CSRF middleware → /mcp mount → Bearer middleware
          → fastmcp JSON-RPC dispatch → MCP tool → self-HTTP client
          → FastAPI /api/* handler

  - The CSRF middleware lets MCP clients through: they send no Origin or
    Referer (non-browser), which it already treats as a CLI caller.
  - The Bearer middleware is the access check, in every bind mode.
  - Self-HTTP calls set an allowlisted Origin so CSRF passes on the inner
    call too.
"""
from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from backend.mcp.token import get_or_create_mcp_token

logger = logging.getLogger(__name__)

# The ONE FastMCP instance — the mounted server and the /mcp page's tool
# list read the same object, so they can never disagree.
_mcp_app = None


def _reset_mcp_app_cache() -> None:
    """Test-only hook: drop the cached instance so the next call rebuilds."""
    global _mcp_app
    _mcp_app = None


def _build_mcp_app():
    """Construct the FastMCP server and register every module. Memoized.

    fastmcp is imported lazily so a missing dependency disables MCP alone
    instead of taking the whole backend down at startup.
    """
    global _mcp_app
    if _mcp_app is not None:
        return _mcp_app

    from fastmcp import FastMCP

    mcp = FastMCP("ViralMint")

    # MUST run before any register() call — see the function.
    _install_full_description_decorator(mcp)

    # Registration order is the order tools/list returns, so keep it
    # workflow-shaped: shortcuts first, then research → acquire → generate →
    # output → tools, then job control. Discovery last: it enumerates the
    # argument VALUES the tools above take (caption styles, voices).
    from backend.mcp.tools import (
        macros,
        research,
        acquire,
        generate,
        output,
        tools as tools_module,
        orchestration,
        intelligence,
        discovery,
    )
    macros.register(mcp)
    research.register(mcp)
    acquire.register(mcp)
    generate.register(mcp)
    output.register(mcp)
    tools_module.register(mcp)
    orchestration.register(mcp)
    intelligence.register(mcp)
    discovery.register(mcp)

    from backend.mcp import prompts as prompts_module
    prompts_module.register(mcp)

    from backend.mcp import resources as resources_module
    resources_module.register(mcp)

    _mcp_app = mcp
    return mcp


# Docstring sections fastmcp routes elsewhere or that add nothing for a caller.
# `Args:` entries become per-parameter schema descriptions, so re-appending them
# to the tool description would duplicate them in every tools/list payload.
_DOCSTRING_SECTIONS_HANDLED_ELSEWHERE = ("Args:", "Arguments:", "Parameters:")


def _tool_description_from_docstring(doc: str) -> str:
    """Rebuild a tool description from its raw docstring, dropping only the
    argument section (fastmcp puts that in the parameter schemas).

    Everything else — the summary, the body, `Returns:`, and any trailing
    "Next:" chaining hint — is content we deliberately wrote FOR the model and
    that must survive to it.

    Indentation is normalized with inspect.cleandoc FIRST, so section headers
    sit at column 0 regardless of how deeply the docstring was nested in the
    source (these live inside `register(mcp)`, so they start 8 spaces in).
    Without that, "is this line a new section header?" is unanswerable.
    """
    import inspect
    import re

    if not doc or not doc.strip():
        return ""

    text = inspect.cleandoc(doc)
    arg_header = re.compile(
        r"^(?:%s)\s*$" % "|".join(
            re.escape(s) for s in _DOCSTRING_SECTIONS_HANDLED_ELSEWHERE))
    # Any other column-0 "Word:" line starts a new section we want to keep
    # (Returns:, Raises:, Note:, Example:, …).
    other_header = re.compile(r"^[A-Z][A-Za-z ]{0,30}:\s*$")

    out: list[str] = []
    skipping = False
    for line in text.splitlines():
        if arg_header.match(line):
            skipping = True
            continue
        if skipping:
            if other_header.match(line):
                skipping = False          # fall through and keep this header
            elif line.strip() and not line[:1].isspace():
                skipping = False          # un-indented prose = section over
            else:
                continue                  # arg entry or blank line
        out.append(line)

    # Collapse the blank lines the removed section left behind.
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(out))
    return result.strip()


def _install_full_description_decorator(mcp) -> None:
    """Wrap `mcp.tool` so a tool's full docstring reaches the model.

    fastmcp parses Google-style docstrings via griffe, and that parse is
    lossy: when a docstring has an `Args:` section only the text above it
    survives as the description (so the `Returns:` shape — what lets the
    model chain one tool into the next — is discarded), and an indented `-`
    list truncates the description at the summary line.

    Passing an explicit `description=` built from the raw `__doc__` bypasses
    that parse, while `Args:` stays in the docstring for fastmcp to route into
    the parameter schemas. Installed before any tool registers, so every
    module keeps using a plain `@mcp.tool()`. A tool that passes its own
    `description=` wins.
    """
    original = mcp.tool

    def _describe(fn) -> str | None:
        try:
            return _tool_description_from_docstring(fn.__doc__ or "") or None
        except Exception:
            # A malformed docstring must never block registration — fall back
            # to fastmcp's own (lossy but working) parse.
            logger.warning("MCP: could not rebuild description for %s",
                           getattr(fn, "__name__", "?"), exc_info=True)
            return None

    def tool(*args, **kwargs):
        # Bare `@mcp.tool` — the function itself is the first positional arg.
        if args and callable(args[0]) and not isinstance(args[0], str):
            fn = args[0]
            if kwargs.get("description") is None:
                desc = _describe(fn)
                if desc:
                    kwargs["description"] = desc
            return original(fn, **kwargs)

        # `@mcp.tool(...)` — defer until we can see the function.
        def decorator(fn):
            kw = dict(kwargs)
            if kw.get("description") is None:
                desc = _describe(fn)
                if desc:
                    kw["description"] = desc
            return original(*args, **kw)(fn)

        return decorator

    mcp.tool = tool


class ActivityLogMiddleware(BaseHTTPMiddleware):
    """Record every authenticated MCP request in the activity buffer.

    Runs inside the Bearer check (see the add order in build_mcp_asgi_app), so
    a 401 never reaches the Activity tab. The JSON-RPC body is read through
    `request.body()`, which Starlette caches, so the fastmcp handler still
    sees it. Only the first 64 KB is parsed — far above any real MCP payload,
    small enough that a huge POST can't balloon memory here.
    """

    _MAX_BODY_BYTES = 64 * 1024

    async def dispatch(self, request: Request, call_next):
        import json
        import time
        from backend.mcp import activity

        start = time.monotonic()
        method_name: str | None = None
        tool_name: str | None = None
        try:
            rpc = json.loads((await request.body())[: self._MAX_BODY_BYTES] or b"null")
            if isinstance(rpc, dict):
                method_name = rpc.get("method")
                params = rpc.get("params")
                if method_name in ("tools/call", "prompts/get") and isinstance(params, dict):
                    tool_name = params.get("name")
        except Exception:
            pass  # not JSON-RPC (a GET stream, a truncated body) — log the HTTP verb

        status_code = 500
        error: str | None = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception as e:
            error = f"{type(e).__name__}: {str(e)[:160]}"
            raise
        finally:
            await activity.record_and_broadcast(
                method=method_name or request.method,
                tool=tool_name,
                status_code=status_code,
                latency_ms=(time.monotonic() - start) * 1000,
                error=error,
            )


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Reject MCP requests without (or with the wrong) Bearer token.

    Required in every bind mode. On loopback it ties one MCP client config to
    one ViralMint install (a dev and a packaged build can't be cross-wired);
    in LAN mode (HOST=0.0.0.0) it is also what stops another device on the
    network from driving the agent tools.

    Compared with `secrets.compare_digest` (no timing oracle). The expected
    token comes from a callable read per request, so rotating it on the /mcp
    page takes effect without a restart.
    """

    def __init__(self, app, token_provider):
        super().__init__(app)
        self._token_provider = token_provider

    async def dispatch(self, request: Request, call_next):
        import secrets
        from backend.mcp.token import TOKEN_FILE
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse(
                {
                    "error": "missing_token",
                    "detail": (
                        "MCP endpoint requires Authorization: Bearer <token>. "
                        "Find your token on the ViralMint /mcp page, or read "
                        f"it directly from {TOKEN_FILE}."
                    ),
                },
                status_code=401,
            )
        provided = auth[len("Bearer "):].strip()
        # Re-read per request so token rotation takes effect immediately.
        expected = self._token_provider()
        if not secrets.compare_digest(provided, expected):
            return JSONResponse(
                {
                    "error": "invalid_token",
                    "detail": (
                        "MCP token does not match. Re-copy it from the "
                        "ViralMint /mcp page, or read the current "
                        f"value from {TOKEN_FILE} (the token may have been "
                        "rotated, or your dev/packaged DATA_DIR may differ "
                        "from the one you copied from)."
                    ),
                },
                status_code=401,
            )
        return await call_next(request)


def build_mcp_asgi_app():
    """Construct the MCP ASGI app + Bearer middleware, ready to be mounted.

    Returns the Starlette app, or None if fastmcp is unavailable or
    construction failed (the rest of the backend keeps working). The caller
    must (1) `app.mount("/mcp", mcp_asgi)` BEFORE the SPA catch-all route,
    and (2) enter `mcp_asgi.router.lifespan_context(app)` from the parent
    lifespan — Starlette doesn't forward lifespan events to mounted sub-apps,
    and without the session manager every request fails "Session terminated".
    """
    try:
        token = get_or_create_mcp_token()
        mcp = _build_mcp_app()
        # path="/" so the mount at /mcp serves /mcp, not /mcp/mcp.
        mcp_asgi = mcp.http_app(path="/")
        # Starlette runs middleware in REVERSE add order: activity is added
        # first so auth runs first and a rejected request is never logged.
        mcp_asgi.add_middleware(ActivityLogMiddleware)
        # The token provider is the FUNCTION, re-read per request, so a
        # rotation on the /mcp page takes effect without a restart.
        mcp_asgi.add_middleware(
            BearerAuthMiddleware,
            token_provider=get_or_create_mcp_token,
        )
        logger.info("MCP server mounted at /mcp (token %s…)", token[:8])
        return mcp_asgi
    except ImportError as e:
        # Only a missing DEPENDENCY is the soft case. An ImportError raised
        # from inside one of our own modules is a bug, and calling it "fastmcp
        # missing" would send the reader after the wrong cause.
        if (getattr(e, "name", None) or "").split(".")[0] not in ("fastmcp", "mcp"):
            logger.exception("MCP server failed to construct: %s", e)
            return None
        logger.warning(
            "MCP server not built — %s. The rest of the backend works "
            "normally; `pip install -r requirements.txt` to enable it.", e)
        return None
    except Exception as e:
        logger.exception("MCP server failed to construct: %s", e)
        return None
