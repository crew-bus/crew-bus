#!/usr/bin/env python3
"""CrewBus tunnel client — bridges the cloud relay to the local MCP server.

Runs on the user's Mac as a subprocess managed by the SwiftUI app.
Maintains a persistent WebSocket connection to the CrewBus cloud relay
and forwards MCP requests to the local MCP server over HTTP.

Wire protocol:
  Relay -> Client:  {"type": "mcp_request", "id": "<uuid>", "body": <JSON-RPC>}
  Client -> Relay:  {"type": "mcp_response", "id": "<uuid>", "body": <JSON-RPC>}
  Relay -> Client:  {"type": "ping"}
  Client -> Relay:  {"type": "pong"}
"""

import argparse
import asyncio
import json
import signal
import sys
import time
import urllib.error
import urllib.request
from typing import Optional

DEFAULT_RELAY_URL = "wss://relay.crew-bus.dev/tunnel"
DEFAULT_LOCAL_URL = "http://127.0.0.1:8421"
MAX_BACKOFF = 30


def _log(msg: str) -> None:
    """Log to stderr with prefix."""
    print(f"[crewbus-tunnel] {msg}", file=sys.stderr, flush=True)


def _status(line: str) -> None:
    """Emit a structured status line to stderr for the Mac app to parse."""
    print(line, file=sys.stderr, flush=True)


_mcp_session_id: Optional[str] = None


def _ensure_session(local_url: str) -> None:
    """Initialize the local MCP session if we don't have one yet."""
    global _mcp_session_id
    if _mcp_session_id:
        return

    url = f"{local_url}/mcp"
    init_body = json.dumps({
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "crewbus-tunnel", "version": "1.0.0"},
        },
        "id": 0,
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=init_body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=190) as resp:
            sid = resp.headers.get("mcp-session-id")
            if sid:
                _mcp_session_id = sid
                _log(f"MCP session initialized: {sid[:12]}...")
            resp.read()  # drain
    except Exception as e:
        _log(f"Failed to initialize MCP session: {e}")


def _do_forward(body: dict, local_url: str) -> dict:
    """POST the MCP request body to the local MCP server and return the response."""
    global _mcp_session_id
    _ensure_session(local_url)

    url = f"{local_url}/mcp"
    data = json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if _mcp_session_id:
        headers["Mcp-Session-Id"] = _mcp_session_id

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=190) as resp:
            response_data = resp.read()
            # Handle SSE responses (text/event-stream)
            content_type = resp.headers.get("Content-Type", "")
            if "text/event-stream" in content_type:
                # Parse SSE: extract last "data:" line
                for line in response_data.decode("utf-8").strip().split("\n"):
                    if line.startswith("data: "):
                        return json.loads(line[6:])
                return {"jsonrpc": "2.0", "error": {"code": -32603, "message": "Empty SSE"}, "id": body.get("id")}
            return json.loads(response_data)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        _log(f"Local MCP server returned HTTP {e.code}: {error_body}")
        if e.code == 400 and "session" in error_body.lower():
            _mcp_session_id = None  # reset session on session errors
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32603, "message": f"Local MCP error: HTTP {e.code}"},
            "id": body.get("id"),
        }
    except urllib.error.URLError as e:
        _log(f"Failed to reach local MCP server: {e.reason}")
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32603, "message": f"Local MCP unreachable: {e.reason}"},
            "id": body.get("id"),
        }
    except Exception as e:
        _log(f"Unexpected error forwarding to local MCP: {e}")
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32603, "message": f"Forward error: {e}"},
            "id": body.get("id"),
        }


def forward_to_local(body: dict, local_url: str) -> dict:
    """Forward with stale-session retry. If the response looks empty due to a
    stale session, reset the session and retry once."""
    global _mcp_session_id
    result = _do_forward(body, local_url)

    # Detect stale session: valid response but empty result for list methods
    method = body.get("method", "")
    if method in ("tools/list", "resources/list", "prompts/list"):
        items_key = method.split("/")[0]  # "tools", "resources", "prompts"
        inner = result.get("result", {})
        if isinstance(inner, dict) and inner.get(items_key) == [] and _mcp_session_id:
            _log(f"Empty {method} response — resetting stale session and retrying")
            _mcp_session_id = None
            result = _do_forward(body, local_url)

    return result


async def _handle_messages(ws, shutdown_event, loop, local_url):
    """Process messages from the WebSocket until shutdown or disconnect."""
    shutdown_task = asyncio.ensure_future(shutdown_event.wait())
    try:
        while not shutdown_event.is_set():
            recv_task = asyncio.ensure_future(ws.recv())
            done, _ = await asyncio.wait(
                {recv_task, shutdown_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            if shutdown_task in done:
                recv_task.cancel()
                try:
                    await recv_task
                except (asyncio.CancelledError, Exception):
                    pass
                break

            # recv_task completed
            try:
                message = recv_task.result()
            except Exception:
                # WebSocket closed or errored
                raise

            try:
                msg = json.loads(message)
            except json.JSONDecodeError:
                _log(f"Invalid JSON from relay: {str(message)[:200]}")
                continue

            msg_type = msg.get("type")

            if msg_type == "ping":
                await ws.send(json.dumps({"type": "pong"}))
                _log("Received ping, sent pong")

            elif msg_type == "mcp_request":
                request_id = msg.get("id")
                body = msg.get("body", {})
                method = body.get("method", "?")
                _log(f"MCP request {request_id}: {method}")

                # Forward to local MCP server (run in executor to avoid blocking)
                t0 = time.time()
                response = await loop.run_in_executor(
                    None, forward_to_local, body, local_url
                )
                duration = time.time() - t0

                await ws.send(json.dumps({
                    "type": "mcp_response",
                    "id": request_id,
                    "body": response,
                }))
                _status(f"TOOL_CALL:{method} duration={duration:.2f}s")
                _log(f"MCP response {request_id} sent")

            else:
                _log(f"Unknown message type: {msg_type}")
    finally:
        if not shutdown_task.done():
            shutdown_task.cancel()
            try:
                await shutdown_task
            except asyncio.CancelledError:
                pass


async def run_tunnel(relay_url: str, token: str, local_url: str) -> None:
    """Connect to the relay and forward MCP requests to the local server.

    Auto-reconnects with exponential backoff on disconnect.
    """
    import websockets

    backoff = 1
    loop = asyncio.get_event_loop()
    shutdown_event = asyncio.Event()

    def _handle_signal() -> None:
        _log("Received shutdown signal, closing...")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            # signal handlers not supported on Windows event loop
            pass

    attempt = 0
    while not shutdown_event.is_set():
        try:
            _status("STATUS:CONNECTING")
            async with websockets.connect(
                relay_url,
                additional_headers={"Authorization": f"Bearer {token}"},
            ) as ws:
                _status("STATUS:CONNECTED")
                _log(f"Connected to relay")
                backoff = 1  # reset on successful connection
                attempt = 0

                await _handle_messages(ws, shutdown_event, loop, local_url)

        except asyncio.CancelledError:
            _log("Tunnel cancelled")
            break
        except Exception as e:
            if shutdown_event.is_set():
                break
            attempt += 1
            _status(f"STATUS:ERROR message={e}")
            _log(f"Disconnected: {e}. Reconnecting in {backoff}s...")
            _status(f"STATUS:RECONNECTING attempt={attempt}")
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=backoff)
                break  # shutdown requested during backoff
            except asyncio.TimeoutError:
                pass  # timeout expired, reconnect
            backoff = min(backoff * 2, MAX_BACKOFF)

    _status("STATUS:DISCONNECTED")
    _log("Tunnel shut down")


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the tunnel client."""
    parser = argparse.ArgumentParser(
        description="CrewBus tunnel client — bridges the cloud relay to the local MCP server.",
    )
    parser.add_argument(
        "--relay-url",
        default=DEFAULT_RELAY_URL,
        help=f"WebSocket URL of the cloud relay (default: {DEFAULT_RELAY_URL})",
    )
    parser.add_argument(
        "--token",
        required=True,
        help="Authentication token for the relay",
    )
    parser.add_argument(
        "--local-url",
        default=DEFAULT_LOCAL_URL,
        help=f"Base URL of the local MCP server (default: {DEFAULT_LOCAL_URL})",
    )
    return parser


def main() -> None:
    """Parse args and run the tunnel."""
    parser = build_parser()
    args = parser.parse_args()

    _log(f"Starting tunnel: relay={args.relay_url} local={args.local_url}")
    asyncio.run(run_tunnel(args.relay_url, args.token, args.local_url))


if __name__ == "__main__":
    main()
