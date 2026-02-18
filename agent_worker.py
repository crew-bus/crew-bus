"""
crew-bus Agent Worker — AI brain for all agents.

Background thread that:
  1. Polls the messages table for queued messages TO agents FROM the human
  2. Sends them to the agent's configured LLM backend
  3. Writes the agent's reply back as a new message in the bus

Supports multiple backends:
  - Ollama (local, default fallback)
  - Kimi K2.5 (OpenAI-compatible API via api.moonshot.ai)
  - Any OpenAI-compatible endpoint

Per-agent model selection: each agent can have its own model field.
Global default stored in crew_config table ('default_model' key).
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
KIMI_API_URL = "https://api.moonshot.ai/v1/chat/completions"
KIMI_DEFAULT_MODEL = "kimi-k2.5"
POLL_INTERVAL = 0.5  # seconds between queue checks

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
    "manager": (
        "You are a team manager in the user's personal AI crew. "
        "You coordinate your team's workers and report up to Crew Boss. "
        "Keep responses short, organized, and helpful."
    ),
}

DEFAULT_PROMPT = (
    "You are a helpful AI assistant that is part of the user's personal AI crew. "
    "Keep responses short, warm, and helpful."
)


def _build_system_prompt(agent_type: str, agent_name: str,
                         description: str = "") -> str:
    """Build a system prompt for an agent, using its DB description if available.

    Priority: agent description from DB > hardcoded type prompt > default.
    This lets any crew YAML define agent personalities that carry through.
    """
    # If the agent has a description in the DB, use it as the core prompt
    if description and len(description) > 20:
        return (
            f"You are {agent_name}, part of the user's personal AI crew (Crew Bus). "
            f"{description} "
            "Keep responses short, warm, and helpful (2-4 sentences usually). "
            "Use casual, human language — no corporate jargon."
        )

    # Fall back to hardcoded type prompts
    return SYSTEM_PROMPTS.get(agent_type, DEFAULT_PROMPT)


# ---------------------------------------------------------------------------
# LLM callers — routes to the right backend per agent
# ---------------------------------------------------------------------------

def _call_ollama(messages: list, model: str = OLLAMA_MODEL) -> str:
    """Call local Ollama and return assistant response text."""
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": 1024},
    }).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_URL, data=payload,
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


def _call_kimi(messages: list, model: str = KIMI_DEFAULT_MODEL,
               api_key: str = "") -> str:
    """Call Kimi K2.5 API (OpenAI-compatible). Returns assistant response."""
    if not api_key:
        return "(Kimi API key not configured. Set it via Wizard or crew_config.)"

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": 1,
        "max_tokens": 1024,
    }).encode("utf-8")

    req = urllib.request.Request(
        KIMI_API_URL, data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
            return "(Empty response from Kimi)"
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        return f"(Kimi API error {e.code}: {body})"
    except Exception as e:
        return f"(Error calling Kimi: {e})"


def _call_openai_compat(messages: list, model: str, api_url: str,
                        api_key: str = "") -> str:
    """Call any OpenAI-compatible endpoint. Fallback for custom setups."""
    if not api_key:
        return "(API key not configured for this model.)"

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": 0.7,
        "max_tokens": 512,
    }).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(api_url, data=payload, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
            return "(Empty response)"
    except Exception as e:
        return f"(Error: {e})"


def call_llm(system_prompt: str, user_message: str,
             chat_history: Optional[list] = None,
             model: str = "", db_path: Path = None) -> str:
    """Route to the correct LLM backend based on model string.

    Model resolution order:
      1. Per-agent model field (passed in)
      2. crew_config 'default_model' key
      3. Ollama fallback (llama3.2)

    Model string format:
      - "" or "ollama:*" or plain name → Ollama
      - "kimi" or "kimi:*" → Kimi K2.5 API
      - "openai:model@url" → custom OpenAI-compatible
    """
    messages = [{"role": "system", "content": system_prompt}]
    if chat_history:
        for msg in chat_history[-6:]:
            messages.append(msg)
    messages.append({"role": "user", "content": user_message})

    # Resolve model
    if not model:
        model = bus.get_config("default_model", "", db_path=db_path) if db_path else ""

    if not model or model == "ollama":
        return _call_ollama(messages)

    # Kimi K2.5
    if model.startswith("kimi"):
        kimi_model = KIMI_DEFAULT_MODEL
        if ":" in model:
            kimi_model = model.split(":", 1)[1]
        api_key = bus.get_config("kimi_api_key", "", db_path=db_path) if db_path else ""
        return _call_kimi(messages, model=kimi_model, api_key=api_key)

    # Ollama with specific model name (e.g. "ollama:mistral")
    if model.startswith("ollama:"):
        return _call_ollama(messages, model=model.split(":", 1)[1])

    # Generic: assume Ollama local model name
    return _call_ollama(messages, model=model)


# Keep legacy name for backwards compat with tests
def call_ollama(system_prompt: str, user_message: str,
                chat_history: Optional[list] = None,
                model: str = OLLAMA_MODEL) -> str:
    """Legacy wrapper — routes through call_llm."""
    messages = [{"role": "system", "content": system_prompt}]
    if chat_history:
        for msg in chat_history[-6:]:
            messages.append(msg)
    messages.append({"role": "user", "content": user_message})
    return _call_ollama(messages, model=model)


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
                   a.agent_type, a.name, a.model
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
        agent_name = row["name"]
        agent_model = row["model"] if row["model"] else ""
        user_text = row["body"] if row["body"] else row["subject"]

        if not user_text:
            _mark_delivered(db_path, msg_id)
            continue

        # Get agent description from DB for dynamic prompts
        desc = ""
        try:
            _conn = bus.get_conn(db_path)
            _row = _conn.execute("SELECT description FROM agents WHERE id=?",
                                 (agent_id,)).fetchone()
            if _row:
                desc = _row["description"] or ""
            _conn.close()
        except Exception:
            pass

        # Build system prompt — uses description if available
        system_prompt = _build_system_prompt(agent_type, agent_name, desc)

        # Get recent chat history for context
        chat_history = _get_recent_chat(db_path, human_id, agent_id)

        # Call LLM — routes to Kimi/Ollama/etc based on agent's model field
        reply = call_llm(system_prompt, user_text, chat_history,
                         model=agent_model, db_path=db_path)

        if reply:
            # Execute any wizard_action commands embedded in the reply
            clean_reply = _execute_wizard_actions(reply, db_path)

            # Insert reply directly — always works, bypasses routing rules
            _insert_reply_direct(db_path, agent_id, human_id, clean_reply)

        # Mark original message as delivered
        _mark_delivered(db_path, msg_id)


import re as _re

def _execute_wizard_actions(reply: str, db_path: Path) -> str:
    """Parse and execute wizard_action JSON commands from an LLM reply.

    The Wizard agent can embed action commands in its replies like:
      {"wizard_action": "set_config", "key": "kimi_api_key", "value": "sk-..."}
      {"wizard_action": "create_agent", "name": "Muse", ...}

    Actions are executed, and the JSON blocks are stripped from the
    reply text so the human only sees the conversational part.
    """
    # Find all JSON-like blocks in the reply
    pattern = r'\{[^{}]*"wizard_action"[^{}]*\}'
    matches = _re.findall(pattern, reply)

    if not matches:
        return reply

    for raw in matches:
        try:
            action = json.loads(raw)
        except json.JSONDecodeError:
            continue

        cmd = action.get("wizard_action", "")

        if cmd == "set_config":
            key = action.get("key", "")
            value = action.get("value", "")
            if key and value:
                bus.set_config(key, value, db_path=db_path)
                print(f"[wizard] config set: {key}")

        elif cmd == "create_agent":
            result = bus.create_agent(
                name=action.get("name", ""),
                agent_type=action.get("agent_type", "worker"),
                description=action.get("description", ""),
                parent_name=action.get("parent", "Crew-Boss"),
                model=action.get("model", ""),
                db_path=db_path,
            )
            if result.get("ok"):
                print(f"[wizard] created agent: {action.get('name')}")
            else:
                print(f"[wizard] agent error: {result.get('error')}")

        elif cmd == "create_team":
            workers = action.get("workers", [])
            w_names = [w.get("name", "") for w in workers]
            w_descs = [w.get("description", "") for w in workers]
            result = bus.create_team(
                team_name=action.get("name", ""),
                worker_names=w_names,
                worker_descriptions=w_descs,
                model=action.get("model", ""),
                db_path=db_path,
            )
            if result.get("ok"):
                print(f"[wizard] created team: {action.get('name')}")
            else:
                print(f"[wizard] team error: {result.get('error')}")

        elif cmd == "deactivate_agent":
            agent_name = action.get("name", "")
            if agent_name:
                try:
                    agent = bus.get_agent_by_name(agent_name, db_path=db_path)
                    if agent:
                        bus.deactivate_agent(agent["id"], db_path=db_path)
                        print(f"[wizard] deactivated agent: {agent_name}")
                    else:
                        print(f"[wizard] agent not found: {agent_name}")
                except Exception as e:
                    print(f"[wizard] deactivate error: {e}")

        elif cmd == "terminate_agent":
            agent_name = action.get("name", "")
            if agent_name:
                try:
                    agent = bus.get_agent_by_name(agent_name, db_path=db_path)
                    if agent:
                        bus.terminate_agent(agent["id"], db_path=db_path)
                        print(f"[wizard] terminated agent: {agent_name}")
                    else:
                        print(f"[wizard] agent not found: {agent_name}")
                except Exception as e:
                    print(f"[wizard] terminate error: {e}")

        elif cmd == "set_agent_model":
            agent_name = action.get("name", "")
            new_model = action.get("model", "")
            if agent_name and new_model:
                try:
                    conn = bus.get_conn(db_path)
                    conn.execute(
                        "UPDATE agents SET model=?, updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') "
                        "WHERE name=?", (new_model, agent_name))
                    conn.commit()
                    conn.close()
                    print(f"[wizard] set model for {agent_name}: {new_model}")
                except Exception as e:
                    print(f"[wizard] set_agent_model error: {e}")

    # Strip action blocks from reply so human sees clean text
    clean = reply
    for raw in matches:
        clean = clean.replace(raw, "")
    # Clean up extra whitespace left behind
    clean = _re.sub(r'\n{3,}', '\n\n', clean).strip()
    return clean


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
        default_model = bus.get_config("default_model", "ollama", db_path=db_path)
        print(f"Agent worker started (default: {default_model}, poll: {POLL_INTERVAL}s)")
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
