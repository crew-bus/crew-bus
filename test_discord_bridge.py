"""Tests for discord_bridge.py — Discord webhook posting, embed formatting, error handling."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import bus
import discord_bridge


def _fresh_db():
    """Create a temp DB with full schema + bootstrap agent + guard activation."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db = Path(tmp.name)
    tmp.close()
    bus.init_db(db)
    conn = bus.get_conn(db)
    conn.execute(
        "INSERT OR IGNORE INTO agents (id, name, agent_type, role, active, status) "
        "VALUES (1, 'TestHuman', 'human', 'human', 1, 'active')"
    )
    conn.commit()
    conn.close()
    return db


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------

def test_setup_discord_webhook():
    """setup_discord_webhook stores webhook URL in crew_config."""
    db = _fresh_db()
    result = discord_bridge.setup_discord_webhook(
        "general", "https://discord.com/api/webhooks/123/abc", db)
    assert result["ok"] is True

    val = bus.get_config("discord_webhook_general", "", db)
    assert val == "https://discord.com/api/webhooks/123/abc"


def test_setup_discord_webhook_invalid_channel():
    """setup_discord_webhook rejects unknown channel names."""
    db = _fresh_db()
    result = discord_bridge.setup_discord_webhook(
        "invalid_channel", "https://discord.com/api/webhooks/123/abc", db)
    assert result["ok"] is False
    assert "Unknown channel" in result["error"]


def test_is_configured_false():
    """is_configured returns False when no webhooks are set."""
    db = _fresh_db()
    assert discord_bridge.is_configured(db) is False


def test_is_configured_true():
    """is_configured returns True when at least one webhook is set."""
    db = _fresh_db()
    bus.set_config("discord_webhook_general", "https://discord.com/api/webhooks/123/abc", db)
    assert discord_bridge.is_configured(db) is True


def test_get_webhook_missing():
    """_get_webhook raises ValueError when no webhook URL is configured."""
    db = _fresh_db()
    try:
        discord_bridge._get_webhook("general", db)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "No Discord webhook" in str(e)


def test_get_webhook_success():
    """_get_webhook returns the webhook URL for a configured channel."""
    db = _fresh_db()
    bus.set_config("discord_webhook_general",
                   "https://discord.com/api/webhooks/123/abc", db)
    url = discord_bridge._get_webhook("general", db)
    assert url == "https://discord.com/api/webhooks/123/abc"


# ---------------------------------------------------------------------------
# _send_webhook
# ---------------------------------------------------------------------------

def test_send_webhook_success_204():
    """_send_webhook handles 204 No Content (Discord success response)."""
    mock_resp = MagicMock()
    mock_resp.status = 204
    mock_resp.read.return_value = b""
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = discord_bridge._send_webhook(
            "https://discord.com/api/webhooks/123/abc",
            content="Test message",
        )
        assert result["ok"] is True


def test_send_webhook_success_with_json():
    """_send_webhook handles JSON response body."""
    resp_data = json.dumps({"id": "12345"}).encode()
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = resp_data
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = discord_bridge._send_webhook(
            "https://discord.com/api/webhooks/123/abc",
            content="Test",
        )
        assert result.get("id") == "12345"


def test_send_webhook_http_error():
    """_send_webhook handles HTTP errors from Discord."""
    import urllib.error
    err_body = MagicMock()
    err_body.read.return_value = b"Bad Request"
    err = urllib.error.HTTPError(
        "http://fake", 400, "Bad Request", {}, err_body)

    with patch("urllib.request.urlopen", side_effect=err):
        result = discord_bridge._send_webhook(
            "https://discord.com/api/webhooks/123/abc",
            content="Test",
        )
        assert result["ok"] is False
        assert "400" in result["error"]


def test_send_webhook_network_error():
    """_send_webhook handles network/connection errors."""
    with patch("urllib.request.urlopen",
               side_effect=ConnectionError("Connection refused")):
        result = discord_bridge._send_webhook(
            "https://discord.com/api/webhooks/123/abc",
            content="Test",
        )
        assert result["ok"] is False
        assert "refused" in result["error"].lower()


def test_send_webhook_content_truncation():
    """_send_webhook truncates content to Discord's 2000 char limit."""
    long_content = "x" * 3000

    mock_resp = MagicMock()
    mock_resp.status = 204
    mock_resp.read.return_value = b""
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_url:
        discord_bridge._send_webhook(
            "https://discord.com/api/webhooks/123/abc",
            content=long_content,
        )
        # Check the request was made with truncated content
        call_args = mock_url.call_args
        req = call_args[0][0]
        payload = json.loads(req.data)
        assert len(payload["content"]) == 2000


def test_send_webhook_embed_limit():
    """_send_webhook limits embeds to 10."""
    embeds = [{"title": f"Embed {i}"} for i in range(15)]

    mock_resp = MagicMock()
    mock_resp.status = 204
    mock_resp.read.return_value = b""
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_url:
        discord_bridge._send_webhook(
            "https://discord.com/api/webhooks/123/abc",
            embeds=embeds,
        )
        req = mock_url.call_args[0][0]
        payload = json.loads(req.data)
        assert len(payload["embeds"]) == 10


# ---------------------------------------------------------------------------
# post_message
# ---------------------------------------------------------------------------

def test_post_message_success():
    """post_message sends text and logs to audit_log."""
    db = _fresh_db()
    bus.set_config("discord_webhook_general",
                   "https://discord.com/api/webhooks/123/abc", db)

    mock_resp = MagicMock()
    mock_resp.status = 204
    mock_resp.read.return_value = b""
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = discord_bridge.post_message("Test message", "general", db)
        assert result["ok"] is True


def test_post_message_no_webhook():
    """post_message raises ValueError when no webhook configured."""
    db = _fresh_db()
    try:
        discord_bridge.post_message("Test", "general", db)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# post_embed
# ---------------------------------------------------------------------------

def test_post_embed_success():
    """post_embed sends a rich embed to Discord."""
    db = _fresh_db()
    bus.set_config("discord_webhook_general",
                   "https://discord.com/api/webhooks/123/abc", db)

    mock_resp = MagicMock()
    mock_resp.status = 204
    mock_resp.read.return_value = b""
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_url:
        result = discord_bridge.post_embed(
            title="Test Embed",
            description="Test description",
            color=0xFF0000,
            fields=[{"name": "Field1", "value": "Value1", "inline": True}],
            db_path=db,
        )
        assert result["ok"] is True

        # Verify embed structure in payload
        req = mock_url.call_args[0][0]
        payload = json.loads(req.data)
        assert len(payload["embeds"]) == 1
        embed = payload["embeds"][0]
        assert embed["title"] == "Test Embed"
        assert embed["color"] == 0xFF0000


def test_post_embed_truncates_description():
    """post_embed truncates description to 4096 chars (Discord limit)."""
    db = _fresh_db()
    bus.set_config("discord_webhook_general",
                   "https://discord.com/api/webhooks/123/abc", db)

    mock_resp = MagicMock()
    mock_resp.status = 204
    mock_resp.read.return_value = b""
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_url:
        discord_bridge.post_embed(
            title="Long",
            description="x" * 5000,
            db_path=db,
        )
        req = mock_url.call_args[0][0]
        payload = json.loads(req.data)
        assert len(payload["embeds"][0]["description"]) == 4096


def test_post_embed_with_url():
    """post_embed includes URL in embed when provided."""
    db = _fresh_db()
    bus.set_config("discord_webhook_general",
                   "https://discord.com/api/webhooks/123/abc", db)

    mock_resp = MagicMock()
    mock_resp.status = 204
    mock_resp.read.return_value = b""
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_url:
        discord_bridge.post_embed(
            title="Click Me",
            description="Link embed",
            url="https://crew-bus.dev",
            db_path=db,
        )
        req = mock_url.call_args[0][0]
        payload = json.loads(req.data)
        assert payload["embeds"][0]["url"] == "https://crew-bus.dev"


# ---------------------------------------------------------------------------
# post_announcement
# ---------------------------------------------------------------------------

def test_post_announcement():
    """post_announcement sends to general channel with Crew Bus orange."""
    db = _fresh_db()
    bus.set_config("discord_webhook_general",
                   "https://discord.com/api/webhooks/123/abc", db)

    mock_resp = MagicMock()
    mock_resp.status = 204
    mock_resp.read.return_value = b""
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_url:
        result = discord_bridge.post_announcement(
            title="Launch!",
            body="Crew Bus is live!",
            link="https://crew-bus.dev",
            db_path=db,
        )
        assert result["ok"] is True
        req = mock_url.call_args[0][0]
        payload = json.loads(req.data)
        assert payload["embeds"][0]["color"] == 0xf0883e


# ---------------------------------------------------------------------------
# post_approved_draft
# ---------------------------------------------------------------------------

def test_post_approved_draft_not_found():
    """post_approved_draft returns error for missing draft."""
    db = _fresh_db()
    result = discord_bridge.post_approved_draft(99999, db)
    assert result["ok"] is False
    assert "not found" in result["error"].lower()


def test_post_approved_draft_not_approved():
    """post_approved_draft rejects drafts that aren't approved."""
    db = _fresh_db()
    draft = bus.create_social_draft(1, "discord", "Test body", db_path=db)
    result = discord_bridge.post_approved_draft(draft["draft_id"], db)
    assert result["ok"] is False
    assert "must be 'approved'" in result["error"]


def test_post_approved_draft_text():
    """post_approved_draft sends text draft without title as plain message."""
    db = _fresh_db()
    bus.set_config("discord_webhook_general",
                   "https://discord.com/api/webhooks/123/abc", db)

    draft = bus.create_social_draft(1, "discord", "Hello Discord!", db_path=db)
    bus.update_draft_status(draft["draft_id"], "approved", db)

    mock_resp = MagicMock()
    mock_resp.status = 204
    mock_resp.read.return_value = b""
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = discord_bridge.post_approved_draft(draft["draft_id"], db)
        assert result["ok"] is True


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def test_status_unconfigured():
    """status() returns configured=False when no webhooks set."""
    db = _fresh_db()
    s = discord_bridge.status(db)
    assert s["configured"] is False
    assert s["total_drafts"] == 0


def test_status_configured():
    """status() returns channel info and draft counts."""
    db = _fresh_db()
    bus.set_config("discord_webhook_general", "https://hook.url", db)
    bus.create_social_draft(1, "discord", "Draft 1", db_path=db)
    bus.create_social_draft(1, "discord", "Draft 2", db_path=db)

    s = discord_bridge.status(db)
    assert s["configured"] is True
    assert s["channels"]["general"] is True
    assert s["total_drafts"] == 2
