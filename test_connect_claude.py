"""Tests for scripts/connect_claude.py — Claude Desktop MCP connector."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import pytest

SCRIPT = str(Path(__file__).parent / "scripts" / "connect_claude.py")


def _make_wrapper(tmp_path, config_file):
    """Create a wrapper script that patches CONFIG_PATH and CLAUDE_APP."""
    wrapper = tmp_path / "wrapper.py"
    # Point CLAUDE_APP at a real dir so _check_claude_installed() returns True
    wrapper.write_text(f"""
import sys
sys.path.insert(0, "{Path(SCRIPT).parent}")
import connect_claude
from pathlib import Path
connect_claude.CONFIG_PATH = Path("{config_file}")
connect_claude.CLAUDE_APP = Path("{tmp_path}")
connect_claude.main()
""")
    return wrapper


def _run_wrapper(wrapper, *args):
    result = subprocess.run(
        [sys.executable, str(wrapper), *args],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"Wrapper failed: {result.stderr}"
    return json.loads(result.stdout)


def run_script(*args, env_override=None):
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


# ── Status ──

def test_status_json_output():
    """status returns valid JSON with expected keys."""
    data = run_script("status")
    for key in ("claude_installed", "already_connected", "crewbus_running",
                "mcp_available", "python3_path", "mcp_script_path", "config_path"):
        assert key in data, f"Missing key: {key}"
    assert isinstance(data["claude_installed"], bool)
    assert isinstance(data["already_connected"], bool)
    assert isinstance(data["crewbus_running"], bool)
    assert isinstance(data["mcp_available"], bool)
    assert isinstance(data["python3_path"], str)
    assert isinstance(data["config_path"], str)


# ── Connect ──

def test_connect_auto_detects_mcp_path(tmp_path):
    """connect without --mcp-path auto-detects the script."""
    config_file = tmp_path / "Claude" / "claude_desktop_config.json"
    wrapper = _make_wrapper(tmp_path, config_file)

    # If auto-detection finds a real crew_bus_mcp.py, it connects.
    # If not, it returns a friendly error — either way, valid JSON.
    data = _run_wrapper(wrapper, "connect")
    assert "success" in data
    assert isinstance(data["success"], bool)


def test_connect_with_mcp_path(tmp_path):
    """connect with --mcp-path writes config correctly."""
    config_file = tmp_path / "Claude" / "claude_desktop_config.json"
    mcp_script = tmp_path / "crew_bus_mcp.py"
    mcp_script.write_text("# dummy")
    wrapper = _make_wrapper(tmp_path, config_file)

    data = _run_wrapper(wrapper, "connect", "--mcp-path", str(mcp_script))
    assert data["success"] is True
    assert data["needs_restart"] is True
    assert config_file.exists()

    config = json.loads(config_file.read_text())
    assert "crew-bus" in config["mcpServers"]


def test_connect_nonexistent_mcp_path():
    """connect with a bad --mcp-path returns friendly error."""
    data = run_script("connect", "--mcp-path", "/nonexistent/crew_bus_mcp.py")
    assert data["success"] is False
    assert data["error"] is not None


def test_connect_idempotent(tmp_path):
    """Running connect twice is safe — second call overwrites cleanly."""
    config_file = tmp_path / "Claude" / "claude_desktop_config.json"
    mcp_script = tmp_path / "crew_bus_mcp.py"
    mcp_script.write_text("# dummy")
    wrapper = _make_wrapper(tmp_path, config_file)

    data1 = _run_wrapper(wrapper, "connect", "--mcp-path", str(mcp_script))
    assert data1["success"] is True

    data2 = _run_wrapper(wrapper, "connect", "--mcp-path", str(mcp_script))
    assert data2["success"] is True

    # Still only one crew-bus entry
    config = json.loads(config_file.read_text())
    assert "crew-bus" in config["mcpServers"]


# ── Disconnect ──

def test_disconnect_roundtrip(tmp_path):
    """Connect then disconnect — crew-bus entry removed, config intact."""
    config_file = tmp_path / "Claude" / "claude_desktop_config.json"
    mcp_script = tmp_path / "crew_bus_mcp.py"
    mcp_script.write_text("# dummy")
    wrapper = _make_wrapper(tmp_path, config_file)

    _run_wrapper(wrapper, "connect", "--mcp-path", str(mcp_script))
    data = _run_wrapper(wrapper, "disconnect")
    assert data["success"] is True

    config = json.loads(config_file.read_text())
    assert "crew-bus" not in config.get("mcpServers", {})


def test_disconnect_when_not_connected(tmp_path):
    """disconnect when not connected returns success + 'already' message."""
    config_file = tmp_path / "Claude" / "claude_desktop_config.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text('{"mcpServers": {}}')
    wrapper = _make_wrapper(tmp_path, config_file)

    data = _run_wrapper(wrapper, "disconnect")
    assert data["success"] is True
    assert "already" in data["message"].lower()


def test_disconnect_idempotent(tmp_path):
    """Running disconnect twice is safe."""
    config_file = tmp_path / "Claude" / "claude_desktop_config.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text('{"mcpServers": {}}')
    wrapper = _make_wrapper(tmp_path, config_file)

    data1 = _run_wrapper(wrapper, "disconnect")
    data2 = _run_wrapper(wrapper, "disconnect")
    assert data1["success"] is True
    assert data2["success"] is True


# ── Config safety ──

def test_backup_created_on_connect(tmp_path):
    """connect creates a .backup file before modifying config."""
    config_file = tmp_path / "Claude" / "claude_desktop_config.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text('{"mcpServers": {"other-server": {}}}')
    mcp_script = tmp_path / "crew_bus_mcp.py"
    mcp_script.write_text("# dummy")
    wrapper = _make_wrapper(tmp_path, config_file)

    _run_wrapper(wrapper, "connect", "--mcp-path", str(mcp_script))
    backup = config_file.with_suffix(".json.backup")
    assert backup.exists()
    backup_data = json.loads(backup.read_text())
    assert "other-server" in backup_data.get("mcpServers", {})
    assert "crew-bus" not in backup_data.get("mcpServers", {})


def test_backup_created_on_disconnect(tmp_path):
    """disconnect creates a .backup file before modifying config."""
    config_file = tmp_path / "Claude" / "claude_desktop_config.json"
    mcp_script = tmp_path / "crew_bus_mcp.py"
    mcp_script.write_text("# dummy")
    wrapper = _make_wrapper(tmp_path, config_file)

    _run_wrapper(wrapper, "connect", "--mcp-path", str(mcp_script))
    # Remove any backup from connect
    backup = config_file.with_suffix(".json.backup")
    if backup.exists():
        backup.unlink()

    _run_wrapper(wrapper, "disconnect")
    assert backup.exists()


def test_preserves_other_mcp_servers(tmp_path):
    """connect/disconnect preserves other MCP server entries."""
    config_file = tmp_path / "Claude" / "claude_desktop_config.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text(json.dumps({
        "mcpServers": {
            "my-other-tool": {"command": "node", "args": ["server.js"]}
        }
    }))
    mcp_script = tmp_path / "crew_bus_mcp.py"
    mcp_script.write_text("# dummy")
    wrapper = _make_wrapper(tmp_path, config_file)

    # Connect — other server still there
    _run_wrapper(wrapper, "connect", "--mcp-path", str(mcp_script))
    config = json.loads(config_file.read_text())
    assert "my-other-tool" in config["mcpServers"]
    assert "crew-bus" in config["mcpServers"]

    # Disconnect — other server still there
    _run_wrapper(wrapper, "disconnect")
    config = json.loads(config_file.read_text())
    assert "my-other-tool" in config["mcpServers"]
    assert "crew-bus" not in config["mcpServers"]


def test_corrupted_config_handled(tmp_path):
    """connect handles corrupted JSON config gracefully."""
    config_file = tmp_path / "Claude" / "claude_desktop_config.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text("NOT VALID JSON {{{")
    mcp_script = tmp_path / "crew_bus_mcp.py"
    mcp_script.write_text("# dummy")
    wrapper = _make_wrapper(tmp_path, config_file)

    # Should treat as empty config and write a fresh one
    data = _run_wrapper(wrapper, "connect", "--mcp-path", str(mcp_script))
    assert data["success"] is True
    config = json.loads(config_file.read_text())
    assert "crew-bus" in config["mcpServers"]


def test_no_config_dir_creates_it(tmp_path):
    """connect creates the config directory if it doesn't exist."""
    config_file = tmp_path / "nonexistent" / "Claude" / "claude_desktop_config.json"
    mcp_script = tmp_path / "crew_bus_mcp.py"
    mcp_script.write_text("# dummy")
    wrapper = _make_wrapper(tmp_path, config_file)

    data = _run_wrapper(wrapper, "connect", "--mcp-path", str(mcp_script))
    assert data["success"] is True
    assert config_file.exists()
