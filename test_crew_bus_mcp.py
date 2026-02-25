"""Tests for crew_bus_mcp.py — MCP server tool naming, annotations, and transport."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

MCP_SCRIPT = str(Path(__file__).parent / "crew_bus_mcp.py")

# Use venv python if available (has mcp installed), else system python
_VENV_PYTHON = str(Path(__file__).parent / ".venv" / "bin" / "python3")
PYTHON = _VENV_PYTHON if os.path.exists(_VENV_PYTHON) else sys.executable

# ---------------------------------------------------------------------------
# Import the module to inspect tools (without starting the server)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mcp_server():
    """Import the mcp object from crew_bus_mcp.py for tool inspection."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("crew_bus_mcp", MCP_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.mcp
    except ImportError:
        pytest.skip("mcp package not available in this Python")


# ---------------------------------------------------------------------------
# Tool naming
# ---------------------------------------------------------------------------

def test_tools_have_crewbus_prefix(mcp_server):
    """All registered tools must start with 'crewbus_'."""
    tools = list(mcp_server._tool_manager._tools.keys())
    assert len(tools) == 11, f"Expected 11 tools, got {len(tools)}: {tools}"
    for name in tools:
        assert name.startswith("crewbus_"), f"Tool '{name}' missing crewbus_ prefix"


def test_expected_tool_names(mcp_server):
    """Verify the exact set of expected tool names."""
    tools = set(mcp_server._tool_manager._tools.keys())
    expected = {
        "crewbus_list_agents",
        "crewbus_send_message",
        "crewbus_get_agent_chat",
        "crewbus_get_crew_stats",
        "crewbus_list_teams",
        "crewbus_get_team_detail",
        "crewbus_get_message_feed",
        "crewbus_search_agent_memory",
        "crewbus_get_agent_learnings",
        "crewbus_get_audit_log",
        "crewbus_post_to_team_mailbox",
    }
    assert tools == expected


# ---------------------------------------------------------------------------
# Tool annotations
# ---------------------------------------------------------------------------

def test_all_tools_have_annotations(mcp_server):
    """Every tool must have ToolAnnotations with readOnlyHint set."""
    for name, tool in mcp_server._tool_manager._tools.items():
        ann = getattr(tool, "annotations", None)
        assert ann is not None, f"Tool '{name}' missing annotations"
        assert ann.readOnlyHint is not None, f"Tool '{name}' has no readOnlyHint"


def test_write_tools_are_read_write(mcp_server):
    """send_message and post_to_team_mailbox should have readOnlyHint=False."""
    write_tools = {"crewbus_send_message", "crewbus_post_to_team_mailbox"}
    for name in write_tools:
        tool = mcp_server._tool_manager._tools[name]
        assert tool.annotations.readOnlyHint is False, f"{name} should be RW"


def test_read_tools_are_read_only(mcp_server):
    """All other tools should have readOnlyHint=True."""
    write_tools = {"crewbus_send_message", "crewbus_post_to_team_mailbox"}
    for name, tool in mcp_server._tool_manager._tools.items():
        if name not in write_tools:
            assert tool.annotations.readOnlyHint is True, f"{name} should be RO"


# ---------------------------------------------------------------------------
# Transport / argparse
# ---------------------------------------------------------------------------

def test_default_transport_is_stdio():
    """No args -> stdio transport."""
    result = subprocess.run(
        [PYTHON, "-c",
         "import sys; sys.argv = ['crew_bus_mcp.py']\n"
         f"exec(open({MCP_SCRIPT!r}).read().split('if __name__')[0])\n"
         "args = _build_parser().parse_args([])\n"
         "print(args.transport)"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert result.stdout.strip() == "stdio"


def test_http_transport_flag():
    """--transport http -> http transport with correct port."""
    result = subprocess.run(
        [PYTHON, "-c",
         "import sys; sys.argv = ['crew_bus_mcp.py']\n"
         f"exec(open({MCP_SCRIPT!r}).read().split('if __name__')[0])\n"
         "args = _build_parser().parse_args(['--transport', 'http', '--port', '9999'])\n"
         "print(args.transport, args.port)"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert result.stdout.strip() == "http 9999"


def test_public_flag_sets_host():
    """--public should be parsed correctly."""
    result = subprocess.run(
        [PYTHON, "-c",
         "import sys; sys.argv = ['crew_bus_mcp.py']\n"
         f"exec(open({MCP_SCRIPT!r}).read().split('if __name__')[0])\n"
         "args = _build_parser().parse_args(['--transport', 'http', '--public'])\n"
         "print(args.public)"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert result.stdout.strip() == "True"


# ---------------------------------------------------------------------------
# Health endpoint (requires HTTP server running)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def http_server():
    """Start the MCP server in HTTP mode for integration tests."""
    proc = subprocess.Popen(
        [PYTHON, MCP_SCRIPT, "--transport", "http", "--port", "8431"],
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    # Wait for server to be ready
    import urllib.request
    for _ in range(15):
        try:
            urllib.request.urlopen("http://127.0.0.1:8431/health", timeout=2)
            break
        except Exception:
            time.sleep(1)
    else:
        proc.terminate()
        pytest.skip("HTTP server did not start within 15s")

    yield proc

    proc.terminate()
    proc.wait(timeout=5)


def test_health_endpoint_returns_json(http_server):
    """GET /health returns valid JSON with expected keys."""
    import urllib.request
    with urllib.request.urlopen("http://127.0.0.1:8431/health", timeout=5) as resp:
        data = json.loads(resp.read())
    assert data["status"] == "ok"
    assert data["server"] == "crew-bus-mcp"
    assert data["version"] == "1.0.0"
    assert "agents_online" in data
    assert "uptime_seconds" in data
    assert data["uptime_seconds"] >= 0


def test_health_endpoint_fast(http_server):
    """Health check should respond in under 2 seconds."""
    import urllib.request
    start = time.time()
    urllib.request.urlopen("http://127.0.0.1:8431/health", timeout=5)
    elapsed = time.time() - start
    assert elapsed < 2.0, f"Health check took {elapsed:.2f}s"


# ---------------------------------------------------------------------------
# Backwards compatibility
# ---------------------------------------------------------------------------

def test_no_args_is_stdio():
    """Running with no args defaults to stdio (existing behavior preserved)."""
    result = subprocess.run(
        [PYTHON, "-c",
         "import sys; sys.argv = ['crew_bus_mcp.py']\n"
         f"exec(open({MCP_SCRIPT!r}).read().split('if __name__')[0])\n"
         "args = _build_parser().parse_args([])\n"
         "assert args.transport == 'stdio'\n"
         "assert args.port == 8421\n"
         "assert args.host == '127.0.0.1'\n"
         "assert args.public is False\n"
         "assert args.token is None\n"
         "print('OK')"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert result.stdout.strip() == "OK"


# ---------------------------------------------------------------------------
# Token authentication (requires auth-enabled HTTP server)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def auth_http_server():
    """Start the MCP server in HTTP mode with token auth."""
    proc = subprocess.Popen(
        [PYTHON, MCP_SCRIPT, "--transport", "http", "--port", "8432", "--token", "test-secret"],
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    import urllib.request, urllib.error
    for _ in range(15):
        try:
            req = urllib.request.Request("http://127.0.0.1:8432/health")
            req.add_header("Authorization", "Bearer test-secret")
            urllib.request.urlopen(req, timeout=2)
            break
        except Exception:
            time.sleep(1)
    else:
        proc.terminate()
        pytest.skip("Auth HTTP server did not start within 15s")

    yield proc

    proc.terminate()
    proc.wait(timeout=5)


def test_token_auth_rejects_without_token(auth_http_server):
    """Requests without token should get 401."""
    import urllib.request, urllib.error
    req = urllib.request.Request("http://127.0.0.1:8432/health")
    try:
        urllib.request.urlopen(req, timeout=5)
        assert False, "Expected 401 but got 200"
    except urllib.error.HTTPError as e:
        assert e.code == 401
        data = json.loads(e.read())
        assert data["error"] == "Unauthorized"


def test_token_auth_rejects_wrong_token(auth_http_server):
    """Requests with wrong token should get 401."""
    import urllib.request, urllib.error
    req = urllib.request.Request("http://127.0.0.1:8432/health")
    req.add_header("Authorization", "Bearer wrong-token")
    try:
        urllib.request.urlopen(req, timeout=5)
        assert False, "Expected 401 but got 200"
    except urllib.error.HTTPError as e:
        assert e.code == 401


def test_token_auth_accepts_correct_token(auth_http_server):
    """Requests with correct token should get 200."""
    import urllib.request
    req = urllib.request.Request("http://127.0.0.1:8432/health")
    req.add_header("Authorization", "Bearer test-secret")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        data = json.loads(resp.read())
        assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# Origin header validation (uses the no-auth HTTP server on port 8431)
# ---------------------------------------------------------------------------

def test_origin_localhost_ip_allowed(http_server):
    """Requests with 127.0.0.1 Origin should be accepted."""
    import urllib.request
    req = urllib.request.Request("http://127.0.0.1:8431/health")
    req.add_header("Origin", "http://127.0.0.1:3000")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200


def test_origin_localhost_name_allowed(http_server):
    """Requests with 'localhost' Origin should be accepted."""
    import urllib.request
    req = urllib.request.Request("http://127.0.0.1:8431/health")
    req.add_header("Origin", "http://localhost:8080")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200


def test_origin_external_rejected(http_server):
    """Requests with external Origin should get 403."""
    import urllib.request, urllib.error
    req = urllib.request.Request("http://127.0.0.1:8431/health")
    req.add_header("Origin", "http://evil.com")
    try:
        urllib.request.urlopen(req, timeout=5)
        assert False, "Expected 403 but got 200"
    except urllib.error.HTTPError as e:
        assert e.code == 403
        data = json.loads(e.read())
        assert data["error"] == "Forbidden: invalid origin"


def test_no_origin_header_allowed(http_server):
    """Requests without Origin header should be accepted (e.g., curl)."""
    import urllib.request
    req = urllib.request.Request("http://127.0.0.1:8431/health")
    # No Origin header set — should pass through
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200


# ---------------------------------------------------------------------------
# Backwards compatibility — stdio unaffected by token/origin
# ---------------------------------------------------------------------------

def test_stdio_ignores_token_flag():
    """Token flag should be accepted but not affect stdio mode."""
    result = subprocess.run(
        [PYTHON, "-c",
         "import sys; sys.argv = ['crew_bus_mcp.py']\n"
         f"exec(open({MCP_SCRIPT!r}).read().split('if __name__')[0])\n"
         "args = _build_parser().parse_args(['--token', 'secret'])\n"
         "assert args.transport == 'stdio'\n"
         "assert args.token == 'secret'\n"
         "print('OK')"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert result.stdout.strip() == "OK"
