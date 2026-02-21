"""Tests for telegram_bridge.py — Telegram Bot API integration, polling, messaging."""

import json
import tempfile
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import bus
import telegram_bridge


def _fresh_db():
    """Create a temp DB with full schema + bootstrap human agent."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db = Path(tmp.name)
    tmp.close()
    bus.init_db(db)
    conn = bus.get_conn(db)
    conn.execute(
        "INSERT OR IGNORE INTO agents (id, name, agent_type, role, active, status) "
        "VALUES (1, 'TestHuman', 'human', 'human', 1, 'active')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO agents (id, name, agent_type, role, active, status) "
        "VALUES (2, 'Crew-Boss', 'right_hand', 'right_hand', 1, 'active')"
    )
    conn.commit()
    conn.close()
    return db


# ---------------------------------------------------------------------------
# tg_request
# ---------------------------------------------------------------------------

def test_tg_request_success():
    """tg_request returns parsed JSON on success."""
    fake_resp = json.dumps({"ok": True, "result": {"id": 123}}).encode()
    mock_ctx = MagicMock()
    mock_ctx.read.return_value = fake_resp
    mock_ctx.__enter__ = lambda s: s
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_ctx):
        telegram_bridge.bot_token = "fake:token"
        result = telegram_bridge.tg_request("getMe")
        assert result["ok"] is True
        assert result["result"]["id"] == 123


def test_tg_request_http_error():
    """tg_request handles HTTP errors gracefully."""
    import urllib.error
    err = urllib.error.HTTPError(
        "http://fake", 403, "Forbidden", {}, MagicMock(read=lambda: b"Forbidden"))
    with patch("urllib.request.urlopen", side_effect=err):
        telegram_bridge.bot_token = "fake:token"
        result = telegram_bridge.tg_request("getMe")
        assert result["ok"] is False
        assert "error" in result


def test_tg_request_network_error():
    """tg_request handles connection/timeout errors."""
    with patch("urllib.request.urlopen", side_effect=ConnectionError("refused")):
        telegram_bridge.bot_token = "fake:token"
        result = telegram_bridge.tg_request("getMe")
        assert result["ok"] is False
        assert "refused" in result["error"]


# ---------------------------------------------------------------------------
# send_message
# ---------------------------------------------------------------------------

def test_send_message_no_chat_id():
    """send_message returns False when no chat_id is set."""
    original = telegram_bridge.chat_id
    telegram_bridge.chat_id = None
    result = telegram_bridge.send_message("Hello")
    assert result is False
    telegram_bridge.chat_id = original


def test_send_message_success():
    """send_message sends via Telegram and returns True on success."""
    original = telegram_bridge.chat_id
    telegram_bridge.chat_id = 12345

    with patch.object(telegram_bridge, "tg_request", return_value={"ok": True}):
        result = telegram_bridge.send_message("Hello!")
        assert result is True

    telegram_bridge.chat_id = original


def test_send_message_markdown_fallback():
    """send_message retries without Markdown on parse error."""
    original = telegram_bridge.chat_id
    telegram_bridge.chat_id = 12345

    call_count = 0
    def fake_tg_request(method, data=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"ok": False, "error": "parse error"}
        return {"ok": True}

    with patch.object(telegram_bridge, "tg_request", side_effect=fake_tg_request):
        result = telegram_bridge.send_message("*bad markdown")
        assert result is True
        assert call_count == 2

    telegram_bridge.chat_id = original


# ---------------------------------------------------------------------------
# poll_telegram
# ---------------------------------------------------------------------------

def test_poll_telegram_no_updates():
    """poll_telegram handles empty update list."""
    with patch.object(telegram_bridge, "tg_request",
                      return_value={"ok": True, "result": []}):
        telegram_bridge.poll_telegram()  # Should not raise


def test_poll_telegram_private_message():
    """poll_telegram processes a private message and forwards to bus."""
    original_chat = telegram_bridge.chat_id
    original_update = telegram_bridge.last_update_id
    telegram_bridge.chat_id = 999
    telegram_bridge.last_update_id = 0

    update = {
        "ok": True,
        "result": [{
            "update_id": 1,
            "message": {
                "text": "Hello Crew Boss",
                "from": {"first_name": "Test"},
                "chat": {"id": 999, "type": "private"},
            }
        }],
    }

    with patch.object(telegram_bridge, "tg_request", return_value=update), \
         patch.object(telegram_bridge, "post_to_bus") as mock_post:
        telegram_bridge.poll_telegram()
        mock_post.assert_called_once()
        args = mock_post.call_args
        assert args[0][0] == "/api/compose"
        assert args[0][1]["body"] == "Hello Crew Boss"

    telegram_bridge.chat_id = original_chat
    telegram_bridge.last_update_id = original_update


def test_poll_telegram_ignores_group_messages():
    """poll_telegram ignores non-private (group) messages."""
    original_chat = telegram_bridge.chat_id
    original_update = telegram_bridge.last_update_id
    telegram_bridge.chat_id = None
    telegram_bridge.last_update_id = 0

    update = {
        "ok": True,
        "result": [{
            "update_id": 1,
            "message": {
                "text": "Group message",
                "from": {"first_name": "Test"},
                "chat": {"id": 111, "type": "group"},
            }
        }],
    }

    with patch.object(telegram_bridge, "tg_request", return_value=update), \
         patch.object(telegram_bridge, "post_to_bus") as mock_post:
        telegram_bridge.poll_telegram()
        mock_post.assert_not_called()

    telegram_bridge.chat_id = original_chat
    telegram_bridge.last_update_id = original_update


def test_poll_telegram_start_command_pairs():
    """poll_telegram pairs with chat on /start and sends welcome message."""
    original_chat = telegram_bridge.chat_id
    original_update = telegram_bridge.last_update_id
    telegram_bridge.chat_id = None
    telegram_bridge.last_update_id = 0

    update = {
        "ok": True,
        "result": [{
            "update_id": 1,
            "message": {
                "text": "/start",
                "from": {"first_name": "Tester"},
                "chat": {"id": 7777, "type": "private"},
            }
        }],
    }

    with patch.object(telegram_bridge, "tg_request", return_value=update), \
         patch.object(telegram_bridge, "send_message") as mock_send, \
         patch.object(telegram_bridge, "_save_chat_id"):
        telegram_bridge.poll_telegram()
        assert telegram_bridge.chat_id == 7777
        mock_send.assert_called_once()
        assert "connected" in mock_send.call_args[0][0].lower()

    telegram_bridge.chat_id = original_chat
    telegram_bridge.last_update_id = original_update


def test_poll_telegram_ignores_unknown_chat():
    """poll_telegram ignores messages from a non-paired chat."""
    original_chat = telegram_bridge.chat_id
    original_update = telegram_bridge.last_update_id
    telegram_bridge.chat_id = 100
    telegram_bridge.last_update_id = 0

    update = {
        "ok": True,
        "result": [{
            "update_id": 1,
            "message": {
                "text": "Sneaky message",
                "from": {"first_name": "Hacker"},
                "chat": {"id": 200, "type": "private"},
            }
        }],
    }

    with patch.object(telegram_bridge, "tg_request", return_value=update), \
         patch.object(telegram_bridge, "post_to_bus") as mock_post:
        telegram_bridge.poll_telegram()
        mock_post.assert_not_called()

    telegram_bridge.chat_id = original_chat
    telegram_bridge.last_update_id = original_update


def test_poll_telegram_api_failure():
    """poll_telegram handles API failure gracefully."""
    with patch.object(telegram_bridge, "tg_request",
                      return_value={"ok": False, "error": "timeout"}):
        telegram_bridge.poll_telegram()  # Should not raise


# ---------------------------------------------------------------------------
# poll_outbound
# ---------------------------------------------------------------------------

def test_poll_outbound_no_chat_id():
    """poll_outbound returns early when no chat_id."""
    original = telegram_bridge.chat_id
    telegram_bridge.chat_id = None
    with patch.object(telegram_bridge, "get_from_bus") as mock_get:
        telegram_bridge.poll_outbound()
        mock_get.assert_not_called()
    telegram_bridge.chat_id = original


def test_poll_outbound_no_crew_boss():
    """poll_outbound returns early when crew_boss_agent_id not set."""
    original_chat = telegram_bridge.chat_id
    original_boss = telegram_bridge.crew_boss_agent_id
    telegram_bridge.chat_id = 123
    telegram_bridge.crew_boss_agent_id = None

    with patch.object(telegram_bridge, "get_from_bus") as mock_get:
        telegram_bridge.poll_outbound()
        mock_get.assert_not_called()

    telegram_bridge.chat_id = original_chat
    telegram_bridge.crew_boss_agent_id = original_boss


def test_poll_outbound_sends_crew_boss_messages():
    """poll_outbound sends Crew-Boss->Human messages to Telegram."""
    original_chat = telegram_bridge.chat_id
    original_boss = telegram_bridge.crew_boss_agent_id
    original_seen = telegram_bridge.last_seen_message_id
    telegram_bridge.chat_id = 123
    telegram_bridge.crew_boss_agent_id = 2
    telegram_bridge.last_seen_message_id = 0

    messages = [
        {"id": 1, "from_agent_id": 2, "to_type": "human",
         "body": "Hello!", "subject": "Greeting"},
    ]

    with patch.object(telegram_bridge, "get_from_bus", return_value=messages), \
         patch.object(telegram_bridge, "send_message", return_value=True) as mock_send:
        telegram_bridge.poll_outbound()
        mock_send.assert_called_once()
        assert "Hello!" in mock_send.call_args[0][0]

    telegram_bridge.chat_id = original_chat
    telegram_bridge.crew_boss_agent_id = original_boss
    telegram_bridge.last_seen_message_id = original_seen


def test_poll_outbound_skips_non_boss_messages():
    """poll_outbound ignores messages not from Crew Boss."""
    original_chat = telegram_bridge.chat_id
    original_boss = telegram_bridge.crew_boss_agent_id
    original_seen = telegram_bridge.last_seen_message_id
    telegram_bridge.chat_id = 123
    telegram_bridge.crew_boss_agent_id = 2
    telegram_bridge.last_seen_message_id = 0

    messages = [
        {"id": 1, "from_agent_id": 99, "to_type": "human",
         "body": "Not from boss", "subject": "Spam"},
    ]

    with patch.object(telegram_bridge, "get_from_bus", return_value=messages), \
         patch.object(telegram_bridge, "send_message") as mock_send:
        telegram_bridge.poll_outbound()
        mock_send.assert_not_called()

    telegram_bridge.chat_id = original_chat
    telegram_bridge.crew_boss_agent_id = original_boss
    telegram_bridge.last_seen_message_id = original_seen


def test_poll_outbound_handles_api_error():
    """poll_outbound handles bus API errors."""
    original_chat = telegram_bridge.chat_id
    original_boss = telegram_bridge.crew_boss_agent_id
    telegram_bridge.chat_id = 123
    telegram_bridge.crew_boss_agent_id = 2

    with patch.object(telegram_bridge, "get_from_bus",
                      side_effect=Exception("Connection refused")):
        telegram_bridge.poll_outbound()  # Should not raise

    telegram_bridge.chat_id = original_chat
    telegram_bridge.crew_boss_agent_id = original_boss


# ---------------------------------------------------------------------------
# Token / chat_id persistence
# ---------------------------------------------------------------------------

def test_load_token_from_bus():
    """_load_token_from_bus loads token from crew_config."""
    db = _fresh_db()
    bus.set_config("telegram_bot_token", "123:FAKE_TOKEN", db)

    original = telegram_bridge.bot_token
    telegram_bridge.bot_token = ""

    with patch("bus.get_config", return_value="123:FAKE_TOKEN"):
        result = telegram_bridge._load_token_from_bus()
        assert result is True
        assert telegram_bridge.bot_token == "123:FAKE_TOKEN"

    telegram_bridge.bot_token = original


def test_load_token_already_set():
    """_load_token_from_bus returns True immediately if token already set."""
    original = telegram_bridge.bot_token
    telegram_bridge.bot_token = "already:set"
    result = telegram_bridge._load_token_from_bus()
    assert result is True
    telegram_bridge.bot_token = original


def test_save_and_load_chat_id():
    """_save_chat_id and _load_chat_id persist chat_id through bus config."""
    original = telegram_bridge.chat_id

    with patch("bus.set_config") as mock_set:
        telegram_bridge._save_chat_id(42)
        mock_set.assert_called_once()

    telegram_bridge.chat_id = original


# ---------------------------------------------------------------------------
# resolve_agents
# ---------------------------------------------------------------------------

def test_resolve_agents_success():
    """resolve_agents finds Human and Crew-Boss agent IDs."""
    original_human = telegram_bridge.human_agent_id
    original_boss = telegram_bridge.crew_boss_agent_id
    original_seen = telegram_bridge.last_seen_message_id

    agents = [
        {"id": 1, "agent_type": "human", "name": "TestHuman", "status": "active"},
        {"id": 2, "agent_type": "right_hand", "name": "Crew-Boss", "status": "active"},
    ]

    with patch.object(telegram_bridge, "get_from_bus") as mock_get:
        mock_get.side_effect = [agents, [{"id": 5}]]
        result = telegram_bridge.resolve_agents()
        assert result is True
        assert telegram_bridge.human_agent_id == 1
        assert telegram_bridge.crew_boss_agent_id == 2

    telegram_bridge.human_agent_id = original_human
    telegram_bridge.crew_boss_agent_id = original_boss
    telegram_bridge.last_seen_message_id = original_seen


def test_resolve_agents_failure():
    """resolve_agents returns False when agents not found."""
    original_human = telegram_bridge.human_agent_id
    original_boss = telegram_bridge.crew_boss_agent_id
    telegram_bridge.human_agent_id = None
    telegram_bridge.crew_boss_agent_id = None

    with patch.object(telegram_bridge, "get_from_bus", return_value=[]):
        result = telegram_bridge.resolve_agents()
        assert result is False

    telegram_bridge.human_agent_id = original_human
    telegram_bridge.crew_boss_agent_id = original_boss


def test_resolve_agents_api_error():
    """resolve_agents handles API errors gracefully."""
    with patch.object(telegram_bridge, "get_from_bus",
                      side_effect=Exception("timeout")):
        result = telegram_bridge.resolve_agents()
        assert result is False


# ---------------------------------------------------------------------------
# Bus HTTP helpers
# ---------------------------------------------------------------------------

def test_post_to_bus():
    """post_to_bus sends JSON POST to bus API."""
    fake_resp = json.dumps({"ok": True}).encode()
    mock_ctx = MagicMock()
    mock_ctx.read.return_value = fake_resp
    mock_ctx.__enter__ = lambda s: s
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_ctx) as mock_url:
        result = telegram_bridge.post_to_bus("/api/compose", {"body": "test"})
        assert result["ok"] is True


def test_get_from_bus():
    """get_from_bus fetches JSON from bus API."""
    fake_resp = json.dumps([{"id": 1}]).encode()
    mock_ctx = MagicMock()
    mock_ctx.read.return_value = fake_resp
    mock_ctx.__enter__ = lambda s: s
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_ctx):
        result = telegram_bridge.get_from_bus("/api/messages")
        assert isinstance(result, list)
        assert result[0]["id"] == 1


# ---------------------------------------------------------------------------
# BridgeHandler HTTP server
# ---------------------------------------------------------------------------

def test_bridge_handler_status():
    """BridgeHandler /status returns bridge state as JSON."""
    handler = MagicMock(spec=telegram_bridge.BridgeHandler)
    handler.path = "/status"
    handler.headers = {}
    handler.wfile = MagicMock()

    # Call the actual do_GET with mocked self
    telegram_bridge.BridgeHandler.do_GET(handler)
    handler._json.assert_called_once()
    code, data = handler._json.call_args[0]
    assert code == 200
    assert "status" in data


def test_bridge_handler_404():
    """BridgeHandler returns 404 for unknown paths."""
    handler = MagicMock(spec=telegram_bridge.BridgeHandler)
    handler.path = "/unknown"
    handler.headers = {}

    telegram_bridge.BridgeHandler.do_GET(handler)
    handler._json.assert_called_once()
    code, data = handler._json.call_args[0]
    assert code == 404


# ---------------------------------------------------------------------------
# Helper for new tests
# ---------------------------------------------------------------------------

def _reset_state():
    """Reset module-level globals to clean state."""
    telegram_bridge.bot_token = "test-token-123"
    telegram_bridge.chat_id = 12345
    telegram_bridge.bot_username = "test_bot"
    telegram_bridge.human_agent_id = 1
    telegram_bridge.crew_boss_agent_id = 2
    telegram_bridge.last_seen_message_id = 0
    telegram_bridge.last_update_id = 0
    telegram_bridge.status = "connected"
    telegram_bridge._message_queue.clear()


# ===========================================================================
# Retry with exponential backoff
# ===========================================================================


def test_retry_on_500():
    """tg_request retries on 500 errors with exponential backoff."""
    _reset_state()

    ok_resp = MagicMock()
    ok_resp.read.return_value = json.dumps({"ok": True}).encode()
    ok_resp.__enter__ = lambda s: s
    ok_resp.__exit__ = MagicMock(return_value=False)

    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise urllib.error.HTTPError(
                "url", 500, "Internal Server Error", {}, BytesIO(b"error"))
        return ok_resp

    with patch("urllib.request.urlopen", side_effect=side_effect):
        with patch("time.sleep") as mock_sleep:
            result = telegram_bridge.tg_request("sendMessage", retries=3)

    assert result["ok"] is True
    assert call_count == 3
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(1)
    mock_sleep.assert_any_call(2)


def test_retry_on_429_rate_limit():
    """tg_request retries on 429 Too Many Requests."""
    _reset_state()

    ok_resp = MagicMock()
    ok_resp.read.return_value = json.dumps({"ok": True}).encode()
    ok_resp.__enter__ = lambda s: s
    ok_resp.__exit__ = MagicMock(return_value=False)

    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise urllib.error.HTTPError(
                "url", 429, "Too Many Requests", {}, BytesIO(b"rate limited"))
        return ok_resp

    with patch("urllib.request.urlopen", side_effect=side_effect):
        with patch("time.sleep"):
            result = telegram_bridge.tg_request("sendMessage", retries=2)

    assert result["ok"] is True
    assert call_count == 2


def test_retry_on_network_error():
    """tg_request retries on network errors (URLError)."""
    _reset_state()

    ok_resp = MagicMock()
    ok_resp.read.return_value = json.dumps({"ok": True}).encode()
    ok_resp.__enter__ = lambda s: s
    ok_resp.__exit__ = MagicMock(return_value=False)

    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise urllib.error.URLError("Connection refused")
        return ok_resp

    with patch("urllib.request.urlopen", side_effect=side_effect):
        with patch("time.sleep"):
            result = telegram_bridge.tg_request("getMe", retries=2)

    assert result["ok"] is True
    assert call_count == 2


def test_no_retry_on_400():
    """tg_request does NOT retry on 400 client errors."""
    _reset_state()

    def side_effect(*args, **kwargs):
        raise urllib.error.HTTPError(
            "url", 400, "Bad Request", {}, BytesIO(b"bad request"))

    with patch("urllib.request.urlopen", side_effect=side_effect):
        with patch("time.sleep") as mock_sleep:
            result = telegram_bridge.tg_request("sendMessage", retries=3)

    assert result["ok"] is False
    assert mock_sleep.call_count == 0


def test_max_retries_exhausted():
    """tg_request returns error after all retries are exhausted."""
    _reset_state()

    def side_effect(*args, **kwargs):
        raise urllib.error.HTTPError(
            "url", 500, "Server Error", {}, BytesIO(b"error"))

    with patch("urllib.request.urlopen", side_effect=side_effect):
        with patch("time.sleep"):
            result = telegram_bridge.tg_request("sendMessage", retries=2)

    assert result["ok"] is False


# ===========================================================================
# Token expiration detection and recovery
# ===========================================================================


def test_401_triggers_token_reload():
    """tg_request detects 401 and attempts token reload."""
    _reset_state()

    def side_effect(*args, **kwargs):
        raise urllib.error.HTTPError(
            "url", 401, "Unauthorized", {}, BytesIO(b"unauthorized"))

    with patch("urllib.request.urlopen", side_effect=side_effect):
        with patch.object(telegram_bridge, "_try_reload_token",
                          return_value=False) as mock_reload:
            result = telegram_bridge.tg_request("getMe", retries=1)

    assert result["ok"] is False
    assert result.get("token_expired") is True
    mock_reload.assert_called_once()


def test_401_with_successful_reload():
    """On 401, reloads token and retries successfully."""
    _reset_state()

    ok_resp = MagicMock()
    ok_resp.read.return_value = json.dumps({"ok": True}).encode()
    ok_resp.__enter__ = lambda s: s
    ok_resp.__exit__ = MagicMock(return_value=False)

    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise urllib.error.HTTPError(
                "url", 401, "Unauthorized", {}, BytesIO(b"unauthorized"))
        return ok_resp

    def fake_reload():
        telegram_bridge.bot_token = "new-token-456"
        return True

    with patch("urllib.request.urlopen", side_effect=side_effect):
        with patch.object(telegram_bridge, "_try_reload_token",
                          side_effect=fake_reload):
            result = telegram_bridge.tg_request("getMe", retries=2)

    assert result["ok"] is True
    assert call_count == 2


def test_try_reload_token_loads_new_token():
    """_try_reload_token loads a different token from crew_config."""
    _reset_state()
    telegram_bridge.bot_token = "old-token"

    mock_bus = MagicMock()
    mock_bus.get_config.return_value = "brand-new-token"

    with patch.dict("sys.modules", {"bus": mock_bus}):
        result = telegram_bridge._try_reload_token()

    assert result is True
    assert telegram_bridge.bot_token == "brand-new-token"


def test_try_reload_token_no_change():
    """_try_reload_token returns False if token hasn't changed."""
    _reset_state()
    telegram_bridge.bot_token = "same-token"

    mock_bus = MagicMock()
    mock_bus.get_config.return_value = "same-token"

    with patch.dict("sys.modules", {"bus": mock_bus}):
        result = telegram_bridge._try_reload_token()

    assert result is False


# ===========================================================================
# File/media support
# ===========================================================================


def test_extract_media_info_photo():
    """Extracts photo media info, picks largest size."""
    msg = {
        "photo": [
            {"file_id": "small", "file_size": 100},
            {"file_id": "large", "file_size": 5000},
            {"file_id": "medium", "file_size": 1000},
        ],
        "caption": "Look at this!",
    }
    info = telegram_bridge._extract_media_info(msg)
    assert info["type"] == "photo"
    assert info["file_id"] == "large"
    assert info["caption"] == "Look at this!"
    assert info["filename"] == "photo.jpg"


def test_extract_media_info_document():
    """Extracts document media info."""
    msg = {
        "document": {"file_id": "doc123", "file_name": "report.pdf"},
        "caption": "The report",
    }
    info = telegram_bridge._extract_media_info(msg)
    assert info["type"] == "document"
    assert info["file_id"] == "doc123"
    assert info["filename"] == "report.pdf"


def test_extract_media_info_voice():
    """Extracts voice message media info."""
    msg = {"voice": {"file_id": "voice456", "duration": 5}}
    info = telegram_bridge._extract_media_info(msg)
    assert info["type"] == "voice"
    assert info["file_id"] == "voice456"
    assert info["filename"] == "voice.ogg"


def test_extract_media_info_text_only():
    """Returns empty dict for text-only messages."""
    assert telegram_bridge._extract_media_info({"text": "hello"}) == {}


def test_send_photo_success():
    """send_photo calls tg_request_multipart correctly."""
    _reset_state()
    with patch.object(telegram_bridge, "tg_request_multipart",
                      return_value={"ok": True}) as mock_mp:
        result = telegram_bridge.send_photo(b"img-data", "test.jpg", "My photo")
    assert result is True
    assert mock_mp.call_args[0][0] == "sendPhoto"
    assert mock_mp.call_args[0][2] == "photo"
    assert mock_mp.call_args[0][3] == b"img-data"


def test_send_document_success():
    """send_document calls tg_request_multipart correctly."""
    _reset_state()
    with patch.object(telegram_bridge, "tg_request_multipart",
                      return_value={"ok": True}) as mock_mp:
        result = telegram_bridge.send_document(b"doc-data", "report.pdf")
    assert result is True
    assert mock_mp.call_args[0][0] == "sendDocument"


def test_send_voice_success():
    """send_voice calls tg_request_multipart correctly."""
    _reset_state()
    with patch.object(telegram_bridge, "tg_request_multipart",
                      return_value={"ok": True}) as mock_mp:
        result = telegram_bridge.send_voice(b"audio-data", "Memo")
    assert result is True
    assert mock_mp.call_args[0][0] == "sendVoice"


def test_send_photo_no_chat_id():
    """send_photo returns False when no chat_id."""
    _reset_state()
    telegram_bridge.chat_id = None
    assert telegram_bridge.send_photo(b"data") is False


def test_download_tg_file_success():
    """download_tg_file retrieves file bytes from Telegram."""
    _reset_state()
    mock_resp = MagicMock()
    mock_resp.read.return_value = b"file-content"
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch.object(telegram_bridge, "tg_request",
                      return_value={"ok": True, "result": {"file_path": "photos/test.jpg"}}):
        with patch("urllib.request.urlopen", return_value=mock_resp):
            data, path = telegram_bridge.download_tg_file("file123")
    assert data == b"file-content"
    assert path == "photos/test.jpg"


def test_download_tg_file_api_failure():
    """download_tg_file returns None on API failure."""
    _reset_state()
    with patch.object(telegram_bridge, "tg_request", return_value={"ok": False}):
        data, path = telegram_bridge.download_tg_file("file123")
    assert data is None
    assert path is None


def test_poll_telegram_with_photo():
    """poll_telegram forwards photo messages with metadata to bus."""
    _reset_state()
    updates = {
        "ok": True,
        "result": [{
            "update_id": 100,
            "message": {
                "chat": {"id": 12345, "type": "private"},
                "from": {"first_name": "Test"},
                "photo": [
                    {"file_id": "small", "file_size": 100},
                    {"file_id": "big", "file_size": 9000},
                ],
                "caption": "Check this",
            },
        }],
    }
    with patch.object(telegram_bridge, "tg_request", return_value=updates):
        with patch.object(telegram_bridge, "post_to_bus") as mock_post:
            with patch.object(telegram_bridge, "_drain_queue"):
                telegram_bridge.poll_telegram()
    mock_post.assert_called_once()
    payload = mock_post.call_args[0][1]
    assert "[photo: photo.jpg]" in payload["body"]
    assert "Check this" in payload["body"]
    assert payload["metadata"]["media_type"] == "photo"
    assert payload["metadata"]["file_id"] == "big"


# ===========================================================================
# Message queue on bus downtime
# ===========================================================================


def test_enqueue_message():
    """_enqueue_message adds to the queue."""
    _reset_state()
    telegram_bridge._enqueue_message({"body": "test"})
    assert len(telegram_bridge._message_queue) == 1
    assert telegram_bridge._message_queue[0]["body"] == "test"


def test_enqueue_respects_maxlen():
    """Queue caps at maxlen=1000."""
    _reset_state()
    for i in range(1010):
        telegram_bridge._enqueue_message({"body": f"msg-{i}"})
    assert len(telegram_bridge._message_queue) == 1000
    assert telegram_bridge._message_queue[0]["body"] == "msg-10"


def test_drain_queue_success():
    """_drain_queue delivers all queued messages when bus is up."""
    _reset_state()
    telegram_bridge._enqueue_message({"body": "msg1"})
    telegram_bridge._enqueue_message({"body": "msg2"})
    with patch.object(telegram_bridge, "post_to_bus") as mock_post:
        telegram_bridge._drain_queue()
    assert mock_post.call_count == 2
    assert len(telegram_bridge._message_queue) == 0


def test_drain_queue_partial_failure():
    """_drain_queue stops on first failure, keeps remaining in queue."""
    _reset_state()
    telegram_bridge._enqueue_message({"body": "msg1"})
    telegram_bridge._enqueue_message({"body": "msg2"})
    telegram_bridge._enqueue_message({"body": "msg3"})

    call_count = 0

    def side_effect(path, data):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise ConnectionError("bus down")
        return {}

    with patch.object(telegram_bridge, "post_to_bus", side_effect=side_effect):
        telegram_bridge._drain_queue()
    assert call_count == 2
    assert len(telegram_bridge._message_queue) == 2


def test_drain_queue_empty_noop():
    """_drain_queue is a no-op when queue is empty."""
    _reset_state()
    with patch.object(telegram_bridge, "post_to_bus") as mock_post:
        telegram_bridge._drain_queue()
    mock_post.assert_not_called()


def test_poll_telegram_queues_on_bus_failure():
    """poll_telegram queues messages when bus is unreachable."""
    _reset_state()
    updates = {
        "ok": True,
        "result": [{
            "update_id": 200,
            "message": {
                "text": "hello crew boss",
                "chat": {"id": 12345, "type": "private"},
                "from": {"first_name": "Test"},
            },
        }],
    }
    with patch.object(telegram_bridge, "tg_request", return_value=updates):
        with patch.object(telegram_bridge, "post_to_bus",
                          side_effect=ConnectionError("bus down")):
            with patch.object(telegram_bridge, "_drain_queue"):
                telegram_bridge.poll_telegram()
    assert len(telegram_bridge._message_queue) == 1
    assert telegram_bridge._message_queue[0]["body"] == "hello crew boss"


def test_poll_telegram_calls_drain_queue():
    """poll_telegram calls _drain_queue at the start."""
    _reset_state()
    with patch.object(telegram_bridge, "tg_request",
                      return_value={"ok": True, "result": []}):
        with patch.object(telegram_bridge, "_drain_queue") as mock_drain:
            telegram_bridge.poll_telegram()
    mock_drain.assert_called_once()


def test_status_includes_queue_count():
    """The /status response includes queued_messages."""
    _reset_state()
    telegram_bridge._enqueue_message({"body": "test"})
    telegram_bridge._enqueue_message({"body": "test2"})

    handler = MagicMock(spec=telegram_bridge.BridgeHandler)
    handler.path = "/status"
    handler.headers = {}
    handler.wfile = MagicMock()

    telegram_bridge.BridgeHandler.do_GET(handler)
    handler._json.assert_called_once()
    code, data = handler._json.call_args[0]
    assert code == 200
    assert data["queued_messages"] == 2
