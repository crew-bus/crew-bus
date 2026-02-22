#!/usr/bin/env python3
"""Crew Bus MCP Server — exposes the local crew to Claude Desktop.

Runs as a stdio JSON-RPC server using the `mcp` (FastMCP) package.
Claude Desktop launches this as a child process and communicates via stdin/stdout.
All crew interaction goes through the Crew Bus REST API on localhost.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from mcp.server.fastmcp import FastMCP

CREW_BUS_URL = os.environ.get("CREW_BUS_URL", "http://127.0.0.1:8420")

mcp = FastMCP("crew-bus", instructions="Talk to your local Crew Bus agents")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    """Log to stderr (stdout is reserved for JSON-RPC)."""
    print(f"[crew-bus-mcp] {msg}", file=sys.stderr, flush=True)


def _api_get(path: str, params: dict | None = None):
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


def _api_post(path: str, body: dict | None = None):
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


def _find_agent(agents: list, name: str) -> dict | None:
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


def _resolve_agent(name: str) -> tuple[dict | None, str | None]:
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
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_agents() -> str:
    """List all crew members with their status, type, and role."""
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


@mcp.tool()
def send_message(agent_name: str, message: str) -> str:
    """Send a message to a crew member and get their reply.

    Use list_agents() first to see available agent names.
    """
    agent, err = _resolve_agent(agent_name)
    if err:
        return err
    result = _api_post(f"/api/agent/{agent['id']}/chat", {"text": message})
    if isinstance(result, dict) and "error" in result:
        return result["error"]
    reply = (result.get("reply") or result.get("response")
             or result.get("text") or json.dumps(result))
    return reply


@mcp.tool()
def get_agent_chat(agent_name: str, limit: int = 20) -> str:
    """Get recent chat history with a crew member."""
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
            sender = m.get("role", m.get("sender", "?"))
            text = m.get("content", m.get("text", ""))
            lines.append(f"[{sender}] {text}")
        return "\n".join(lines) if lines else "No chat history."
    return json.dumps(messages)


@mcp.tool()
def get_crew_stats() -> str:
    """Get a dashboard overview of the crew — agent counts, trust score, burnout, etc."""
    stats = _api_get("/api/stats")
    return json.dumps(stats, indent=2)


@mcp.tool()
def list_teams() -> str:
    """List all teams with their manager and member count."""
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


@mcp.tool()
def get_team_detail(team_name: str) -> str:
    """Get detailed info about a team including its agent list."""
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


@mcp.tool()
def get_message_feed(limit: int = 30) -> str:
    """Get the recent crew message feed — inter-agent messages, bus events, etc."""
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


@mcp.tool()
def search_agent_memory(agent_name: str, query: str = "") -> str:
    """Search a crew member's memory — experiences, facts, learned info.

    If query is provided, filters memories containing that text.
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


@mcp.tool()
def get_agent_learnings(agent_name: str) -> str:
    """Get what a crew member has learned — mistakes and what works well."""
    agent, err = _resolve_agent(agent_name)
    if err:
        return err
    result = _api_get(f"/api/agent/{agent['id']}/learnings")
    return json.dumps(result, indent=2)


@mcp.tool()
def get_audit_log(limit: int = 50) -> str:
    """Get recent crew audit events — actions, decisions, configuration changes."""
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


@mcp.tool()
def post_to_team_mailbox(
    from_agent_name: str, subject: str, body: str, severity: str = "info"
) -> str:
    """Post a message to a team mailbox on behalf of an agent.

    severity: info, warning, or code_red.
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
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _log("Starting Crew Bus MCP server...")
    mcp.run()
