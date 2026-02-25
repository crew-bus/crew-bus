# Crew Bus

**Open-source agent framework — local-first, private, sovereign.**

Crew Bus is an agent coordination framework that runs entirely on your machine. Agents communicate through a message bus, with built-in encryption, trust scoring, and a security Guardian that controls all external access.

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)](#)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](#)

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

## Contributing

Contributions welcome. Please run `pytest` before submitting PRs.

Conventional commits: `feat:`, `fix:`, `chore:`, `tweak:`, `ci:`.

---

## License

MIT — use it however you want.
