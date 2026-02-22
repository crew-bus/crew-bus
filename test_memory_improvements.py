"""Tests for memory improvements — expiry, dedup, feedback, sharing, temporal, summarization."""

import json
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bus
import agent_worker


def _setup_db():
    """Create a temp DB with human + crew boss agents."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = Path(tmp.name)
    tmp.close()
    bus.init_db(db_path=db_path)

    conn = bus.get_conn(db_path)
    conn.execute(
        "INSERT INTO agents (name, agent_type, role, status, active) "
        "VALUES (?, ?, ?, ?, ?)",
        ("Human", "human", "human", "active", 1),
    )
    conn.execute(
        "INSERT INTO agents (name, agent_type, role, parent_agent_id, status, active) "
        "VALUES (?, ?, ?, 1, ?, ?)",
        ("Crew Boss", "right_hand", "right_hand", "active", 1),
    )
    conn.execute(
        "INSERT INTO agents (name, agent_type, role, parent_agent_id, status, active) "
        "VALUES (?, ?, ?, 2, ?, ?)",
        ("Health Buddy", "wellness", "core_crew", "active", 1),
    )
    conn.commit()
    conn.close()
    return db_path


# ===== Change 8: Schema Migration =====

def test_schema_has_auto_summary_source():
    """agent_memory table accepts 'auto_summary' as a source."""
    db_path = _setup_db()
    mid = bus.remember(2, "test summary", memory_type="summary",
                       source="auto_summary", db_path=db_path)
    assert mid > 0
    mems = bus.get_agent_memories(2, db_path=db_path)
    assert any(m["source"] == "auto_summary" for m in mems)


# ===== Change 4: Memory Expiry =====

def test_remember_sets_expires_at_low_importance():
    """Low importance memories (1-3) get 7-day expiry."""
    db_path = _setup_db()
    mid = bus.remember(2, "trivial fact", importance=2, db_path=db_path)
    conn = bus.get_conn(db_path)
    row = conn.execute("SELECT expires_at FROM agent_memory WHERE id=?", (mid,)).fetchone()
    conn.close()
    assert row["expires_at"] is not None
    exp = datetime.strptime(row["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    # Should be ~7 days from now
    assert 6 <= (exp - now).days <= 7


def test_remember_no_expiry_high_importance():
    """High importance (8+) memories never expire."""
    db_path = _setup_db()
    mid = bus.remember(2, "critical fact", importance=9, db_path=db_path)
    conn = bus.get_conn(db_path)
    row = conn.execute("SELECT expires_at FROM agent_memory WHERE id=?", (mid,)).fetchone()
    conn.close()
    assert row["expires_at"] is None


def test_remember_no_expiry_instruction_type():
    """Instruction-type memories never expire regardless of importance."""
    db_path = _setup_db()
    mid = bus.remember(2, "always be concise", memory_type="instruction",
                       importance=3, db_path=db_path)
    conn = bus.get_conn(db_path)
    row = conn.execute("SELECT expires_at FROM agent_memory WHERE id=?", (mid,)).fetchone()
    conn.close()
    assert row["expires_at"] is None


def test_remember_no_expiry_persona_type():
    """Persona-type memories never expire regardless of importance."""
    db_path = _setup_db()
    mid = bus.remember(2, "I am friendly", memory_type="persona",
                       importance=2, db_path=db_path)
    conn = bus.get_conn(db_path)
    row = conn.execute("SELECT expires_at FROM agent_memory WHERE id=?", (mid,)).fetchone()
    conn.close()
    assert row["expires_at"] is None


def test_remember_medium_importance_30_days():
    """importance 4-5 → 30-day expiry."""
    db_path = _setup_db()
    mid = bus.remember(2, "some fact", importance=4, db_path=db_path)
    conn = bus.get_conn(db_path)
    row = conn.execute("SELECT expires_at FROM agent_memory WHERE id=?", (mid,)).fetchone()
    conn.close()
    exp = datetime.strptime(row["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    assert 29 <= (exp - now).days <= 30


def test_remember_high_medium_importance_90_days():
    """importance 6-7 → 90-day expiry."""
    db_path = _setup_db()
    mid = bus.remember(2, "notable fact", importance=6, db_path=db_path)
    conn = bus.get_conn(db_path)
    row = conn.execute("SELECT expires_at FROM agent_memory WHERE id=?", (mid,)).fetchone()
    conn.close()
    exp = datetime.strptime(row["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    assert 89 <= (exp - now).days <= 90


def test_cleanup_expired_memories():
    """cleanup_expired_memories soft-deletes expired memories."""
    db_path = _setup_db()
    # Insert a memory with expiry in the past
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = bus.get_conn(db_path)
    conn.execute(
        "INSERT INTO agent_memory (agent_id, content, source, importance, expires_at, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (2, "expired fact", "conversation", 2, past, now, now),
    )
    conn.commit()
    conn.close()

    count = bus.cleanup_expired_memories(db_path=db_path)
    assert count >= 1

    # Verify it's now inactive
    mems = bus.get_agent_memories(2, db_path=db_path)
    assert all("expired fact" not in m["content"] for m in mems)


# ===== Change 5: Better Dedup =====

def test_normalize_for_dedup():
    """_normalize_for_dedup strips tags, prefixes, punctuation."""
    result = agent_worker._normalize_for_dedup("[task] Human said: do the thing!")
    assert "task" not in result
    assert "human said" not in result
    assert "!" not in result
    assert "do the thing" in result


def test_is_duplicate_memory_substring():
    """Exact substring match is detected as duplicate."""
    db_path = _setup_db()
    bus.remember(2, "My dog is named Max", source="conversation", db_path=db_path)
    assert agent_worker._is_duplicate_memory(2, "My dog is named Max", db_path)


def test_is_duplicate_memory_keyword_overlap():
    """60%+ keyword overlap detected as duplicate."""
    db_path = _setup_db()
    bus.remember(2, "I love hiking mountains every weekend morning",
                 source="conversation", db_path=db_path)
    # Same core keywords — hiking, mountains, every, weekend, morning
    assert agent_worker._is_duplicate_memory(
        2, "I enjoy hiking mountains every weekend morning too", db_path)


def test_is_not_duplicate_memory():
    """Genuinely different content is NOT flagged as duplicate."""
    db_path = _setup_db()
    bus.remember(2, "My dog is named Max", source="conversation", db_path=db_path)
    assert not agent_worker._is_duplicate_memory(
        2, "I work at a coffee shop downtown", db_path)


# ===== Change 3: Feedback-Loop Learning =====

def test_positive_feedback_boosts_importance():
    """Positive feedback boosts last 3 memories by +1."""
    db_path = _setup_db()
    # Store 3 memories at importance 5
    ids = []
    for i in range(3):
        mid = bus.remember(2, f"memory {i}", importance=5,
                           source="conversation", db_path=db_path)
        ids.append(mid)

    agent_worker._apply_feedback_signal(db_path, 2, "great answer! nailed it")

    conn = bus.get_conn(db_path)
    for mid in ids:
        row = conn.execute("SELECT importance FROM agent_memory WHERE id=?", (mid,)).fetchone()
        assert row["importance"] == 6
    conn.close()


def test_negative_feedback_demotes_and_stores_correction():
    """Negative feedback demotes memories and stores a correction."""
    db_path = _setup_db()
    mid = bus.remember(2, "some wrong info", importance=5,
                       source="conversation", db_path=db_path)

    agent_worker._apply_feedback_signal(db_path, 2, "that's wrong, please fix that")

    conn = bus.get_conn(db_path)
    row = conn.execute("SELECT importance FROM agent_memory WHERE id=?", (mid,)).fetchone()
    assert row["importance"] == 3  # 5 - 2
    conn.close()

    # Check correction was stored
    mems = bus.get_agent_memories(2, db_path=db_path)
    assert any("[feedback]" in m["content"] for m in mems)


def test_importance_caps_at_10():
    """Positive feedback doesn't exceed importance 10."""
    db_path = _setup_db()
    mid = bus.remember(2, "perfect memory", importance=10,
                       source="conversation", db_path=db_path)
    agent_worker._apply_feedback_signal(db_path, 2, "great answer!")
    conn = bus.get_conn(db_path)
    row = conn.execute("SELECT importance FROM agent_memory WHERE id=?", (mid,)).fetchone()
    assert row["importance"] == 10
    conn.close()


def test_importance_floors_at_1():
    """Negative feedback doesn't go below importance 1."""
    db_path = _setup_db()
    mid = bus.remember(2, "bad memory", importance=1,
                       source="conversation", db_path=db_path)
    agent_worker._apply_feedback_signal(db_path, 2, "that's wrong")
    conn = bus.get_conn(db_path)
    row = conn.execute("SELECT importance FROM agent_memory WHERE id=?", (mid,)).fetchone()
    assert row["importance"] == 1
    conn.close()


# ===== Change 2: Cross-Agent Memory Sharing =====

def test_share_to_knowledge_store():
    """High-importance facts get shared to knowledge store."""
    db_path = _setup_db()
    agent_worker._share_to_knowledge_store(
        db_path, 2, "Human's dog is named Max", "fact")

    results = bus.search_knowledge("Max", db_path=db_path)
    assert len(results) >= 1
    assert any("Max" in r["subject"] for r in results)


def test_share_deduplicates():
    """Sharing same content twice doesn't create duplicates."""
    db_path = _setup_db()
    agent_worker._share_to_knowledge_store(
        db_path, 2, "Human loves pizza", "preference")
    agent_worker._share_to_knowledge_store(
        db_path, 2, "Human loves pizza", "preference")

    results = bus.search_knowledge("pizza", category_filter="preference",
                                   db_path=db_path)
    assert len(results) == 1


def test_get_shared_knowledge():
    """get_shared_knowledge retrieves entries without a search query."""
    db_path = _setup_db()
    bus.store_knowledge(2, "lesson", "Test lesson",
                        {"detail": "testing"}, db_path=db_path)
    bus.store_knowledge(2, "preference", "Test pref",
                        {"detail": "pref testing"}, db_path=db_path)

    results = bus.get_shared_knowledge(limit=10, db_path=db_path)
    assert len(results) >= 2

    # With category filter
    lessons = bus.get_shared_knowledge(category_filter="lesson",
                                       limit=10, db_path=db_path)
    assert all(r["category"] == "lesson" for r in lessons)


# ===== Change 7: Better Auto-Summarization =====

def test_extract_message_essence_decision():
    """Detects decisions in messages."""
    points = agent_worker._extract_message_essence(
        "I decided to go with the blue theme for the website.", True)
    assert any("Decided:" in p for p in points)


def test_extract_message_essence_url():
    """Detects URLs in messages."""
    points = agent_worker._extract_message_essence(
        "Check out https://example.com/docs for more info.", True)
    assert any("URL" in p for p in points)


def test_extract_message_essence_cost():
    """Detects costs in messages."""
    points = agent_worker._extract_message_essence(
        "The hosting costs $29.99 per month.", True)
    assert any("$29.99" in p for p in points)


def test_extract_message_essence_action():
    """Detects completed actions from agent replies."""
    points = agent_worker._extract_message_essence(
        "I've sent the report to the marketing team.", False)
    assert any("Done:" in p for p in points)


def test_extract_message_essence_reason():
    """Detects reasons/explanations."""
    points = agent_worker._extract_message_essence(
        "We changed vendors because the old one was too expensive.", True)
    assert any("Reason:" in p for p in points)


def test_extract_message_essence_fallback():
    """Falls back to first 2 sentences when no special signals."""
    points = agent_worker._extract_message_essence(
        "The weather is nice today. I went for a long walk in the park.", True)
    assert len(points) >= 1
    assert any("Human:" in p for p in points)


def test_extract_message_essence_max_3():
    """Returns at most 3 points per message."""
    body = ("I decided to switch providers because it costs $50/month. "
            "Check https://example.com for details. The deadline is Friday.")
    points = agent_worker._extract_message_essence(body, True)
    assert len(points) <= 3


# ===== Change 6: Temporal Patterns =====

def test_longest_contiguous_hours_simple():
    """Simple contiguous block."""
    start, end = agent_worker._longest_contiguous_hours({1, 2, 3, 4})
    assert start == 1
    assert end == 5


def test_longest_contiguous_hours_wrap():
    """Wrap around midnight."""
    start, end = agent_worker._longest_contiguous_hours({22, 23, 0, 1, 2})
    assert start == 22
    assert end == 3


def test_longest_contiguous_hours_empty():
    """Empty set returns None."""
    start, end = agent_worker._longest_contiguous_hours(set())
    assert start is None
    assert end is None


def test_temporal_seasonal_pattern_detection():
    """Seasonal patterns are detected and stored."""
    db_path = _setup_db()
    # Initialize human_profile
    conn = bus.get_conn(db_path)
    conn.execute("INSERT OR IGNORE INTO human_profile (human_id) VALUES (?)", (1,))
    conn.commit()
    conn.close()

    agent_worker._update_temporal_patterns(
        db_path, 2, "Holiday stress is killing me, Christmas shopping is crazy")

    val = bus.get_config("seasonal_patterns", db_path=db_path)
    assert val  # should have been set
    data = json.loads(val)
    assert any("holiday_stress" in v for v in data.values())


def test_temporal_trigger_detection():
    """Known triggers are detected and written to profile."""
    db_path = _setup_db()
    conn = bus.get_conn(db_path)
    conn.execute("INSERT OR IGNORE INTO human_profile (human_id) VALUES (?)", (1,))
    conn.commit()
    conn.close()

    agent_worker._update_temporal_patterns(
        db_path, 2, "Never mention my ex-boss, it triggers me badly")

    profile = bus.get_extended_profile(1, db_path=db_path)
    triggers = profile.get("known_triggers", [])
    assert len(triggers) >= 1


# ===== Change 1: Tiered Memory Limits =====

def test_format_memories_compact():
    """Memory formatting truncates to 100 chars and uses compact prefixes."""
    memories = [
        {"memory_type": "instruction", "content": "A" * 150},
        {"memory_type": "preference", "content": "short pref"},
        {"memory_type": "summary", "content": "context info"},
    ]
    result = agent_worker._format_memories_for_prompt(memories)
    assert "[instr]" in result
    assert "[pref]" in result
    assert "[ctx]" in result
    # Long content should be truncated
    assert "..." in result
    # The original 150-char content should be trimmed
    for line in result.split("\n"):
        if "[instr]" in line:
            # prefix + content should be under ~110 chars
            assert len(line) < 120


# ===== Integration =====

def test_extract_learnings_with_feedback():
    """Full integration: feedback + extraction in one call."""
    db_path = _setup_db()
    # First store some memories
    bus.remember(2, "user likes coffee", importance=5,
                 source="conversation", db_path=db_path)

    # Then positive feedback should boost
    agent_worker._extract_conversation_learnings(
        db_path, 2, "right_hand",
        "great answer! I love herbal tea as well",
        "Glad you liked it!")

    # The coffee memory should have been boosted
    conn = bus.get_conn(db_path)
    row = conn.execute(
        "SELECT importance FROM agent_memory WHERE content='user likes coffee'"
    ).fetchone()
    conn.close()
    assert row["importance"] == 6  # was 5, boosted +1

    # And "herbal tea" preference should have been extracted
    mems = bus.get_agent_memories(2, db_path=db_path)
    assert any("herbal tea" in m["content"] for m in mems)
