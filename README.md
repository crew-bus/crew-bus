# Crew Bus

**Open-source agent framework — local-first, private, sovereign.**

Crew Bus is an agent coordination framework that runs entirely on your machine. Agents communicate through a message bus, with built-in encryption, trust scoring, and a security Guardian that controls all external access.

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)](#)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](#)

---

## What It Does

- **Message bus** — agents communicate through a structured SQLite-backed bus, not direct calls
- **Agent worker engine** — manages agent lifecycle, thinking levels, and task execution
- **Built-in security** — encryption, trust scoring, private sessions, and a Guardian agent that vets all external access
- **Skill system** — install, sandbox, and monitor agent skills with health scoring and auto-quarantine
- **Bridges** — connect agents to Discord, Twitter, Reddit, and the web
- **MCP server** — integrate with Claude Desktop via the Model Context Protocol
- **CLI** — full command-line interface for managing agents, messages, and crews

---

## Install

### MCPB Bundle (Claude Desktop)

Download the latest `.mcpb` bundle from [Releases](https://github.com/crew-bus/crew-bus/releases) and double-click to install in Claude Desktop.

### pip (Claude Code, VS Code, any MCP client)

```bash
pip install crew-bus-mcp
```

Then add to your MCP client config:

```json
{
  "mcpServers": {
    "crew-bus": {
      "command": "crew-bus-mcp",
      "env": {
        "CREW_BUS_URL": "http://127.0.0.1:8420"
      }
    }
  }
}
```

### Mac App (required)

CrewBus must be running on your Mac for any of the above to work.
Download: [crew-bus.dev](https://crew-bus.dev)

---

## Usage Examples

### Example 1 — Ask Crew Boss to plan your day

**User prompt to Claude:**
"Ask Crew Boss what I should focus on today"

**MCP tools called:**
1. `crewbus_send_message(agent_name="Crew Boss", message="What should I focus on today?")`

**Response from Crew Bus:**
Crew Boss reviews the user's active tasks, team status, and any flagged items from other agents, then returns a prioritized plan:

> "Good morning! Here's what I'd focus on today:
> 1. The website redesign mockups are due — Vault has the latest assets saved
> 2. Guardian flagged a new MCP skill request that needs your approval
> 3. Your Freelance team has 2 pending client responses
>
> Want me to delegate any of these to a specific agent?"

---

### Example 2 — Review Guardian's security flags

**User prompt to Claude:**
"What has Guardian flagged recently?"

**MCP tools called:**
1. `crewbus_get_agent_chat(agent_name="Guardian", limit=10)`
2. `crewbus_search_agent_memory(agent_name="Guardian", query="flagged")`

**Response from Crew Bus:**
Guardian returns recent security events and skill approval requests:

> "Guardian has flagged 2 items:
> 1. A new MCP skill 'weather-lookup' was requested — pending your approval (marked safe, read-only)
> 2. An agent tried to write outside its allowed directory — blocked automatically
>
> No active threats. All agent permissions are within normal bounds."

---

### Example 3 — Get a crew status overview

**User prompt to Claude:**
"Show me my crew stats and which agents are online"

**MCP tools called:**
1. `crewbus_get_crew_stats()`
2. `crewbus_list_agents()`

**Response from Crew Bus:**
Returns a dashboard overview of all agents and teams:

> "Your crew status:
> - 4 agents total: Crew Boss (online), Guardian (online), Vault (online), Scout (offline)
> - 2 teams: Household (3 members), Passion Project (2 members)
> - Trust score: 98/100
> - Energy: 85%
>
> Crew Boss and Guardian have been active today. Scout went offline 2 hours ago — want me to check why?"

---

## Quick Start

```bash
git clone https://github.com/crew-bus/crew-bus.git
cd crew-bus
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Run the CLI

```bash
python3 cli.py --help
python3 cli.py create-human "Alice"
python3 cli.py send Alice "Hello from the bus!"
```

### Connect to Claude Desktop

```bash
python3 crew_bus_mcp.py
```

This starts the MCP server so Claude Desktop can talk to your crew.

### Connect from Any MCP Client (HTTP)

Start the MCP server in HTTP mode for Claude Code, Cowork, or any MCP-compatible client:

```bash
python3 crew_bus_mcp.py --transport http --port 8421
```

Then point your MCP client to: `http://127.0.0.1:8421/mcp`

Health check: `GET http://127.0.0.1:8421/health`

**With token authentication:**

```bash
python3 crew_bus_mcp.py --transport http --port 8421 --token YOUR_SECRET
```

Clients must include `Authorization: Bearer YOUR_SECRET` in all requests.

**LAN mode (accessible from other devices):**

```bash
python3 crew_bus_mcp.py --transport http --public --token YOUR_SECRET
```

> Always use `--token` when exposing to the network.

---

## Architecture

```
+-------------------------------------------+
|           Agent Worker Engine              |
|  +-------------------------------------+  |
|  |  Crew Boss  |  Guardian  |   Vault  |  |
|  +-------------------------------------+  |
+-------------------------------------------+
|  Guardian Layer                           |
|  +----------+-----------+-----------+     |
|  |Web Bridge| Skill Store|  Sandbox |     |
|  +----------+-----------+-----------+     |
+-------------------------------------------+
|        Message Bus (SQLite)               |
+-------------------------------------------+
```

**Boss talks, Guard protects, Vault remembers.**

- **Crew Boss** — your AI right-hand, coordinates everything
- **Guardian** — security gatekeeper, vets skills, controls web access
- **Vault** — private journal and memory agent

---

## Key Files

| File | Purpose |
|------|---------|
| `bus.py` | Message bus + SQLite schema |
| `agent_worker.py` | AI agent execution engine |
| `agent_bridge.py` | Agent routing & message filtering |
| `security.py` | Encryption & trust model |
| `delivery.py` | Message delivery abstraction |
| `cli.py` | Command-line interface |
| `crew_bus_mcp.py` | MCP server for Claude integration |
| `skill_sandbox.py` | Skill execution sandbox |
| `skill_store.py` | Skill library & vetting |
| `*_bridge.py` | Platform bridges (Discord, Twitter, Reddit, web) |

---

## Bridges

Connect your crew to external platforms:

- **Discord** — `discord_bridge.py`
- **Twitter** — `twitter_bridge.py`
- **Reddit** — `reddit_bridge.py`
- **Web** — `web_bridge.py`, `website_bridge.py`

---

## Mac App

Want a native macOS experience? **[Download Crew Bus for Mac](https://crew-bus.dev/install)** — a SwiftUI app that wraps this framework with a beautiful desktop UI.

---

## Tests

```bash
pytest
```

---

## Privacy Policy

Crew Bus is privacy-first. All AI agent processing runs locally on your Mac.

**Data Collection:**
- **Email address** — collected for authentication via magic links. Used solely for login. Not shared with third parties.
- No analytics, no tracking, no telemetry.

**Data Processing:**
- All agent conversations, memory, and files stay on your Mac in `~/.crewbus/`
- The Cloudflare Workers relay at `relay.crew-bus.dev` is pass-through only — it forwards encrypted WebSocket messages between your iPhone and Mac. No message content is stored or logged.
- Email delivery uses Resend (transactional only, magic link codes).

**Third-Party Services:**
- Cloudflare Workers (relay infrastructure)
- Resend (email delivery for magic links)
- No data is sold, shared, or used for advertising.

**Data Retention:**
- Agent data persists locally until you delete it
- Relay messages are ephemeral (not stored)
- Email records retained only as needed for authentication

Full privacy policy: https://crew-bus.dev/privacy

---

## Contributing

Contributions welcome. Please run `pytest` before submitting PRs.

Conventional commits: `feat:`, `fix:`, `chore:`, `tweak:`, `ci:`.

---

## License

MIT — use it however you want.
