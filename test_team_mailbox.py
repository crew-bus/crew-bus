"""
test_team_mailbox.py - Team Mailbox integration tests for crew-bus.

Tests:
  1.  Worker can send to team mailbox
  2.  Message appears with correct severity
  3.  Rate limit enforced (4th message in 24h rejected)
  4.  Code Red creates audit entry
  5.  Audit logs existence but not content
  6.  Manager can also send to mailbox
  7.  Agent NOT in a team cannot send to mailbox
  8.  get_team_mailbox_summary returns correct counts
  9.  Mark as read works
  10. Unread filter works
  11. Multiple severities display correctly in summary

Run:
  python test_team_mailbox.py
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

TEST_DB = Path(__file__).parent / "test_team_mailbox.db"
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
manager = conn.execute("SELECT * FROM agents WHERE agent_type='manager' LIMIT 1").fetchone()
worker = None
if manager:
    worker = conn.execute("SELECT * FROM agents WHERE parent_agent_id=? LIMIT 1",
                          (manager["id"],)).fetchone()
conn.close()

check("setup.human", human is not None, f"Human: {human['name'] if human else 'N/A'}")
check("setup.manager", manager is not None, f"Manager: {manager['name'] if manager else 'N/A'}")
check("setup.worker", worker is not None, f"Worker: {worker['name'] if worker else 'N/A'}")

team_id = manager["id"] if manager else None

# ---------------------------------------------------------------------------
# Test 1: Worker can send to team mailbox
# ---------------------------------------------------------------------------

section("Test 1: Worker sends to team mailbox")

result1 = bus.send_to_team_mailbox(worker["id"], "Urgent: System down",
                                    "The system has been unresponsive for 30 minutes.",
                                    severity="warning", db_path=TEST_DB)
check("worker_send.ok", result1.get("ok") is True, f"Result: {result1}")
check("worker_send.id", result1.get("mailbox_id") is not None,
      f"Mailbox ID: {result1.get('mailbox_id')}")
check("worker_send.severity", result1.get("severity") == "warning",
      f"Severity: {result1.get('severity')}")

msg1_id = result1["mailbox_id"]

# ---------------------------------------------------------------------------
# Test 2: Message appears with correct severity
# ---------------------------------------------------------------------------

section("Test 2: Message has correct severity")

msgs = bus.get_team_mailbox(team_id, db_path=TEST_DB)
check("severity.count", len(msgs) >= 1, f"Found {len(msgs)} messages")
first_msg = msgs[0]
check("severity.value", first_msg["severity"] == "warning",
      f"Severity: {first_msg['severity']}")
check("severity.subject", first_msg["subject"] == "Urgent: System down",
      f"Subject: {first_msg['subject']}")
check("severity.unread", first_msg["read"] == 0, f"Read: {first_msg['read']}")

# ---------------------------------------------------------------------------
# Test 3: Rate limit enforced (4th message in 24h rejected)
# ---------------------------------------------------------------------------

section("Test 3: Rate limit enforced")

# Send 2 more (total 3) - should work
r2 = bus.send_to_team_mailbox(worker["id"], "Update 1", "Status update",
                               severity="info", db_path=TEST_DB)
check("rate.msg2", r2.get("ok") is True, f"Message 2: {r2}")

r3 = bus.send_to_team_mailbox(worker["id"], "Update 2", "Another update",
                               severity="info", db_path=TEST_DB)
check("rate.msg3", r3.get("ok") is True, f"Message 3: {r3}")

# 4th should be rejected
r4 = bus.send_to_team_mailbox(worker["id"], "Update 3", "This should be rejected",
                               severity="info", db_path=TEST_DB)
check("rate.msg4_rejected", r4.get("ok") is not True,
      f"4th message result: {r4}")
check("rate.error_msg", "rate" in r4.get("error", "").lower() or "limit" in r4.get("error", "").lower(),
      f"Error: {r4.get('error')}")

# ---------------------------------------------------------------------------
# Test 4: Code Red creates audit entry
# ---------------------------------------------------------------------------

section("Test 4: Code Red audit entry")

# Use a different agent (manager) for code_red to avoid rate limit on worker
code_red_result = bus.send_to_team_mailbox(manager["id"], "CRITICAL FAILURE",
                                            "Production database is corrupted",
                                            severity="code_red", db_path=TEST_DB)
check("code_red.ok", code_red_result.get("ok") is True, f"Result: {code_red_result}")

conn = bus.get_conn(TEST_DB)
audit_rows = conn.execute("""
    SELECT * FROM audit_log WHERE event_type='team_mailbox_message'
    ORDER BY timestamp DESC LIMIT 10
""").fetchall()
conn.close()
check("code_red.audit_exists", len(audit_rows) > 0,
      f"Found {len(audit_rows)} audit entries")

# ---------------------------------------------------------------------------
# Test 5: Audit logs existence but not content
# ---------------------------------------------------------------------------

section("Test 5: Audit without content")

if audit_rows:
    details = audit_rows[0]["details"]
    check("audit.no_body", "corrupted" not in details.lower(),
          f"Details should not contain message body: {details[:120]}")
    check("audit.has_severity", "severity" in details.lower(),
          f"Has severity info: {'severity' in details.lower()}")
    check("audit.has_team_id", "team_id" in details,
          f"Has team_id: {'team_id' in details}")
else:
    check("audit.skip", False, "No audit entries found")

# ---------------------------------------------------------------------------
# Test 6: Manager can also send to mailbox
# ---------------------------------------------------------------------------

section("Test 6: Manager sends to mailbox")

mgr_msg = bus.send_to_team_mailbox(manager["id"], "Manager update",
                                    "Team performance review notes",
                                    severity="info", db_path=TEST_DB)
# Manager already sent code_red, so this is #2 for manager
check("mgr_send.ok", mgr_msg.get("ok") is True, f"Result: {mgr_msg}")

# ---------------------------------------------------------------------------
# Test 7: Agent NOT in a team cannot send to mailbox
# ---------------------------------------------------------------------------

section("Test 7: Non-team agent rejected")

# Core agent like wellness should be rejected
bad_result = bus.send_to_team_mailbox(wellness["id"], "I'm not in a team",
                                       "This shouldn't work",
                                       severity="info", db_path=TEST_DB)
check("nonteam.rejected", bad_result.get("ok") is not True,
      f"Result: {bad_result}")

# Human should also be rejected
bad_result2 = bus.send_to_team_mailbox(human["id"], "Humans can't send",
                                        "Not allowed",
                                        severity="info", db_path=TEST_DB)
check("nonteam.human_rejected", bad_result2.get("ok") is not True,
      f"Result: {bad_result2}")

# ---------------------------------------------------------------------------
# Test 8: get_team_mailbox_summary returns correct counts
# ---------------------------------------------------------------------------

section("Test 8: Mailbox summary counts")

summary = bus.get_team_mailbox_summary(team_id, db_path=TEST_DB)
check("summary.unread", summary["unread_count"] >= 4,
      f"Unread count: {summary['unread_count']}")
check("summary.code_red", summary["code_red_count"] >= 1,
      f"Code red count: {summary['code_red_count']}")
check("summary.warning", summary["warning_count"] >= 1,
      f"Warning count: {summary['warning_count']}")
check("summary.latest", summary["latest_severity"] == "code_red",
      f"Latest severity: {summary['latest_severity']}")

# ---------------------------------------------------------------------------
# Test 9: Mark as read works
# ---------------------------------------------------------------------------

section("Test 9: Mark as read")

mark_result = bus.mark_mailbox_read(msg1_id, db_path=TEST_DB)
check("mark_read.ok", mark_result.get("ok") is True, f"Result: {mark_result}")

conn = bus.get_conn(TEST_DB)
read_msg = conn.execute("SELECT * FROM team_mailbox WHERE id=?", (msg1_id,)).fetchone()
conn.close()
check("mark_read.flag", read_msg["read"] == 1, f"read: {read_msg['read']}")
check("mark_read.at", read_msg["read_at"] is not None,
      f"read_at: {read_msg['read_at']}")

# ---------------------------------------------------------------------------
# Test 10: Unread filter works
# ---------------------------------------------------------------------------

section("Test 10: Unread filter")

all_msgs = bus.get_team_mailbox(team_id, unread_only=False, db_path=TEST_DB)
unread_msgs = bus.get_team_mailbox(team_id, unread_only=True, db_path=TEST_DB)
check("unread_filter.less", len(unread_msgs) < len(all_msgs),
      f"Unread: {len(unread_msgs)}, All: {len(all_msgs)}")
# Verify msg1 (now read) is NOT in unread list
unread_ids = [m["id"] for m in unread_msgs]
check("unread_filter.excluded", msg1_id not in unread_ids,
      f"Read message {msg1_id} should not appear in unread")

# ---------------------------------------------------------------------------
# Test 11: Multiple severities in summary after mark read
# ---------------------------------------------------------------------------

section("Test 11: Summary after mark read")

summary2 = bus.get_team_mailbox_summary(team_id, db_path=TEST_DB)
# After marking one warning as read, unread_count should decrease
check("summary2.unread_decreased", summary2["unread_count"] < summary["unread_count"],
      f"Before: {summary['unread_count']}, After: {summary2['unread_count']}")
# Warning count should decrease since we read the warning
check("summary2.warning_decreased", summary2["warning_count"] < summary["warning_count"],
      f"Before: {summary['warning_count']}, After: {summary2['warning_count']}")

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
