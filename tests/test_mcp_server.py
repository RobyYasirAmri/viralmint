# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""The MCP server's plumbing: token, auth, mount, wiring, settings endpoints.

Per-tool behaviour lives in the test_mcp_<module> files; this file covers what
every tool depends on.
"""
from __future__ import annotations

import inspect
import json
import re

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.mcp import client as mcp_client
from backend.mcp import token as mcp_token
from backend.mcp.server import _build_mcp_app, _tool_description_from_docstring


# ── token ───────────────────────────────────────────────────────────────────

def test_token_is_created_once_and_persisted(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_token, "TOKEN_FILE", tmp_path / "mcp_token")
    first = mcp_token.get_or_create_mcp_token()
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", first)
    assert mcp_token.get_or_create_mcp_token() == first
    assert (tmp_path / "mcp_token").read_text() == first


def test_rotation_replaces_the_token(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_token, "TOKEN_FILE", tmp_path / "mcp_token")
    first = mcp_token.get_or_create_mcp_token()
    second = mcp_token.reset_mcp_token()
    assert second != first
    assert mcp_token.get_or_create_mcp_token() == second


def test_empty_token_file_is_regenerated(tmp_path, monkeypatch):
    f = tmp_path / "mcp_token"
    f.write_text("  \n")
    monkeypatch.setattr(mcp_token, "TOKEN_FILE", f)
    assert len(mcp_token.get_or_create_mcp_token()) == 43


# ── self-client address ─────────────────────────────────────────────────────

@pytest.mark.parametrize("host,expected", [
    ("127.0.0.1", "127.0.0.1"),
    # LAN mode binds the wildcard — a BIND address, not a destination.
    ("0.0.0.0", "127.0.0.1"),
    ("::", "127.0.0.1"),
    # A concrete bind is NOT listening on loopback; dial it as-is.
    ("192.168.1.5", "192.168.1.5"),
])
def test_self_host_dials_a_reachable_address(monkeypatch, host, expected):
    monkeypatch.setattr(settings, "HOST", host)
    assert mcp_client.self_host() == expected


def test_self_client_origin_is_allowlisted(monkeypatch):
    """The loopback call must pass the CSRF check it goes through."""
    from backend.core.origins import origin_ok
    monkeypatch.setattr(settings, "HOST", "127.0.0.1")
    assert origin_ok(mcp_client._base_url())


def test_error_envelope_is_parseable_json():
    raw = mcp_client._build_error_envelope("POST", "/api/x", 404, "nope")
    env = json.loads(raw)
    assert env["error_code"] == "not_found"
    assert env["retryable"] is False
    assert env["status"] == 404
    raw = mcp_client._build_error_envelope("POST", "/api/x", 503, "")
    assert json.loads(raw)["retryable"] is True


# ── tool descriptions ───────────────────────────────────────────────────────

def test_description_keeps_returns_and_drops_args():
    doc = '''Do a thing.

        Longer body that matters.

        Args:
            x: the x.
            y: the y.

        Returns:
            {"ok": bool}
        '''
    out = _tool_description_from_docstring(doc)
    assert "Do a thing." in out
    assert "Longer body" in out
    assert "Returns:" in out and '{"ok": bool}' in out
    assert "the x." not in out


# ── the registered surface ──────────────────────────────────────────────────

@pytest.fixture(scope="module")
def registered_tools():
    import asyncio
    mcp = _build_mcp_app()
    return asyncio.run(mcp.list_tools())


def test_server_registers_tools(registered_tools):
    names = {t.name for t in registered_tools}
    for core in ("get_job_status", "wait_for_job", "list_jobs", "cancel_job"):
        assert core in names


def test_tool_names_are_unique(registered_tools):
    names = [t.name for t in registered_tools]
    assert len(names) == len(set(names))


def test_every_tool_documents_its_return_shape(registered_tools):
    """The description is what the model chains on — Returns: must survive."""
    missing = [t.name for t in registered_tools if "Returns:" not in (t.description or "")]
    assert not missing, f"tools whose description lost Returns: {missing}"


def test_no_hosted_only_vocabulary_reaches_the_model(registered_tools):
    """This build has no billing and no cloud. A description that talks about
    balance or credits sends the model after something that doesn't exist."""
    bad = re.compile(r"\b(balance|top[- ]?up|credits?|cents?|billed|billing|cloud_client|openrouter)\b", re.I)
    offenders = {t.name: bad.findall(t.description or "") for t in registered_tools}
    offenders = {k: v for k, v in offenders.items() if v}
    assert not offenders, offenders


def test_no_publishing_tool_is_exposed(registered_tools):
    """The uploader posts to the user's channels — never something an agent
    fires without a human clicking confirm in the UI."""
    names = {t.name for t in registered_tools}
    assert not any(re.search(r"upload|publish", n) for n in names), names


def test_mcp_package_has_no_billing_or_shell_strings():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "backend" / "mcp"
    pattern = re.compile(r"cloud_client|require_balance|\bbill\(|openrouter|shell=True|from backend\.mcp import pricing")
    hits = []
    for f in root.rglob("*.py"):
        for i, line in enumerate(f.read_text().splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{f.name}:{i}: {line.strip()}")
    assert not hits, hits


def test_every_tool_module_has_the_license_header():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "backend" / "mcp"
    missing = [str(f) for f in root.rglob("*.py")
               if "SPDX-License-Identifier: AGPL-3.0-only" not in f.read_text()[:200]]
    assert not missing, missing


# ── mount + auth over the real app ──────────────────────────────────────────

_INIT = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "pytest", "version": "0"},
    },
}
_MCP_HEADERS = {"Accept": "application/json, text/event-stream",
                "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def app_client():
    # A FRESH app: fastmcp's session manager runs once per instance, and any
    # earlier test that opened TestClient(backend.main.app) has already used
    # the shared one. Production starts the lifespan exactly once.
    from backend.main import create_app
    from backend.mcp.server import _reset_mcp_app_cache
    _reset_mcp_app_cache()
    app = create_app()
    # A real loopback peer: the token endpoints refuse anyone else.
    with TestClient(app, client=("127.0.0.1", 50000)) as c:
        yield c


def test_mcp_rejects_a_missing_token(app_client):
    r = app_client.post("/mcp/", json=_INIT, headers=_MCP_HEADERS)
    assert r.status_code == 401
    assert r.json()["error"] == "missing_token"


def test_mcp_rejects_a_wrong_token(app_client):
    r = app_client.post("/mcp/", json=_INIT,
                        headers={**_MCP_HEADERS, "Authorization": "Bearer nope"})
    assert r.status_code == 401
    assert r.json()["error"] == "invalid_token"


def _rpc_result(resp):
    """Streamable HTTP answers either plain JSON or an SSE stream."""
    if resp.headers.get("content-type", "").startswith("application/json"):
        return resp.json()
    for line in resp.text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    raise AssertionError(f"no JSON-RPC payload in {resp.text[:300]!r}")


def test_mcp_initializes_with_the_token(app_client):
    """The mount is reached (not the SPA catch-all), the session manager is
    running (the lifespan was entered), and auth passes."""
    token = mcp_token.get_or_create_mcp_token()
    r = app_client.post("/mcp/", json=_INIT,
                        headers={**_MCP_HEADERS, "Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text[:500]
    payload = _rpc_result(r)
    assert payload["result"]["serverInfo"]["name"] == "ViralMint"


def test_rotation_takes_effect_without_a_restart(app_client):
    old = mcp_token.get_or_create_mcp_token()
    new = app_client.post("/api/settings/mcp/rotate").json()["token"]
    assert new != old
    stale = app_client.post("/mcp/", json=_INIT,
                            headers={**_MCP_HEADERS, "Authorization": f"Bearer {old}"})
    assert stale.status_code == 401
    fresh = app_client.post("/mcp/", json=_INIT,
                            headers={**_MCP_HEADERS, "Authorization": f"Bearer {new}"})
    assert fresh.status_code == 200


# ── settings endpoints ──────────────────────────────────────────────────────

def test_settings_returns_token_and_client_snippets(app_client):
    data = app_client.get("/api/settings/mcp").json()
    token = mcp_token.get_or_create_mcp_token()
    assert data["token"] == token
    assert data["endpoint_url"].endswith(f":{settings.PORT}/mcp/")
    ids = {c["id"] for c in data["clients"]}
    assert {"claude_code", "claude_desktop", "codex", "cursor"} <= ids
    for c in data["clients"]:
        assert token in c["snippet"], c["id"]


def test_endpoint_url_never_names_the_wildcard_bind(monkeypatch):
    from backend.api.mcp_settings import mcp_endpoint_url
    monkeypatch.setattr(settings, "HOST", "0.0.0.0")
    assert "0.0.0.0" not in mcp_endpoint_url()


def test_tools_endpoint_lists_the_mounted_server(app_client, registered_tools):
    data = app_client.get("/api/settings/mcp/tools").json()
    assert data["available"] is True and data["ok"] is True
    assert {t["name"] for t in data["tools"]} == {t.name for t in registered_tools}
    assert all(t["summary"] for t in data["tools"])


def test_tools_are_grouped_by_the_module_that_registers_them(app_client, registered_tools):
    """Groups are derived, so a new tool can't land in "other" for want of a
    hand-kept map — and none does today."""
    from backend.api.mcp_settings import MCP_GROUP_ORDER
    data = app_client.get("/api/settings/mcp/tools").json()
    grouped = [t["name"] for g in data["groups"] for t in g["tools"]]
    assert sorted(grouped) == sorted(t.name for t in registered_tools)
    assert data["total"] == len(registered_tools)
    names = [g["name"] for g in data["groups"]]
    assert "other" not in names
    assert names == [g for g in MCP_GROUP_ORDER if g in names], "groups render in display order"
    by_name = {t["name"]: g["name"] for g in data["groups"] for t in g["tools"]}
    assert by_name["wait_for_job"] == "orchestration"
    assert all("parameters" in t for g in data["groups"] for t in g["tools"])


def test_prompts_and_resources_endpoints(app_client):
    prompts = app_client.get("/api/settings/mcp/prompts").json()
    assert prompts["ok"] and prompts["total"] == len(prompts["prompts"]) > 0
    assert all(p["name"].startswith("viralmint:") for p in prompts["prompts"])
    resources = app_client.get("/api/settings/mcp/resources").json()
    assert resources["ok"]
    templates = [r for r in resources["resources"] if r["is_template"]]
    assert any("{" in r["uri_template"] for r in templates), "templated resources are listed too"


def test_activity_logs_authenticated_requests_only(app_client):
    from backend.mcp import activity
    activity.clear()
    app_client.post("/mcp/", json=_INIT, headers=_MCP_HEADERS)          # 401, not logged
    token = mcp_token.get_or_create_mcp_token()
    r = app_client.post("/mcp/", json=_INIT,
                        headers={**_MCP_HEADERS, "Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    events = app_client.get("/api/settings/mcp/activity").json()["events"]
    assert [(e["method"], e["status_code"]) for e in events] == [("initialize", 200)]
    assert app_client.post("/api/settings/mcp/activity/clear").json()["cleared"]
    assert app_client.get("/api/settings/mcp/activity").json()["events"] == []


def test_activity_names_the_tool_of_a_call():
    import asyncio
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from backend.mcp import activity
    from backend.mcp.server import ActivityLogMiddleware

    inner = Starlette(routes=[Route("/", lambda r: PlainTextResponse("ok"), methods=["POST"])])
    inner.add_middleware(ActivityLogMiddleware)
    activity.clear()
    TestClient(inner).post("/", json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                      "params": {"name": "list_jobs", "arguments": {}}})
    (event,) = activity.snapshot()
    assert (event["method"], event["tool"], event["status_code"]) == ("tools/call", "list_jobs", 200)
    asyncio.run(asyncio.sleep(0))


# ── one-click install ───────────────────────────────────────────────────────

@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """The installer writes into the user's home; point it somewhere safe."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    return tmp_path


def test_install_merges_into_an_existing_json_config(app_client, fake_home):
    cfg = fake_home / ".cursor" / "mcp.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"mcpServers": {"other": {"url": "http://x"}}, "theme": "dark"}))
    r = app_client.post("/api/settings/mcp/install/cursor")
    assert r.status_code == 200, r.text
    data = json.loads(cfg.read_text())
    assert data["theme"] == "dark" and data["mcpServers"]["other"] == {"url": "http://x"}
    entry = data["mcpServers"]["viralmint"]
    assert entry["url"].endswith("/mcp/")
    assert entry["headers"]["Authorization"] == f"Bearer {mcp_token.get_or_create_mcp_token()}"
    assert (cfg.parent / "mcp.json.viralmint-bak").exists()
    # Idempotent: a second run leaves one entry, not two.
    app_client.post("/api/settings/mcp/install/cursor")
    assert list(json.loads(cfg.read_text())["mcpServers"]) == ["other", "viralmint"]


def test_install_refuses_a_config_it_cannot_parse(app_client, fake_home):
    cfg = fake_home / ".gemini" / "settings.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("{not json")
    r = app_client.post("/api/settings/mcp/install/gemini_cli")
    assert r.status_code == 409
    assert cfg.read_text() == "{not json", "a broken config is left for the user, never replaced"


def test_install_codex_keeps_the_rest_of_config_toml(app_client, fake_home):
    import tomllib
    cfg = fake_home / ".codex" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('# mine\nmodel = "o5"\n\n[mcp_servers."viralmint"]\nurl = "http://old"\n\n'
                   '[mcp_servers.viralmint.http_headers]\nAuthorization = "Bearer stale"\n\n'
                   '[mcp_servers.other]\nurl = "http://other"\n')
    r = app_client.post("/api/settings/mcp/install/codex")
    assert r.status_code == 200, r.text
    text = cfg.read_text()
    assert text.startswith("# mine\nmodel = \"o5\"")
    parsed = tomllib.loads(text)
    assert parsed["mcp_servers"]["other"] == {"url": "http://other"}
    vm = parsed["mcp_servers"]["viralmint"]
    assert vm["url"].endswith("/mcp/") and "stale" not in text


def test_install_claude_code_needs_the_cli(app_client, fake_home, monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert app_client.post("/api/settings/mcp/install/claude_code").status_code == 409


def test_install_rejects_an_unknown_client(app_client, fake_home):
    assert app_client.post("/api/settings/mcp/install/notepad").status_code == 400


def test_install_targets_lists_every_client(app_client, fake_home):
    (fake_home / ".cursor").mkdir()
    targets = {t["id"]: t for t in app_client.get("/api/settings/mcp/install/targets").json()["targets"]}
    assert {"claude_code", "claude_desktop", "codex", "cursor", "windsurf", "gemini_cli"} <= set(targets)
    assert targets["cursor"]["detected"] is True
    assert targets["windsurf"]["detected"] is False


def test_settings_endpoints_are_async():
    """Sync handlers run on the shared threadpool; these must not."""
    from backend.api import mcp_settings
    for name in ("get_mcp_config", "test_mcp_connection", "rotate_mcp_token", "list_mcp_tools",
                 "list_mcp_prompts", "list_mcp_resources", "get_mcp_activity",
                 "clear_mcp_activity", "mcp_install_targets", "mcp_install_client"):
        assert inspect.iscoroutinefunction(getattr(mcp_settings, name))


def test_unwrap_exception_group_finds_the_real_cause():
    import asyncio
    from backend.api.mcp_settings import _unwrap_exception_group
    real = ConnectionError("refused")
    eg = BaseExceptionGroup("tg", [asyncio.CancelledError(), ExceptionGroup("inner", [real])])
    assert _unwrap_exception_group(eg) is real


@pytest.mark.parametrize("peer", ["192.168.1.20", "10.0.0.7", "testclient"])
def test_token_endpoints_refuse_other_machines(peer):
    """LAN mode exposes the UI to the network; it must not expose the token,
    which unlocks tools that read files on this machine."""
    from backend.main import app
    c = TestClient(app, client=(peer, 50000))
    assert c.get("/api/settings/mcp").status_code == 403
    assert c.post("/api/settings/mcp/rotate").status_code == 403
    assert c.post("/api/settings/mcp/test").status_code == 403
    # The installer writes files on this machine — same rule as the token.
    assert c.get("/api/settings/mcp/install/targets").status_code == 403
    assert c.post("/api/settings/mcp/install/cursor").status_code == 403
    # The tool list carries no secret.
    assert c.get("/api/settings/mcp/tools").status_code == 200


def test_ipv6_loopback_is_the_same_machine():
    from backend.main import app
    c = TestClient(app, client=("::1", 50000))
    assert c.get("/api/settings/mcp").status_code == 200


@pytest.mark.parametrize("status,body", [
    # The SDK's 401 wrapped in the endpoint's generic 500 — measured live.
    (500, "{\"detail\":\"Script generation failed: Error code: 401 - "
          "{'type': 'error', 'error': {'type': 'authentication_error', "
          "'message': 'invalid x-api-key'}}\"}"),
    # AIKeyMissingError, which endpoints answer with a 400.
    (400, "{\"detail\":\"No AI provider configured. Set ANTHROPIC_API_KEY, ...\"}"),
])
def test_a_key_problem_is_not_reported_as_retryable(status, body):
    env = json.loads(mcp_client._build_error_envelope("POST", "/api/x", status, body))
    assert env["error_code"] == "ai_key_problem"
    assert env["retryable"] is False
    assert "AI Provider" in env["suggested_action"]


def test_an_ordinary_500_stays_retryable():
    env = json.loads(mcp_client._build_error_envelope("POST", "/api/x", 500, "boom"))
    assert env["error_code"] == "backend_error" and env["retryable"] is True
