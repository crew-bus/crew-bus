"""
crew-bus Telegram Bridge — Crew Boss Only

Pure Python bridge connecting Telegram to the crew-bus system.
No external dependencies — uses only the Telegram Bot API via urllib.

Inbound:  Telegram message from you → POST to crew-bus API → Human→Crew-Boss
Outbound: Polls crew-bus for new Crew-Boss→Human messages → sends to your Telegram

Usage:
    python3 telegram_bridge.py                         # reads token from crew_config
    TELEGRAM_BOT_TOKEN=123:ABC python3 telegram_bridge.py  # env override

Setup:
    1. Talk to @BotFather on Telegram → /newbot → get your bot token
    2. Paste the token into Crew Bus (Guardian handles this)
    3. Send /start to your bot — that links your Telegram chat ID
    4. Done — Crew Boss messages flow through Telegram
"""

import json
import os
import sys
import time
import threading
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────

TELEGRAM_API = "https://api.telegram.org/bot{token}"
BUS_URL = os.environ.get("BUS_URL", "http://localhost:8080")
HTTP_PORT = int(os.environ.get("TG_PORT", "3002"))
OUTBOUND_POLL = 1  # seconds — check bus for new replies (fast = snappy responses)

# ── State ───────────────────────────────────────────────────────────

bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
chat_id = None          # Your Telegram chat ID (set on first /start or message)
bot_username = None      # Bot's @username
human_agent_id = None
crew_boss_agent_id = None
last_seen_message_id = 0
last_update_id = 0       # Telegram update offset
running = True
status = "initializing"

# ── Telegram Bot API helpers ────────────────────────────────────────


def tg_request(method: str, data: dict = None) -> dict:
    """Call a Telegram Bot API method."""
    url = f"{TELEGRAM_API.format(token=bot_token)}/{method}"
    if data:
        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        print(f"[tg-bridge] API error {e.code}: {body}")
        return {"ok": False, "error": body}
    except Exception as e:
        print(f"[tg-bridge] Request error: {e}")
        return {"ok": False, "error": str(e)}


def send_message(text: str) -> bool:
    """Send a message to the paired Telegram chat."""
    if not chat_id:
        print("[tg-bridge] No chat_id yet — can't send")
        return False
    result = tg_request("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    })
    if not result.get("ok"):
        # Retry without markdown (in case of parse errors)
        result = tg_request("sendMessage", {
            "chat_id": chat_id,
            "text": text,
        })
    return result.get("ok", False)


# ── Inbound: Telegram → crew-bus ────────────────────────────────────


def poll_telegram():
    """Long-poll Telegram for new messages and forward to crew-bus."""
    global last_update_id, chat_id, status

    result = tg_request("getUpdates", {
        "offset": last_update_id + 1,
        "timeout": 30,
        "allowed_updates": ["message"],
    })

    if not result.get("ok"):
        return

    for update in result.get("result", []):
        update_id = update.get("update_id", 0)
        if update_id > last_update_id:
            last_update_id = update_id

        msg = update.get("message")
        if not msg:
            continue

        # Extract text
        text = msg.get("text", "")
        from_user = msg.get("from", {})
        msg_chat_id = msg.get("chat", {}).get("id")

        if not text or not msg_chat_id:
            continue

        # Only accept DMs (private chat), not groups
        if msg.get("chat", {}).get("type") != "private":
            continue

        # Pair on first message or /start
        if not chat_id:
            chat_id = msg_chat_id
            _save_chat_id(chat_id)
            status = "connected"
            print(f"[tg-bridge] Paired with chat_id: {chat_id} "
                  f"(user: {from_user.get('first_name', '?')})")
            if text.strip() == "/start":
                send_message(
                    "🚌 *Crew Bus connected!*\n\n"
                    "You're now talking to Crew Boss through Telegram. "
                    "Just type a message and Crew Boss will reply here."
                )
                continue

        # Only accept messages from the paired chat
        if msg_chat_id != chat_id:
            print(f"[tg-bridge] Ignoring message from unknown chat {msg_chat_id}")
            continue

        # Handle /start after already paired
        if text.strip() == "/start":
            send_message("Already connected! Just type your message.")
            continue

        # Forward to crew-bus
        print(f"[tg-bridge] ← Inbound: {text[:80]}")
        try:
            post_to_bus("/api/compose", {
                "to_agent": "Crew-Boss",
                "message_type": "task",
                "subject": "Telegram message",
                "body": text,
                "priority": "normal",
            })
            print("[tg-bridge]   → Delivered to crew-bus")
        except Exception as e:
            print(f"[tg-bridge]   ✗ Failed: {e}")


# ── Outbound: crew-bus → Telegram ───────────────────────────────────


def poll_outbound():
    """Check crew-bus for new Crew-Boss→Human messages and send to Telegram."""
    global last_seen_message_id

    if not chat_id or not crew_boss_agent_id:
        return

    try:
        msgs = get_from_bus("/api/messages?limit=20")
        if not isinstance(msgs, list):
            return

        for msg in msgs:
            msg_id = msg.get("id", 0)
            if msg_id <= last_seen_message_id:
                continue

            # Only forward Crew-Boss → Human messages
            if msg.get("from_agent_id") != crew_boss_agent_id:
                last_seen_message_id = max(last_seen_message_id, msg_id)
                continue
            if msg.get("to_type") != "human":
                last_seen_message_id = max(last_seen_message_id, msg_id)
                continue

            text = msg.get("body") or msg.get("subject") or "(empty)"
            print(f"[tg-bridge] → Outbound: {text[:80]}")

            if send_message(f"[Crew Boss] {text}"):
                print("[tg-bridge]   ✓ Sent to Telegram")
            else:
                print("[tg-bridge]   ✗ Send failed")

            last_seen_message_id = max(last_seen_message_id, msg_id)

    except Exception as e:
        if "ECONNREFUSED" not in str(e) and "Connection refused" not in str(e):
            print(f"[tg-bridge] Outbound poll error: {e}")


# ── Agent resolution ────────────────────────────────────────────────


def resolve_agents():
    """Find Human and Crew-Boss agent IDs from crew-bus."""
    global human_agent_id, crew_boss_agent_id, last_seen_message_id

    try:
        agents = get_from_bus("/api/agents")
        if not isinstance(agents, list):
            return False

        for a in agents:
            if a.get("agent_type") == "human":
                human_agent_id = a["id"]
            if a.get("name") == "Crew-Boss" and a.get("status") == "active":
                crew_boss_agent_id = a["id"]

        if human_agent_id and crew_boss_agent_id:
            print(f"[tg-bridge] Agents resolved — Human:{human_agent_id} "
                  f"Crew-Boss:{crew_boss_agent_id}")
            # Seed last seen message ID
            msgs = get_from_bus("/api/messages?limit=1")
            if isinstance(msgs, list) and msgs:
                last_seen_message_id = msgs[0].get("id", 0)
                print(f"[tg-bridge] Seeded last message ID: {last_seen_message_id}")
            return True

        print("[tg-bridge] Could not find Human or Crew-Boss agent")
        return False
    except Exception as e:
        print(f"[tg-bridge] Agent resolution failed: {e}")
        return False


# ── Bus HTTP helpers ────────────────────────────────────────────────


def post_to_bus(path: str, data: dict) -> dict:
    """POST JSON to crew-bus API."""
    url = f"{BUS_URL}{path}"
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_from_bus(path: str):
    """GET from crew-bus API."""
    url = f"{BUS_URL}{path}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ── Config persistence ──────────────────────────────────────────────


def _load_token_from_bus():
    """Load bot token from crew_config via bus API."""
    global bot_token
    if bot_token:
        return True
    try:
        # Try reading from crew_config via direct DB
        sys.path.insert(0, str(Path(__file__).parent))
        import bus as _bus
        token = _bus.get_config("telegram_bot_token", "")
        if token:
            bot_token = token
            return True
    except Exception:
        pass
    return False


def _save_chat_id(cid):
    """Save the paired chat_id to crew_config."""
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        import bus as _bus
        _bus.set_config("telegram_chat_id", str(cid))
    except Exception as e:
        print(f"[tg-bridge] Could not save chat_id: {e}")


def _load_chat_id():
    """Load saved chat_id from crew_config."""
    global chat_id
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        import bus as _bus
        saved = _bus.get_config("telegram_chat_id", "")
        if saved:
            chat_id = int(saved)
            print(f"[tg-bridge] Restored chat_id: {chat_id}")
            return True
    except Exception:
        pass
    return False


# ── HTTP Server (status + control) ──────────────────────────────────


class BridgeHandler(BaseHTTPRequestHandler):
    """Simple HTTP API for status and control."""

    def log_message(self, format, *args):
        pass  # Suppress default logging

    def do_GET(self):
        if self.path == "/status":
            self._json(200, {
                "status": status,
                "ready": status == "connected",
                "chat_id": chat_id,
                "bot_username": bot_username,
                "human_agent_id": human_agent_id,
                "crew_boss_agent_id": crew_boss_agent_id,
                "last_seen_message_id": last_seen_message_id,
                "engine": "telegram-bot-api",
            })
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/send":
            body = self._read_body()
            text = body.get("text", "")
            if not text:
                self._json(400, {"error": "need 'text' field"})
                return
            if send_message(text):
                self._json(200, {"ok": True, "sent_to": chat_id})
            else:
                self._json(503, {"error": "not connected or no chat_id"})

        elif self.path == "/stop":
            self._json(200, {"ok": True, "message": "shutting down"})
            threading.Thread(target=_shutdown, daemon=True).start()

        else:
            self._json(404, {"error": "not found"})

    def _json(self, code, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length:
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception:
                pass
        return {}


def _shutdown():
    """Graceful shutdown."""
    global running
    running = False
    time.sleep(1)
    os._exit(0)


# ── Main loop ───────────────────────────────────────────────────────


def main():
    global bot_token, bot_username, status, running

    print("[tg-bridge] crew-bus Telegram Bridge — Crew Boss Only")
    print(f"[tg-bridge] HTTP server on port {HTTP_PORT}")

    # Load token
    if not bot_token:
        _load_token_from_bus()

    if not bot_token:
        print("[tg-bridge] ERROR: No bot token. Set TELEGRAM_BOT_TOKEN "
              "or configure via Guardian.")
        status = "no_token"
        # Still start HTTP server so dashboard can check status
        server = HTTPServer(("127.0.0.1", HTTP_PORT), BridgeHandler)
        server.serve_forever()
        return

    # Verify token with getMe
    me = tg_request("getMe")
    if me.get("ok"):
        bot_info = me.get("result", {})
        bot_username = bot_info.get("username", "")
        print(f"[tg-bridge] Bot: @{bot_username} "
              f"({bot_info.get('first_name', '')})")
    else:
        print(f"[tg-bridge] ERROR: Invalid bot token — {me.get('error', '?')}")
        status = "invalid_token"
        server = HTTPServer(("127.0.0.1", HTTP_PORT), BridgeHandler)
        server.serve_forever()
        return

    # Load saved chat_id
    _load_chat_id()
    if chat_id:
        status = "connected"
        print(f"[tg-bridge] Already paired with chat_id: {chat_id}")
    else:
        status = "waiting_for_start"
        print("[tg-bridge] Waiting for user to send /start to the bot...")

    # Resolve agent IDs
    resolve_agents()

    # Start HTTP server in background
    server = HTTPServer(("127.0.0.1", HTTP_PORT), BridgeHandler)
    server_thread = threading.Thread(
        target=server.serve_forever, daemon=True, name="tg-http")
    server_thread.start()

    print(f"[tg-bridge] Listening on http://localhost:{HTTP_PORT}")

    # Inbound (Telegram → bus) runs on its own thread because Telegram
    # long-polling blocks for up to 30s waiting for new messages.
    def _inbound_loop():
        while running:
            try:
                poll_telegram()
            except Exception as e:
                print(f"[tg-bridge] Telegram poll error: {e}")
                time.sleep(5)
            # Re-resolve agents if needed
            if not crew_boss_agent_id:
                resolve_agents()

    threading.Thread(target=_inbound_loop, daemon=True, name="tg-inbound").start()

    # Outbound (bus → Telegram) polls fast so replies arrive in ~1-2s.
    print(f"[tg-bridge] Outbound polling every {OUTBOUND_POLL}s")
    while running:
        try:
            poll_outbound()
        except Exception as e:
            if "Connection refused" not in str(e):
                print(f"[tg-bridge] Outbound error: {e}")
        time.sleep(OUTBOUND_POLL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[tg-bridge] Stopped.")
