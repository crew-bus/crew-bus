"""
test_day3.py - Day 3 integration tests for crew-bus.

Tests:
  1. Dashboard starts and serves the landing page
  2. All API endpoints return valid JSON
  3. CrewBridge can send a report and it appears in the message feed
  4. CrewBridge can check inbox and receive messages
  5. CrewBridge escalation bypasses hierarchy correctly
  6. Trust score update via dashboard API changes Crew Boss behavior
  7. Quarantine via dashboard API blocks agent messages
  8. Knowledge store and search work through CrewBridge
  9. Dashboard auto-refresh endpoint returns updated data after new messages

Run:
  python test_day3.py
"""

import json
import os
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import bus
from agent_bridge import CrewBridge
from dashboard import create_server

# ---------------------------------------------------------------------------
# Test DB and setup
# ---------------------------------------------------------------------------

TEST_DB = Path(__file__).parent / "test_day3.db"
CONFIG = Path(__file__).parent / "configs" / "ryan_stack.yaml"
PORT = 18932  # Use a random high port for testing

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
      f"Loaded {len(agents_loaded)} agents: {agents_loaded}")

# Get key agent references
ryan = bus.get_agent_by_name("Ryan", TEST_DB)
chief = bus.get_agent_by_name("Crew-Boss", TEST_DB)
quant = bus.get_agent_by_name("Quant", TEST_DB)
v4 = bus.get_agent_by_name("V4", TEST_DB)
rjc_mgr = bus.get_agent_by_name("RJC-Manager", TEST_DB)
lead_tracker = bus.get_agent_by_name("Lead-Tracker", TEST_DB)

check("setup.agents", all([ryan, chief, quant, v4, rjc_mgr, lead_tracker]),
      "All key agents exist")


# ---------------------------------------------------------------------------
# Test 1: Dashboard starts and serves the landing page
# ---------------------------------------------------------------------------

section("Test 1: Dashboard starts and serves landing page")

server = create_server(port=PORT, db_path=TEST_DB, host="127.0.0.1")
server_thread = threading.Thread(target=server.serve_forever, daemon=True)
server_thread.start()
time.sleep(0.5)  # Give server time to start

BASE = f"http://127.0.0.1:{PORT}"

try:
    resp = urllib.request.urlopen(f"{BASE}/")
    html = resp.read().decode("utf-8")
    check("1.1", resp.status == 200, "Landing page returns 200")
    check("1.2", "crew-bus" in html, "Landing page contains 'crew-bus'")
    check("1.3", "data-page=\"crew\"" in html, "Landing page has data-page=crew")
    check("1.4", "trust-slider" in html, "Landing page has trust slider")
    check("1.5", "burnout-slider" in html, "Landing page has burnout slider")
except Exception as e:
    check("1.1", False, f"Landing page request failed: {e}")

# Test other pages load
for page_path, page_key in [("/messages", "messages"), ("/decisions", "decisions"), ("/audit", "audit")]:
    try:
        resp = urllib.request.urlopen(f"{BASE}{page_path}")
        html = resp.read().decode("utf-8")
        check(f"1.page.{page_key}", resp.status == 200 and f'data-page="{page_key}"' in html,
              f"Page {page_path} loads correctly")
    except Exception as e:
        check(f"1.page.{page_key}", False, f"Page {page_path} failed: {e}")


# ---------------------------------------------------------------------------
# Test 2: All API endpoints return valid JSON
# ---------------------------------------------------------------------------

section("Test 2: API endpoints return valid JSON")

api_endpoints = [
    ("/api/stats", "stats"),
    ("/api/agents", "agents"),
    ("/api/messages?limit=10", "messages"),
    ("/api/decisions?limit=10", "decisions"),
    ("/api/audit?limit=10", "audit"),
    ("/api/health", "health"),
]

for path, name in api_endpoints:
    try:
        resp = urllib.request.urlopen(f"{BASE}{path}")
        data = json.loads(resp.read().decode("utf-8"))
        check(f"2.{name}", resp.status == 200,
              f"GET {path} -> 200, data type: {type(data).__name__}")
    except Exception as e:
        check(f"2.{name}", False, f"GET {path} failed: {e}")

# Test /api/stats content
try:
    resp = urllib.request.urlopen(f"{BASE}/api/stats")
    stats = json.loads(resp.read().decode("utf-8"))
    check("2.stats.fields", "crew_name" in stats and "trust_score" in stats and "burnout_score" in stats,
          f"Stats has required fields: crew={stats.get('crew_name')}, trust={stats.get('trust_score')}, burnout={stats.get('burnout_score')}")
except Exception as e:
    check("2.stats.fields", False, f"Stats check failed: {e}")

# Test /api/agents content
try:
    resp = urllib.request.urlopen(f"{BASE}/api/agents")
    agents = json.loads(resp.read().decode("utf-8"))
    check("2.agents.count", len(agents) >= 10,
          f"Agents endpoint returned {len(agents)} agents")
    first = agents[0]
    check("2.agents.fields", "unread_count" in first and "last_message_time" in first and "parent_name" in first,
          "Agent entries have unread_count, last_message_time, parent_name")
except Exception as e:
    check("2.agents.fields", False, f"Agents check failed: {e}")


# ---------------------------------------------------------------------------
# Test 3: CrewBridge can send a report and it appears in message feed
# ---------------------------------------------------------------------------

section("Test 3: CrewBridge report -> message feed")

bridge_lt = CrewBridge("Lead-Tracker", db_path=TEST_DB)
check("3.1", bridge_lt.agent_id == lead_tracker["id"],
      f"Bridge resolved Lead-Tracker id={bridge_lt.agent_id}")

result = bridge_lt.report(
    subject="New Lead Logged",
    body="Dave Wilson, 250-334-5678, pressure tank replacement, Black Creek"
)
check("3.2", result.get("ok") is True,
      f"Report sent: message_id={result.get('message_id')}")

# Check it appears in dashboard message feed
try:
    resp = urllib.request.urlopen(f"{BASE}/api/messages?limit=10")
    msgs = json.loads(resp.read().decode("utf-8"))
    found = any(m.get("subject") == "New Lead Logged" for m in msgs)
    check("3.3", found, "Report appears in /api/messages")
except Exception as e:
    check("3.3", False, f"Message feed check failed: {e}")


# ---------------------------------------------------------------------------
# Test 4: CrewBridge can check inbox and receive messages
# ---------------------------------------------------------------------------

section("Test 4: CrewBridge inbox")

# Chief sends task to Lead-Tracker via bus
task_result = bus.send_message(
    from_id=chief["id"],
    to_id=lead_tracker["id"],
    message_type="task",
    subject="Follow up with Dave Wilson",
    body="Call Dave Wilson tomorrow to schedule pressure tank install.",
    priority="normal",
    db_path=TEST_DB,
)
check("4.1", task_result.get("message_id") is not None,
      f"Task sent to Lead-Tracker: id={task_result.get('message_id')}")

inbox = bridge_lt.check_inbox(unread_only=True)
check("4.2", len(inbox) > 0, f"Lead-Tracker inbox has {len(inbox)} messages")

task_msg = [m for m in inbox if m["type"] == "task"]
check("4.3", len(task_msg) > 0, f"Found {len(task_msg)} task(s) in inbox")

if task_msg:
    check("4.4", task_msg[0]["subject"] == "Follow up with Dave Wilson",
          f"Task subject matches: {task_msg[0]['subject']}")

# get_tasks convenience method
tasks = bridge_lt.get_tasks()
check("4.5", len(tasks) > 0, f"get_tasks() returned {len(tasks)} task(s)")

# mark_done
if task_msg:
    done_result = bridge_lt.mark_done(task_msg[0]["id"])
    check("4.6", done_result.get("ok") is True,
          f"mark_done returned ok=True")

    # Verify it's no longer unread
    inbox_after = bridge_lt.check_inbox(unread_only=True)
    still_there = any(m["id"] == task_msg[0]["id"] for m in inbox_after)
    check("4.7", not still_there,
          "Task no longer appears in unread inbox after mark_done")


# ---------------------------------------------------------------------------
# Test 5: CrewBridge escalation bypasses hierarchy
# ---------------------------------------------------------------------------

section("Test 5: Escalation bypasses hierarchy")

# Lead-Tracker is a worker under RJC-Manager.
# Escalation should go directly to Crew Boss (Chief), not RJC-Manager.
esc_result = bridge_lt.escalate(
    subject="Suspicious Client Activity",
    body="Dave Wilson flagged in fraud database. Halt engagement."
)
check("5.1", esc_result.get("ok") is True,
      f"Escalation sent: message_id={esc_result.get('message_id')}")

# Verify it landed in Chief's inbox, not RJC-Manager's
chief_inbox = bus.read_inbox(chief["id"], db_path=TEST_DB)
esc_msgs = [m for m in chief_inbox if m["message_type"] == "escalation"
            and "Suspicious Client Activity" in m["subject"]]
check("5.2", len(esc_msgs) > 0,
      f"Escalation found in Chief's inbox ({len(esc_msgs)} match)")

mgr_inbox = bus.read_inbox(rjc_mgr["id"], db_path=TEST_DB)
esc_in_mgr = [m for m in mgr_inbox if m["message_type"] == "escalation"
              and "Suspicious Client Activity" in m.get("subject", "")]
check("5.3", len(esc_in_mgr) == 0,
      "Escalation NOT in RJC-Manager inbox (bypassed correctly)")


# ---------------------------------------------------------------------------
# Test 6: Trust score update via dashboard API
# ---------------------------------------------------------------------------

section("Test 6: Trust score update via dashboard API")

# Get current trust
try:
    resp = urllib.request.urlopen(f"{BASE}/api/stats")
    before = json.loads(resp.read().decode("utf-8"))
    old_trust = before.get("trust_score")
    check("6.1", old_trust is not None, f"Current trust score: {old_trust}")
except Exception as e:
    check("6.1", False, f"Stats failed: {e}")
    old_trust = 5

# Update trust via POST
new_trust = 8
try:
    req = urllib.request.Request(
        f"{BASE}/api/trust",
        data=json.dumps({"score": new_trust}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read().decode("utf-8"))
    check("6.2", result.get("ok") is True, f"Trust update returned ok=True")
except Exception as e:
    check("6.2", False, f"Trust update failed: {e}")

# Verify trust changed
try:
    resp = urllib.request.urlopen(f"{BASE}/api/stats")
    after = json.loads(resp.read().decode("utf-8"))
    check("6.3", after.get("trust_score") == new_trust,
          f"Trust score updated: {old_trust} -> {after.get('trust_score')}")
except Exception as e:
    check("6.3", False, f"Trust verify failed: {e}")

# Verify trust affects Crew Boss behavior
autonomy = bus.get_autonomy_level(chief["id"], db_path=TEST_DB)
check("6.4", autonomy["trust_score"] == new_trust,
      f"get_autonomy_level reflects new trust: {autonomy['trust_score']}, level={autonomy['level']}")
check("6.5", autonomy["level"] == "operator",
      f"Trust 8 -> operator level (got '{autonomy['level']}')")


# ---------------------------------------------------------------------------
# Test 7: Quarantine via dashboard API blocks agent messages
# ---------------------------------------------------------------------------

section("Test 7: Quarantine blocks messages")

# Quarantine Lead-Tracker via dashboard API
try:
    req = urllib.request.Request(
        f"{BASE}/api/quarantine/{lead_tracker['id']}",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read().decode("utf-8"))
    check("7.1", result.get("ok") is True and result.get("status") == "quarantined",
          "Lead-Tracker quarantined via dashboard")
except Exception as e:
    check("7.1", False, f"Quarantine failed: {e}")

# Verify Lead-Tracker agent status
lt_agent = bus.get_agent_by_name("Lead-Tracker", TEST_DB)
check("7.2", lt_agent["status"] == "quarantined",
      f"Lead-Tracker status: {lt_agent['status']}")

# Try to send message FROM quarantined agent - should be blocked
bridge_lt_q = CrewBridge("Lead-Tracker", db_path=TEST_DB)
blocked = bridge_lt_q.report(
    subject="Should Be Blocked",
    body="This should not go through"
)
check("7.3", blocked.get("ok") is False or blocked.get("blocked") is True,
      f"Quarantined agent message blocked: {blocked.get('error', 'no error')[:60]}")

# Restore via dashboard API
try:
    req = urllib.request.Request(
        f"{BASE}/api/restore/{lead_tracker['id']}",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read().decode("utf-8"))
    check("7.4", result.get("ok") is True and result.get("status") == "active",
          "Lead-Tracker restored via dashboard")
except Exception as e:
    check("7.4", False, f"Restore failed: {e}")

# Verify restored agent can send
bridge_lt_r = CrewBridge("Lead-Tracker", db_path=TEST_DB)
restored_msg = bridge_lt_r.report(
    subject="Back Online",
    body="Lead-Tracker restored and operational"
)
check("7.5", restored_msg.get("ok") is True,
      f"Restored agent can send: message_id={restored_msg.get('message_id')}")


# ---------------------------------------------------------------------------
# Test 8: Knowledge store and search via CrewBridge
# ---------------------------------------------------------------------------

section("Test 8: Knowledge store and search")

bridge_mem = CrewBridge("Memory", db_path=TEST_DB)

k_result = bridge_mem.post_knowledge(
    category="contact",
    subject="Dave Wilson",
    content="Needs pressure tank replacement, Black Creek, 250-334-5678",
    tags=["lead", "plumbing", "black-creek"],
)
check("8.1", k_result.get("ok") is True,
      f"Knowledge stored: id={k_result.get('knowledge_id')}")

k_result2 = bridge_mem.post_knowledge(
    category="lesson",
    subject="Pressure Tank Pricing",
    content="Standard pressure tank install runs $1200-1800 parts + labor",
    tags=["plumbing", "pricing"],
)
check("8.2", k_result2.get("ok") is True,
      f"Second knowledge entry stored: id={k_result2.get('knowledge_id')}")

# Search
search_results = bridge_mem.search_knowledge("Dave Wilson")
check("8.3", len(search_results) > 0,
      f"Search 'Dave Wilson' returned {len(search_results)} result(s)")

search_results2 = bridge_mem.search_knowledge("pressure tank")
check("8.4", len(search_results2) >= 2,
      f"Search 'pressure tank' returned {len(search_results2)} results (expected >= 2)")

# Search with category filter
search_cat = bridge_mem.search_knowledge("pressure", category="lesson")
check("8.5", len(search_cat) > 0 and all(r["category"] == "lesson" for r in search_cat),
      f"Category-filtered search works: {len(search_cat)} lesson(s)")


# ---------------------------------------------------------------------------
# Test 9: Dashboard returns updated data after new messages
# ---------------------------------------------------------------------------

section("Test 9: Dashboard live data updates")

# Get message count before
try:
    resp = urllib.request.urlopen(f"{BASE}/api/stats")
    before_stats = json.loads(resp.read().decode("utf-8"))
    before_count = before_stats.get("message_count", 0)
except Exception as e:
    before_count = 0

# Send a new message via bridge
bridge_v4 = CrewBridge("V4", db_path=TEST_DB)
v4_result = bridge_v4.submit_idea(
    subject="YouTube Shorts for Lead Gen",
    body="Quick 30-second videos showing before/after of rural property jobs"
)
check("9.1", v4_result.get("ok") is True,
      f"V4 submitted idea: message_id={v4_result.get('message_id')}")

# Get message count after
try:
    resp = urllib.request.urlopen(f"{BASE}/api/stats")
    after_stats = json.loads(resp.read().decode("utf-8"))
    after_count = after_stats.get("message_count", 0)
    check("9.2", after_count > before_count,
          f"Message count increased: {before_count} -> {after_count}")
except Exception as e:
    check("9.2", False, f"Stats after failed: {e}")

# Verify the new message appears in feed
try:
    resp = urllib.request.urlopen(f"{BASE}/api/messages?limit=5")
    recent = json.loads(resp.read().decode("utf-8"))
    found = any("YouTube" in m.get("subject", "") for m in recent)
    check("9.3", found, "New idea appears in /api/messages")
except Exception as e:
    check("9.3", False, f"Messages check failed: {e}")

# Test message type filter
try:
    resp = urllib.request.urlopen(f"{BASE}/api/messages?type=report&limit=50")
    reports = json.loads(resp.read().decode("utf-8"))
    all_reports = all(m.get("message_type") == "report" for m in reports)
    check("9.4", all_reports and len(reports) > 0,
          f"Type filter works: {len(reports)} reports, all type=report: {all_reports}")
except Exception as e:
    check("9.4", False, f"Type filter check failed: {e}")

# Test burnout update via API
try:
    req = urllib.request.Request(
        f"{BASE}/api/burnout",
        data=json.dumps({"score": 3}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read().decode("utf-8"))
    check("9.5", result.get("ok") is True,
          "Burnout score updated via API")
except Exception as e:
    check("9.5", False, f"Burnout update failed: {e}")

# Verify burnout in stats
try:
    resp = urllib.request.urlopen(f"{BASE}/api/stats")
    stats = json.loads(resp.read().decode("utf-8"))
    check("9.6", stats.get("burnout_score") == 3,
          f"Burnout score reflected in stats: {stats.get('burnout_score')}")
except Exception as e:
    check("9.6", False, f"Burnout verify failed: {e}")


# ---------------------------------------------------------------------------
# Bonus: Test decision approve/override via API
# ---------------------------------------------------------------------------

section("Bonus: Decision approve/override via dashboard")

# Create a decision to test with
decision_id = bus.log_decision(
    right_hand_id=chief["id"],
    human_id=ryan["id"],
    decision_type="queue",
    context={"subject": "YouTube Shorts idea", "message_type": "idea"},
    action="Queued for morning brief - burnout is elevated",
    reasoning="Burnout was 7/10, idea not urgent, queue for tomorrow",
    db_path=TEST_DB,
)
check("bonus.1", decision_id > 0, f"Decision logged: id={decision_id}")

# Approve via dashboard
try:
    req = urllib.request.Request(
        f"{BASE}/api/decision/{decision_id}/approve",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read().decode("utf-8"))
    check("bonus.2", result.get("ok") is True,
          f"Decision {decision_id} approved via dashboard")
except Exception as e:
    check("bonus.2", False, f"Approve failed: {e}")

# Create another decision and override it
decision_id2 = bus.log_decision(
    right_hand_id=chief["id"],
    human_id=ryan["id"],
    decision_type="filter",
    context={"subject": "GST reminder", "message_type": "alert"},
    action="Filtered - not urgent at current burnout",
    db_path=TEST_DB,
)

try:
    req = urllib.request.Request(
        f"{BASE}/api/decision/{decision_id2}/override",
        data=json.dumps({"note": "GST is actually urgent, deliver now"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read().decode("utf-8"))
    check("bonus.3", result.get("ok") is True,
          f"Decision {decision_id2} overridden via dashboard")
except Exception as e:
    check("bonus.3", False, f"Override failed: {e}")

# Verify decisions show in API
try:
    resp = urllib.request.urlopen(f"{BASE}/api/decisions?limit=10")
    decisions = json.loads(resp.read().decode("utf-8"))
    check("bonus.4", len(decisions) >= 2,
          f"Decisions API returned {len(decisions)} entries")

    overridden = [d for d in decisions if d.get("human_override") == 1]
    check("bonus.5", len(overridden) > 0,
          f"Found {len(overridden)} overridden decision(s)")
except Exception as e:
    check("bonus.4", False, f"Decisions API failed: {e}")


# ---------------------------------------------------------------------------
# Bonus: Wellness agent bridge
# ---------------------------------------------------------------------------

section("Bonus: Wellness agent bridge")

bridge_quant = CrewBridge("Quant", db_path=TEST_DB)
wellness_result = bridge_quant.update_wellness(
    burnout_score=7,
    notes="Long work week, multiple client emergencies"
)
check("wellness.1", wellness_result.get("ok") is True,
      f"Wellness update succeeded: burnout={wellness_result.get('burnout_score')}")

# Verify burnout changed
ryan_updated = bus.get_agent_by_name("Ryan", TEST_DB)
check("wellness.2", ryan_updated["burnout_score"] == 7,
      f"Ryan burnout updated to {ryan_updated['burnout_score']}")

# Non-wellness agent should fail
bridge_cfo = CrewBridge("CFO", db_path=TEST_DB)
bad_wellness = bridge_cfo.update_wellness(burnout_score=3)
check("wellness.3", bad_wellness.get("ok") is False,
      f"Non-wellness agent blocked: {bad_wellness.get('error', '')[:50]}")


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

section("Cleanup")

server.shutdown()
print("  Server shut down.")

if TEST_DB.exists():
    os.remove(str(TEST_DB))
    print(f"  Removed {TEST_DB}")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print(f"\n{'='*60}")
print(f"  DAY 3 RESULTS: {passed} passed, {failed} failed")
print(f"{'='*60}")

if failed > 0:
    sys.exit(1)
else:
    print("\n  All tests passed. Day 3 is complete.")
    sys.exit(0)
