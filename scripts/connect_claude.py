#!/usr/bin/env python3
"""Helper script for connecting Crew Bus to Claude Desktop via MCP.

Called from the macOS SwiftUI app via subprocess.
All output is JSON to stdout. Logs go to stderr.

Usage:
  python3 connect_claude.py status
  python3 connect_claude.py connect [--mcp-path /path/to/crew_bus_mcp.py]
  python3 connect_claude.py disconnect
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

CONFIG_PATH = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
CLAUDE_APP = Path("/Applications/Claude.app")

# Candidate python paths, checked in order
_PYTHON_CANDIDATES = [
    Path.home() / "crew-bus" / ".venv" / "bin" / "python",
    Path("/opt/homebrew/bin/python3"),
    Path("/usr/local/bin/python3"),
    Path("/usr/bin/python3"),
]

# Candidate MCP script locations, checked in order
_MCP_CANDIDATES = [
    Path("/Applications/CrewBus.app/Contents/Resources/crew_bus_mcp.py"),
    Path.home() / "crew-bus" / "crew_bus_mcp.py",
]


def _find_python() -> str:
    """Return the first available python3 path."""
    for p in _PYTHON_CANDIDATES:
        if p.exists():
            return str(p)
    # Fall back to bare name (relies on PATH)
    return "python3"


def _find_mcp_script() -> str:
    """Return the first available crew_bus_mcp.py path."""
    for p in _MCP_CANDIDATES:
        if p.exists():
            return str(p)
    return ""


def _check_server() -> bool:
    """Return True if Crew Bus server is reachable on port 8420."""
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:8420/api/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _check_claude_installed() -> bool:
    """Return True if Claude Desktop app and config dir exist."""
    config_dir = CONFIG_PATH.parent
    return CLAUDE_APP.exists() or config_dir.exists()


def _check_mcp_available() -> bool:
    """Return True if the mcp package is importable by the target python."""
    python = _find_python()
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


def _backup_config() -> None:
    """Create a backup of the config file before modifying it."""
    if CONFIG_PATH.exists():
        backup = CONFIG_PATH.with_suffix(".json.backup")
        shutil.copy2(CONFIG_PATH, backup)


def _write_config(config: dict) -> None:
    """Write config JSON, creating parent dirs if needed."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")


def cmd_status() -> dict:
    server_ok = _check_server()
    claude_installed = _check_claude_installed()
    config = _read_config()
    servers = config.get("mcpServers", {})
    already_connected = "crew-bus" in servers
    mcp_available = _check_mcp_available()
    python_path = _find_python()
    mcp_script_path = _find_mcp_script()
    return {
        "claude_installed": claude_installed,
        "already_connected": already_connected,
        "crewbus_running": server_ok,
        "mcp_available": mcp_available,
        "python3_path": python_path,
        "mcp_script_path": mcp_script_path,
        "config_path": str(CONFIG_PATH),
    }


def cmd_connect(mcp_path: str) -> dict:
    # Auto-detect MCP script if not provided
    if not mcp_path:
        mcp_path = _find_mcp_script()
    if not mcp_path:
        return {"success": False, "message": "Could not find crew_bus_mcp.py.", "needs_restart": False, "error": "mcp_script_missing"}

    mcp_script = Path(mcp_path)
    if not mcp_script.exists():
        return {"success": False, "message": "Could not find the connection script.", "needs_restart": False, "error": f"not_found:{mcp_path}"}

    if not _check_claude_installed():
        return {"success": False, "message": "Claude Desktop doesn't appear to be installed.", "needs_restart": False, "error": "claude_not_installed"}

    python = _find_python()
    config = _read_config()

    # Back up before modifying
    _backup_config()

    servers = config.get("mcpServers", {})
    was_connected = "crew-bus" in servers
    servers["crew-bus"] = {
        "command": python,
        "args": [str(mcp_script)],
        "env": {"CREW_BUS_URL": "http://127.0.0.1:8420"},
    }
    config["mcpServers"] = servers

    try:
        _write_config(config)
    except OSError as e:
        return {"success": False, "message": "Couldn't save the connection settings.", "needs_restart": False, "error": str(e)}

    return {
        "success": True,
        "message": "Connected! Restart Claude Desktop to start chatting with your crew.",
        "needs_restart": True,
        "error": None,
    }


def cmd_disconnect() -> dict:
    config = _read_config()
    servers = config.get("mcpServers", {})
    if "crew-bus" not in servers:
        return {"success": True, "message": "Already disconnected.", "needs_restart": False, "error": None}

    # Back up before modifying
    _backup_config()

    del servers["crew-bus"]
    config["mcpServers"] = servers

    try:
        _write_config(config)
    except OSError as e:
        return {"success": False, "message": "Couldn't update the connection settings.", "needs_restart": False, "error": str(e)}

    return {"success": True, "message": "Disconnected. Restart Claude Desktop to apply.", "needs_restart": True, "error": None}


def main():
    parser = argparse.ArgumentParser(description="Crew Bus ↔ Claude Desktop connector")
    parser.add_argument("action", choices=["status", "connect", "disconnect"],
                        help="Action to perform")
    parser.add_argument("--mcp-path", default="",
                        help="Absolute path to crew_bus_mcp.py (auto-detected if omitted)")

    args = parser.parse_args()

    if args.action == "status":
        result = cmd_status()
    elif args.action == "connect":
        result = cmd_connect(args.mcp_path)
    elif args.action == "disconnect":
        result = cmd_disconnect()

    json.dump(result, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
