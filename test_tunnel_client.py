"""Tests for scripts/tunnel_client.py — WebSocket tunnel client for CrewBus cloud relay."""

import asyncio
import io
import json
import os
import signal as signal_mod
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import the tunnel client module from scripts/
sys.path.insert(0, str(Path(__file__).parent / "scripts"))
import tunnel_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_async(coro):
    """Run an async coroutine in a fresh event loop (avoids pytest-asyncio dependency)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class FakeWS:
    """Fake WebSocket that yields pre-loaded messages via recv() and records sent data."""

    def __init__(self, messages=None):
        self._messages = list(messages or [])
        self._index = 0
        self.sent = []

    async def recv(self):
        if self._index < len(self._messages):
            msg = self._messages[self._index]
            self._index += 1
            return msg
        # Simulate connection closed after all messages consumed
        raise Exception("connection closed")

    async def send(self, data):
        self.sent.append(json.loads(data))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


# ---------------------------------------------------------------------------
# forward_to_local
# ---------------------------------------------------------------------------

def test_forward_to_local():
    """forward_to_local POSTs body to local MCP server and returns the response."""
    mcp_request = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
    mcp_response = {"jsonrpc": "2.0", "result": {"tools": []}, "id": 1}

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mcp_response).encode("utf-8")
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        result = tunnel_client.forward_to_local(mcp_request, "http://127.0.0.1:8421")

    assert result == mcp_response

    # Verify the request was sent correctly
    call_args = mock_urlopen.call_args
    req = call_args[0][0]
    assert req.full_url == "http://127.0.0.1:8421/mcp"
    assert req.get_header("Content-type") == "application/json"
    assert json.loads(req.data) == mcp_request


def test_forward_to_local_http_error():
    """forward_to_local returns a JSON-RPC error on HTTP failure."""
    import urllib.error

    err_body = MagicMock()
    err_body.read.return_value = b"Internal Server Error"
    err = urllib.error.HTTPError(
        "http://127.0.0.1:8421/mcp", 500, "Internal Server Error", {}, err_body
    )

    with patch("urllib.request.urlopen", side_effect=err):
        result = tunnel_client.forward_to_local(
            {"jsonrpc": "2.0", "method": "test", "id": 42},
            "http://127.0.0.1:8421",
        )

    assert result["error"]["code"] == -32603
    assert "500" in result["error"]["message"]
    assert result["id"] == 42


def test_forward_to_local_connection_error():
    """forward_to_local returns a JSON-RPC error when local server is unreachable."""
    import urllib.error

    err = urllib.error.URLError("Connection refused")

    with patch("urllib.request.urlopen", side_effect=err):
        result = tunnel_client.forward_to_local(
            {"jsonrpc": "2.0", "method": "test", "id": 7},
            "http://127.0.0.1:8421",
        )

    assert result["error"]["code"] == -32603
    assert "unreachable" in result["error"]["message"].lower()
    assert result["id"] == 7


# ---------------------------------------------------------------------------
# ping / pong
# ---------------------------------------------------------------------------

def test_ping_pong():
    """Receiving a ping message causes a pong to be sent back."""
    ping_msg = json.dumps({"type": "ping"})
    fake_ws = FakeWS(messages=[ping_msg])

    mock_websockets = MagicMock()
    mock_websockets.connect.return_value = fake_ws

    async def _run():
        with patch.dict("sys.modules", {"websockets": mock_websockets}):
            task = asyncio.create_task(
                tunnel_client.run_tunnel("wss://fake/tunnel", "tok", "http://127.0.0.1:8421")
            )
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    _run_async(_run())

    assert len(fake_ws.sent) >= 1
    assert fake_ws.sent[0] == {"type": "pong"}


# ---------------------------------------------------------------------------
# mcp_request forwarding
# ---------------------------------------------------------------------------

def test_mcp_request_forwarding():
    """An mcp_request is forwarded to the local server and the response sent back."""
    mcp_body = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
    mcp_response = {"jsonrpc": "2.0", "result": {"tools": []}, "id": 1}
    request_id = "abc-123"

    incoming_msg = json.dumps({
        "type": "mcp_request",
        "id": request_id,
        "body": mcp_body,
    })

    fake_ws = FakeWS(messages=[incoming_msg])

    mock_websockets = MagicMock()
    mock_websockets.connect.return_value = fake_ws

    async def _run():
        with patch.dict("sys.modules", {"websockets": mock_websockets}), \
             patch.object(tunnel_client, "forward_to_local", return_value=mcp_response) as mock_fwd:

            task = asyncio.create_task(
                tunnel_client.run_tunnel("wss://fake/tunnel", "tok", "http://127.0.0.1:8421")
            )
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Verify forward_to_local was called with the body
        mock_fwd.assert_called_once_with(mcp_body, "http://127.0.0.1:8421")

    _run_async(_run())

    # Verify the response was sent back with the correct id
    assert len(fake_ws.sent) == 1
    resp = fake_ws.sent[0]
    assert resp["type"] == "mcp_response"
    assert resp["id"] == request_id
    assert resp["body"] == mcp_response


# ---------------------------------------------------------------------------
# Reconnect backoff
# ---------------------------------------------------------------------------

def test_reconnect_backoff():
    """Backoff doubles on each disconnect: 1, 2, 4, 8, 16, 30, 30..."""
    backoff = 1
    sequence = []
    for _ in range(7):
        sequence.append(backoff)
        backoff = min(backoff * 2, tunnel_client.MAX_BACKOFF)

    assert sequence == [1, 2, 4, 8, 16, 30, 30]


def test_reconnect_backoff_max():
    """MAX_BACKOFF constant is 30 seconds."""
    assert tunnel_client.MAX_BACKOFF == 30


def test_reconnect_backoff_reset_logic():
    """Backoff resets to 1 after a successful connection.

    Simulates connections that succeed (recv raises immediately to end the
    session) followed by a connection failure, verifying backoff=1 after reset.
    """
    connect_count = 0
    recorded_backoffs = []

    mock_websockets = MagicMock()

    class EmptyWS:
        """WS that connects successfully but has no messages (recv raises immediately)."""
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def recv(self):
            raise Exception("no messages")
        async def send(self, data):
            pass

    def fake_connect(*args, **kwargs):
        nonlocal connect_count
        connect_count += 1
        if connect_count <= 3:
            return EmptyWS()  # succeeds but recv raises
        raise ConnectionError("done testing")

    mock_websockets.connect = fake_connect

    async def _run():
        async def patched_wait_for(coro, timeout):
            recorded_backoffs.append(timeout)
            if len(recorded_backoffs) >= 2:
                raise asyncio.CancelledError()
            raise asyncio.TimeoutError()

        with patch.dict("sys.modules", {"websockets": mock_websockets}), \
             patch("asyncio.wait_for", side_effect=patched_wait_for):
            try:
                await tunnel_client.run_tunnel("wss://fake/tunnel", "tok", "http://127.0.0.1:8421")
            except asyncio.CancelledError:
                pass

    _run_async(_run())

    # After successful connections (EmptyWS), backoff is reset to 1 each time.
    # The first recorded backoff should be 1.
    assert len(recorded_backoffs) >= 1
    assert recorded_backoffs[0] == 1


# ---------------------------------------------------------------------------
# argparse defaults
# ---------------------------------------------------------------------------

def test_argparse_defaults():
    """Default values for --relay-url and --local-url are correct."""
    parser = tunnel_client.build_parser()
    args = parser.parse_args(["--token", "test-token"])

    assert args.relay_url == "wss://relay.crew-bus.dev/tunnel"
    assert args.local_url == "http://127.0.0.1:8421"
    assert args.token == "test-token"


def test_argparse_custom_values():
    """Custom values for all args are parsed correctly."""
    parser = tunnel_client.build_parser()
    args = parser.parse_args([
        "--token", "my-secret",
        "--relay-url", "wss://custom.relay/tunnel",
        "--local-url", "http://localhost:9999",
    ])

    assert args.relay_url == "wss://custom.relay/tunnel"
    assert args.local_url == "http://localhost:9999"
    assert args.token == "my-secret"


def test_argparse_token_required():
    """--token is required; omitting it raises SystemExit."""
    parser = tunnel_client.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------

def test_graceful_shutdown():
    """SIGTERM causes the tunnel to shut down gracefully."""

    class BlockingWS:
        """WS that blocks on recv() forever, simulating waiting for messages."""
        async def recv(self):
            await asyncio.sleep(100)
            return '{"type": "ping"}'

        async def send(self, data):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    mock_websockets = MagicMock()
    mock_websockets.connect.return_value = BlockingWS()

    async def _run():
        with patch.dict("sys.modules", {"websockets": mock_websockets}):
            task = asyncio.create_task(
                tunnel_client.run_tunnel("wss://fake/tunnel", "tok", "http://127.0.0.1:8421")
            )
            # Give the tunnel time to connect and set up signal handlers
            await asyncio.sleep(0.1)

            # Send SIGTERM to trigger graceful shutdown
            os.kill(os.getpid(), signal_mod.SIGTERM)

            # The tunnel should shut down within a reasonable time
            try:
                await asyncio.wait_for(task, timeout=2.0)
                shutdown_ok = True
            except asyncio.TimeoutError:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                shutdown_ok = False

        assert shutdown_ok, "Tunnel did not shut down within 2 seconds after SIGTERM"

    _run_async(_run())


# ---------------------------------------------------------------------------
# Structured status output protocol
# ---------------------------------------------------------------------------

def _capture_stderr_async(coro_func):
    """Run an async function while capturing stderr, return stderr_text."""
    buf = io.StringIO()
    old_stderr = sys.stderr
    sys.stderr = buf
    try:
        _run_async(coro_func())
    finally:
        sys.stderr = old_stderr
    return buf.getvalue()


def test_status_connected_on_successful_connect():
    """STATUS:CONNECTED is emitted after a successful WebSocket connection."""
    ping_msg = json.dumps({"type": "ping"})
    fake_ws = FakeWS(messages=[ping_msg])

    mock_websockets = MagicMock()
    mock_websockets.connect.return_value = fake_ws

    async def _run():
        with patch.dict("sys.modules", {"websockets": mock_websockets}):
            task = asyncio.create_task(
                tunnel_client.run_tunnel("wss://fake/tunnel", "tok", "http://127.0.0.1:8421")
            )
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    stderr = _capture_stderr_async(_run)
    lines = stderr.strip().splitlines()
    status_lines = [l for l in lines if l.startswith("STATUS:")]

    assert "STATUS:CONNECTING" in status_lines
    assert "STATUS:CONNECTED" in status_lines
    # CONNECTING should come before CONNECTED
    assert status_lines.index("STATUS:CONNECTING") < status_lines.index("STATUS:CONNECTED")


def test_status_reconnecting_includes_attempt():
    """STATUS:RECONNECTING includes the attempt count on connection failure."""
    connect_count = 0
    mock_websockets = MagicMock()

    class FailingWS:
        async def __aenter__(self):
            raise ConnectionError("refused")
        async def __aexit__(self, *args):
            pass

    def fake_connect(*args, **kwargs):
        nonlocal connect_count
        connect_count += 1
        return FailingWS()

    mock_websockets.connect = fake_connect

    async def _run():
        async def patched_wait_for(coro, timeout):
            if connect_count >= 3:
                raise asyncio.CancelledError()
            raise asyncio.TimeoutError()

        with patch.dict("sys.modules", {"websockets": mock_websockets}), \
             patch("asyncio.wait_for", side_effect=patched_wait_for):
            try:
                await tunnel_client.run_tunnel("wss://fake/tunnel", "tok", "http://127.0.0.1:8421")
            except asyncio.CancelledError:
                pass

    stderr = _capture_stderr_async(_run)
    lines = stderr.strip().splitlines()
    reconnect_lines = [l for l in lines if l.startswith("STATUS:RECONNECTING")]

    assert len(reconnect_lines) >= 2
    assert "attempt=1" in reconnect_lines[0]
    assert "attempt=2" in reconnect_lines[1]


def test_status_disconnected_on_shutdown():
    """STATUS:DISCONNECTED is emitted when the tunnel shuts down."""

    class BlockingWS:
        async def recv(self):
            await asyncio.sleep(100)
            return '{"type": "ping"}'
        async def send(self, data):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    mock_websockets = MagicMock()
    mock_websockets.connect.return_value = BlockingWS()

    async def _run():
        with patch.dict("sys.modules", {"websockets": mock_websockets}):
            task = asyncio.create_task(
                tunnel_client.run_tunnel("wss://fake/tunnel", "tok", "http://127.0.0.1:8421")
            )
            await asyncio.sleep(0.1)
            os.kill(os.getpid(), signal_mod.SIGTERM)
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except asyncio.TimeoutError:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    stderr = _capture_stderr_async(_run)
    lines = stderr.strip().splitlines()
    assert "STATUS:DISCONNECTED" in lines


def test_tool_call_status_includes_method_and_duration():
    """TOOL_CALL status line includes the method name and duration."""
    mcp_body = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
    mcp_response = {"jsonrpc": "2.0", "result": {"tools": []}, "id": 1}
    request_id = "tc-001"

    incoming_msg = json.dumps({
        "type": "mcp_request",
        "id": request_id,
        "body": mcp_body,
    })

    fake_ws = FakeWS(messages=[incoming_msg])
    mock_websockets = MagicMock()
    mock_websockets.connect.return_value = fake_ws

    async def _run():
        with patch.dict("sys.modules", {"websockets": mock_websockets}), \
             patch.object(tunnel_client, "forward_to_local", return_value=mcp_response):
            task = asyncio.create_task(
                tunnel_client.run_tunnel("wss://fake/tunnel", "tok", "http://127.0.0.1:8421")
            )
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    stderr = _capture_stderr_async(_run)
    lines = stderr.strip().splitlines()
    tool_call_lines = [l for l in lines if l.startswith("TOOL_CALL:")]

    assert len(tool_call_lines) >= 1
    assert "tools/list" in tool_call_lines[0]
    assert "duration=" in tool_call_lines[0]
    assert tool_call_lines[0].endswith("s")


def test_status_error_on_connection_failure():
    """STATUS:ERROR is emitted with error message on connection failure."""
    mock_websockets = MagicMock()

    class FailingWS:
        async def __aenter__(self):
            raise ConnectionError("Connection refused")
        async def __aexit__(self, *args):
            pass

    mock_websockets.connect.return_value = FailingWS()

    async def _run():
        async def patched_wait_for(coro, timeout):
            raise asyncio.CancelledError()

        with patch.dict("sys.modules", {"websockets": mock_websockets}), \
             patch("asyncio.wait_for", side_effect=patched_wait_for):
            try:
                await tunnel_client.run_tunnel("wss://fake/tunnel", "tok", "http://127.0.0.1:8421")
            except asyncio.CancelledError:
                pass

    stderr = _capture_stderr_async(_run)
    lines = stderr.strip().splitlines()
    error_lines = [l for l in lines if l.startswith("STATUS:ERROR")]

    assert len(error_lines) >= 1
    assert "message=" in error_lines[0]
