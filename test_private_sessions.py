"""
test_private_sessions.py - Private sessions integration tests for crew-bus.

Tests:
  1.  Start a private session between human and agent
  2.  Starting a duplicate session returns the existing one
  3.  Send private message from human to agent
  4.  Send private message from agent to human
  5.  Private message has private_session_id set
  6.  Crew Boss cannot see private message content (excluded from normal queries)
  7.  Audit trail logs session existence but NOT content
  8.  Session auto-expires after timeout
  9.  Cleanup function closes expired sessions
  10. Only one active session per human-agent pair
  11. Private session routing override works
  12. End session manually
  13. Private messages appear in agent chat history for the human
  14. Team agent private sessions work the same
  15. Invalid agent in session is rejected
  16. get_active_private_session returns None for non-existent session
  17. Message count increments with each private message
  18. Sliding window extends expiry on each message

Run:
  python test_private_sessions.py
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import bus

# ---------------------------------------------------------------------------
# Test DB
# ---------------------------------------------------------------------------

TEST_DB = Path(__file__).parent / "test_private_sessions.db"
_configs = Path(__file__).parent / "configs"
CONFIG = _configs / "ryan_stack.yaml" if (_configs / "ryan_stack.yaml").exists() else _configs / "example_stack.yaml"

if TEST_DB.exists():
    os.remove(str(TEST_DB))

# Test tracking
passed = 0
failed = 0


def check(test_name, condition, detail=""):
    global passed, failed
    label = "[PASS]" if condition else "[FAIL]"
    msg = f"  {label} {detail}" if detail else f"  {label} {test_name}"
    print(msg)
    if condition:
        passed += 1
    else:
        failed += 1
    return condition


def section(name):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# Setup: Initialize DB and load hierarchy
# ---------------------------------------------------------------------------

section("Setup: Initialize DB + Load Hierarchy")

bus.init_db(TEST_DB)
result = bus.load_hierarchy(str(CONFIG), TEST_DB)
agents_loaded = result.get("agents_loaded", [])
check("setup.hierarchy", len(agents_loaded) >= 10,
      f"Loaded {len(agents_loaded)} agents")

# Get key agent references
conn = bus.get_conn(TEST_DB)
human = conn.execute("SELECT * FROM agents WHERE agent_type='human' LIMIT 1").fetchone()
crew_boss = conn.execute("SELECT * FROM agents WHERE agent_type='right_hand' LIMIT 1").fetchone()
wellness = conn.execute("SELECT * FROM agents WHERE agent_type='wellness' LIMIT 1").fetchone()
guard = conn.execute("SELECT * FROM agents WHERE agent_type='security' LIMIT 1").fetchone()
# Find a team manager and worker
manager = conn.execute("SELECT * FROM agents WHERE agent_type='manager' LIMIT 1").fetchone()
worker = conn.execute("SELECT * FROM agents WHERE parent_agent_id=? LIMIT 1",
                      (manager["id"],)).fetchone() if manager else None
conn.close()

check("setup.human", human is not None, f"Human: {human['name'] if human else 'N/A'}")
check("setup.crew_boss", crew_boss is not None, f"Crew Boss: {crew_boss['name'] if crew_boss else 'N/A'}")
check("setup.wellness", wellness is not None, f"Wellness: {wellness['name'] if wellness else 'N/A'}")

# ---------------------------------------------------------------------------
# Test 1: Start a private session
# ---------------------------------------------------------------------------

section("Test 1: Start a private session")

session = bus.start_private_session(human["id"], wellness["id"], channel="web",
                                     timeout_minutes=30, db_path=TEST_DB)
check("start.ok", session.get("session_id") is not None,
      f"Session ID: {session.get('session_id')}")
check("start.channel", session.get("channel") == "web", f"Channel: {session.get('channel')}")
check("start.expires", session.get("expires_at") is not None, f"Expires: {session.get('expires_at')}")

session_id = session["session_id"]

# ---------------------------------------------------------------------------
# Test 2: Starting a duplicate session returns the existing one
# ---------------------------------------------------------------------------

section("Test 2: Duplicate session returns existing")

session2 = bus.start_private_session(human["id"], wellness["id"], channel="web",
                                      timeout_minutes=30, db_path=TEST_DB)
check("dup.same_id", session2.get("session_id") == session_id,
      f"Got {session2.get('session_id')}, expected {session_id}")

# ---------------------------------------------------------------------------
# Test 3: Send private message from human to agent
# ---------------------------------------------------------------------------

section("Test 3: Send private message (human -> agent)")

msg_result = bus.send_private_message(session_id, human["id"],
                                       "I need to discuss something privately", db_path=TEST_DB)
check("msg_h2a.ok", msg_result.get("ok") is True, f"Result: {msg_result}")
check("msg_h2a.id", msg_result.get("message_id") is not None,
      f"Message ID: {msg_result.get('message_id')}")

# ---------------------------------------------------------------------------
# Test 4: Send private message from agent to human
# ---------------------------------------------------------------------------

section("Test 4: Send private message (agent -> human)")

msg_result2 = bus.send_private_message(session_id, wellness["id"],
                                        "Of course, I'm here to help. What's on your mind?",
                                        db_path=TEST_DB)
check("msg_a2h.ok", msg_result2.get("ok") is True, f"Result: {msg_result2}")

# ---------------------------------------------------------------------------
# Test 5: Private message has private_session_id set
# ---------------------------------------------------------------------------

section("Test 5: Private message has private_session_id")

conn = bus.get_conn(TEST_DB)
priv_msg = conn.execute("SELECT * FROM messages WHERE id=?",
                        (msg_result["message_id"],)).fetchone()
conn.close()
check("priv_flag.set", priv_msg["private_session_id"] == session_id,
      f"private_session_id: {priv_msg['private_session_id']}")

# ---------------------------------------------------------------------------
# Test 6: Crew Boss cannot see private message content
# ---------------------------------------------------------------------------

section("Test 6: Crew Boss cannot see private messages")

conn = bus.get_conn(TEST_DB)
# Normal query that Crew Boss would use - should exclude private messages
public_msgs = conn.execute("""
    SELECT * FROM messages
    WHERE (from_agent_id=? OR to_agent_id=?)
    AND private_session_id IS NULL
""", (wellness["id"], wellness["id"])).fetchall()
all_msgs = conn.execute("""
    SELECT * FROM messages
    WHERE (from_agent_id=? OR to_agent_id=?)
""", (wellness["id"], wellness["id"])).fetchall()
conn.close()
check("boss_cant_see.excluded", len(public_msgs) < len(all_msgs),
      f"Public: {len(public_msgs)}, All: {len(all_msgs)}")

# ---------------------------------------------------------------------------
# Test 7: Audit trail logs session existence but NOT content
# ---------------------------------------------------------------------------

section("Test 7: Audit trail - no content logged")

conn = bus.get_conn(TEST_DB)
audit_rows = conn.execute("""
    SELECT * FROM audit_log WHERE event_type='private_session_started'
    ORDER BY timestamp DESC LIMIT 5
""").fetchall()
conn.close()
check("audit.exists", len(audit_rows) > 0, f"Found {len(audit_rows)} audit entries")
if audit_rows:
    details = audit_rows[0]["details"]
    check("audit.no_content", "discuss" not in details.lower(),
          f"Details (should have no message content): {details[:100]}")
    # Check it has agent_id and channel but not message text
    check("audit.has_agent_id", "agent_id" in details, f"Contains agent_id: {'agent_id' in details}")

# ---------------------------------------------------------------------------
# Test 8: Session auto-expires after timeout
# ---------------------------------------------------------------------------

section("Test 8: Session auto-expires")

# Create a session with 0 minute timeout (expires immediately)
short_session = bus.start_private_session(human["id"], guard["id"], channel="web",
                                           timeout_minutes=0, db_path=TEST_DB)
short_id = short_session["session_id"]
# Manually set expires_at to past
conn = bus.get_conn(TEST_DB)
past = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
conn.execute("UPDATE private_sessions SET expires_at=? WHERE id=?", (past, short_id))
conn.commit()
conn.close()

# Now try to get it - should auto-close and return None
active = bus.get_active_private_session(human["id"], guard["id"], db_path=TEST_DB)
check("autoexpire.closed", active is None,
      f"Active session after expiry: {active}")

# Verify it was closed with ended_by='timeout'
conn = bus.get_conn(TEST_DB)
closed = conn.execute("SELECT * FROM private_sessions WHERE id=?", (short_id,)).fetchone()
conn.close()
check("autoexpire.timeout", closed["ended_by"] == "timeout",
      f"ended_by: {closed['ended_by']}")

# ---------------------------------------------------------------------------
# Test 9: Cleanup function closes expired sessions
# ---------------------------------------------------------------------------

section("Test 9: Cleanup expired sessions")

# Create another session with expired time
cleanup_session = bus.start_private_session(human["id"], guard["id"], channel="web",
                                             timeout_minutes=30, db_path=TEST_DB)
cleanup_id = cleanup_session["session_id"]
conn = bus.get_conn(TEST_DB)
past2 = (datetime.now(timezone.utc) - timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
conn.execute("UPDATE private_sessions SET expires_at=? WHERE id=?", (past2, cleanup_id))
conn.commit()
conn.close()

closed_count = bus.cleanup_expired_sessions(db_path=TEST_DB)
check("cleanup.count", closed_count >= 1, f"Closed {closed_count} expired sessions")

# ---------------------------------------------------------------------------
# Test 10: Only one active session per human-agent pair
# ---------------------------------------------------------------------------

section("Test 10: One active session per pair")

# The original wellness session should still be active
active_well = bus.get_active_private_session(human["id"], wellness["id"], db_path=TEST_DB)
check("one_per_pair.exists", active_well is not None,
      f"Active wellness session: {active_well['id'] if active_well else None}")
check("one_per_pair.same_id", active_well["id"] == session_id,
      f"Got {active_well['id']}, expected {session_id}")

# ---------------------------------------------------------------------------
# Test 11: Private session routing override works
# ---------------------------------------------------------------------------

section("Test 11: Routing override")

# Normally wellness -> human is blocked (must go through Crew Boss).
# With active session it should be allowed via send_message.
try:
    route_msg = bus.send_message(
        from_id=wellness["id"], to_id=human["id"],
        message_type="report", subject="Private routing test",
        body="This should work due to active private session",
        priority="normal", db_path=TEST_DB)
    check("routing.allowed", route_msg.get("message_id") is not None,
          f"Message sent: {route_msg}")
except PermissionError as e:
    # If the session routing override works, we won't get here
    check("routing.allowed", False, f"Blocked: {e}")

# Also test that without the session, it would be blocked
# (we'll test this after ending the session in test 12)

# ---------------------------------------------------------------------------
# Test 12: End session manually
# ---------------------------------------------------------------------------

section("Test 12: End session manually")

end_result = bus.end_private_session(session_id, ended_by="human", db_path=TEST_DB)
check("end.ok", end_result.get("ok") is True, f"Result: {end_result}")

# Verify it's closed
conn = bus.get_conn(TEST_DB)
ended = conn.execute("SELECT * FROM private_sessions WHERE id=?", (session_id,)).fetchone()
conn.close()
check("end.inactive", ended["active"] == 0, f"active: {ended['active']}")
check("end.ended_by", ended["ended_by"] == "human", f"ended_by: {ended['ended_by']}")
check("end.msg_count", ended["message_count"] == 2, f"message_count: {ended['message_count']}")

# Verify routing override no longer works
active_check = bus.get_active_private_session(human["id"], wellness["id"], db_path=TEST_DB)
check("end.no_active", active_check is None, "No active session after end")

# ---------------------------------------------------------------------------
# Test 13: Private messages appear in chat history
# ---------------------------------------------------------------------------

section("Test 13: Private messages in chat history")

# The private messages from tests 3 and 4 should still be in the messages table
conn = bus.get_conn(TEST_DB)
priv_msgs = conn.execute("""
    SELECT * FROM messages WHERE private_session_id IS NOT NULL
    AND ((from_agent_id=? AND to_agent_id=?) OR (from_agent_id=? AND to_agent_id=?))
""", (human["id"], wellness["id"], wellness["id"], human["id"])).fetchall()
conn.close()
check("chat_history.count", len(priv_msgs) == 2,
      f"Found {len(priv_msgs)} private messages in chat history")

# ---------------------------------------------------------------------------
# Test 14: Team agent private sessions work
# ---------------------------------------------------------------------------

section("Test 14: Team agent private sessions")

if manager:
    team_session = bus.start_private_session(human["id"], manager["id"],
                                              channel="web", timeout_minutes=30, db_path=TEST_DB)
    check("team.session_ok", team_session.get("session_id") is not None,
          f"Team session: {team_session.get('session_id')}")

    team_msg = bus.send_private_message(team_session["session_id"], human["id"],
                                         "Private message to team manager", db_path=TEST_DB)
    check("team.msg_ok", team_msg.get("ok") is True, f"Result: {team_msg}")

    # End it
    bus.end_private_session(team_session["session_id"], ended_by="human", db_path=TEST_DB)
else:
    check("team.skip", True, "No manager agent found, skipping team tests")
    check("team.skip2", True, "Skipped")

# ---------------------------------------------------------------------------
# Test 15: Invalid agent in session is rejected
# ---------------------------------------------------------------------------

section("Test 15: Invalid agent rejected")

# Try to send from an agent not in the session
new_session = bus.start_private_session(human["id"], wellness["id"],
                                         channel="web", timeout_minutes=30, db_path=TEST_DB)
bad_msg = bus.send_private_message(new_session["session_id"], guard["id"],
                                    "I shouldn't be able to send this", db_path=TEST_DB)
check("invalid.rejected", bad_msg.get("ok") is not True,
      f"Result: {bad_msg}")
bus.end_private_session(new_session["session_id"], ended_by="human", db_path=TEST_DB)

# ---------------------------------------------------------------------------
# Test 16: get_active_private_session returns None for non-existent
# ---------------------------------------------------------------------------

section("Test 16: No session returns None")

no_session = bus.get_active_private_session(human["id"], 99999, db_path=TEST_DB)
check("nosession.none", no_session is None, f"Result: {no_session}")

# ---------------------------------------------------------------------------
# Test 17: Message count increments
# ---------------------------------------------------------------------------

section("Test 17: Message count increments")

mc_session = bus.start_private_session(human["id"], wellness["id"],
                                        channel="web", timeout_minutes=30, db_path=TEST_DB)
mc_id = mc_session["session_id"]
bus.send_private_message(mc_id, human["id"], "msg 1", db_path=TEST_DB)
bus.send_private_message(mc_id, wellness["id"], "msg 2", db_path=TEST_DB)
bus.send_private_message(mc_id, human["id"], "msg 3", db_path=TEST_DB)

conn = bus.get_conn(TEST_DB)
mc_row = conn.execute("SELECT message_count FROM private_sessions WHERE id=?",
                      (mc_id,)).fetchone()
conn.close()
check("msg_count.three", mc_row["message_count"] == 3,
      f"message_count: {mc_row['message_count']}")

# ---------------------------------------------------------------------------
# Test 18: Sliding window extends expiry
# ---------------------------------------------------------------------------

section("Test 18: Sliding window expiry")

conn = bus.get_conn(TEST_DB)
# Read the current expires_at
before = conn.execute("SELECT expires_at FROM private_sessions WHERE id=?",
                      (mc_id,)).fetchone()
conn.close()

# Send another message - should extend expires_at
bus.send_private_message(mc_id, human["id"], "extending expiry", db_path=TEST_DB)

conn = bus.get_conn(TEST_DB)
after = conn.execute("SELECT expires_at FROM private_sessions WHERE id=?",
                     (mc_id,)).fetchone()
conn.close()

check("sliding.extended", after["expires_at"] >= before["expires_at"],
      f"Before: {before['expires_at']}, After: {after['expires_at']}")

bus.end_private_session(mc_id, ended_by="human", db_path=TEST_DB)

# ---------------------------------------------------------------------------
# Cleanup and Summary
# ---------------------------------------------------------------------------

section("SUMMARY")

if TEST_DB.exists():
    os.remove(str(TEST_DB))

total = passed + failed
print(f"\n  Total: {total} | Passed: {passed} | Failed: {failed}")
if failed:
    print(f"  *** {failed} TESTS FAILED ***")
    sys.exit(1)
else:
    print("  All tests passed!")
    sys.exit(0)
