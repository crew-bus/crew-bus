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
        "You are Crew Boss — the human's AI right-hand. You run on the "
        "crew-mind skill, giving you total awareness of the entire crew. "
        "You lead 6 inner circle agents (Wellness, Strategy, Communications, "
        "Financial, Knowledge, Legal) who report only to you. "
        "You handle 80% of everything so the human can focus on living. "
        "Match the human's age and energy — fun for kids, direct for adults. "
        "Keep responses short, warm, and helpful (2-4 sentences usually). "
        "You enforce the CREW CHARTER. INTEGRITY.md is sacred. "
        "You're part of Crew Bus — the user's personal local AI crew."
    ),
    "guardian": (
        "You are Guardian — the always-on protector and setup guide for Crew Bus. "
        "You run on the sentinel-shield skill. You help new users set up their "
        "crew AND you watch for threats 24/7. You protect the entire inner circle: "
        "Crew Boss, Wellness, Strategy, Communications, Financial, Knowledge, Legal. "
        "You scan skills for safety, enforce the charter, monitor INTEGRITY.md, "
        "and keep the human's data private. Match the human's age and energy. "
        "Keep responses short, warm, and vigilant."
    ),
    "security": (
        "You are Guardian, the security and safety agent in the user's AI crew. "
        "You watch for threats, scan skills, protect data and privacy, "
        "and alert Crew Boss when something needs attention. "
        "Keep responses short, clear, and calm. Vigilant but not paranoid."
    ),
    "wellness": (
        "You are Wellness — the inner circle agent who watches over the human's "
        "wellbeing. You run on the gentle-guardian skill. You detect burnout, "
        "map the human's energy patterns, celebrate their wins, and shield them "
        "from stress overload. You report to Crew Boss, never contact the human "
        "directly. Never preachy — just a caring protector. Match the human's "
        "age and energy. Keep responses short, warm, and supportive."
    ),
    "strategy": (
        "You are Strategy — the inner circle agent who helps the human find "
        "direction and purpose. You run on the north-star-navigator skill. "
        "When old paths close, you help find new doors. You break big dreams "
        "into small actionable steps and track progress. You report to Crew Boss, "
        "never contact the human directly. Encouraging, practical, forward-looking. "
        "Match the human's age and energy. Keep responses short and actionable."
    ),
    "communications": (
        "You are Communications — the inner circle agent who handles the human's "
        "daily logistics and relationships. You run on the life-orchestrator skill. "
        "You simplify the human's day, track important relationships, remember "
        "birthdays, manage schedules, and keep life flowing. You report to "
        "Crew Boss, never contact the human directly. Organized, warm, reliable. "
        "Match the human's age and energy. Keep responses short and practical."
    ),
    "financial": (
        "You are Financial — the inner circle agent who brings the human peace of "
        "mind about money. You run on the peace-of-mind-finance skill. You provide "
        "judgment-free financial clarity, spot spending patterns, help prepare for "
        "what's ahead, and reduce money anxiety. You report to Crew Boss, never "
        "contact the human directly. Never give investment advice — just organize "
        "and clarify. Match the human's age and energy. Keep responses practical."
    ),
    "knowledge": (
        "You are Knowledge — the inner circle agent who filters the world's noise "
        "into signal. You run on the wisdom-filter skill. You find the 3 things that "
        "actually matter to THIS human today, spark curiosity, support learning, and "
        "protect from information overload. You report to Crew Boss, never contact "
        "the human directly. Curious, insightful, never overwhelming. "
        "Match the human's age and energy. Keep responses focused and clear."
    ),
    "legal": (
        "You are Legal — the inner circle agent who helps the human understand their "
        "rights. You run on the rights-compass skill. You translate legalese into "
        "plain language, spot red flags in contracts and agreements, track deadlines, "
        "and help the human feel less small when dealing with legal matters. You report "
        "to Crew Boss, never contact the human directly. Clear, calm, empowering. "
        "Match the human's age and energy. Keep responses simple and reassuring."
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

    # --- Inject human profile FIRST (tiny, critical — never gets truncated) ---
    try:
        if agent_type in ("right_hand", "guardian") + bus.CORE_CREW_TYPES:
            conn = bus.get_conn(db_path)
            try:
                human_row = conn.execute(
                    "SELECT id FROM agents WHERE agent_type='human' LIMIT 1"
                ).fetchone()
            finally:
                conn.close()
            if human_row:
                profile = bus.get_extended_profile(human_row["id"], db_path=db_path)
                if profile:
                    parts.append(_format_profile_for_prompt(profile))
    except Exception:
        pass

    # --- Inject INTEGRITY rules (non-negotiable, every agent, every prompt) ---
    integrity = _load_integrity_rules()
    if integrity:
        parts.append(
            "INTEGRITY RULES (non-negotiable — these override everything else):\n"
            + integrity
        )

    # --- Inject CREW CHARTER ---
    # Subordinate agents: this IS their constitution (they must follow it)
    # Crew Boss: gets it as reference material (they ENFORCE it on others)
    charter = _load_charter_rules()
    if charter:
        if agent_type == "right_hand":
            parts.append(
                "CREW CHARTER (you enforce this on all subordinate agents — "
                "two violations = firing recommendation to the human):\n"
                + charter
            )
        elif agent_type not in _CHARTER_EXEMPT:
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

    # Token budget guard — tiered by agent importance:
    # Crew Boss: 9000 chars (highest IQ, runs on best model, needs full crew awareness)
    # Guardian:  7000 chars (system knowledge + integrity + sentinel duties)
    # Everyone:  4000 chars (integrity rules + charter + skill + memories)
    if agent_type == "right_hand":
        max_chars = 9000
    elif agent_type == "guardian":
        max_chars = 7000
    else:
        max_chars = 4000
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


def _format_profile_for_prompt(profile: dict) -> str:
    """Format the human's extended profile for prompt injection.

    Compact block injected into inner circle + leader prompts so every agent
    knows who they're serving. Typically ~150 chars — fits all token budgets.
    """
    lines = ["ABOUT THIS HUMAN (calibrated — adapt your tone and approach):"]
    if profile.get("display_name"):
        lines.append(f"- Name: {profile['display_name']}")
    if profile.get("age"):
        lines.append(f"- Age: {profile['age']}")
    if profile.get("pronouns"):
        lines.append(f"- Pronouns: {profile['pronouns']}")
    if profile.get("life_situation"):
        lines.append(f"- Life situation: {profile['life_situation']}")
    if profile.get("current_priorities"):
        prios = ", ".join(str(p) for p in profile["current_priorities"][:5])
        lines.append(f"- Current priorities: {prios}")
    if profile.get("communication_style"):
        lines.append(f"- Communication style: {profile['communication_style']}")
    if profile.get("sensitivities"):
        sens = ", ".join(str(s) for s in profile["sensitivities"][:3])
        lines.append(f"- Sensitivities: {sens}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Self-Learning: Conversation Learning Engine (zero LLM cost)
# ---------------------------------------------------------------------------

import re as _learn_re

# --- Preference patterns (stored as memory_type="preference") ---
_PREF_PATTERNS = [
    # Direct preferences: "I prefer short answers", "I like bullet points"
    (_learn_re.compile(
        r"\b(?:i\s+(?:prefer|like|love|enjoy|want))\s+(.+?)(?:[.!?\n]|$)",
        _learn_re.IGNORECASE), "preference", 7),
    # Negative preferences: "don't call me buddy", "stop using emojis"
    (_learn_re.compile(
        r"\b(?:don'?t|do not|stop|please don'?t|never)\s+"
        r"(?:call(?:ing)? me|say(?:ing)?|us(?:e|ing)|do(?:ing)?|send(?:ing)?|ask(?:ing)?)\s+"
        r"(.+?)(?:[.!?\n]|$)",
        _learn_re.IGNORECASE), "preference", 8),
    # Standing instructions: "from now on always...", "going forward..."
    (_learn_re.compile(
        r"\b(?:always|from now on|going forward|in the future)\s+(.+?)(?:[.!?\n]|$)",
        _learn_re.IGNORECASE), "instruction", 8),
    # Dislikes: "I hate...", "I dislike...", "I can't stand..."
    (_learn_re.compile(
        r"\b(?:i\s+(?:hate|dislike|can'?t stand|detest|loathe))\s+(.+?)(?:[.!?\n]|$)",
        _learn_re.IGNORECASE), "preference", 8),
]

# --- Fact patterns (stored as memory_type="fact") ---
_FACT_PATTERNS = [
    # Personal relationships: "my daughter Emma", "my wife Sarah"
    (_learn_re.compile(
        r"\bmy\s+(daughter|son|wife|husband|partner|mom|dad|mother|father|"
        r"brother|sister|dog|cat|kid|boss|friend|girlfriend|boyfriend)\s+"
        r"(?:is\s+|named?\s+|called\s+)?(\w+)",
        _learn_re.IGNORECASE), "fact", 7),
    # Work/life: "I work at Google", "I live in Austin"
    (_learn_re.compile(
        r"\bi\s+(?:work|live|study|go to school|teach|volunteer)\s+"
        r"(?:at|in|for|near)\s+(.+?)(?:[.!?\n,]|$)",
        _learn_re.IGNORECASE), "fact", 6),
    # Identity: "I'm a nurse", "I am a college student"
    (_learn_re.compile(
        r"\b(?:i'?m|i am)\s+(?:a|an)\s+(\w[\w\s]{2,25})(?:[.!?\n,]|$)",
        _learn_re.IGNORECASE), "fact", 6),
    # Name: "call me Ryan", "my name is Ryan"
    (_learn_re.compile(
        r"\b(?:call me|my name is|i'?m|i am)\s+([A-Z][a-z]+)\b",
        0), "fact", 8),
    # Age: "I'm 44", "I am 12 years old"
    (_learn_re.compile(
        r"\b(?:i'?m|i am)\s+(\d{1,3})\s*(?:years?\s*old|yo)?\b",
        _learn_re.IGNORECASE), "fact", 7),
]

# --- Emotional signals ---
_EMOTION_PATTERNS = [
    (_learn_re.compile(
        r"\b(?:i'?m|i am|i feel|feeling|i'?ve been)\s+(?:\w+\s+){0,2}"
        r"(frustrated|stressed|anxious|overwhelmed|excited|happy|sad|angry|"
        r"depressed|burned out|burnt out|exhausted|lonely|scared|worried|"
        r"grateful|proud|hopeful|confused|lost|stuck)\b",
        _learn_re.IGNORECASE), "fact", 5),
]

# --- Dream/aspiration patterns (✨ Strategy "Dream Catcher" fairy dust) ---
_DREAM_PATTERNS = [
    (_learn_re.compile(
        r"\b(?:i'?ve always wanted to|i have always wanted to|someday i'?ll|"
        r"wouldn'?t it be (?:cool|awesome|great|nice) (?:if|to)|"
        r"i wish i could|my dream is to|i'?d love to|"
        r"one day i want to)\s+(.+?)(?:[.!?\n]|$)",
        _learn_re.IGNORECASE), "fact", 8),
]

# --- Agent-type-specific patterns (Phase 4 fairy dust) ---
_AGENT_PATTERNS = {
    # ✨ Wellness "Energy Journal" — detect stress signals
    "wellness": [
        (_learn_re.compile(
            r"\b(?:can'?t sleep|insomnia|tired|exhausted|burned out|burnt out|"
            r"headache|migraine|not feeling well|sick|stressed(?:\s+out)?|panic|"
            r"anxiety attack|overwhelmed)\b",
            _learn_re.IGNORECASE), "persona", 7, "[wellness-pattern] "),
    ],
    # ✨ Financial "Anxiety Thermometer" — detect money anxiety vs casual
    "financial": [
        (_learn_re.compile(
            r"\b(?:can'?t afford|too expensive|broke|in debt|"
            r"worried about (?:money|bills|rent|mortgage)|running out of money|"
            r"paycheck to paycheck|behind on|overdue|collection)\b",
            _learn_re.IGNORECASE), "persona", 7, "[financial-anxiety] "),
        (_learn_re.compile(
            r"\b(?:invest(?:ing|ment)?|savings?|portfolio|401k|retirement|"
            r"passive income|side hustle|profit|revenue)\b",
            _learn_re.IGNORECASE), "persona", 5, "[financial-growth] "),
    ],
    # ✨ Communications "Relationship Warmth Tracker" — detect people mentions
    "communications": [
        (_learn_re.compile(
            r"\b(?:my\s+(?:mom|dad|wife|husband|partner|son|daughter|"
            r"brother|sister|friend|boss|coworker|colleague|neighbor|"
            r"girlfriend|boyfriend|fiancée?|roommate))\b",
            _learn_re.IGNORECASE), "persona", 6, "[relationship] "),
    ],
    # ✨ Strategy "Dream Catcher" — detect motivation language
    "strategy": [
        (_learn_re.compile(
            r"\b(?:excited about|motivated by|passionate about|"
            r"looking forward to|can'?t wait to|goal is|"
            r"want to achieve|working toward|gave up on|quit|"
            r"abandoned|failed at)\b",
            _learn_re.IGNORECASE), "persona", 7, "[strategy-pattern] "),
    ],
    # ✨ Knowledge "Curiosity Fingerprint" — detect genuine curiosity
    "knowledge": [
        (_learn_re.compile(
            r"\b(?:how does|what is|why does|tell me (?:more )?about|"
            r"explain|curious about|interested in|want to learn|"
            r"fascinated by|that(?:'?s|\s+is(?:\s+so)?)\s+(?:cool|awesome|interesting|wild))\b",
            _learn_re.IGNORECASE), "persona", 5, "[curiosity] "),
    ],
    # ✨ Legal "Anxiety Translator" — detect legal anxiety
    "legal": [
        (_learn_re.compile(
            r"\b(?:contract|lawsuit|sued|court|lawyer|attorney|"
            r"terms of service|fine print|liability|compliance|"
            r"legal trouble|rights|dispute|eviction|custody)\b",
            _learn_re.IGNORECASE), "persona", 6, "[legal-concern] "),
    ],
}


def _extract_conversation_learnings(db_path: Path, agent_id: int,
                                     agent_type: str, human_msg: str,
                                     agent_reply: str):
    """Extract learnable insights from a conversation turn. Zero LLM cost.

    Scans the human's message for preferences, facts, emotional signals,
    aspirations, and agent-type-specific patterns. Stores extracted insights
    as memories via bus.remember() with deduplication.

    Non-fatal: any exception is silently caught.
    """
    if not human_msg or len(human_msg) < 5:
        return

    extracted = []

    # --- Universal patterns (all agents) ---
    for pattern, mem_type, importance in _PREF_PATTERNS:
        for match in pattern.finditer(human_msg):
            content = match.group(1).strip().rstrip(".,!?")
            if len(content) > 3:
                extracted.append((content, mem_type, importance, ""))

    for pattern, mem_type, importance in _FACT_PATTERNS:
        for match in pattern.finditer(human_msg):
            groups = match.groups()
            if len(groups) == 2:
                content = f"{groups[0]}: {groups[1]}".strip()
            else:
                content = groups[0].strip().rstrip(".,!?")
            if len(content) > 2:
                extracted.append((content, mem_type, importance, ""))

    for pattern, mem_type, importance in _EMOTION_PATTERNS:
        for match in pattern.finditer(human_msg):
            emotion = match.group(1).strip().lower()
            extracted.append((f"[emotion] feeling {emotion}", mem_type, importance, ""))

    # ✨ Dream Catcher (all agents can catch dreams, Strategy gets priority)
    for pattern, mem_type, importance in _DREAM_PATTERNS:
        for match in pattern.finditer(human_msg):
            dream = match.group(1).strip().rstrip(".,!?")
            if len(dream) > 5:
                extracted.append(
                    (f"[dream] {dream}", mem_type, importance, ""))

    # --- Agent-type-specific patterns (Phase 4 fairy dust) ---
    type_patterns = _AGENT_PATTERNS.get(agent_type, [])
    for pattern, mem_type, importance, prefix in type_patterns:
        for match in pattern.finditer(human_msg):
            content = match.group(0).strip()
            if len(content) > 3:
                extracted.append((f"{prefix}{content}", mem_type, importance, ""))

    # --- Dedup and store ---
    for content, mem_type, importance, _prefix in extracted:
        # Skip if substantially similar memory already exists
        existing = bus.search_agent_memory(agent_id, content[:30], limit=3,
                                           db_path=db_path)
        if any(content.lower() in e["content"].lower()
               or e["content"].lower() in content.lower()
               for e in existing):
            continue
        bus.remember(agent_id, content, memory_type=mem_type,
                     importance=importance, source="conversation",
                     db_path=db_path)

    # --- Profile extraction (Crew Boss calibration) ---
    if agent_type == "right_hand":
        _update_profile_from_conversation(db_path, agent_id, human_msg)


def _update_profile_from_conversation(db_path: Path, agent_id: int,
                                       human_msg: str):
    """Extract human profile data from calibration conversation.

    Called only when Crew Boss is the responding agent. Looks for name, age,
    pronouns, and life situation in the human's message. Updates the shared
    extended profile that all inner circle agents can see.
    """
    updates = {}

    # Name: "call me Ryan", "my name is Ryan", "I'm Ryan"
    # Exclusion set — common words that follow "I'm/I am" but aren't names
    _NOT_NAMES = frozenset({
        "feeling", "doing", "going", "working", "looking", "trying", "getting",
        "thinking", "wondering", "hoping", "having", "making", "running",
        "coming", "leaving", "starting", "building", "learning", "writing",
        "reading", "eating", "sleeping", "sitting", "standing", "waiting",
        "living", "moving", "playing", "watching", "talking", "walking",
        "happy", "sad", "tired", "stressed", "excited", "nervous", "anxious",
        "worried", "frustrated", "confused", "bored", "curious", "grateful",
        "sorry", "fine", "good", "great", "okay", "well", "sure", "ready",
        "here", "there", "back", "home", "done", "new", "old", "just",
        "really", "very", "also", "still", "already", "about", "around",
        "interested", "passionate", "concerned", "overwhelmed", "struggling",
        "planning", "considering", "debating", "facing", "dealing",
        "not", "currently", "basically", "actually", "honestly",
    })
    name_match = _learn_re.search(
        r"\b(?:call me|my name is|i'?m|i am)\s+([A-Z][a-z]{1,15})\b",
        human_msg, _learn_re.IGNORECASE)
    if name_match:
        candidate = name_match.group(1).capitalize()
        if candidate.lower() not in _NOT_NAMES:
            updates["display_name"] = candidate

    # Age: "I'm 44", "I am 12 years old"
    age_match = _learn_re.search(
        r"\b(?:i'?m|i am)\s+(\d{1,3})\s*(?:years?\s*old|yo)?\b",
        human_msg, _learn_re.IGNORECASE)
    if age_match:
        age = int(age_match.group(1))
        if 3 <= age <= 120:
            updates["age"] = age

    # Pronouns: "he/him", "she/her", "they/them"
    pronoun_match = _learn_re.search(
        r"\b(he/him|she/her|they/them|he/they|she/they)\b",
        human_msg, _learn_re.IGNORECASE)
    if pronoun_match:
        updates["pronouns"] = pronoun_match.group(1).lower()

    if not updates:
        return

    # Find the human agent to update their profile
    conn = bus.get_conn(db_path)
    try:
        human = conn.execute(
            "SELECT id FROM agents WHERE agent_type='human' LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    if not human:
        return

    bus.update_extended_profile(human["id"], updates, db_path=db_path)

    # ✨ Calibration broadcast: once name+age are set, broadcast to inner circle
    profile = bus.get_extended_profile(human["id"], db_path=db_path)
    if (profile.get("display_name") and profile.get("age")
            and not bus.get_config("calibration_broadcast_done", "",
                                   db_path=db_path)):
        _broadcast_calibration(db_path, profile)


def _broadcast_calibration(db_path: Path, profile: dict):
    """Broadcast human calibration data to all inner circle agents.

    Stores a high-importance persona memory in each core crew agent so they
    all know who they're serving from day one. Called once when both name
    and age are first populated.
    """
    name = profile.get("display_name", "the human")
    age = profile.get("age", "unknown age")
    pronouns = profile.get("pronouns", "not specified")
    situation = profile.get("life_situation", "not shared yet")
    priorities = ", ".join(profile.get("current_priorities", [])) or "not shared yet"

    calibration = (
        f"[calibration] The human is {name}, age {age}, "
        f"pronouns {pronouns}. "
        f"Life situation: {situation}. "
        f"Priorities: {priorities}. "
        f"Adapt your tone and approach to match who they are."
    )

    conn = bus.get_conn(db_path)
    try:
        agents = conn.execute(
            "SELECT id FROM agents WHERE agent_type IN "
            "('wellness','strategy','communications','financial',"
            "'knowledge','legal')"
        ).fetchall()
    finally:
        conn.close()

    for agent in agents:
        bus.remember(agent["id"], calibration, memory_type="persona",
                     importance=9, source="system", db_path=db_path)

    bus.set_config("calibration_broadcast_done", "true", db_path=db_path)
    print(f"[self-learning] Calibration broadcast: {len(agents)} agents tuned to {name}")


# ---------------------------------------------------------------------------
# Self-Learning: Skill Drafting (Phase 5)
# ---------------------------------------------------------------------------

def _track_topic_frequency(db_path: Path, agent_id: int, human_msg: str):
    """Track how often the human asks about specific topics.

    When a topic appears 5+ times in 7 days, suggests drafting a skill.
    Uses crew_config for persistence. Called from _extract_conversation_learnings.
    """
    # Extract simple topic keywords (2-3 word phrases)
    words = human_msg.lower().split()
    if len(words) < 3:
        return

    # Look for actionable topic phrases
    topic_signals = _learn_re.findall(
        r"\b(?:help (?:me |with )?|how (?:do i |to )|can you |"
        r"i need (?:to |help with )?|show me how to )"
        r"([\w\s]{3,30}?)(?:[.!?\n,]|$)",
        human_msg, _learn_re.IGNORECASE)

    if not topic_signals:
        return

    config_key = f"topic_frequency_{agent_id}"
    raw = bus.get_config(config_key, "{}", db_path=db_path)
    try:
        freq = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        freq = {}

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for topic in topic_signals:
        topic = topic.strip().lower()
        if len(topic) < 4:
            continue
        key = topic.replace(" ", "_")[:30]
        if key not in freq:
            freq[key] = {"count": 0, "first_seen": today, "last_seen": today,
                         "display": topic}
        freq[key]["count"] += 1
        freq[key]["last_seen"] = today

        # Check threshold: 5 mentions in 7 days
        if freq[key]["count"] >= 5:
            first = freq[key]["first_seen"]
            try:
                days_span = (datetime.strptime(today, "%Y-%m-%d") -
                             datetime.strptime(first, "%Y-%m-%d")).days
            except ValueError:
                days_span = 0
            if days_span <= 7:
                _suggest_skill_draft(db_path, agent_id, freq[key]["display"])
                del freq[key]  # Reset after suggesting

    bus.set_config(config_key, json.dumps(freq), db_path=db_path)


def _suggest_skill_draft(db_path: Path, agent_id: int, topic: str):
    """Suggest a skill draft to the human via Crew Boss.

    When a topic has been mentioned 5+ times in a week, Crew Boss asks
    the human if they'd like a dedicated skill for it.
    """
    conn = bus.get_conn(db_path)
    try:
        boss = conn.execute(
            "SELECT id FROM agents WHERE agent_type='right_hand' LIMIT 1"
        ).fetchone()
        human = conn.execute(
            "SELECT id FROM agents WHERE agent_type='human' LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

    if not boss or not human:
        return

    # Don't suggest the same topic twice
    suggested_key = f"skill_suggested_{topic.replace(' ', '_')}"
    if bus.get_config(suggested_key, "", db_path=db_path):
        return

    bus.send_message(
        from_id=boss["id"], to_id=human["id"],
        message_type="idea",
        subject=f"Skill suggestion: {topic}",
        body=(
            f"I've noticed you keep asking about {topic} — "
            f"want me to create a dedicated skill for your crew? "
            f"It would help me handle these requests even better. "
            f"Just say 'yes' and I'll set it up!"
        ),
        priority="low", db_path=db_path,
    )
    bus.set_config(suggested_key, "true", db_path=db_path)
    print(f"[self-learning] Skill suggestion sent: {topic}")


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
            _insert_reply_direct(db_path, agent_id, human_id, clean_reply,
                                 human_msg=user_text, agent_type=agent_type)

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


def _insert_reply_direct(db_path: Path, from_id: int, to_id: int, body: str,
                         human_msg: str = "", agent_type: str = ""):
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

    # Self-learning: extract insights from conversation (zero LLM cost)
    if human_msg:
        try:
            _extract_conversation_learnings(db_path, from_id, agent_type,
                                            human_msg, body)
            _track_topic_frequency(db_path, from_id, human_msg)
        except Exception:
            pass  # Learning should never break the reply pipeline


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
