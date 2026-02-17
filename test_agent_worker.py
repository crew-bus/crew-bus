"""Tests for agent_worker — Ollama-powered AI responses."""

import json
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import bus
import agent_worker


def _setup_db():
    """Create a temp DB with human + crew boss agents (proper roles)."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = Path(tmp.name)
    tmp.close()
    bus.init_db(db_path=db_path)

    conn = bus.get_conn(db_path)
    # Create human
    conn.execute(
        "INSERT INTO agents (name, agent_type, role, status, active) "
        "VALUES (?, ?, ?, ?, ?)",
        ("Ryan", "human", "human", "active", 1),
    )
    # Create Crew Boss (right_hand) — parent is human
    conn.execute(
        "INSERT INTO agents (name, agent_type, role, parent_agent_id, status, active) "
        "VALUES (?, ?, ?, 1, ?, ?)",
        ("Crew Boss", "right_hand", "right_hand", "active", 1),
    )
    # Create Health Buddy (wellness) — parent is Crew Boss
    conn.execute(
        "INSERT INTO agents (name, agent_type, role, parent_agent_id, status, active) "
        "VALUES (?, ?, ?, 2, ?, ?)",
        ("Health Buddy", "wellness", "core_crew", "active", 1),
    )
    conn.commit()
    conn.close()
    return db_path


def test_call_ollama_mock():
    """Test that call_ollama formats the request correctly."""
    mock_response = json.dumps({
        "message": {"role": "assistant", "content": "Hey! How can I help?"}
    }).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_ctx = MagicMock()
        mock_ctx.read.return_value = mock_response
        mock_ctx.__enter__ = lambda s: s
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_ctx

        result = agent_worker.call_ollama("You are helpful.", "Hello!")
        assert result == "Hey! How can I help?"
        mock_urlopen.assert_called_once()


def test_process_queued_messages_mock():
    """Test that the worker picks up queued messages and generates replies."""
    db_path = _setup_db()

    # Send a message from human (id=1) to Crew Boss (id=2)
    bus.send_message(
        from_id=1, to_id=2,
        message_type="task", subject="Chat message",
        body="Hey what's up?", priority="normal",
        db_path=db_path,
    )

    # Verify message is queued
    conn = bus.get_conn(db_path)
    queued = conn.execute(
        "SELECT * FROM messages WHERE status='queued'"
    ).fetchall()
    conn.close()
    assert len(queued) == 1

    # Mock Ollama to return a canned response
    with patch.object(agent_worker, "call_ollama",
                      return_value="Hey! I'm doing great, thanks for asking!"):
        agent_worker._process_queued_messages(db_path)

    # Verify: original message (human->agent) marked delivered
    conn = bus.get_conn(db_path)
    original = conn.execute(
        "SELECT * FROM messages WHERE from_agent_id=1 AND to_agent_id=2"
    ).fetchone()
    assert original["status"] == "delivered"

    # Verify: reply message exists from agent to human
    replies = conn.execute(
        "SELECT * FROM messages WHERE from_agent_id=2 AND to_agent_id=1"
    ).fetchall()
    conn.close()
    assert len(replies) >= 1
    assert "great" in replies[-1]["body"].lower()


def test_worker_start_stop():
    """Test that the worker thread starts and stops cleanly."""
    db_path = _setup_db()

    with patch.object(agent_worker, "_process_queued_messages"):
        agent_worker.start_worker(db_path=db_path)
        assert agent_worker._worker_thread is not None
        assert agent_worker._worker_thread.is_alive()

        agent_worker.stop_worker()
        time.sleep(0.5)
        assert not agent_worker._worker_thread.is_alive()


def test_get_recent_chat():
    """Test chat history retrieval for Ollama context."""
    db_path = _setup_db()

    # Send from human to Crew Boss
    bus.send_message(1, 2, "task", "Chat", body="Hello!", db_path=db_path)
    # Insert a reply directly (simulating agent response)
    agent_worker._insert_reply_direct(db_path, 2, 1, "Hi there!")

    history = agent_worker._get_recent_chat(db_path, 1, 2)
    assert len(history) >= 2
    # First message should be from user (human)
    roles = [h["role"] for h in history]
    assert "user" in roles
    assert "assistant" in roles


def test_insert_reply_direct():
    """Test fallback direct reply insertion."""
    db_path = _setup_db()

    agent_worker._insert_reply_direct(db_path, 2, 1, "Hello from Crew Boss!")

    conn = bus.get_conn(db_path)
    msgs = conn.execute(
        "SELECT * FROM messages WHERE from_agent_id=2 AND to_agent_id=1"
    ).fetchall()
    conn.close()
    assert len(msgs) == 1
    assert msgs[0]["body"] == "Hello from Crew Boss!"
    assert msgs[0]["status"] == "delivered"


def test_system_prompts_exist():
    """All core agent types should have system prompts."""
    for agent_type in ("right_hand", "security", "wellness", "strategy", "financial"):
        assert agent_type in agent_worker.SYSTEM_PROMPTS
        assert len(agent_worker.SYSTEM_PROMPTS[agent_type]) > 20
