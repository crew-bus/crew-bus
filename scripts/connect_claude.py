#!/usr/bin/env python3
"""Helper script for connecting Crew Bus to Claude Desktop via MCP.

Called from the macOS SwiftUI app via subprocess.
All output is JSON to stdout. Logs go to stderr.

Subcommands:
  --status              Check server, Claude Desktop, and MCP status
  --connect --mcp-path  Write crew-bus entry into Claude Desktop config
  --disconnect          Remove crew-bus entry from Claude Desktop config
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

CONFIG_PATH = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"


def _python_path() -> str:
    """Return the best available python path (venv preferred)."""
    venv = Path.home() / "crew-bus" / ".venv" / "bin" / "python"
    if venv.exists():
        return str(venv)
    return "python3"


def _check_server() -> bool:
    """Return True if Crew Bus server is reachable on port 8420."""
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:8420/api/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _check_mcp_available() -> bool:
    """Return True if the mcp package is importable by the target python."""
    python = _python_path()
    try:
        result = subprocess.run(
            [python, "-c", "import mcp"],
            capture_output=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _read_config() -> dict:
    """Read existing Claude Desktop config or return empty dict."""
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _write_config(config: dict) -> None:
    """Write config JSON, creating parent dirs if needed."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")


def cmd_status() -> dict:
    server_ok = _check_server()
    claude_installed = CONFIG_PATH.exists()
    config = _read_config()
    servers = config.get("mcpServers", {})
    mcp_linked = "crew-bus" in servers
    mcp_available = _check_mcp_available()
    return {
        "server_ok": server_ok,
        "claude_installed": claude_installed,
        "mcp_linked": mcp_linked,
        "mcp_available": mcp_available,
    }


def cmd_connect(mcp_path: str) -> dict:
    if not mcp_path:
        return {"ok": False, "message": "--mcp-path is required"}

    mcp_script = Path(mcp_path)
    if not mcp_script.exists():
        return {"ok": False, "message": f"MCP script not found: {mcp_path}"}

    python = _python_path()
    config = _read_config()
    servers = config.get("mcpServers", {})
    servers["crew-bus"] = {
        "command": python,
        "args": [str(mcp_script)],
        "env": {"CREW_BUS_URL": "http://127.0.0.1:8420"},
    }
    config["mcpServers"] = servers

    try:
        _write_config(config)
    except OSError as e:
        return {"ok": False, "message": f"Failed to write config: {e}"}

    return {"ok": True, "message": "Connected. Restart Claude Desktop to activate."}


def cmd_disconnect() -> dict:
    config = _read_config()
    servers = config.get("mcpServers", {})
    if "crew-bus" not in servers:
        return {"ok": True, "message": "Already disconnected."}

    del servers["crew-bus"]
    config["mcpServers"] = servers

    try:
        _write_config(config)
    except OSError as e:
        return {"ok": False, "message": f"Failed to write config: {e}"}

    return {"ok": True, "message": "Disconnected. Restart Claude Desktop to apply."}


def main():
    parser = argparse.ArgumentParser(description="Crew Bus ↔ Claude Desktop connector")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--status", action="store_true", help="Check connection status")
    group.add_argument("--connect", action="store_true", help="Connect crew-bus to Claude Desktop")
    group.add_argument("--disconnect", action="store_true", help="Disconnect crew-bus from Claude Desktop")
    parser.add_argument("--mcp-path", help="Absolute path to crew_bus_mcp.py")

    args = parser.parse_args()

    if args.status:
        result = cmd_status()
    elif args.connect:
        result = cmd_connect(args.mcp_path)
    elif args.disconnect:
        result = cmd_disconnect()

    json.dump(result, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
