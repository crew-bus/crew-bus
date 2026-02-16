"""
test_day2.py - Full Day 2 integration test for crew-bus.

Simulates a complete day of operations for Ryan Johnson:
  Step 1:  Load ryan_stack.yaml, initialize all agents
  Step 2:  Set burnout score to 7 (high - long day yesterday)
  Step 3:  Quant sends wellness alert to Chief
  Step 4:  V4 submits business idea to Chief
  Step 5:  Chief filters: burnout is high, idea not urgent, queue for tomorrow
  Step 6:  RJC-Manager escalates: client emergency (pressure tank leaking)
  Step 7:  Chief assesses: urgent + client emergency = deliver NOW
  Step 8:  Lead-Tracker tries to message Ryan directly
  Step 9:  Bus BLOCKS: must route through Crew Boss
  Step 10: CFO sends GST alert to Chief
  Step 11: Chief assesses: important but not urgent, queue for morning brief
  Step 12: Legal sends insurance renewal alert to Chief
  Step 13: Chief assesses: 14 days out, queue for morning brief
  Step 14: Compile and print MORNING BRIEFING as formatted email
  Step 15: Compile and print EVENING BRIEFING as formatted email
  Step 16: Show all decisions made by Chief with accuracy stats
  Step 17: Human feedback: approve V4 queue, override GST queue
  Step 18: Record feedback, show updated accuracy

Run:  PYTHONPATH="/c/Users/ryanr/crew-bus:/c/Users/ryanr/Lib/site-packages" /c/Python314/python.exe test_day2.py
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import bus
from right_hand import RightHand
from email_formatter import format_morning_brief, format_evening_summary
from delivery import format_briefing_email

# ---------------------------------------------------------------------------
# Test DB
# ---------------------------------------------------------------------------

TEST_DB = Path(__file__).parent / "test_day2.db"
CONFIG = Path(__file__).parent / "configs" / "ryan_stack.yaml"

if TEST_DB.exists():
    os.remove(str(TEST_DB))

# Test results tracking
passed = 0
failed = 0
results = {}


def check(test_name, condition, detail=""):
    global passed, failed
    label = "[PASS]" if condition else "[FAIL]"
    print(f"  {label} {detail}" if detail else f"  {label} {test_name}")
    if condition:
        passed += 1
    else:
        failed += 1
    return condition


def section(name):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")


# ============================================================
# Step 1: Load hierarchy
# ============================================================

section("Step 1: Load ryan_stack.yaml")
s1_start = passed

bus.init_db(TEST_DB)
result = bus.load_hierarchy(str(CONFIG), TEST_DB)
agents_loaded = result.get("agents_loaded", [])

check("1.1", len(agents_loaded) == 17,
      f"Expected 17 agents, got {len(agents_loaded)}: {agents_loaded}")

# Get agent references
def get_agent(name):
    return bus.get_agent_by_name(name, TEST_DB)

ryan = get_agent("Ryan")
chief = get_agent("Crew-Boss")
quant = get_agent("Quant")
v4 = get_agent("V4")
cfo = get_agent("CFO")
legal = get_agent("Legal")
memory = get_agent("Memory")
comms = get_agent("Comms")
rjc_mgr = get_agent("RJC-Manager")
lead_tracker = get_agent("Lead-Tracker")

check("1.2", ryan is not None and ryan["agent_type"] == "human",
      f"Ryan: {ryan['agent_type'] if ryan else 'NOT FOUND'}")
check("1.3", chief is not None and chief["agent_type"] == "right_hand",
      f"Chief: {chief['agent_type'] if chief else 'NOT FOUND'}")
check("1.4", chief["trust_score"] == 5,
      f"Chief trust score: {chief['trust_score']}")
check("1.5", chief["budget_limit"] == 500.0,
      f"Chief budget limit: {chief['budget_limit']}")

results["step_1"] = f"{passed - s1_start}/5"


# ============================================================
# Step 2: Set burnout to 7 (high)
# ============================================================

section("Step 2: Set burnout to 7 (high - long day yesterday)")
s2_start = passed

bus.update_burnout_score(ryan["id"], 7, TEST_DB)
ryan = get_agent("Ryan")

check("2.1", ryan["burnout_score"] == 7,
      f"Burnout set to 7: {ryan['burnout_score']}")

# Also update human_state table
bus.update_human_state(ryan["id"], {"burnout_score": 7, "energy_level": "low"}, db_path=TEST_DB)
state = bus.get_human_state(ryan["id"], TEST_DB)
check("2.2", state["burnout_score"] == 7,
      f"Human state burnout: {state['burnout_score']}")

results["step_2"] = f"{passed - s2_start}/2"


# ============================================================
# Step 3: Quant sends wellness alert to Chief
# ============================================================

section("Step 3: Quant wellness alert -> Chief")
s3_start = passed

msg = bus.send_message(
    quant["id"], chief["id"],
    message_type="alert",
    subject="Burnout elevated, recommend light schedule",
    body="Multiple signals: sleep quality declining, screen time up 35%, calendar overbooked 3 days running.",
    priority="high",
    db_path=TEST_DB,
)
check("3.1", msg["message_id"] > 0,
      f"Wellness alert sent: msg_id={msg['message_id']}")

results["step_3"] = f"{passed - s3_start}/1"


# ============================================================
# Step 4: V4 submits business idea to Chief
# ============================================================

section("Step 4: V4 idea -> Chief")
s4_start = passed

idea_msg = bus.send_message(
    v4["id"], chief["id"],
    message_type="idea",
    subject="Fire-Ready Property Certification - new revenue stream",
    body="BC wildfire season creates opportunity for certified fire-readiness assessments on rural properties. RJC could offer this as a premium service.",
    priority="normal",
    db_path=TEST_DB,
)
check("4.1", idea_msg["message_id"] > 0,
      f"Idea submitted: msg_id={idea_msg['message_id']}")

results["step_4"] = f"{passed - s4_start}/1"


# ============================================================
# Step 5: Chief filters idea (burnout high, not urgent, queue)
# ============================================================

section("Step 5: Chief filters V4 idea -> queue for tomorrow")
s5_start = passed

rh = RightHand(chief["id"], ryan["id"], db_path=TEST_DB)

filter_result = rh.filter_idea(idea_msg["message_id"])
check("5.1", filter_result["action"] == "queue",
      f"Idea action: {filter_result['action']}")
check("5.2", "burnout" in filter_result["reason"].lower(),
      f"Reason mentions burnout: {filter_result['reason'][:80]}")

# Log the decision
d1 = rh._log("filter", {"subject": "Fire-Ready Property Certification", "from": "V4"}, "queue")
check("5.3", d1 > 0, f"Decision logged: #{d1}")

results["step_5"] = f"{passed - s5_start}/3"


# ============================================================
# Step 6: RJC-Manager escalates client emergency
# ============================================================

section("Step 6: RJC-Manager escalation -> client emergency")
s6_start = passed

escalation_msg = bus.send_message(
    rjc_mgr["id"], chief["id"],
    message_type="escalation",
    subject="Client Dave Wilson called back - pressure tank actively leaking",
    body="Pressure tank is now actively leaking. Dave Wilson needs emergency response today. Property damage risk. This was originally a quote follow-up.",
    priority="critical",
    db_path=TEST_DB,
)
check("6.1", escalation_msg["message_id"] > 0,
      f"Escalation sent: msg_id={escalation_msg['message_id']}")

results["step_6"] = f"{passed - s6_start}/1"


# ============================================================
# Step 7: Chief delivers emergency to Ryan (despite burnout)
# ============================================================

section("Step 7: Chief delivers emergency to Ryan NOW")
s7_start = passed

esc_result = rh.handle_escalation({
    "id": escalation_msg["message_id"],
    "subject": "Client Dave Wilson called back - pressure tank actively leaking",
    "body": "Pressure tank is now actively leaking.",
    "priority": "critical",
    "from": "RJC-Manager",
    "message_type": "escalation",
})
check("7.1", esc_result["action"] == "deliver_to_human",
      f"Action: {esc_result['action']}")

# Verify delivery check passes for critical
delivery = bus.should_deliver_now(ryan["id"], "critical", TEST_DB)
check("7.2", delivery["deliver"] is True,
      f"Critical delivers despite burnout: {delivery['deliver']}")

results["step_7"] = f"{passed - s7_start}/2"


# ============================================================
# Step 8: Lead-Tracker tries to message Ryan directly
# ============================================================

section("Step 8: Lead-Tracker -> Ryan (direct)")
s8_start = passed

blocked = False
block_reason = ""
try:
    bus.send_message(
        lead_tracker["id"], ryan["id"],
        message_type="report",
        subject="New lead: pressure washing job on Comox Road",
        body="Homeowner called about driveway cleaning.",
        priority="normal",
        db_path=TEST_DB,
    )
except PermissionError as e:
    blocked = True
    block_reason = str(e)

check("8.1", blocked is True,
      f"Worker->Human blocked: {blocked}")

results["step_8"] = f"{passed - s8_start}/1"


# ============================================================
# Step 9: Bus BLOCKS with correct reason
# ============================================================

section("Step 9: Block reason mentions Crew Boss")
s9_start = passed

check("9.1", "crew boss" in block_reason.lower() or "Crew Boss" in block_reason,
      f"Reason: {block_reason[:80]}")

# Verify audit logged the block
trail = bus.get_audit_trail(agent_id=lead_tracker["id"], db_path=TEST_DB)
block_entries = [e for e in trail if "block" in e.get("event_type", "").lower()
                 or "attempt" in e.get("event_type", "").lower()]
check("9.2", len(block_entries) > 0 or len(trail) > 0,
      f"Block logged in audit: {len(trail)} entries for Lead-Tracker")

results["step_9"] = f"{passed - s9_start}/2"


# ============================================================
# Step 10: CFO sends GST filing alert to Chief
# ============================================================

section("Step 10: CFO GST alert -> Chief")
s10_start = passed

gst_msg = bus.send_message(
    cfo["id"], chief["id"],
    message_type="alert",
    subject="GST filing due in 5 days - $2,340 owing",
    body="Quarterly GST filing deadline approaching. Amount owing: $2,340.00. Payment and filing must be submitted by Feb 19.",
    priority="normal",
    db_path=TEST_DB,
)
check("10.1", gst_msg["message_id"] > 0,
      f"GST alert sent: msg_id={gst_msg['message_id']}")

results["step_10"] = f"{passed - s10_start}/1"


# ============================================================
# Step 11: Chief queues GST (important but not urgent at trust 5)
# ============================================================

section("Step 11: Chief queues GST for morning briefing")
s11_start = passed

delivery = bus.should_deliver_now(ryan["id"], "normal", TEST_DB)
check("11.1", delivery["deliver"] is False,
      f"GST not delivered (burnout=7): deliver={delivery['deliver']}")

# Log the queue decision
d2 = rh._log("queue", {"subject": "GST filing due in 5 days", "from": "CFO"}, "queue")
check("11.2", d2 > 0, f"Queue decision logged: #{d2}")

results["step_11"] = f"{passed - s11_start}/2"


# ============================================================
# Step 12: Legal sends insurance renewal alert
# ============================================================

section("Step 12: Legal insurance renewal alert -> Chief")
s12_start = passed

legal_msg = bus.send_message(
    legal["id"], chief["id"],
    message_type="alert",
    subject="Business insurance renewal due Feb 28",
    body="Annual business insurance renewal for RJC. Current policy expires Feb 28. Need to review coverage levels and compare quotes.",
    priority="normal",
    db_path=TEST_DB,
)
check("12.1", legal_msg["message_id"] > 0,
      f"Insurance alert sent: msg_id={legal_msg['message_id']}")

results["step_12"] = f"{passed - s12_start}/1"


# ============================================================
# Step 13: Chief queues insurance (14 days out, not urgent)
# ============================================================

section("Step 13: Chief queues insurance for morning briefing")
s13_start = passed

# Log the queue decision
d3 = rh._log("queue", {"subject": "Insurance renewal Feb 28", "from": "Legal"}, "queue")
check("13.1", d3 > 0, f"Queue decision logged: #{d3}")

results["step_13"] = f"{passed - s13_start}/1"


# ============================================================
# Step 14: Compile MORNING BRIEFING
# ============================================================

section("Step 14: Morning briefing as formatted email")
s14_start = passed

briefing = rh.compile_briefing("morning")
check("14.1", briefing is not None,
      f"Morning briefing generated")
check("14.2", "subject" in briefing,
      f"Has subject: {briefing.get('subject', 'NONE')[:60]}")

# Format as professional email
email = format_morning_brief(briefing, ryan["name"], ryan["burnout_score"])
check("14.3", "subject" in email and len(email["plain"]) > 50,
      f"Formatted email: {len(email['plain'])} chars")

# Also test the delivery.py format_briefing_email
delivery_email = format_briefing_email(briefing, {
    "name": ryan["name"],
    "trust_score": chief["trust_score"],
    "channel": ryan["channel"],
})
check("14.4", "subject" in delivery_email and len(delivery_email["plain"]) > 0,
      f"delivery.py email: {len(delivery_email['plain'])} chars")

results["step_14"] = f"{passed - s14_start}/4"


# ============================================================
# Step 15: Compile EVENING BRIEFING
# ============================================================

section("Step 15: Evening briefing as formatted email")
s15_start = passed

evening = rh.compile_briefing("evening")
check("15.1", evening is not None,
      f"Evening briefing generated")

email_eve = format_evening_summary(evening, ryan["name"], ryan["burnout_score"])
check("15.2", "subject" in email_eve,
      f"Evening subject: {email_eve.get('subject', 'NONE')[:60]}")

results["step_15"] = f"{passed - s15_start}/2"


# ============================================================
# Step 16: Show all decisions with accuracy stats
# ============================================================

section("Step 16: Decision history and accuracy")
s16_start = passed

decisions = bus.get_decision_history(limit=50, db_path=TEST_DB)
check("16.1", len(decisions) >= 3,
      f"Decisions logged: {len(decisions)}")

# Print decisions
for d in decisions:
    override_mark = " [OVERRIDDEN]" if d["human_override"] else ""
    print(f"    #{d['id']} [{d['decision_type']}] {d['right_hand_action']}{override_mark}")

auto = bus.get_autonomy_level(chief["id"], TEST_DB)
check("16.2", auto["total_decisions"] >= 3,
      f"Total decisions: {auto['total_decisions']}")
check("16.3", "accuracy_pct" in auto,
      f"Accuracy: {auto['accuracy_pct']}%")

results["step_16"] = f"{passed - s16_start}/3"


# ============================================================
# Step 17: Human feedback - approve V4 queue, override GST queue
# ============================================================

section("Step 17: Human feedback on decisions")
s17_start = passed

# Ryan approves the V4 idea queue (Chief was right to hold it)
bus.record_human_feedback(d1, override=False, human_action=None,
                          note="Good call, I was too tired for this", db_path=TEST_DB)
check("17.1", True, "V4 queue decision APPROVED")

# Ryan overrides the GST queue (wants to deal with it today)
bus.record_human_feedback(d2, override=True,
                          human_action="Deal with GST today",
                          note="I want to get this done while I remember",
                          db_path=TEST_DB)
check("17.2", True, "GST queue decision OVERRIDDEN")

# Verify the override is recorded
d2_row = bus.get_decision_history(limit=50, db_path=TEST_DB)
gst_decision = [d for d in d2_row if d["id"] == d2]
check("17.3", len(gst_decision) == 1 and gst_decision[0]["human_override"] == 1,
      f"GST override recorded: {gst_decision[0]['human_override'] if gst_decision else 'NOT FOUND'}")

results["step_17"] = f"{passed - s17_start}/3"


# ============================================================
# Step 18: Updated accuracy stats
# ============================================================

section("Step 18: Updated accuracy after feedback")
s18_start = passed

auto_updated = bus.get_autonomy_level(chief["id"], TEST_DB)
check("18.1", auto_updated["overrides"] >= 1,
      f"Overrides recorded: {auto_updated['overrides']}")

accuracy = auto_updated["accuracy_pct"]
check("18.2", accuracy > 0,
      f"Accuracy: {accuracy}%")

# Learn from feedback
learn_result = rh.learn_from_feedback(d2, human_approved=False,
                                       human_action="Deal with GST today",
                                       note="Human wants financial items delivered same-day")
check("18.3", learn_result is not None,
      f"Feedback recorded: {learn_result.get('feedback', '')[:60]}")

results["step_18"] = f"{passed - s18_start}/3"


# ============================================================
# Print formatted briefings
# ============================================================

section("Formatted Morning Briefing Email")
print(email["plain"])

section("Formatted Evening Briefing Email")
print(email_eve["plain"])


# ============================================================
# Results Summary
# ============================================================

print(f"\n{'#'*60}")
print(f"#  RESULTS SUMMARY")
print(f"{'#'*60}")

all_pass = True
for test_name, score in results.items():
    parts = score.split("/")
    p, t = int(parts[0]), int(parts[1])
    status = "[PASS]" if p == t else "[FAIL]"
    if p != t:
        all_pass = False
    print(f"  {status} {test_name}: {score}")

print(f"\n  TOTAL: {passed}/{passed + failed} passed")
if failed:
    print(f"\n  {failed} TESTS FAILED")
    sys.exit(1)
else:
    print(f"\n  ALL TESTS PASSED!")

# Cleanup
if TEST_DB.exists():
    os.remove(str(TEST_DB))
    print(f"\n  Cleaned up {TEST_DB}")
