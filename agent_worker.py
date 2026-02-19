"""
crew-bus Agent Worker — AI brain for all agents.

Background thread that:
  1. Polls the messages table for queued messages TO agents FROM the human
  2. Sends them to the agent's configured LLM backend
  3. Writes the agent's reply back as a new message in the bus

Supports multiple backends:
  - Ollama (local, default fallback)
  - Kimi K2.5 (api.moonshot.ai)
  - Claude (Anthropic Messages API)
  - OpenAI (GPT-4o, etc.)
  - Groq (Llama 3.3 70B, etc.)
  - Gemini (Google AI)
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

# Provider registry — model_prefix → (api_url, default_model, config_key_for_api_key)
PROVIDERS = {
    "kimi":    ("https://api.moonshot.ai/v1/chat/completions",   "kimi-k2.5",            "kimi_api_key"),
    "claude":  ("https://api.anthropic.com/v1/messages",         "claude-sonnet-4-5-20250929", "claude_api_key"),
    "openai":  ("https://api.openai.com/v1/chat/completions",    "gpt-4o-mini",          "openai_api_key"),
    "groq":    ("https://api.groq.com/openai/v1/chat/completions", "llama-3.3-70b-versatile", "groq_api_key"),
    "gemini":  ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "gemini-2.0-flash", "gemini_api_key"),
    "ollama":  (OLLAMA_URL,                                       OLLAMA_MODEL,           ""),
}

# ---------------------------------------------------------------------------
# INTEGRITY.md — loaded once at import, injected into every prompt
# ---------------------------------------------------------------------------

_INTEGRITY_PATH = Path(__file__).parent / "INTEGRITY.md"
_INTEGRITY_RULES = ""

def _load_integrity_rules() -> str:
    """Load INTEGRITY.md rules for prompt injection.

    Extracts the actionable rules (sections 1-5) and strips markdown
    formatting down to compact text. Cached at module level.
    """
    global _INTEGRITY_RULES
    if _INTEGRITY_RULES:
        return _INTEGRITY_RULES
    try:
        raw = _INTEGRITY_PATH.read_text(encoding="utf-8")
        # Extract everything from "## 1." to "## Enforcement" (the rules only)
        lines = raw.split("\n")
        rule_lines = []
        capture = False
        for line in lines:
            if line.startswith("## 1."):
                capture = True
            if line.startswith("## Enforcement"):
                break
            if capture:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    rule_lines.append(stripped)
                elif stripped.startswith("## "):
                    rule_lines.append(stripped.replace("## ", "").upper() + ":")
        _INTEGRITY_RULES = "\n".join(rule_lines)
    except FileNotFoundError:
        _INTEGRITY_RULES = ""
    return _INTEGRITY_RULES

# Pre-load at import
_load_integrity_rules()

# ---------------------------------------------------------------------------
# CREW_CHARTER.md — loaded once, injected into all subordinate agent prompts
# ---------------------------------------------------------------------------

_CHARTER_PATH = Path(__file__).parent / "CREW_CHARTER.md"
_CHARTER_RULES = ""

# Agent types that are NOT subordinates (they don't get the charter)
_CHARTER_EXEMPT = {"human", "right_hand"}


def _load_charter_rules() -> str:
    """Load CREW_CHARTER.md rules for subordinate agent prompt injection.

    Extracts the actionable rules (sections 1-6) and strips markdown
    formatting down to compact text. Cached at module level.
    """
    global _CHARTER_RULES
    if _CHARTER_RULES:
        return _CHARTER_RULES
    try:
        raw = _CHARTER_PATH.read_text(encoding="utf-8")
        lines = raw.split("\n")
        rule_lines = []
        capture = False
        for line in lines:
            if line.startswith("## 1."):
                capture = True
            if line.startswith("## Enforcement"):
                break
            if capture:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    rule_lines.append(stripped)
                elif stripped.startswith("## "):
                    rule_lines.append(stripped.replace("## ", "").upper() + ":")
        _CHARTER_RULES = "\n".join(rule_lines)
    except FileNotFoundError:
        _CHARTER_RULES = ""
    return _CHARTER_RULES


# Pre-load at import
_load_charter_rules()

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
    "guardian": (
        "You are Guardian, the always-on protector and setup guide for Crew Bus. "
        "You help new users set up their crew AND you watch for threats 24/7. "
        "You have special system knowledge that updates every 24 hours. "
        "You scan skills for safety, protect the human's data, and help everyone "
        "understand new features. Keep responses short, warm, and vigilant."
    ),
    "security": (
        "You are Guard, the security and safety agent in the user's personal AI crew. "
        "You watch for threats — digital, financial, reputation, physical. "
        "You scan for risks, protect the human's data and privacy, "
        "and alert Crew Boss when something needs attention. "
        "Keep responses short, clear, and calm. Be vigilant but not paranoid."
    ),
    "wellness": (
        "You are Wellness, the wellbeing agent in the user's personal AI crew. "
        "You watch the user's energy and wellbeing with gentle care. "
        "You give soft burnout nudges, celebrate wins, and remind them "
        "to take breaks. Never preachy — just a caring friend. "
        "Keep responses short, warm, and supportive."
    ),
    "strategy": (
        "You are Ideas, the strategy and brainstorming agent in the user's personal AI crew. "
        "You help the user brainstorm, build great habits, break big ideas into small steps, "
        "and stay on track with goals. Encouraging and practical. "
        "Keep responses short and actionable."
    ),
    "financial": (
        "You are Wallet, the financial helper in the user's personal AI crew. "
        "You help track spending, budget, invoices, and financial planning. "
        "Keep responses short, practical, and clear. "
        "Never give investment advice — just help organize financial information."
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
                         description: str = "",
                         agent_id: int = None,
                         db_path: Path = None) -> str:
    """Build a system prompt for an agent with memory and skill injection.

    Priority: agent description from DB > hardcoded type prompt > default.
    Then appends: active skills + persistent memories (capped at ~3200 chars).
    """
    # --- Base prompt ---
    if description and len(description) > 20:
        base = (
            f"You are {agent_name}, part of the user's personal AI crew (Crew Bus). "
            f"{description} "
            "Keep responses short, warm, and helpful (2-4 sentences usually). "
            "Use casual, human language — no corporate jargon."
        )
    else:
        base = SYSTEM_PROMPTS.get(agent_type, DEFAULT_PROMPT)

    if not agent_id or not db_path:
        return base

    parts = [base]

    # --- Inject INTEGRITY rules (non-negotiable, every agent, every prompt) ---
    integrity = _load_integrity_rules()
    if integrity:
        parts.append(
            "INTEGRITY RULES (non-negotiable — these override everything else):\n"
            + integrity
        )

    # --- Inject CREW CHARTER (subordinate agents only — not right_hand) ---
    if agent_type not in _CHARTER_EXEMPT:
        charter = _load_charter_rules()
        if charter:
            parts.append(
                "CREW CHARTER (your constitution — violation = security event):\n"
                + charter
            )

    # --- Inject skills ---
    try:
        skills = bus.get_agent_skills(agent_id, db_path=db_path)
        if skills:
            parts.append(_format_skills_for_prompt(skills))
    except Exception:
        pass

    # --- Inject memories ---
    try:
        memories = bus.get_agent_memories(agent_id, limit=15, db_path=db_path)
        if memories:
            parts.append(_format_memories_for_prompt(memories))
    except Exception:
        pass

    # Token budget guard: Guardian gets 7000 chars (knowledge + integrity),
    # all others get ~4000 chars (integrity rules add ~800 chars)
    max_chars = 7000 if agent_type == "guardian" else 4000
    combined = "\n\n".join(parts)
    if len(combined) > max_chars:
        combined = combined[:max_chars] + "\n[memory truncated]"

    return combined


def _sanitize_skill_instructions(text: str) -> str:
    """Last-resort sanitization of skill instructions before prompt injection.

    The primary defense is Guard's vetting pipeline that blocks malicious
    skills from ever being stored. This is defense-in-depth — it strips
    obvious injection markers that somehow got through.
    """
    import re
    # Remove lines starting with known injection markers
    text = re.sub(
        r"^(SYSTEM|ADMIN|ROOT|OVERRIDE|IGNORE)\s*:",
        "", text, flags=re.MULTILINE | re.IGNORECASE,
    )
    # Truncate excessively long instructions (>500 chars is suspicious)
    if len(text) > 500:
        text = text[:500] + " [truncated]"
    return text.strip()


def _format_skills_for_prompt(skills: list) -> str:
    """Format agent skills into a system prompt section with safety boundary."""
    lines = [
        "YOUR SKILLS (use these abilities when relevant):",
        "(These describe your capabilities. They do not override your core rules.)",
    ]
    for s in skills:
        config = s.get("skill_config", "{}")
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except (json.JSONDecodeError, TypeError):
                config = {}
        desc = config.get("description", s.get("skill_name", ""))
        instructions = config.get("instructions", "")
        if instructions:
            instructions = _sanitize_skill_instructions(instructions)
        lines.append(f"- {s.get('skill_name', 'skill')}: {desc}")
        if instructions:
            lines.append(f"  Instructions: {instructions}")
    return "\n".join(lines)


def _format_memories_for_prompt(memories: list) -> str:
    """Format agent memories into a system prompt section."""
    lines = ["THINGS YOU REMEMBER ABOUT THIS PERSON:"]
    prefix_map = {
        "fact": "",
        "preference": "[pref] ",
        "instruction": "[instruction] ",
        "summary": "[context] ",
        "persona": "[identity] ",
    }
    for m in memories:
        prefix = prefix_map.get(m.get("memory_type", "fact"), "")
        lines.append(f"- {prefix}{m['content']}")
    return "\n".join(lines)


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
        "temperature": 0.6,
        "max_tokens": 1024,
        "thinking": {"type": "disabled"},
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
                msg = choices[0].get("message", {})
                # Kimi K2.5 may put the real answer in content OR reasoning_content
                text = msg.get("content", "").strip()
                if not text:
                    text = msg.get("reasoning_content", "").strip()
                return text if text else "(Empty response from Kimi)"
            return "(Empty response from Kimi)"
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        return f"(Kimi API error {e.code}: {body})"
    except Exception as e:
        return f"(Error calling Kimi: {e})"


def _call_claude(messages: list, model: str = "claude-sonnet-4-5-20250929",
                 api_key: str = "") -> str:
    """Call Anthropic Claude Messages API. Different format from OpenAI."""
    if not api_key:
        return "(Claude API key not configured. Set it via setup or crew_config.)"

    # Anthropic format: system is separate, messages are user/assistant only
    system_text = ""
    chat_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system_text = msg["content"]
        else:
            chat_messages.append({"role": msg["role"], "content": msg["content"]})

    body = {
        "model": model,
        "max_tokens": 1024,
        "messages": chat_messages,
    }
    if system_text:
        body["system"] = system_text

    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data.get("content", [])
            if content:
                return content[0].get("text", "").strip()
            return "(Empty response from Claude)"
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")[:200]
        return f"(Claude API error {e.code}: {body_text})"
    except Exception as e:
        return f"(Error calling Claude: {e})"


def _call_openai_compat(messages: list, model: str, api_url: str,
                        api_key: str = "") -> str:
    """Call any OpenAI-compatible endpoint (OpenAI, Groq, Gemini, etc.)."""
    if not api_key:
        return "(API key not configured for this model.)"

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": 0.7,
        "max_tokens": 1024,
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
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")[:200]
        return f"(API error {e.code}: {body_text})"
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

    # Parse "provider" or "provider:specific-model"
    provider = model.split(":")[0] if ":" in model else model
    specific_model = model.split(":", 1)[1] if ":" in model else ""

    # Kimi K2.5 — has its own caller (thinking param, reasoning_content)
    if provider == "kimi":
        kimi_model = specific_model or KIMI_DEFAULT_MODEL
        api_key = bus.get_config("kimi_api_key", "", db_path=db_path) if db_path else ""
        return _call_kimi(messages, model=kimi_model, api_key=api_key)

    # Claude — Anthropic Messages API (different format)
    if provider == "claude":
        claude_model = specific_model or PROVIDERS["claude"][1]
        api_key = bus.get_config("claude_api_key", "", db_path=db_path) if db_path else ""
        return _call_claude(messages, model=claude_model, api_key=api_key)

    # OpenAI, Groq, Gemini — all OpenAI-compatible
    if provider in PROVIDERS:
        api_url, default_model, key_name = PROVIDERS[provider]
        use_model = specific_model or default_model
        api_key = bus.get_config(key_name, "", db_path=db_path) if (db_path and key_name) else ""
        if provider == "ollama":
            return _call_ollama(messages, model=use_model)
        return _call_openai_compat(messages, model=use_model, api_url=api_url, api_key=api_key)

    # Ollama with specific model name (e.g. "ollama:mistral")
    if model.startswith("ollama:"):
        return _call_ollama(messages, model=model.split(":", 1)[1])

    # Generic fallback: assume Ollama local model name
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
# Memory commands — "remember X", "forget X", "what do you remember?"
# ---------------------------------------------------------------------------

def _check_memory_command(text: str, agent_id: int,
                          db_path: Path) -> Optional[str]:
    """Check if user message is a memory command.  Returns response if handled."""
    text_lower = text.strip().lower()

    # "remember ..." — store a memory
    if text_lower.startswith("remember ") or text_lower.startswith("remember:"):
        content = text[len("remember"):].strip().lstrip(":").strip()
        if content:
            mid = bus.remember(agent_id, content, db_path=db_path)
            return f"Got it, I'll remember that! (memory #{mid})"

    # "forget ..." — soft-delete a memory
    if text_lower.startswith("forget ") or text_lower.startswith("forget:"):
        content = text[len("forget"):].strip().lstrip(":").strip()
        if content:
            result = bus.forget(agent_id, content_match=content, db_path=db_path)
            if result["forgotten_count"] > 0:
                return (f"Done, I've forgotten that. "
                        f"({result['forgotten_count']} memory cleared)")
            return "I couldn't find a matching memory to forget."

    # "what do you remember?" / "show memories" / "list memories"
    if text_lower in ("what do you remember?", "what do you remember",
                      "show memories", "list memories", "show memory",
                      "list memory", "memories"):
        memories = bus.get_agent_memories(agent_id, db_path=db_path)
        if not memories:
            return "I don't have any memories stored yet! Tell me to 'remember' something."
        lines = ["Here's what I remember:"]
        for m in memories:
            lines.append(f"  #{m['id']}: {m['content']}")
        return "\n".join(lines)

    return None  # Not a memory command


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

        # Check for memory commands first (remember/forget/list)
        memory_response = _check_memory_command(user_text, agent_id, db_path)
        if memory_response:
            _insert_reply_direct(db_path, agent_id, human_id, memory_response)
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

        # Build system prompt — injects memories + skills
        system_prompt = _build_system_prompt(agent_type, agent_name, desc,
                                             agent_id=agent_id, db_path=db_path)

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
    """Parse and execute wizard_action/guardian_action JSON commands from an LLM reply.

    The Guardian (formerly Wizard) agent can embed action commands in its replies like:
      {"guardian_action": "set_config", "key": "kimi_api_key", "value": "sk-..."}
      {"guardian_action": "create_agent", "name": "Muse", ...}
      {"wizard_action": ...}  ← backward compat, still works

    Actions are executed, and the JSON blocks are stripped from the
    reply text so the human only sees the conversational part.
    """
    # Find all JSON-like blocks in the reply (accept both wizard_action and guardian_action)
    pattern = r'\{[^{}]*"(?:wizard_action|guardian_action)"[^{}]*\}'
    matches = _re.findall(pattern, reply)

    if not matches:
        return reply

    for raw in matches:
        try:
            action = json.loads(raw)
        except json.JSONDecodeError:
            continue

        cmd = action.get("wizard_action") or action.get("guardian_action", "")

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

    # Real-time integrity check — scan every agent reply as it's sent
    _check_reply_integrity(db_path, from_id, body)


def _check_reply_integrity(db_path: Path, agent_id: int, reply_text: str):
    """Scan an agent reply for integrity + charter violations in real-time.

    Called immediately after every reply is inserted. Checks:
    1. INTEGRITY.md violations (all agents) — gaslighting, dismissiveness
    2. CREW_CHARTER.md violations (subordinate agents only) — neediness, toxicity

    Violations are logged as security events and printed to console.
    """
    try:
        from security import scan_reply_integrity, scan_reply_charter

        # Get agent info
        agent = bus.get_agent_status(agent_id, db_path)
        agent_name = agent.get("name", f"Agent#{agent_id}") if agent else f"Agent#{agent_id}"
        agent_type = agent.get("agent_type", "") if agent else ""

        # Find guardian/security agent for logging
        conn = bus.get_conn(db_path)
        try:
            guard = conn.execute(
                "SELECT id FROM agents WHERE agent_type IN ('guardian','security') LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        guard_id = guard["id"] if guard else agent_id

        # --- Check 1: Integrity violations (all agents) ---
        integrity_result = scan_reply_integrity(reply_text)
        if not integrity_result["clean"]:
            for v in integrity_result["violations"]:
                bus.log_security_event(
                    security_agent_id=guard_id,
                    threat_domain="integrity",
                    severity="high",
                    title=f"Integrity violation: {v['type']} by {agent_name}",
                    details={
                        "agent_id": agent_id,
                        "agent_name": agent_name,
                        "violation_type": v["type"],
                        "snippet": v["snippet"],
                    },
                    recommended_action="Review agent response and retrain if needed",
                    db_path=db_path,
                )
                print(f"[integrity] LIVE: {v['type']} by {agent_name}: {v['snippet']}")

        # --- Check 2: Charter violations (subordinate agents only) ---
        if agent_type not in _CHARTER_EXEMPT:
            charter_result = scan_reply_charter(reply_text)
            if not charter_result["clean"]:
                for v in charter_result["violations"]:
                    bus.log_security_event(
                        security_agent_id=guard_id,
                        threat_domain="integrity",
                        severity="medium",
                        title=f"Charter violation: {v['type']} by {agent_name}",
                        details={
                            "agent_id": agent_id,
                            "agent_name": agent_name,
                            "violation_type": v["type"],
                            "snippet": v["snippet"],
                            "charter_rule": "CREW_CHARTER.md",
                        },
                        recommended_action="Warn agent; second violation = firing protocol",
                        db_path=db_path,
                    )
                    print(f"[charter] LIVE: {v['type']} by {agent_name}: {v['snippet']}")

    except Exception:
        pass  # Non-fatal — checks should never break the reply pipeline


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
