"""Tests for scripts/connect_claude.py — Claude Desktop MCP connector."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import pytest

SCRIPT = str(Path(__file__).parent / "scripts" / "connect_claude.py")


def run_script(*args: str, env_override: Optional[dict] = None) -> dict:
    """Run connect_claude.py with args and return parsed JSON output."""
    env = os.environ.copy()
    if env_override:
        env.update(env_override)
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True, timeout=30, env=env,
    )
    assert result.returncode == 0, f"Script failed: {result.stderr}"
    return json.loads(result.stdout)


def test_status_json_output():
    """--status returns valid JSON with expected keys."""
    data = run_script("--status")
    assert "server_ok" in data
    assert "claude_installed" in data
    assert "mcp_linked" in data
    assert "mcp_available" in data
    assert isinstance(data["server_ok"], bool)
    assert isinstance(data["claude_installed"], bool)
    assert isinstance(data["mcp_linked"], bool)
    assert isinstance(data["mcp_available"], bool)


def test_connect_requires_mcp_path():
    """--connect without --mcp-path returns error JSON."""
    data = run_script("--connect")
    assert data["ok"] is False
    assert "mcp-path" in data["message"].lower() or "required" in data["message"].lower()


def test_connect_disconnect_roundtrip(tmp_path):
    """Connect then disconnect with a temp config directory."""
    config_file = tmp_path / "Claude" / "claude_desktop_config.json"

    # Create a dummy mcp script
    mcp_script = tmp_path / "crew_bus_mcp.py"
    mcp_script.write_text("# dummy")

    # Monkey-patch CONFIG_PATH inside the script via a wrapper
    wrapper = tmp_path / "wrapper.py"
    wrapper.write_text(f"""
import sys
sys.path.insert(0, "{Path(SCRIPT).parent}")
import connect_claude
from pathlib import Path
connect_claude.CONFIG_PATH = Path("{config_file}")
connect_claude.main()
""")

    def run_wrapper(*args):
        result = subprocess.run(
            [sys.executable, str(wrapper), *args],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"Wrapper failed: {result.stderr}"
        return json.loads(result.stdout)

    # Connect
    data = run_wrapper("--connect", "--mcp-path", str(mcp_script))
    assert data["ok"] is True
    assert config_file.exists()

    # Verify config contains crew-bus
    config = json.loads(config_file.read_text())
    assert "crew-bus" in config.get("mcpServers", {})

    # Disconnect
    data = run_wrapper("--disconnect")
    assert data["ok"] is True

    # Verify crew-bus removed
    config = json.loads(config_file.read_text())
    assert "crew-bus" not in config.get("mcpServers", {})


def test_connect_nonexistent_mcp_path():
    """--connect with a bad --mcp-path returns error."""
    data = run_script("--connect", "--mcp-path", "/nonexistent/crew_bus_mcp.py")
    assert data["ok"] is False
    assert "not found" in data["message"].lower()


def test_disconnect_when_not_connected(tmp_path):
    """--disconnect when not connected returns ok."""
    config_file = tmp_path / "Claude" / "claude_desktop_config.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text('{"mcpServers": {}}')

    wrapper = tmp_path / "wrapper.py"
    wrapper.write_text(f"""
import sys
sys.path.insert(0, "{Path(SCRIPT).parent}")
import connect_claude
from pathlib import Path
connect_claude.CONFIG_PATH = Path("{config_file}")
connect_claude.main()
""")

    result = subprocess.run(
        [sys.executable, str(wrapper), "--disconnect"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert "already" in data["message"].lower()
