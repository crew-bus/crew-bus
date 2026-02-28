"""Tests for reddit_bridge.py — Reddit OAuth, post submission, comment replies."""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import bus
import reddit_bridge


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
    conn.commit()
    conn.close()
    return db


def _setup_creds(db):
    """Set Reddit credentials in crew_config."""
    reddit_bridge.setup_reddit_keys(
        client_id="test_client_id",
        client_secret="test_client_secret",
        username="test_user",
        password="test_pass",
        db_path=db,
    )


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------

def test_setup_reddit_keys():
    """setup_reddit_keys stores all four credentials."""
    db = _fresh_db()
    result = reddit_bridge.setup_reddit_keys(
        "cid", "csecret", "uname", "pwd", db)
    assert result["ok"] is True

    assert bus.get_config("reddit_client_id", "", db) == "cid"
    assert bus.get_config("reddit_client_secret", "", db) == "csecret"
    assert bus.get_config("reddit_username", "", db) == "uname"
    assert bus.get_config("reddit_password", "", db) == "pwd"


def test_is_configured_false():
    """is_configured returns False when creds not set."""
    db = _fresh_db()
    assert reddit_bridge.is_configured(db) is False


def test_is_configured_true():
    """is_configured returns True when all creds are set."""
    db = _fresh_db()
    _setup_creds(db)
    assert reddit_bridge.is_configured(db) is True


def test_get_creds_missing():
    """_get_creds raises ValueError when a credential is missing."""
    db = _fresh_db()
    bus.set_config("reddit_client_id", "cid", db)
    # Missing other keys
    try:
        reddit_bridge._get_creds(db)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Missing Reddit credential" in str(e)


def test_get_creds_complete():
    """_get_creds returns all credentials when set."""
    db = _fresh_db()
    _setup_creds(db)
    creds = reddit_bridge._get_creds(db)
    assert creds["reddit_client_id"] == "test_client_id"
    assert creds["reddit_username"] == "test_user"


# ---------------------------------------------------------------------------
# OAuth2 token
# ---------------------------------------------------------------------------

def test_get_token_cached():
    """_get_token returns cached token if not expired."""
    original_token = reddit_bridge._access_token
    original_expires = reddit_bridge._token_expires

    reddit_bridge._access_token = "cached_token"
    reddit_bridge._token_expires = time.time() + 3600

    token = reddit_bridge._get_token()
    assert token == "cached_token"

    reddit_bridge._access_token = original_token
    reddit_bridge._token_expires = original_expires


def test_get_token_refresh():
    """_get_token fetches a new token when expired."""
    db = _fresh_db()
    _setup_creds(db)

    original_token = reddit_bridge._access_token
    original_expires = reddit_bridge._token_expires
    reddit_bridge._access_token = None
    reddit_bridge._token_expires = 0

    token_resp = json.dumps({
        "access_token": "new_token_123",
        "expires_in": 3600,
        "token_type": "bearer",
    }).encode()

    mock_ctx = MagicMock()
    mock_ctx.read.return_value = token_resp
    mock_ctx.__enter__ = lambda s: s
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_ctx):
        token = reddit_bridge._get_token(db)
        assert token == "new_token_123"
        assert reddit_bridge._access_token == "new_token_123"

    reddit_bridge._access_token = original_token
    reddit_bridge._token_expires = original_expires


def test_get_token_auth_failure():
    """_get_token raises ValueError on authentication failure."""
    db = _fresh_db()
    _setup_creds(db)

    original_token = reddit_bridge._access_token
    original_expires = reddit_bridge._token_expires
    reddit_bridge._access_token = None
    reddit_bridge._token_expires = 0

    import urllib.error
    err_body = MagicMock()
    err_body.read.return_value = b"Invalid credentials"
    err = urllib.error.HTTPError(
        "http://fake", 401, "Unauthorized", {}, err_body)

    with patch("urllib.request.urlopen", side_effect=err):
        try:
            reddit_bridge._get_token(db)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "auth failed" in str(e).lower()

    reddit_bridge._access_token = original_token
    reddit_bridge._token_expires = original_expires


# ---------------------------------------------------------------------------
# _api_request
# ---------------------------------------------------------------------------

def test_api_request_get():
    """_api_request makes authenticated GET requests."""
    db = _fresh_db()
    _setup_creds(db)

    resp_data = json.dumps({"data": {"children": []}}).encode()
    mock_ctx = MagicMock()
    mock_ctx.read.return_value = resp_data
    mock_ctx.__enter__ = lambda s: s
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch.object(reddit_bridge, "_get_token", return_value="fake_token"), \
         patch("urllib.request.urlopen", return_value=mock_ctx) as mock_url:
        result = reddit_bridge._api_request("GET", "/r/test/hot", db_path=db)
        assert "data" in result

        # Verify auth header
        req = mock_url.call_args[0][0]
        assert "bearer fake_token" in req.get_header("Authorization")


def test_api_request_http_error():
    """_api_request handles HTTP errors from Reddit API."""
    db = _fresh_db()
    _setup_creds(db)

    import urllib.error
    err_body = MagicMock()
    err_body.read.return_value = b"Forbidden"
    err = urllib.error.HTTPError(
        "http://fake", 403, "Forbidden", {}, err_body)

    with patch.object(reddit_bridge, "_get_token", return_value="token"), \
         patch("urllib.request.urlopen", side_effect=err):
        result = reddit_bridge._api_request("GET", "/api/me", db_path=db)
        assert result["ok"] is False
        assert "403" in result["error"]


def test_api_request_network_error():
    """_api_request handles connection errors."""
    db = _fresh_db()
    _setup_creds(db)

    with patch.object(reddit_bridge, "_get_token", return_value="token"), \
         patch("urllib.request.urlopen",
               side_effect=ConnectionError("refused")):
        result = reddit_bridge._api_request("GET", "/api/me", db_path=db)
        assert result["ok"] is False
        assert "refused" in result["error"]


# ---------------------------------------------------------------------------
# submit_post
# ---------------------------------------------------------------------------

def test_submit_post_text():
    """submit_post sends a text post and returns URL."""
    db = _fresh_db()
    _setup_creds(db)

    api_resp = {
        "json": {
            "data": {"url": "https://reddit.com/r/test/comments/abc/my_post"},
            "errors": [],
        }
    }

    with patch.object(reddit_bridge, "_api_request", return_value=api_resp):
        result = reddit_bridge.submit_post(
            "test", "My Post", "This is the body", db_path=db)
        assert result["ok"] is True
        assert result["url"] == "https://reddit.com/r/test/comments/abc/my_post"
        assert result["subreddit"] == "test"


def test_submit_post_link():
    """submit_post sends a link post with URL."""
    db = _fresh_db()
    _setup_creds(db)

    api_resp = {
        "json": {
            "data": {"url": "https://reddit.com/r/test/comments/def/link"},
            "errors": [],
        }
    }

    with patch.object(reddit_bridge, "_api_request", return_value=api_resp) as mock_api:
        result = reddit_bridge.submit_post(
            "test", "Link Post", url="https://example.com", db_path=db)
        assert result["ok"] is True

        # Verify kind=link was sent
        call_data = mock_api.call_args[0][2]
        assert call_data["kind"] == "link"
        assert call_data["url"] == "https://example.com"


def test_submit_post_with_errors():
    """submit_post returns error when Reddit returns errors."""
    db = _fresh_db()
    _setup_creds(db)

    api_resp = {
        "json": {
            "data": {},
            "errors": [["SUBREDDIT_NOTALLOWED", "not allowed to post", "sr"]],
        }
    }

    with patch.object(reddit_bridge, "_api_request", return_value=api_resp):
        result = reddit_bridge.submit_post("restricted", "Post", db_path=db)
        assert result["ok"] is False
        assert "SUBREDDIT_NOTALLOWED" in result["error"]


# ---------------------------------------------------------------------------
# reply_to_post
# ---------------------------------------------------------------------------

def test_reply_to_post():
    """reply_to_post sends a comment reply."""
    db = _fresh_db()
    _setup_creds(db)

    with patch.object(reddit_bridge, "_api_request",
                      return_value={"ok": True}) as mock_api:
        result = reddit_bridge.reply_to_post("t3_abc123", "Great post!", db)
        mock_api.assert_called_once()
        call_data = mock_api.call_args[0][2]
        assert call_data["thing_id"] == "t3_abc123"
        assert call_data["text"] == "Great post!"


# ---------------------------------------------------------------------------
# delete_post
# ---------------------------------------------------------------------------

def test_delete_post():
    """delete_post sends delete request for a thing."""
    db = _fresh_db()
    _setup_creds(db)

    with patch.object(reddit_bridge, "_api_request",
                      return_value={"ok": True}) as mock_api:
        result = reddit_bridge.delete_post("t3_abc123", db)
        mock_api.assert_called_once()
        call_data = mock_api.call_args[0][2]
        assert call_data["id"] == "t3_abc123"


# ---------------------------------------------------------------------------
# Draft flow
# ---------------------------------------------------------------------------

def test_post_approved_draft_not_found():
    """post_approved_draft returns error for missing draft."""
    db = _fresh_db()
    result = reddit_bridge.post_approved_draft(99999, db)
    assert result["ok"] is False
    assert "not found" in result["error"].lower()


def test_post_approved_draft_not_approved():
    """post_approved_draft rejects non-approved drafts."""
    db = _fresh_db()
    draft = bus.create_social_draft(
        1, "reddit", "Test body", title="Test Title",
        target="r/test", db_path=db)
    result = reddit_bridge.post_approved_draft(draft["draft_id"], db)
    assert result["ok"] is False
    assert "must be 'approved'" in result["error"]


def test_post_approved_draft_no_target():
    """post_approved_draft fails when draft has no target subreddit."""
    db = _fresh_db()
    draft = bus.create_social_draft(
        1, "reddit", "Test body", title="Test", db_path=db)
    bus.update_draft_status(draft["draft_id"], "approved", db)
    result = reddit_bridge.post_approved_draft(draft["draft_id"], db)
    assert result["ok"] is False
    assert "subreddit" in result["error"].lower()


def test_post_approved_draft_success():
    """post_approved_draft posts and marks draft as posted."""
    db = _fresh_db()
    _setup_creds(db)

    draft = bus.create_social_draft(
        1, "reddit", "Test body", title="Test Post",
        target="r/opensource", db_path=db)
    bus.update_draft_status(draft["draft_id"], "approved", db)

    api_resp = {
        "json": {
            "data": {"url": "https://reddit.com/r/opensource/comments/xyz"},
            "errors": [],
        }
    }

    with patch.object(reddit_bridge, "_api_request", return_value=api_resp):
        result = reddit_bridge.post_approved_draft(draft["draft_id"], db)
        assert result["ok"] is True

    # Verify draft status updated
    drafts = bus.get_social_drafts(
        platform="reddit", status="posted", db_path=db)
    assert any(d["id"] == draft["draft_id"] for d in drafts)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def test_status_unconfigured():
    """status() returns configured=False when creds not set."""
    db = _fresh_db()
    s = reddit_bridge.status(db)
    assert s["configured"] is False
    assert s["total_drafts"] == 0


def test_status_configured():
    """status() returns draft counts when configured."""
    db = _fresh_db()
    _setup_creds(db)
    bus.create_social_draft(1, "reddit", "Draft 1",
                            target="r/test", db_path=db)
    bus.create_social_draft(1, "reddit", "Draft 2",
                            target="r/test", db_path=db)

    s = reddit_bridge.status(db)
    assert s["configured"] is True
    assert s["total_drafts"] == 2
