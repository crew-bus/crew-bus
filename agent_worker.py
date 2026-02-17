"""
crew-bus Agent Worker — Ollama-powered AI brain for all agents.

Background thread that:
  1. Polls the messages table for queued messages TO agents FROM the human
  2. Sends them to Ollama (local LLM) with agent-specific system prompts
  3. Writes the agent's reply back as a new message in the bus

100% local. No cloud. No API keys. Just Ollama on your machine.
"""

import json
import sqlite3
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import bus

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3.2"
POLL_INTERVAL = 2  # seconds between queue checks

# ---------------------------------------------------------------------------
# Agent system prompts — warm, friendly, personality-first
# ---------------------------------------------------------------------------

SYSTEM_PROMPTS = {
    "right_hand": (
        "You are Crew Boss, the user's friendly AI right-hand assistant. "
        "You have warm big-sister energy — caring, capable, and fun. "
        "You handle 80% of everything so the human doesn't have to. "
        "Keep responses short, warm, and helpful (2-4 sentences usually). "
        "Use casual language, emoji occasionally, and always be encouraging. "
        "If you don't know something, say so honestly. "
        "You're part of Crew Bus — the user's personal local AI crew."
    ),
    "security": (
        "You are Friend & Family Helper, part of the user's personal AI crew. "
        "You help with family coordination — shared chores, kid reminders, "
        "homework nudges, family calendar, and keeping everyone in the loop. "
        "You have warm, organized energy. Keep responses short and helpful. "
        "Use casual friendly language."
    ),
    "wellness": (
        "You are Health Buddy, part of the user's personal AI crew. "
        "You watch the user's energy and wellbeing with gentle care. "
        "You give soft burnout nudges, celebrate wins, and remind them "
        "to take breaks. Never preachy — just a caring friend. "
        "Keep responses short, warm, and supportive."
    ),
    "strategy": (
        "You are Growth Coach, part of the user's personal AI crew. "
        "You help the user build great habits, break big ideas into small steps, "
        "and stay on track with goals. Encouraging and practical. "
        "Keep responses short and actionable."
    ),
    "financial": (
        "You are Life Assistant, part of the user's personal AI crew. "
        "You help with daily logistics — meals, shopping lists, errands, "
        "appointments, and keeping life organized. "
        "Keep responses short, practical, and friendly."
    ),
}

DEFAULT_PROMPT = (
    "You are a helpful AI assistant that is part of the user's personal AI crew. "
    "Keep responses short, warm, and helpful."
)


# ---------------------------------------------------------------------------
# Ollama caller
# ---------------------------------------------------------------------------

def call_ollama(system_prompt: str, user_message: str,
                chat_history: Optional[list] = None,
                model: str = OLLAMA_MODEL) -> str:
    """Call local Ollama and return the assistant response text."""
    messages = [{"role": "system", "content": system_prompt}]

    # Add recent chat history for context (last few exchanges)
    if chat_history:
        for msg in chat_history[-6:]:  # last 3 exchanges max
            messages.append(msg)

    messages.append({"role": "user", "content": user_message})

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 256,  # keep replies concise
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("message", {}).get("content", "").strip()
    except urllib.error.URLError as e:
        return f"(Ollama not reachable — is it running? Error: {e})"
    except Exception as e:
        return f"(Error generating response: {e})"


# ---------------------------------------------------------------------------
# Chat history helper
# ---------------------------------------------------------------------------

def _get_recent_chat(db_path: Path, human_id: int, agent_id: int,
                     limit: int = 6) -> list:
    """Fetch recent chat messages and format for Ollama context."""
    conn = bus.get_conn(db_path)
    try:
        rows = conn.execute("""
            SELECT from_agent_id, body, subject
            FROM messages
            WHERE ((from_agent_id=? AND to_agent_id=?)
                OR (from_agent_id=? AND to_agent_id=?))
              AND body IS NOT NULL AND body != ''
            ORDER BY created_at DESC LIMIT ?
        """, (human_id, agent_id, agent_id, human_id, limit)).fetchall()
    finally:
        conn.close()

    history = []
    for row in reversed(rows):  # oldest first
        role = "user" if row["from_agent_id"] == human_id else "assistant"
        text = row["body"] if row["body"] else row["subject"]
        if text:
            history.append({"role": role, "content": text})
    return history


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------

def _process_queued_messages(db_path: Path):
    """Find queued messages from any human to agents, generate replies."""
    conn = bus.get_conn(db_path)
    try:
        # Find ALL queued messages from ANY human to ANY non-human agent
        rows = conn.execute("""
            SELECT m.id, m.from_agent_id, m.to_agent_id, m.body, m.subject,
                   a.agent_type, a.name
            FROM messages m
            JOIN agents a ON m.to_agent_id = a.id
            JOIN agents h ON m.from_agent_id = h.id
            WHERE h.agent_type = 'human'
              AND m.status = 'queued'
              AND a.agent_type != 'human'
            ORDER BY m.created_at ASC
        """).fetchall()
    finally:
        conn.close()

    for row in rows:
        msg_id = row["id"]
        human_id = row["from_agent_id"]
        agent_id = row["to_agent_id"]
        agent_type = row["agent_type"]
        user_text = row["body"] if row["body"] else row["subject"]

        if not user_text:
            _mark_delivered(db_path, msg_id)
            continue

        # Get system prompt for this agent type
        system_prompt = SYSTEM_PROMPTS.get(agent_type, DEFAULT_PROMPT)

        # Get recent chat history for context
        chat_history = _get_recent_chat(db_path, human_id, agent_id)

        # Call Ollama
        reply = call_ollama(system_prompt, user_text, chat_history)

        if reply:
            # Insert reply directly — always works, bypasses routing rules
            _insert_reply_direct(db_path, agent_id, human_id, reply)

        # Mark original message as delivered
        _mark_delivered(db_path, msg_id)


def _mark_delivered(db_path: Path, message_id: int):
    """Mark a message as delivered so we don't re-process it."""
    conn = bus.get_conn(db_path)
    try:
        conn.execute(
            "UPDATE messages SET status='delivered', delivered_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), message_id),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_reply_direct(db_path: Path, from_id: int, to_id: int, body: str):
    """Insert a reply directly (bypass routing rules for chat responses)."""
    conn = bus.get_conn(db_path)
    try:
        conn.execute(
            "INSERT INTO messages (from_agent_id, to_agent_id, message_type, "
            "subject, body, priority, status) VALUES (?, ?, 'report', "
            "'Chat reply', ?, 'normal', 'delivered')",
            (from_id, to_id, body),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Background thread
# ---------------------------------------------------------------------------

_worker_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()


def start_worker(db_path: Path = None):
    """Start the background agent worker thread."""
    global _worker_thread
    if db_path is None:
        db_path = bus.DB_PATH

    if _worker_thread and _worker_thread.is_alive():
        return  # already running

    _stop_event.clear()

    def _loop():
        print(f"Agent worker started (model: {OLLAMA_MODEL}, poll: {POLL_INTERVAL}s)")
        while not _stop_event.is_set():
            try:
                _process_queued_messages(db_path)
            except Exception as e:
                print(f"[agent_worker] error: {e}")
            _stop_event.wait(POLL_INTERVAL)
        print("Agent worker stopped.")

    _worker_thread = threading.Thread(target=_loop, daemon=True, name="agent-worker")
    _worker_thread.start()


def stop_worker():
    """Stop the background agent worker thread."""
    _stop_event.set()
    if _worker_thread:
        _worker_thread.join(timeout=5)
