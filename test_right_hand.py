"""Tests for right_hand.py — RightHand decision engine, trust scoring, burnout, briefings."""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import bus
import right_hand


def _fresh_db():
    """Create a temp DB with full schema + human and Crew Boss agents."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db = Path(tmp.name)
    tmp.close()
    bus.init_db(db)
    conn = bus.get_conn(db)
    # Human
    conn.execute(
        "INSERT INTO agents (id, name, agent_type, role, status, active, "
        "burnout_score, trust_score) "
        "VALUES (1, 'TestHuman', 'human', 'human', 'active', 1, 3, 1)"
    )
    # Crew Boss
    conn.execute(
        "INSERT INTO agents (id, name, agent_type, role, status, active, "
        "parent_agent_id, trust_score) "
        "VALUES (2, 'Crew-Boss', 'right_hand', 'right_hand', 'active', 1, 1, 5)"
    )
    # Worker
    conn.execute(
        "INSERT INTO agents (id, name, agent_type, role, status, active, "
        "parent_agent_id, trust_score) "
        "VALUES (3, 'TestWorker', 'worker', 'worker', 'active', 1, 2, 1)"
    )
    # Guardian
    conn.execute(
        "INSERT INTO agents (id, name, agent_type, role, status, active, "
        "parent_agent_id, trust_score) "
        "VALUES (4, 'Guardian', 'guardian', 'security', 'active', 1, 2, 1)"
    )
    conn.commit()
    conn.close()
    return db


def _make_rh(db):
    """Create a RightHand instance with the test DB."""
    return right_hand.RightHand(right_hand_id=2, human_id=1, db_path=db)


# ---------------------------------------------------------------------------
# RightHand initialization
# ---------------------------------------------------------------------------

def test_right_hand_init():
    """RightHand initializes with agent and human context."""
    db = _fresh_db()
    rh = _make_rh(db)
    assert rh.rh_id == 2
    assert rh.human_id == 1
    assert rh.trust_score > 0


# ---------------------------------------------------------------------------
# assess_delivery
# ---------------------------------------------------------------------------

def test_deliver_critical_immediately():
    """assess_delivery always delivers critical messages."""
    db = _fresh_db()
    rh = _make_rh(db)
    message = {
        "id": 1,
        "from_agent_id": 3,
        "message_type": "report",
        "subject": "Server down",
        "body": "Production is down",
        "priority": "critical",
    }
    result = rh.assess_delivery(message)
    assert result["deliver"] is True
    assert "critical" in result["reason"].lower()


def test_deliver_escalation_immediately():
    """assess_delivery always delivers escalation messages."""
    db = _fresh_db()
    rh = _make_rh(db)
    message = {
        "id": 1,
        "from_agent_id": 3,
        "message_type": "escalation",
        "subject": "Need approval",
        "body": "Budget request",
        "priority": "normal",
    }
    result = rh.assess_delivery(message)
    assert result["deliver"] is True


def test_deliver_normal_message():
    """assess_delivery delivers normal messages when timing checks pass."""
    db = _fresh_db()
    rh = _make_rh(db)
    message = {
        "id": 1,
        "from_agent_id": 3,
        "message_type": "report",
        "subject": "Daily update",
        "body": "All systems normal",
        "priority": "normal",
    }

    with patch("bus.should_deliver_now",
               return_value={"deliver": True, "reason": "ok", "delay_until": None}):
        result = rh.assess_delivery(message)
        assert result["deliver"] is True


def test_deliver_blocked_by_timing():
    """assess_delivery queues messages when timing rules block delivery."""
    db = _fresh_db()
    rh = _make_rh(db)
    message = {
        "id": 1,
        "from_agent_id": 3,
        "message_type": "report",
        "subject": "Update",
        "body": "Non-urgent",
        "priority": "normal",
    }

    with patch("bus.should_deliver_now",
               return_value={"deliver": False, "reason": "Quiet hours",
                             "delay_until": "2026-02-21T08:00:00Z"}):
        result = rh.assess_delivery(message)
        assert result["deliver"] is False
        assert "quiet" in result["reason"].lower()


def test_deliver_idea_filtered():
    """assess_delivery filters ideas based on rejection history."""
    db = _fresh_db()
    rh = _make_rh(db)
    message = {
        "id": 10,
        "from_agent_id": 3,
        "message_type": "idea",
        "subject": "New feature",
        "body": "Let's add X",
        "priority": "normal",
    }

    with patch("bus.filter_strategy_idea",
               return_value={"action": "filter", "reason": "Similar idea rejected"}):
        result = rh.assess_delivery(message)
        assert result["deliver"] is False
        assert "rejected" in result["reason"].lower()


def test_deliver_idea_queued():
    """assess_delivery queues ideas based on filter result."""
    db = _fresh_db()
    rh = _make_rh(db)
    message = {
        "id": 10,
        "from_agent_id": 3,
        "message_type": "idea",
        "subject": "Strategy idea",
        "body": "What if we...",
        "priority": "normal",
    }

    with patch("bus.filter_strategy_idea",
               return_value={"action": "queue", "reason": "Save for evening",
                             "delay_until": "2026-02-20T18:00:00Z"}):
        result = rh.assess_delivery(message)
        assert result["deliver"] is False
        assert result["delay_until"] is not None


# ---------------------------------------------------------------------------
# filter_idea
# ---------------------------------------------------------------------------

def test_filter_idea_no_id():
    """filter_idea passes through when no message ID provided."""
    db = _fresh_db()
    rh = _make_rh(db)
    result = rh.filter_idea(None)
    assert result["action"] == "pass"


def test_filter_idea_with_id():
    """filter_idea delegates to bus.filter_strategy_idea."""
    db = _fresh_db()
    rh = _make_rh(db)

    with patch("bus.filter_strategy_idea",
               return_value={"action": "pass", "reason": "No prior rejections"}) as mock_filter:
        result = rh.filter_idea(42)
        assert result["action"] == "pass"
        mock_filter.assert_called_once()


# ---------------------------------------------------------------------------
# handle_escalation — trust-based decisions
# ---------------------------------------------------------------------------

def test_escalation_low_trust():
    """handle_escalation delivers to human at trust 1-3."""
    db = _fresh_db()
    rh = _make_rh(db)

    # Set trust to 2
    conn = bus.get_conn(db)
    conn.execute("UPDATE agents SET trust_score=2 WHERE id=2")
    conn.commit()
    conn.close()

    message = {"id": 1, "message_type": "escalation",
               "subject": "Approval needed", "priority": "normal"}
    result = rh.handle_escalation(message)
    assert result["action"] == "deliver_to_human"


def test_escalation_mid_trust_with_precedent():
    """handle_escalation handles autonomously at trust 4-6 with precedent."""
    db = _fresh_db()
    rh = _make_rh(db)

    conn = bus.get_conn(db)
    conn.execute("UPDATE agents SET trust_score=5 WHERE id=2")
    conn.commit()
    conn.close()

    message = {"id": 1, "message_type": "escalation",
               "subject": "Routine approval", "priority": "normal"}

    with patch("bus.search_knowledge", return_value=[{"id": 1, "content": "past decision"}]):
        result = rh.handle_escalation(message)
        assert result["action"] == "handle_autonomously"
        assert "precedent" in result["response"].lower()


def test_escalation_mid_trust_novel():
    """handle_escalation delivers novel situations to human at trust 4-6."""
    db = _fresh_db()
    rh = _make_rh(db)

    conn = bus.get_conn(db)
    conn.execute("UPDATE agents SET trust_score=5 WHERE id=2")
    conn.commit()
    conn.close()

    message = {"id": 1, "message_type": "escalation",
               "subject": "Completely new thing", "priority": "normal"}

    with patch("bus.search_knowledge", return_value=[]):
        result = rh.handle_escalation(message)
        assert result["action"] == "deliver_to_human"


def test_escalation_high_trust_autonomous():
    """handle_escalation handles autonomously at trust 7+."""
    db = _fresh_db()
    rh = _make_rh(db)

    conn = bus.get_conn(db)
    conn.execute("UPDATE agents SET trust_score=8 WHERE id=2")
    conn.commit()
    conn.close()

    message = {"id": 1, "message_type": "escalation",
               "subject": "Standard request", "priority": "normal"}
    result = rh.handle_escalation(message)
    assert result["action"] == "handle_autonomously"


def test_escalation_high_trust_critical():
    """handle_escalation still delivers critical at high trust."""
    db = _fresh_db()
    rh = _make_rh(db)

    conn = bus.get_conn(db)
    conn.execute("UPDATE agents SET trust_score=9 WHERE id=2")
    conn.commit()
    conn.close()

    message = {"id": 1, "message_type": "escalation",
               "subject": "Critical decision", "priority": "critical"}
    result = rh.handle_escalation(message)
    assert result["action"] == "deliver_to_human"


# ---------------------------------------------------------------------------
# compile_briefing
# ---------------------------------------------------------------------------

def test_compile_morning_briefing():
    """compile_briefing('morning') produces a valid briefing dict."""
    db = _fresh_db()
    rh = _make_rh(db)

    # Send some messages so the briefing has content
    bus.send_message(3, 2, "report", "Worker report", body="All good",
                     priority="normal", db_path=db)
    bus.send_message(3, 2, "alert", "High priority", body="Issue found",
                     priority="high", db_path=db)

    briefing = rh.compile_briefing("morning")
    assert briefing["briefing_type"] == "morning"
    assert "subject" in briefing
    assert "body_plain" in briefing
    assert "Morning" in briefing["subject"]
    assert briefing["item_count"] >= 0


def test_compile_evening_briefing():
    """compile_briefing('evening') produces an evening summary."""
    db = _fresh_db()
    rh = _make_rh(db)
    briefing = rh.compile_briefing("evening")
    assert briefing["briefing_type"] == "evening"
    assert "Evening" in briefing["subject"]


def test_compile_urgent_briefing():
    """compile_briefing('urgent') shows only critical items."""
    db = _fresh_db()
    rh = _make_rh(db)

    # Send a critical message
    bus.send_message(3, 2, "alert", "Server fire!", body="Everything is down",
                     priority="critical", db_path=db)

    briefing = rh.compile_briefing("urgent")
    assert briefing["briefing_type"] == "urgent"
    assert briefing["priority"] == "critical"


def test_compile_invalid_type():
    """compile_briefing raises ValueError for unknown type."""
    db = _fresh_db()
    rh = _make_rh(db)
    try:
        rh.compile_briefing("banana")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Unknown briefing type" in str(e)


def test_morning_briefing_burnout_tone():
    """Morning briefing adapts tone based on burnout score."""
    db = _fresh_db()

    # Set high burnout
    conn = bus.get_conn(db)
    conn.execute("UPDATE agents SET burnout_score=8 WHERE id=1")
    conn.commit()
    conn.close()

    rh = _make_rh(db)
    briefing = rh.compile_briefing("morning")
    # High burnout uses lighter tone
    assert "light" in briefing["body_plain"].lower() or "essential" in briefing["body_plain"].lower()


# ---------------------------------------------------------------------------
# learn_from_feedback
# ---------------------------------------------------------------------------

def test_learn_from_feedback_approved():
    """learn_from_feedback records approval."""
    db = _fresh_db()
    rh = _make_rh(db)

    # Create a decision to give feedback on
    decision_id = bus.log_decision(
        2, 1, "deliver",
        {"subject": "Test"}, "delivered",
        db_path=db,
    )

    result = rh.learn_from_feedback(decision_id, human_approved=True)
    assert result["human_approved"] is True
    assert result["override"] is False


def test_learn_from_feedback_override():
    """learn_from_feedback records override with action."""
    db = _fresh_db()
    rh = _make_rh(db)

    decision_id = bus.log_decision(
        2, 1, "filter",
        {"subject": "Test"}, "filtered",
        db_path=db,
    )

    result = rh.learn_from_feedback(
        decision_id, human_approved=False,
        human_action="Delivered manually",
        note="I wanted to see this",
    )
    assert result["override"] is True
    assert result["human_action"] == "Delivered manually"


# ---------------------------------------------------------------------------
# protect_reputation
# ---------------------------------------------------------------------------

def test_reputation_clean_message():
    """protect_reputation approves clean messages."""
    db = _fresh_db()
    rh = _make_rh(db)
    message = {
        "subject": "Meeting notes",
        "body": "Here are the notes from today's meeting.",
    }
    result = rh.protect_reputation(message)
    assert result["action"] == "approve"
    assert result["concerns"] == []


def test_reputation_anger_detected():
    """protect_reputation flags angry language."""
    db = _fresh_db()
    rh = _make_rh(db)
    message = {
        "subject": "Complaint",
        "body": "This is unacceptable! I demand a refund for this incompetent service.",
    }
    result = rh.protect_reputation(message)
    assert result["action"] == "flag_for_review"
    assert any("frustration" in c.lower() for c in result["concerns"])


def test_reputation_overpromising():
    """protect_reputation flags overpromising."""
    db = _fresh_db()
    rh = _make_rh(db)
    message = {
        "subject": "Proposal",
        "body": "We guarantee delivery by Monday. No problem at all, it's easy.",
    }
    result = rh.protect_reputation(message)
    assert len(result["concerns"]) > 0
    assert any("overpromising" in c.lower() for c in result["concerns"])


def test_reputation_high_burnout():
    """protect_reputation flags messages during high burnout."""
    db = _fresh_db()
    conn = bus.get_conn(db)
    conn.execute("UPDATE agents SET burnout_score=8 WHERE id=1")
    conn.commit()
    conn.close()

    rh = _make_rh(db)
    message = {
        "subject": "Quick note",
        "body": "Just a short message.",
    }
    result = rh.protect_reputation(message)
    assert any("burnout" in c.lower() for c in result["concerns"])


# ---------------------------------------------------------------------------
# assess_human_state
# ---------------------------------------------------------------------------

def test_assess_human_state():
    """assess_human_state returns comprehensive human state."""
    db = _fresh_db()
    rh = _make_rh(db)
    state = rh.assess_human_state()
    assert "burnout_score" in state
    assert "recommended_load" in state
    assert "messages_received_today" in state
    assert "decisions_made_today" in state


def test_assess_human_state_high_burnout():
    """assess_human_state recommends emergency_only load at high burnout."""
    db = _fresh_db()
    # assess_human_state reads from human_state table via bus.get_human_state()
    rh = _make_rh(db)
    # Trigger human_state creation first
    rh.assess_human_state()
    # Now update the human_state table
    conn = bus.get_conn(db)
    conn.execute("UPDATE human_state SET burnout_score=9 WHERE human_id=1")
    conn.commit()
    conn.close()

    state = rh.assess_human_state()
    assert state["burnout_score"] == 9
    assert state["recommended_load"] == "emergency_only"


def test_assess_human_state_low_burnout():
    """assess_human_state recommends full load at low burnout."""
    db = _fresh_db()
    rh = _make_rh(db)
    # Trigger human_state creation first
    rh.assess_human_state()
    # Now update
    conn = bus.get_conn(db)
    conn.execute("UPDATE human_state SET burnout_score=1 WHERE human_id=1")
    conn.commit()
    conn.close()

    state = rh.assess_human_state()
    assert state["burnout_score"] == 1
    assert state["recommended_load"] == "full"


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------

def test_heartbeat_init():
    """Heartbeat initializes with RightHand context."""
    db = _fresh_db()
    rh = _make_rh(db)
    hb = right_hand.Heartbeat(rh, db_path=db, interval_minutes=1)
    assert hb.interval == 60
    assert hb.running is False


def test_heartbeat_start_stop():
    """Heartbeat starts and stops its daemon thread."""
    db = _fresh_db()
    rh = _make_rh(db)
    hb = right_hand.Heartbeat(rh, db_path=db, interval_minutes=1)

    with patch.object(hb, "_tick"):
        hb.start()
        assert hb.running is True
        hb.stop()
        assert hb.running is False


def test_heartbeat_default_checks():
    """Heartbeat has default checks configured."""
    checks = right_hand.Heartbeat.DEFAULT_CHECKS
    check_types = [c["type"] for c in checks]
    assert "morning_briefing" in check_types
    assert "evening_summary" in check_types
    assert "burnout_check" in check_types
    assert "integrity_audit" in check_types


def test_heartbeat_burnout_check():
    """Heartbeat burnout check triggers at high burnout."""
    db = _fresh_db()
    rh = _make_rh(db)
    # Trigger human_state creation
    rh.assess_human_state()
    # Set high burnout in human_state table
    conn = bus.get_conn(db)
    conn.execute("UPDATE human_state SET burnout_score=8 WHERE human_id=1")
    conn.commit()
    conn.close()

    hb = right_hand.Heartbeat(rh, db_path=db)
    result = hb._check_burnout()
    assert result is not None
    assert result["action_needed"] is True
    assert result["type"] == "burnout_alert"


def test_heartbeat_burnout_check_ok():
    """Heartbeat burnout check returns None when burnout is low."""
    db = _fresh_db()
    rh = _make_rh(db)
    hb = right_hand.Heartbeat(rh, db_path=db)
    result = hb._check_burnout()
    assert result is None
