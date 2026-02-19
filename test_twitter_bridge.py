"""Tests for twitter_bridge.py — credential management, draft flow, OAuth sig."""
import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import bus
import twitter_bridge


def _fresh_db():
    """Create a temp DB with full schema + bootstrap human agent."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db = Path(tmp.name)
    tmp.close()
    bus.init_db(db)
    # Insert a human agent so FK constraints pass on agent_id=1
    conn = bus.get_conn(db)
    conn.execute(
        "INSERT OR IGNORE INTO agents (id, name, agent_type, role, active) "
        "VALUES (1, 'TestHuman', 'human', 'human', 1)"
    )
    conn.commit()
    conn.close()
    return db


def test_setup_and_check_keys():
    """Store and retrieve Twitter API credentials."""
    db = _fresh_db()
    assert twitter_bridge.is_configured(db) is False

    twitter_bridge.setup_twitter_keys(
        api_key="test_key",
        api_secret="test_secret",
        access_token="test_token",
        access_secret="test_asecret",
        bearer_token="test_bearer",
        db_path=db,
    )
    assert twitter_bridge.is_configured(db) is True

    creds = twitter_bridge._get_creds(db)
    assert creds["twitter_api_key"] == "test_key"
    assert creds["twitter_api_secret"] == "test_secret"
    assert creds["twitter_access_token"] == "test_token"
    assert creds["twitter_access_secret"] == "test_asecret"
    assert creds["twitter_bearer_token"] == "test_bearer"


def test_missing_creds_raises():
    """Should raise ValueError when creds not set."""
    db = _fresh_db()
    try:
        twitter_bridge._get_creds(db)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Missing Twitter credential" in str(e)


def test_oauth_signature():
    """OAuth signature should be deterministic for same inputs."""
    creds = {
        "twitter_api_key": "consumer_key",
        "twitter_api_secret": "consumer_secret",
        "twitter_access_token": "token",
        "twitter_access_secret": "token_secret",
    }
    params = {"status": "Hello", "oauth_nonce": "abc123"}
    sig1 = twitter_bridge._oauth_signature("POST", "https://api.x.com/2/tweets", params, creds)
    sig2 = twitter_bridge._oauth_signature("POST", "https://api.x.com/2/tweets", params, creds)
    assert sig1 == sig2
    assert len(sig1) > 10  # Base64 encoded HMAC-SHA1


def test_draft_to_post_flow():
    """Full flow: create draft → approve → attempt post (mocked API)."""
    db = _fresh_db()

    # Setup keys
    twitter_bridge.setup_twitter_keys("k", "s", "t", "as", db_path=db)

    # Activate guard for social drafts
    key = bus.generate_activation_key("guard", "annual")
    bus.activate_guard(key, db_path=db)

    # Create a twitter draft
    draft = bus.create_social_draft(
        agent_id=1, platform="twitter",
        body="Hello from Crew Bus! 🚌", db_path=db)
    assert draft["ok"]
    draft_id = draft["draft_id"]

    # Draft should be in 'draft' status
    drafts = bus.get_social_drafts(platform="twitter", status="draft", db_path=db)
    assert len(drafts) >= 1

    # Approve the draft
    bus.update_draft_status(draft_id, "approved", db_path=db)

    # Mock the API call so we don't hit real Twitter
    mock_response = {"data": {"id": "1234567890", "text": "Hello from Crew Bus! 🚌"}}
    with patch.object(twitter_bridge, '_api_request', return_value=mock_response):
        result = twitter_bridge.post_approved_draft(draft_id, db_path=db)

    assert result["ok"]
    assert result["tweet_id"] == "1234567890"

    # Draft should now be 'posted'
    drafts = bus.get_social_drafts(platform="twitter", status="posted", db_path=db)
    assert any(d["id"] == draft_id for d in drafts)


def test_post_unapproved_draft_fails():
    """Cannot post a draft that hasn't been approved."""
    db = _fresh_db()
    twitter_bridge.setup_twitter_keys("k", "s", "t", "as", db_path=db)

    draft = bus.create_social_draft(agent_id=1, platform="twitter",
                                     body="Test", db_path=db)
    result = twitter_bridge.post_approved_draft(draft["draft_id"], db_path=db)
    assert not result.get("ok")
    assert "must be 'approved'" in result.get("error", "")


def test_status_check():
    """Status endpoint returns config state and draft counts."""
    db = _fresh_db()
    s = twitter_bridge.status(db)
    assert s["configured"] is False
    assert s["total_drafts"] == 0

    twitter_bridge.setup_twitter_keys("k", "s", "t", "as", db_path=db)
    bus.create_social_draft(1, "twitter", "test1", db_path=db)
    bus.create_social_draft(1, "twitter", "test2", db_path=db)

    s = twitter_bridge.status(db)
    assert s["configured"] is True
    assert s["total_drafts"] == 2
    assert s["draft_counts"].get("draft", 0) == 2


def test_percent_encode():
    """Percent encoding should handle special chars."""
    assert twitter_bridge._percent_encode("hello world") == "hello%20world"
    assert twitter_bridge._percent_encode("a+b=c") == "a%2Bb%3Dc"
    assert twitter_bridge._percent_encode("simple") == "simple"
