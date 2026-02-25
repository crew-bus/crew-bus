#!/usr/bin/env python3
"""Crew Bus MCP Server — exposes the local crew to Claude Desktop & HTTP clients.

Supports two transports:
  stdio  — Claude Desktop launches this as a child process (default)
  http   — Streamable HTTP on port 8421 for Claude Code, Cowork, LAN clients

All crew interaction goes through the Crew Bus REST API on localhost:8420.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional, Tuple, Union

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

CREW_BUS_URL = os.environ.get("CREW_BUS_URL", "http://127.0.0.1:8420")

_start_time = time.time()

mcp = FastMCP("crew-bus", instructions="Talk to your local Crew Bus agents")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    """Log to stderr (stdout is reserved for JSON-RPC)."""
    print(f"[crew-bus-mcp] {msg}", file=sys.stderr, flush=True)


def _api_get(path: str, params: Optional[dict] = None):
    """GET request to the Crew Bus API. Returns parsed JSON or error dict."""
    url = CREW_BUS_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("X-Requested-With", "crewbus-mcp")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        return {"error": f"Crew Bus server unreachable at {CREW_BUS_URL}: {e}"}
    except Exception as e:
        return {"error": str(e)}


def _api_post(path: str, body: Optional[dict] = None):
    """POST request to the Crew Bus API. Returns parsed JSON or error dict."""
    url = CREW_BUS_URL + path
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Requested-With", "crewbus-mcp")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        return {"error": f"Crew Bus server unreachable at {CREW_BUS_URL}: {e}"}
    except Exception as e:
        return {"error": str(e)}


def _find_agent(agents: list, name: str) -> Optional[dict]:
    """Resolve agent by name or display_name, case-insensitive. Tries exact then partial."""
    lower = name.lower()
    # Exact match
    for a in agents:
        if a.get("name", "").lower() == lower:
            return a
        if a.get("display_name", "").lower() == lower:
            return a
    # Partial match
    for a in agents:
        if lower in a.get("name", "").lower():
            return a
        if lower in a.get("display_name", "").lower():
            return a
    return None


def _resolve_agent(name: str) -> Tuple[Optional[dict], Optional[str]]:
    """Fetch agents list and resolve by name. Returns (agent, error)."""
    agents = _api_get("/api/agents")
    if isinstance(agents, dict) and "error" in agents:
        return None, agents["error"]
    agent = _find_agent(agents, name)
    if not agent:
        names = [a.get("display_name") or a.get("name") for a in agents]
        return None, f"Agent '{name}' not found. Available: {', '.join(names)}"
    return agent, None


# ---------------------------------------------------------------------------
# Security middleware (HTTP transport only)
# ---------------------------------------------------------------------------

class _AuthOriginMiddleware:
    """ASGI middleware for Bearer token auth and Origin header validation."""

    def __init__(self, app, token=None, public_mode=False):
        self.app = app
        self.token = token
        self.public_mode = public_mode

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))

        # Token authentication
        if self.token:
            auth = headers.get(b"authorization", b"").decode()
            if auth != f"Bearer {self.token}":
                from starlette.responses import JSONResponse
                resp = JSONResponse({"error": "Unauthorized"}, status_code=401)
                await resp(scope, receive, send)
                return

        # Origin validation (localhost-only unless --public)
        origin = headers.get(b"origin", b"").decode()
        if origin:
            if self.public_mode:
                _log(f"WARNING: Accepting request from origin {origin} (public mode)")
            else:
                from urllib.parse import urlparse
                parsed = urlparse(origin)
                if parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
                    from starlette.responses import JSONResponse
                    resp = JSONResponse(
                        {"error": "Forbidden: invalid origin"}, status_code=403
                    )
                    await resp(scope, receive, send)
                    return

        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# Health endpoint (HTTP transport only)
# ---------------------------------------------------------------------------

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    from starlette.responses import JSONResponse
    agents = _api_get("/api/agents")
    count = len(agents) if isinstance(agents, list) else 0
    return JSONResponse({
        "status": "ok",
        "server": "crew-bus-mcp",
        "version": "1.0.0",
        "agents_online": count,
        "uptime_seconds": int(time.time() - _start_time),
    })


# ---------------------------------------------------------------------------
# MCP Tools — all prefixed with crewbus_
# ---------------------------------------------------------------------------

_RO = ToolAnnotations(readOnlyHint=True)
_RW = ToolAnnotations(readOnlyHint=False)


@mcp.tool(annotations=_RO)
def crewbus_list_agents() -> str:
    """List all crew members with their status, type, and role.

    Returns:
        Formatted list of agents with emoji, name, role, and status.

    Examples:
        crewbus_list_agents() → "🤖 Crew Boss — coordinator (online)"
    """
    agents = _api_get("/api/agents")
    if isinstance(agents, dict) and "error" in agents:
        return json.dumps(agents)
    lines = []
    for a in agents:
        name = a.get("display_name") or a.get("name")
        status = a.get("status", "unknown")
        role = a.get("agent_type", "")
        emoji = a.get("avatar_emoji", "")
        lines.append(f"{emoji} {name} — {role} ({status})")
    return "\n".join(lines) if lines else "No agents found."


@mcp.tool(annotations=_RW)
def crewbus_send_message(agent_name: str, message: str) -> str:
    """Send a message to a crew member and get their reply.

    Args:
        agent_name: Name or display name of the agent (case-insensitive, partial match OK).
        message: The message text to send.

    Returns:
        The agent's reply text.

    Examples:
        crewbus_send_message("Crew Boss", "What's on my schedule today?")
    """
    agent, err = _resolve_agent(agent_name)
    if err:
        return err

    # Synchronous endpoint: sends message and waits for the reply in a single
    # HTTP request (server polls its own DB internally, no HTTP polling overhead).
    url = CREW_BUS_URL + f"/api/agent/{agent['id']}/chat/sync"
    body = json.dumps({"text": message, "timeout": 180}).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Requested-With", "crewbus-mcp")
    try:
        # 185s HTTP timeout > 180s server-side poll, so server always responds first
        with urllib.request.urlopen(req, timeout=185) as resp:
            result = json.loads(resp.read())
    except urllib.error.URLError as e:
        return f"Crew Bus server unreachable at {CREW_BUS_URL}: {e}"
    except Exception as e:
        return f"Error contacting Crew Bus: {e}"

    if isinstance(result, dict) and "error" in result:
        return result["error"]

    reply = result.get("reply")
    if reply:
        return reply

    return "Message sent but no reply yet. The agent may still be thinking."


@mcp.tool(annotations=_RO)
def crewbus_get_agent_chat(agent_name: str, limit: int = 20) -> str:
    """Get recent chat history with a crew member.

    Args:
        agent_name: Name or display name of the agent.
        limit: Maximum number of messages to return (default 20).

    Returns:
        Formatted chat transcript with [role] prefix per line.

    Examples:
        crewbus_get_agent_chat("Crew Boss", limit=5)
    """
    agent, err = _resolve_agent(agent_name)
    if err:
        return err
    messages = _api_get(f"/api/agent/{agent['id']}/chat")
    if isinstance(messages, dict) and "error" in messages:
        return json.dumps(messages)
    if isinstance(messages, list):
        messages = messages[-limit:]
        lines = []
        for m in messages:
            direction = m.get("direction", "")
            sender = "You" if direction == "from_human" else m.get("role", m.get("sender", agent_name))
            text = m.get("text", m.get("content", ""))
            lines.append(f"[{sender}] {text}")
        return "\n".join(lines) if lines else "No chat history."
    return json.dumps(messages)


@mcp.tool(annotations=_RO)
def crewbus_get_crew_stats() -> str:
    """Get a dashboard overview of the crew — agent counts, trust score, energy, etc.

    Returns:
        JSON object with crew statistics (agent counts, trust scores, energy levels).

    Examples:
        crewbus_get_crew_stats() → '{"total_agents": 3, "online": 2, ...}'
    """
    stats = _api_get("/api/stats")
    return json.dumps(stats, indent=2)


@mcp.tool(annotations=_RO)
def crewbus_list_teams() -> str:
    """List all teams with their manager and member count.

    Returns:
        Formatted list of teams with name, manager, and member count.

    Examples:
        crewbus_list_teams() → "Team: Engineering — Manager: Crew Boss, Members: 3"
    """
    teams = _api_get("/api/teams")
    if isinstance(teams, dict) and "error" in teams:
        return json.dumps(teams)
    lines = []
    for t in teams:
        name = t.get("name", "?")
        manager = t.get("manager_name", "?")
        count = t.get("agent_count", t.get("member_count", "?"))
        lines.append(f"Team: {name} — Manager: {manager}, Members: {count}")
    return "\n".join(lines) if lines else "No teams found."


@mcp.tool(annotations=_RO)
def crewbus_get_team_detail(team_name: str) -> str:
    """Get detailed info about a team including its agent list.

    Args:
        team_name: Name of the team (case-insensitive, partial match OK).

    Returns:
        JSON object with team metadata and list of member agents.

    Examples:
        crewbus_get_team_detail("Engineering")
    """
    teams = _api_get("/api/teams")
    if isinstance(teams, dict) and "error" in teams:
        return json.dumps(teams)
    team = None
    name_lower = team_name.lower()
    for t in teams:
        if t.get("name", "").lower() == name_lower:
            team = t
            break
    if not team:
        for t in teams:
            if name_lower in t.get("name", "").lower():
                team = t
                break
    if not team:
        names = [t.get("name") for t in teams]
        return f"Team '{team_name}' not found. Available: {', '.join(names)}"
    agents = _api_get(f"/api/teams/{team['id']}/agents")
    return json.dumps({"team": team, "agents": agents}, indent=2)


@mcp.tool(annotations=_RO)
def crewbus_get_message_feed(limit: int = 30) -> str:
    """Get the recent crew message feed — inter-agent messages, bus events, etc.

    Args:
        limit: Maximum number of messages to return (default 30).

    Returns:
        Formatted feed with timestamps, sender names, and message text.

    Examples:
        crewbus_get_message_feed(limit=10)
    """
    messages = _api_get("/api/messages", {"limit": str(limit)})
    if isinstance(messages, dict) and "error" in messages:
        return json.dumps(messages)
    if isinstance(messages, list):
        lines = []
        for m in messages:
            sender = m.get("from_agent", m.get("sender", "?"))
            text = m.get("content", m.get("text", ""))[:200]
            ts = m.get("created_at", m.get("timestamp", ""))
            lines.append(f"[{ts}] {sender}: {text}")
        return "\n".join(lines) if lines else "No messages."
    return json.dumps(messages, indent=2)


@mcp.tool(annotations=_RO)
def crewbus_search_agent_memory(agent_name: str, query: str = "") -> str:
    """Search a crew member's memory — experiences, facts, learned info.

    Args:
        agent_name: Name or display name of the agent.
        query: Optional text filter — only returns memories containing this string.

    Returns:
        Formatted list of memories with type, importance, and content.

    Examples:
        crewbus_search_agent_memory("Vault", query="password policy")
    """
    agent, err = _resolve_agent(agent_name)
    if err:
        return err
    memories = _api_get(f"/api/agent/{agent['id']}/memories")
    if isinstance(memories, dict) and "error" in memories:
        return json.dumps(memories)
    if query and isinstance(memories, list):
        q = query.lower()
        memories = [m for m in memories if q in json.dumps(m).lower()]
    if isinstance(memories, list):
        lines = []
        for m in memories:
            content = m.get("content", m.get("text", ""))
            mtype = m.get("memory_type", "")
            importance = m.get("importance", "")
            lines.append(f"[{mtype}] (importance: {importance}) {content}")
        return "\n".join(lines) if lines else "No memories found."
    return json.dumps(memories, indent=2)


@mcp.tool(annotations=_RO)
def crewbus_get_agent_learnings(agent_name: str) -> str:
    """Get what a crew member has learned — mistakes and what works well.

    Args:
        agent_name: Name or display name of the agent.

    Returns:
        JSON object with the agent's learned patterns and mistakes.

    Examples:
        crewbus_get_agent_learnings("Guardian")
    """
    agent, err = _resolve_agent(agent_name)
    if err:
        return err
    result = _api_get(f"/api/agent/{agent['id']}/learnings")
    return json.dumps(result, indent=2)


@mcp.tool(annotations=_RO)
def crewbus_get_audit_log(limit: int = 50) -> str:
    """Get recent crew audit events — actions, decisions, configuration changes.

    Args:
        limit: Maximum number of audit entries to return (default 50).

    Returns:
        Formatted log with timestamps, agent names, actions, and details.

    Examples:
        crewbus_get_audit_log(limit=10)
    """
    entries = _api_get("/api/audit", {"limit": str(limit)})
    if isinstance(entries, dict) and "error" in entries:
        return json.dumps(entries)
    if isinstance(entries, list):
        lines = []
        for e in entries:
            ts = e.get("timestamp", e.get("created_at", ""))
            action = e.get("action", e.get("event_type", "?"))
            agent = e.get("agent_name", "?")
            detail = e.get("detail", e.get("details", ""))[:150]
            lines.append(f"[{ts}] {agent}: {action} — {detail}")
        return "\n".join(lines) if lines else "No audit entries."
    return json.dumps(entries, indent=2)


@mcp.tool(annotations=_RW)
def crewbus_post_to_team_mailbox(
    from_agent_name: str, subject: str, body: str, severity: str = "info"
) -> str:
    """Post a message to a team mailbox on behalf of an agent.

    Args:
        from_agent_name: Name of the sending agent.
        subject: Message subject line.
        body: Message body text.
        severity: Priority level — "info", "warning", or "code_red" (default "info").

    Returns:
        JSON confirmation with message ID and delivery status.

    Examples:
        crewbus_post_to_team_mailbox("Guardian", "Security Alert", "Unusual login detected", severity="warning")
    """
    agent, err = _resolve_agent(from_agent_name)
    if err:
        return err
    result = _api_post("/api/mailbox", {
        "from_agent_id": agent["id"],
        "subject": subject,
        "body": body,
        "severity": severity,
    })
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Entry point — dual transport: stdio (default) or streamable-http
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Crew Bus MCP Server — stdio or HTTP transport"
    )
    parser.add_argument(
        "--transport", choices=["stdio", "http"], default="stdio",
        help="Transport mode (default: stdio)"
    )
    parser.add_argument(
        "--port", type=int, default=8421,
        help="HTTP port (default: 8421)"
    )
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="HTTP bind address (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--public", action="store_true",
        help="Bind to 0.0.0.0 (accessible from LAN)"
    )
    parser.add_argument(
        "--token", default=None,
        help="Bearer token for HTTP auth — all HTTP requests must include Authorization: Bearer <token>"
    )
    return parser


def main():
    """Entry point for CLI (crew-bus-mcp) and direct execution."""
    args = _build_parser().parse_args()

    if args.transport == "stdio":
        _log("Starting Crew Bus MCP server (stdio)...")
        mcp.run()
    else:
        host = "0.0.0.0" if args.public else args.host
        if args.public:
            _log("WARNING: Binding to 0.0.0.0 — accessible from LAN")
        mcp.settings.host = host
        mcp.settings.port = args.port
        if host == "0.0.0.0":
            mcp.settings.transport_security.allowed_hosts.append(f"0.0.0.0:{args.port}")
        _log(f"Starting Crew Bus MCP server (HTTP) on {host}:{args.port}")
        _log(f"  MCP endpoint: http://{host}:{args.port}/mcp")
        _log(f"  Health check: http://{host}:{args.port}/health")
        if args.token:
            _log("  Token auth: enabled")

        import uvicorn
        inner_app = mcp.streamable_http_app()
        app = _AuthOriginMiddleware(
            inner_app, token=args.token, public_mode=args.public
        )
        uvicorn.run(app, host=host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
