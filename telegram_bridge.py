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
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────

TELEGRAM_API = "https://api.telegram.org/bot{token}"
TELEGRAM_FILE_API = "https://api.telegram.org/file/bot{token}"
BUS_URL = os.environ.get("BUS_URL", "http://localhost:8080")
HTTP_PORT = int(os.environ.get("TG_PORT", "3002"))
OUTBOUND_POLL = 1  # seconds — check bus for new replies (fast = snappy responses)

# Retry config
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1  # seconds — exponential backoff: 1s, 2s, 4s
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}

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

# Message queue for bus downtime
_message_queue = deque(maxlen=1000)
_queue_lock = threading.Lock()

# ── Telegram Bot API helpers ────────────────────────────────────────


def tg_request(method: str, data: dict = None, retries: int = MAX_RETRIES) -> dict:
    """Call a Telegram Bot API method with exponential backoff retry."""
    url = f"{TELEGRAM_API.format(token=bot_token)}/{method}"
    for attempt in range(retries + 1):
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
            # Token expired/revoked — attempt reload
            if e.code == 401:
                print(f"[tg-bridge] TOKEN EXPIRED/REVOKED (401): {body}")
                if _try_reload_token():
                    url = f"{TELEGRAM_API.format(token=bot_token)}/{method}"
                    print("[tg-bridge] Token reloaded from crew_config, retrying...")
                    continue
                return {"ok": False, "error": body, "token_expired": True}
            # Retryable server/rate-limit errors
            if e.code in RETRYABLE_HTTP_CODES and attempt < retries:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                print(f"[tg-bridge] API error {e.code}, retry {attempt+1}/{retries} in {delay}s")
                time.sleep(delay)
                continue
            print(f"[tg-bridge] API error {e.code}: {body}")
            return {"ok": False, "error": body}
        except (urllib.error.URLError, OSError) as e:
            # Network errors — retryable
            if attempt < retries:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                print(f"[tg-bridge] Network error, retry {attempt+1}/{retries} in {delay}s: {e}")
                time.sleep(delay)
                continue
            print(f"[tg-bridge] Request error after {retries} retries: {e}")
            return {"ok": False, "error": str(e)}
        except Exception as e:
            print(f"[tg-bridge] Request error: {e}")
            return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "max retries exceeded"}


def _try_reload_token() -> bool:
    """Attempt to reload bot token from crew_config after expiration."""
    global bot_token
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        import bus as _bus
        new_token = _bus.get_config("telegram_bot_token", "")
        if new_token and new_token != bot_token:
            bot_token = new_token
            print("[tg-bridge] Loaded new token from crew_config")
            return True
        print("[tg-bridge] No new token found in crew_config")
    except Exception as e:
        print(f"[tg-bridge] Token reload failed: {e}")
    return False


def tg_request_multipart(method: str, data: dict, file_field: str,
                         file_bytes: bytes, filename: str,
                         content_type: str = "application/octet-stream") -> dict:
    """Call a Telegram Bot API method with a file upload (multipart/form-data)."""
    url = f"{TELEGRAM_API.format(token=bot_token)}/{method}"
    boundary = "----CrewBusBoundary"
    body_parts = []
    for key, val in data.items():
        body_parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
            f"{val}\r\n"
        )
    body_parts.append(
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    )
    payload = b""
    for part in body_parts:
        payload += part.encode("utf-8")
    payload += file_bytes
    payload += f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        print(f"[tg-bridge] Upload error {e.code}: {body}")
        return {"ok": False, "error": body}
    except Exception as e:
        print(f"[tg-bridge] Upload error: {e}")
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


# ── Media helpers ──────────────────────────────────────────────────


def send_photo(photo_bytes: bytes, filename: str = "photo.jpg",
               caption: str = "") -> bool:
    """Send a photo to the paired Telegram chat."""
    if not chat_id:
        return False
    data = {"chat_id": str(chat_id)}
    if caption:
        data["caption"] = caption
    result = tg_request_multipart("sendPhoto", data, "photo",
                                  photo_bytes, filename, "image/jpeg")
    return result.get("ok", False)


def send_document(doc_bytes: bytes, filename: str = "file.pdf",
                  caption: str = "") -> bool:
    """Send a document to the paired Telegram chat."""
    if not chat_id:
        return False
    data = {"chat_id": str(chat_id)}
    if caption:
        data["caption"] = caption
    result = tg_request_multipart("sendDocument", data, "document",
                                  doc_bytes, filename, "application/octet-stream")
    return result.get("ok", False)


def send_voice(voice_bytes: bytes, caption: str = "") -> bool:
    """Send a voice message to the paired Telegram chat."""
    if not chat_id:
        return False
    data = {"chat_id": str(chat_id)}
    if caption:
        data["caption"] = caption
    result = tg_request_multipart("sendVoice", data, "voice",
                                  voice_bytes, "voice.ogg", "audio/ogg")
    return result.get("ok", False)


def download_tg_file(file_id: str) -> tuple:
    """Download a file from Telegram by file_id.

    Returns (bytes, file_path) or (None, None) on failure.
    """
    info = tg_request("getFile", {"file_id": file_id})
    if not info.get("ok"):
        return None, None
    file_path = info["result"].get("file_path", "")
    if not file_path:
        return None, None
    url = f"{TELEGRAM_FILE_API.format(token=bot_token)}/{file_path}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return resp.read(), file_path
    except Exception as e:
        print(f"[tg-bridge] File download error: {e}")
        return None, None


def _extract_media_info(msg: dict) -> dict:
    """Extract media info from a Telegram message, if any.

    Returns dict with keys: type, file_id, caption, filename (or empty dict).
    """
    caption = msg.get("caption", "")

    if msg.get("photo"):
        # photo is a list of sizes, pick the largest
        largest = max(msg["photo"], key=lambda p: p.get("file_size", 0))
        return {"type": "photo", "file_id": largest["file_id"],
                "caption": caption, "filename": "photo.jpg"}

    if msg.get("document"):
        doc = msg["document"]
        return {"type": "document", "file_id": doc["file_id"],
                "caption": caption,
                "filename": doc.get("file_name", "document")}

    if msg.get("voice"):
        voice = msg["voice"]
        return {"type": "voice", "file_id": voice["file_id"],
                "caption": caption, "filename": "voice.ogg"}

    return {}


# ── Message queue (bus downtime resilience) ────────────────────────


def _enqueue_message(payload: dict):
    """Queue a message for later delivery to the bus."""
    with _queue_lock:
        _message_queue.append(payload)
    print(f"[tg-bridge] Queued message (queue size: {len(_message_queue)})")


def _drain_queue():
    """Try to deliver all queued messages to the bus. Called periodically."""
    if not _message_queue:
        return
    with _queue_lock:
        pending = list(_message_queue)
    delivered = 0
    for payload in pending:
        try:
            post_to_bus("/api/compose", payload)
            delivered += 1
            with _queue_lock:
                if _message_queue and _message_queue[0] is payload:
                    _message_queue.popleft()
        except Exception:
            break  # bus still down, stop draining
    if delivered:
        print(f"[tg-bridge] Drained {delivered} queued messages")


# ── Inbound: Telegram → crew-bus ────────────────────────────────────


def poll_telegram():
    """Long-poll Telegram for new messages and forward to crew-bus."""
    global last_update_id, chat_id, status

    # Try draining queued messages first
    _drain_queue()

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

        from_user = msg.get("from", {})
        msg_chat_id = msg.get("chat", {}).get("id")

        if not msg_chat_id:
            continue

        # Only accept DMs (private chat), not groups
        if msg.get("chat", {}).get("type") != "private":
            continue

        # Extract text and/or media
        text = msg.get("text", "")
        media = _extract_media_info(msg)

        # Skip messages with neither text nor media
        if not text and not media:
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

        # Build body from text and/or media
        body = text
        if media:
            media_desc = f"[{media['type']}: {media['filename']}]"
            if media.get("caption"):
                media_desc += f" {media['caption']}"
            body = f"{body}\n{media_desc}" if body else media_desc
            print(f"[tg-bridge] ← Inbound media: {media['type']} ({media['filename']})")
        else:
            print(f"[tg-bridge] ← Inbound: {text[:80]}")

        # Forward to crew-bus (queue on failure)
        payload = {
            "to_agent": "Crew-Boss",
            "message_type": "task",
            "subject": "Telegram message",
            "body": body,
            "priority": "normal",
        }
        if media:
            payload["metadata"] = {
                "media_type": media["type"],
                "file_id": media["file_id"],
                "filename": media["filename"],
            }

        try:
            post_to_bus("/api/compose", payload)
            print("[tg-bridge]   → Delivered to crew-bus")
        except Exception as e:
            print(f"[tg-bridge]   ✗ Bus unreachable, queuing: {e}")
            _enqueue_message(payload)


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
                "queued_messages": len(_message_queue),
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
