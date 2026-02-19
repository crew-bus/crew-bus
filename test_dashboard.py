"""
test_dashboard.py - Seed crew_bus.db with rich demo data and verify the dashboard.

Populates the database with:
  - Full agent hierarchy from ryan_stack.yaml
  - 25+ messages across agents spanning 3 days
  - 10+ Crew Boss decisions (mix of approved and overridden)
  - Trust score and burnout score variations
  - At least one quarantined agent
  - Timing rules (quiet hours)
  - Knowledge store entries
  - Audit log entries

Run:  python test_dashboard.py
Then: python dashboard.py

Dashboard will be at http://localhost:8420
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure our project root is on the path
sys.path.insert(0, str(Path(__file__).parent))

import bus
from right_hand import RightHand

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_FILE = Path(__file__).parent / "crew_bus.db"
_configs = Path(__file__).parent / "configs"
CONFIG_FILE = _configs / "ryan_stack.yaml" if (_configs / "ryan_stack.yaml").exists() else _configs / "example_stack.yaml"

# Wipe old DB so we get a clean seed every time
if DB_FILE.exists():
    os.remove(str(DB_FILE))
    print("[seed] Removed old crew_bus.db")


# ---------------------------------------------------------------------------
# Step 1: Load the hierarchy from YAML
# ---------------------------------------------------------------------------

print("[seed] Initializing database ...")
bus.init_db(DB_FILE)

print(f"[seed] Loading hierarchy from {CONFIG_FILE.name} ...")
result = bus.load_hierarchy(str(CONFIG_FILE), DB_FILE)
print(f"  Loaded {result.get('agents_loaded', '?')} agents (org: {result.get('org', '?')})")

# Get agent IDs by name for easy reference
conn = bus.get_conn(DB_FILE)
agents = {}
for row in conn.execute("SELECT id, name, agent_type FROM agents").fetchall():
    agents[row["name"]] = {"id": row["id"], "type": row["agent_type"]}
conn.close()

print(f"  Agents: {', '.join(sorted(agents.keys()))}")

# Convenience IDs — prefer 'Ryan' (ryan_stack), fall back to 'Human' (example_stack)
RYAN = agents.get("Ryan", agents.get("Human", {})).get("id", 1)
CHIEF = agents["Crew-Boss"]["id"]


# ---------------------------------------------------------------------------
# Helper: Insert a message directly (bypassing routing for seeding)
# ---------------------------------------------------------------------------

def seed_message(from_id, to_id, msg_type, subject, body, priority,
                 status="delivered", days_ago=0, hours_ago=0):
    """Insert a message directly into the DB with a backdated timestamp."""
    ts = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=hours_ago)
    iso = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    delivered = iso if status in ("delivered", "read") else None
    read_ts = iso if status == "read" else None

    conn = bus.get_conn(DB_FILE)
    cur = conn.execute(
        """INSERT INTO messages
           (from_agent_id, to_agent_id, message_type, subject, body,
            priority, status, created_at, delivered_at, read_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (from_id, to_id, msg_type, subject, body, priority, status,
         iso, delivered, read_ts)
    )
    msg_id = cur.lastrowid
    conn.commit()
    conn.close()
    return msg_id


def seed_decision(rh_id, human_id, dtype, context, action, reasoning,
                  human_override=0, human_action=None, note=None,
                  days_ago=0, hours_ago=0):
    """Insert a Crew Boss decision directly.

    'reasoning' is folded into the context dict since the schema
    doesn't have a separate reasoning column.
    """
    ts = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=hours_ago)
    iso = ts.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Fold reasoning into context for display in dashboard
    ctx = dict(context)
    ctx["reasoning"] = reasoning

    conn = bus.get_conn(DB_FILE)
    cur = conn.execute(
        """INSERT INTO decision_log
           (right_hand_id, human_id, decision_type, context,
            right_hand_action, human_override, human_action,
            feedback_note, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (rh_id, human_id, dtype, json.dumps(ctx), action,
         1 if human_override else 0, human_action, note, iso)
    )
    did = cur.lastrowid
    conn.commit()
    conn.close()
    return did


def seed_knowledge(agent_id, category, subject, content, tags="",
                   source_msg_id=None, days_ago=0):
    """Insert a knowledge store entry."""
    ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
    iso = ts.strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = bus.get_conn(DB_FILE)
    conn.execute(
        """INSERT INTO knowledge_store
           (agent_id, category, subject, content, tags,
            source_message_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (agent_id, category, subject, json.dumps(content), tags,
         source_msg_id, iso, iso)
    )
    conn.commit()
    conn.close()


def seed_audit(event_type, agent_id, details, days_ago=0, hours_ago=0):
    """Insert an audit log entry."""
    ts = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=hours_ago)
    iso = ts.strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = bus.get_conn(DB_FILE)
    conn.execute(
        "INSERT INTO audit_log (event_type, agent_id, details, timestamp) VALUES (?, ?, ?, ?)",
        (event_type, agent_id, json.dumps(details), iso)
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Step 2: Set trust score and burnout score
# ---------------------------------------------------------------------------

print("[seed] Setting trust/burnout scores ...")

# Set Crew Boss trust to 6 (assistant level)
bus.update_trust_score(RYAN, 6, db_path=DB_FILE)

# Set burnout to 4 (moderate)
bus.update_burnout_score(RYAN, 4, db_path=DB_FILE)

# Audit trail of score changes
seed_audit("trust_change", CHIEF, {"old": 1, "new": 4, "reason": "Initial ramp-up"}, days_ago=3)
seed_audit("trust_change", CHIEF, {"old": 4, "new": 6, "reason": "Solid first week"}, days_ago=1)
seed_audit("burnout_change", RYAN, {"old": 5, "new": 7, "reason": "Heavy sprint"}, days_ago=2)
seed_audit("burnout_change", RYAN, {"old": 7, "new": 4, "reason": "Weekend recovery"}, days_ago=0)


# ---------------------------------------------------------------------------
# Step 3: Add timing rules
# ---------------------------------------------------------------------------

print("[seed] Adding timing rules ...")

conn = bus.get_conn(DB_FILE)
conn.execute(
    "INSERT INTO timing_rules (agent_id, rule_type, rule_config, enabled) VALUES (?, ?, ?, ?)",
    (RYAN, "quiet_hours",
     json.dumps({"start": "22:00", "end": "07:00", "timezone": "America/Vancouver"}), 1)
)
conn.execute(
    "INSERT INTO timing_rules (agent_id, rule_type, rule_config, enabled) VALUES (?, ?, ?, ?)",
    (RYAN, "burnout_threshold",
     json.dumps({"threshold": 7, "action": "queue_non_urgent"}), 1)
)
conn.commit()
conn.close()


# ---------------------------------------------------------------------------
# Step 4: Seed messages (25+ across 3 days)
# ---------------------------------------------------------------------------

print("[seed] Seeding messages ...")

# Agent IDs — prefer ryan_stack names, fall back to example_stack names
V4 = agents.get("V4", agents.get("Ideas", {})).get("id", CHIEF)
QUANT = agents.get("Quant", agents.get("Wallet", {})).get("id", CHIEF)
CFO = agents.get("CFO", agents.get("Wallet", {})).get("id", CHIEF)
LEGAL = agents.get("Legal", {}).get("id", CHIEF)
MEMORY = agents.get("Memory", {}).get("id", CHIEF)
COMMS = agents.get("Comms", {}).get("id", CHIEF)

# Try to get department agents if they exist
RJC_MGR = agents.get("RJC-Manager", {}).get("id")
LEAD_TRACKER = agents.get("Lead-Tracker", {}).get("id")
INVOICE_BOT = agents.get("Invoice-Bot", {}).get("id")
REVIEW_HARV = agents.get("Review-Harvester", {}).get("id")
BCS_MGR = agents.get("BCS-Manager", {}).get("id")
PROP_MON = agents.get("Property-Monitor", {}).get("id")
CLIENT_REP = agents.get("Client-Reporter", {}).get("id")

msg_count = 0

# --- Day 3 (oldest) ---
m1 = seed_message(V4, CHIEF, "report", "Weekly strategy review ready",
    "Q1 metrics compiled. Revenue up 12% MoM. Key risks: market volatility, "
    "competitor launch in March. Recommend accelerating product roadmap.",
    "normal", "read", days_ago=3, hours_ago=2)
msg_count += 1

m2 = seed_message(CFO, CHIEF, "report", "Monthly P&L summary",
    "Operating margin: 23%. Cash runway: 18 months. AR aging: $45K over 90 days. "
    "Recommend follow-up on two delinquent accounts.",
    "normal", "read", days_ago=3, hours_ago=1)
msg_count += 1

m3 = seed_message(QUANT, CHIEF, "alert", "Burnout indicators elevated",
    "Sleep score: 62/100. Screen time up 40% this week. "
    "Calendar density: 7.2 hrs/day scheduled. Recommend blocking Friday PM for recovery.",
    "high", "read", days_ago=3)
msg_count += 1

m4 = seed_message(LEGAL, CHIEF, "report", "Contract review complete - Acme Corp",
    "NDA reviewed. Two clauses flagged: non-compete scope (too broad, recommend narrowing "
    "to 12 months) and liability cap (suggest raising to 2x contract value).",
    "normal", "delivered", days_ago=3)
msg_count += 1

m5 = seed_message(CHIEF, RYAN, "report", "Morning briefing - Day summary",
    "3 items need your attention today: strategy review, P&L sign-off, and "
    "Acme NDA revisions. Quant flagged elevated burnout - I blocked your Friday PM.",
    "normal", "read", days_ago=3)
msg_count += 1

# --- Day 2 ---
m6 = seed_message(V4, CHIEF, "idea", "Partnership opportunity with TechCorp",
    "TechCorp reached out about integration partnership. Could increase TAM by 30%. "
    "Initial call proposed for next week. Want me to schedule?",
    "normal", "delivered", days_ago=2, hours_ago=8)
msg_count += 1

m7 = seed_message(COMMS, CHIEF, "report", "Social engagement weekly digest",
    "LinkedIn: +340 followers, 12K impressions. Twitter: stable. "
    "Newsletter open rate: 42% (up from 38%). Top post: AI hiring trends.",
    "low", "delivered", days_ago=2, hours_ago=6)
msg_count += 1

m8 = seed_message(CFO, CHIEF, "alert", "Unusual expense flagged",
    "AWS bill spiked 45% ($2,340 over budget). Root cause appears to be "
    "a dev staging environment left running. Recommend immediate cleanup.",
    "high", "read", days_ago=2, hours_ago=5)
msg_count += 1

m9 = seed_message(RYAN, CHIEF, "task", "Follow up on Acme NDA revisions",
    "Tell Legal to proceed with the recommended changes. Get revised draft by EOW.",
    "normal", "delivered", days_ago=2, hours_ago=4)
msg_count += 1

m10 = seed_message(CHIEF, LEGAL, "task", "Proceed with Acme NDA revisions",
    "Ryan approved your recommendations. Please narrow non-compete to 12 months "
    "and raise liability cap to 2x. Need revised draft by end of week.",
    "normal", "delivered", days_ago=2, hours_ago=4)
msg_count += 1

if RJC_MGR:
    m11 = seed_message(RJC_MGR, CHIEF, "report", "RJC weekly pipeline update",
        "Active leads: 12. Proposals sent: 3. Won this week: 1 ($18K). "
        "Lost: 0. Pipeline value: $142K. Lead-Tracker pulled 8 new prospects.",
        "normal", "delivered", days_ago=2, hours_ago=3)
    msg_count += 1

if BCS_MGR:
    m12 = seed_message(BCS_MGR, CHIEF, "report", "BCS monthly operations summary",
        "Properties managed: 24. Occupancy: 96%. Maintenance requests: 7 (5 resolved). "
        "Revenue collected: $48K. Two lease renewals due next month.",
        "normal", "delivered", days_ago=2, hours_ago=2)
    msg_count += 1

m13 = seed_message(MEMORY, CHIEF, "report", "Knowledge base growth report",
    "47 entries this week. Top categories: decisions (18), lessons (12), contacts (9). "
    "Duplicate detection caught 3 near-duplicates. Suggest pruning old preferences.",
    "low", "read", days_ago=2, hours_ago=1)
msg_count += 1

m14 = seed_message(QUANT, CHIEF, "report", "Weekly wellness summary",
    "Average sleep: 6.8 hrs (target: 7.5). Exercise: 3 sessions. "
    "Stress markers: moderate. Overall wellness score: 68/100.",
    "normal", "delivered", days_ago=2)
msg_count += 1

# --- Day 1 (yesterday) ---
m15 = seed_message(V4, CHIEF, "escalation", "Competitor launched early - need response",
    "Competitor X just launched their v2 product, 2 weeks ahead of intel. "
    "Our differentiation still holds but we need to accelerate the March release. "
    "Requesting emergency strategy session.",
    "critical", "read", days_ago=1, hours_ago=10)
msg_count += 1

m16 = seed_message(CHIEF, RYAN, "alert", "URGENT: Competitor launched early",
    "V4 flagged: Competitor X launched v2 ahead of schedule. Our differentiation holds "
    "but recommend accelerating March release. V4 requests emergency strategy session. "
    "This is time-sensitive.",
    "critical", "read", days_ago=1, hours_ago=10)
msg_count += 1

m17 = seed_message(RYAN, CHIEF, "task", "Schedule emergency strategy session",
    "Set up a 1-hour session with V4 for tomorrow morning. Also loop in CFO for budget impact.",
    "high", "delivered", days_ago=1, hours_ago=9)
msg_count += 1

m18 = seed_message(CFO, CHIEF, "report", "Emergency budget assessment - March acceleration",
    "Accelerating March release requires $35K additional spend: $20K contractor fees, "
    "$10K infrastructure, $5K overtime. Runway impact: reduces to 16 months. Manageable.",
    "high", "delivered", days_ago=1, hours_ago=6)
msg_count += 1

m19 = seed_message(COMMS, CHIEF, "idea", "Proactive PR about our roadmap",
    "Given competitor launch, suggest publishing our Q2 roadmap teaser on LinkedIn "
    "to reassure customers and attract attention. Draft ready for review.",
    "normal", "delivered", days_ago=1, hours_ago=5)
msg_count += 1

if LEAD_TRACKER:
    m20 = seed_message(LEAD_TRACKER, CHIEF, "report", "3 hot leads identified",
        "Found 3 prospects matching ideal customer profile from competitor review sites. "
        "Two have budget authority. Recommend outreach within 48 hours.",
        "normal", "queued", days_ago=1, hours_ago=4)
    msg_count += 1

if INVOICE_BOT:
    m21 = seed_message(INVOICE_BOT, CHIEF, "alert", "Invoice #1087 overdue 30 days",
        "Client: DataFlow Inc. Amount: $12,500. Last contact: 2 weeks ago. "
        "Recommend escalation to direct outreach.",
        "high", "delivered", days_ago=1, hours_ago=3)
    msg_count += 1

m22 = seed_message(LEGAL, CHIEF, "report", "Revised Acme NDA ready for signature",
    "All changes incorporated. Non-compete narrowed to 12 months, liability cap at 2x. "
    "Acme's counsel approved via email. Ready for Ryan's signature.",
    "normal", "delivered", days_ago=1, hours_ago=2)
msg_count += 1

# --- Today ---
m23 = seed_message(CHIEF, RYAN, "report", "Morning briefing",
    "Good morning. 3 items for today:\n"
    "1. Sign Acme NDA (Legal has it ready)\n"
    "2. Emergency strategy session at 10am (V4 + CFO)\n"
    "3. Review Comms PR draft for roadmap teaser\n\n"
    "Overnight: No critical items. Quant says sleep improved to 7.2 hrs.",
    "normal", "delivered", hours_ago=3)
msg_count += 1

m24 = seed_message(QUANT, CHIEF, "report", "Morning vitals check",
    "Sleep: 7.2 hrs (improving). HRV: 52ms (good). "
    "Calendar today: 4.5 hrs scheduled. Burnout risk: LOW.",
    "low", "delivered", hours_ago=2)
msg_count += 1

m25 = seed_message(V4, CHIEF, "report", "Strategy session prep materials",
    "Attached competitive analysis deck. Key slides: market positioning (slide 3), "
    "feature comparison (slide 7), and timeline options (slide 12). "
    "Three scenarios prepared: aggressive, moderate, and conservative.",
    "normal", "queued", hours_ago=1)
msg_count += 1

if PROP_MON:
    m26 = seed_message(PROP_MON, CHIEF, "alert", "Maintenance emergency - Unit 4B water leak",
        "Tenant reported water leak in bathroom. Plumber dispatched. "
        "Estimated repair: $800-1200. Insurance claim may apply.",
        "high", "delivered", hours_ago=1)
    msg_count += 1

if CLIENT_REP:
    m27 = seed_message(CLIENT_REP, CHIEF, "report", "Client satisfaction snapshot",
        "NPS: 72 (up from 68). 2 detractors identified. "
        "Top feedback: 'Great response time' and 'Need better reporting'.",
        "low", "queued", hours_ago=0)
    msg_count += 1

print(f"  Created {msg_count} messages")


# ---------------------------------------------------------------------------
# Step 5: Seed Crew Boss decisions
# ---------------------------------------------------------------------------

print("[seed] Seeding Crew Boss decisions ...")

dec_count = 0

# Decision 1: Delivered critical competitor alert (approved)
d1 = seed_decision(CHIEF, RYAN, "deliver",
    {"message_subject": "Competitor launched early", "priority": "critical", "from": "V4"},
    "Deliver immediately - critical business intelligence",
    "Critical priority from strategy agent. Competitor launch impacts our timeline. "
    "Human needs to know immediately regardless of burnout level.",
    human_override=0, days_ago=1, hours_ago=10)
dec_count += 1

# Decision 2: Filtered low-priority social media report (approved)
d2 = seed_decision(CHIEF, RYAN, "filter",
    {"message_subject": "Social engagement weekly digest", "priority": "low", "from": "Comms"},
    "Queue for briefing - low priority digest",
    "Low priority informational report. No action required. Will include in evening briefing.",
    human_override=0, days_ago=2, hours_ago=6)
dec_count += 1

# Decision 3: Escalated AWS billing alert (approved)
d3 = seed_decision(CHIEF, RYAN, "escalate",
    {"message_subject": "Unusual expense flagged", "priority": "high", "from": "CFO"},
    "Escalate - unexpected cost spike needs attention",
    "45% AWS overspend is material. Human should be aware and approve cleanup action.",
    human_override=0, days_ago=2, hours_ago=5)
dec_count += 1

# Decision 4: Handled routine task autonomously (OVERRIDDEN - human wanted to see it)
d4 = seed_decision(CHIEF, RYAN, "handle",
    {"message_subject": "Knowledge base growth report", "priority": "low", "from": "Memory"},
    "Handle autonomously - routine knowledge maintenance",
    "Standard weekly report, no anomalies. Will auto-acknowledge and file.",
    human_override=1,
    human_action="I want to see these - the duplicate detection data is useful for my workflow",
    note="Learned: Ryan wants knowledge base reports delivered, not filtered",
    days_ago=2, hours_ago=1)
dec_count += 1

# Decision 5: Queued non-urgent during high burnout (approved)
d5 = seed_decision(CHIEF, RYAN, "queue",
    {"message_subject": "Weekly wellness summary", "priority": "normal", "from": "Quant"},
    "Queue - burnout score elevated, non-urgent",
    "Burnout score was 7 at time of message. Wellness summary is informational. "
    "Will deliver in evening briefing when human has more bandwidth.",
    human_override=0, days_ago=2)
dec_count += 1

# Decision 6: Delivered budget assessment immediately (approved)
d6 = seed_decision(CHIEF, RYAN, "deliver",
    {"message_subject": "Emergency budget assessment", "priority": "high", "from": "CFO"},
    "Deliver now - context for strategy session",
    "High priority and directly relevant to the emergency strategy session Ryan scheduled. "
    "Time-sensitive financial data needed for decision-making.",
    human_override=0, days_ago=1, hours_ago=6)
dec_count += 1

# Decision 7: Filtered idea during busy period (OVERRIDDEN - good idea)
d7 = seed_decision(CHIEF, RYAN, "filter",
    {"message_subject": "Proactive PR about our roadmap", "priority": "normal", "from": "Comms"},
    "Filter - not urgent during crisis response",
    "Normal priority idea. Human is focused on competitor response. "
    "Will queue for tomorrow's review.",
    human_override=1,
    human_action="Actually this is smart timing - deliver it, I want to review the draft today",
    note="Learned: PR responses to competitor moves are time-sensitive, not routine",
    days_ago=1, hours_ago=5)
dec_count += 1

# Decision 8: Delivered overdue invoice alert (approved)
d8 = seed_decision(CHIEF, RYAN, "deliver",
    {"message_subject": "Invoice #1087 overdue 30 days", "priority": "high", "from": "Invoice-Bot"},
    "Deliver - financial exposure requires attention",
    "$12,500 overdue. Cash flow impact. Needs human authorization for escalation.",
    human_override=0, days_ago=1, hours_ago=3)
dec_count += 1

# Decision 9: Auto-handled lease renewal reminder (approved)
d9 = seed_decision(CHIEF, RYAN, "handle",
    {"message_subject": "BCS monthly operations summary", "priority": "normal", "from": "BCS-Manager"},
    "Handle - standard monthly ops report, include in briefing",
    "Routine operations report. Metrics are within normal range. "
    "Two lease renewals noted - will add to next week's task list.",
    human_override=0, days_ago=2, hours_ago=2)
dec_count += 1

# Decision 10: Delivered morning briefing (approved)
d10 = seed_decision(CHIEF, RYAN, "deliver",
    {"message_subject": "Morning briefing", "priority": "normal", "from": "Crew-Boss"},
    "Deliver - daily briefing for human",
    "Compiled overnight items, today's priorities, and wellness update. "
    "3 action items identified.",
    human_override=0, hours_ago=3)
dec_count += 1

# Decision 11: Queued lead tracker report (approved)
d11 = seed_decision(CHIEF, RYAN, "queue",
    {"message_subject": "3 hot leads identified", "priority": "normal", "from": "Lead-Tracker"},
    "Queue for next review block - not time-critical today",
    "Good leads but human is in emergency strategy mode. These can wait 24-48 hours "
    "without losing the opportunity. Will surface in tomorrow's briefing.",
    human_override=0, days_ago=1, hours_ago=4)
dec_count += 1

# Decision 12: Filtered a repeat idea (OVERRIDDEN initially but then approved pattern)
d12 = seed_decision(CHIEF, RYAN, "filter",
    {"message_subject": "Partnership opportunity with TechCorp", "priority": "normal", "from": "V4"},
    "Filter - similar partnership was rejected 2 months ago",
    "Knowledge store shows a TechCorp partnership was previously rejected. "
    "Filtering based on learned preference.",
    human_override=1,
    human_action="Different division of TechCorp - deliver this one, context has changed",
    note="Learned: TechCorp rejection was specific to their enterprise division, not all of TechCorp",
    days_ago=2, hours_ago=8)
dec_count += 1

print(f"  Created {dec_count} decisions ({sum(1 for _ in [d4, d7, d12])} overridden)")


# ---------------------------------------------------------------------------
# Step 6: Quarantine an agent
# ---------------------------------------------------------------------------

print("[seed] Quarantining Review-Harvester (simulated bad behavior) ...")

if REVIEW_HARV:
    bus.quarantine_agent(REVIEW_HARV, db_path=DB_FILE)
    seed_audit("quarantine", REVIEW_HARV,
        {"reason": "Excessive API calls detected - 500 calls in 1 hour (limit: 50)",
         "triggered_by": "rate_limit_monitor"},
        days_ago=1, hours_ago=7)
    print("  Review-Harvester quarantined")
else:
    print("  WARN: Review-Harvester not found in config, skipping quarantine")


# ---------------------------------------------------------------------------
# Step 7: Seed knowledge store entries
# ---------------------------------------------------------------------------

print("[seed] Seeding knowledge store ...")

k_count = 0

seed_knowledge(CHIEF, "decision",
    "Competitor response protocol",
    {"rule": "Deliver competitor alerts immediately regardless of burnout",
     "learned_from": "d1", "confidence": 0.95},
    tags="competitor,strategy,urgent", days_ago=1)
k_count += 1

seed_knowledge(CHIEF, "preference",
    "Knowledge base reports",
    {"preference": "Deliver to human, do not filter",
     "reason": "Ryan uses duplicate detection data for workflow optimization"},
    tags="knowledge,reports,memory", source_msg_id=m13, days_ago=2)
k_count += 1

seed_knowledge(CHIEF, "rejection",
    "TechCorp Enterprise partnership",
    {"rejected_on": "2024-12-15", "reason": "Poor enterprise division culture fit",
     "scope": "enterprise division only, not all TechCorp"},
    tags="partnership,techcorp,rejection", days_ago=2)
k_count += 1

seed_knowledge(CHIEF, "lesson",
    "PR timing during competitive events",
    {"lesson": "Proactive PR during competitor launches is time-sensitive",
     "old_behavior": "Queue as non-urgent idea",
     "new_behavior": "Deliver immediately for review"},
    tags="pr,competitor,timing,comms", days_ago=1)
k_count += 1

seed_knowledge(CHIEF, "contact",
    "Acme Corp - Legal Contact",
    {"name": "Sarah Chen", "role": "General Counsel", "email": "schen@acmecorp.example",
     "notes": "Responsive, prefers email. NDA turnaround: 3 business days."},
    tags="acme,legal,contact", days_ago=3)
k_count += 1

seed_knowledge(CHIEF, "preference",
    "Morning briefing format",
    {"format": "numbered action items first, then context",
     "max_items": 5, "include_wellness": True},
    tags="briefing,morning,format", days_ago=3)
k_count += 1

seed_knowledge(CHIEF, "lesson",
    "AWS cost monitoring",
    {"lesson": "Set up daily cost alerts, not just monthly",
     "trigger": "45% AWS overspend caught late",
     "action": "CFO now sends daily cost snapshots"},
    tags="aws,costs,monitoring,cfo", days_ago=2)
k_count += 1

seed_knowledge(CHIEF, "decision",
    "Burnout-based message queueing",
    {"rule": "When burnout > 6, queue all normal/low priority messages",
     "exceptions": ["financial alerts > $10K", "competitor intelligence", "legal deadlines"],
     "learned_from": "multiple decisions"},
    tags="burnout,queueing,rules", days_ago=2)
k_count += 1

print(f"  Created {k_count} knowledge entries")


# ---------------------------------------------------------------------------
# Step 8: Add more audit trail entries for realism
# ---------------------------------------------------------------------------

print("[seed] Seeding audit trail ...")

audit_entries = [
    ("hierarchy_loaded", RYAN, {"config": CONFIG_FILE.name, "agents": 15}, 3, 4),
    ("message_sent", V4, {"to": "Crew-Boss", "subject": "Weekly strategy review ready"}, 3, 2),
    ("message_delivered", CHIEF, {"to": "Ryan", "subject": "Morning briefing"}, 3, 0),
    ("message_sent", CFO, {"to": "Crew-Boss", "subject": "Unusual expense flagged"}, 2, 5),
    ("decision_made", CHIEF, {"type": "escalate", "subject": "AWS billing spike"}, 2, 5),
    ("message_sent", V4, {"to": "Crew-Boss", "subject": "Competitor launched early"}, 1, 10),
    ("decision_made", CHIEF, {"type": "deliver", "subject": "Competitor alert", "priority": "critical"}, 1, 10),
    ("decision_overridden", CHIEF, {"type": "filter", "subject": "TechCorp partnership", "human_note": "Different division"}, 2, 8),
    ("decision_overridden", CHIEF, {"type": "handle", "subject": "Knowledge base report", "human_note": "Want to see these"}, 2, 1),
    ("decision_overridden", CHIEF, {"type": "filter", "subject": "PR roadmap teaser", "human_note": "Smart timing"}, 1, 5),
    ("agent_quarantined", REVIEW_HARV or CHIEF, {"reason": "Rate limit exceeded", "calls": 500, "limit": 50}, 1, 7),
    ("message_sent", CHIEF, {"to": "Ryan", "subject": "URGENT: Competitor launched early"}, 1, 10),
    ("briefing_compiled", CHIEF, {"type": "morning", "items": 3}, 0, 3),
]

for evt_type, aid, details, d_ago, h_ago in audit_entries:
    seed_audit(evt_type, aid, details, days_ago=d_ago, hours_ago=h_ago)

print(f"  Created {len(audit_entries)} audit entries")


# ---------------------------------------------------------------------------
# Step 9: Verify counts
# ---------------------------------------------------------------------------

print("\n" + "=" * 50)
print("  SEED DATA SUMMARY")
print("=" * 50)

conn = bus.get_conn(DB_FILE)

agent_count = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
active_count = conn.execute("SELECT COUNT(*) FROM agents WHERE status='active'").fetchone()[0]
quarantined_count = conn.execute("SELECT COUNT(*) FROM agents WHERE status='quarantined'").fetchone()[0]
msg_total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
msg_critical = conn.execute("SELECT COUNT(*) FROM messages WHERE priority='critical'").fetchone()[0]
msg_queued = conn.execute("SELECT COUNT(*) FROM messages WHERE status='queued'").fetchone()[0]
dec_total = conn.execute("SELECT COUNT(*) FROM decision_log").fetchone()[0]
dec_overridden = conn.execute("SELECT COUNT(*) FROM decision_log WHERE human_override=1").fetchone()[0]
knowledge_total = conn.execute("SELECT COUNT(*) FROM knowledge_store").fetchone()[0]
audit_total = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
timing_total = conn.execute("SELECT COUNT(*) FROM timing_rules").fetchone()[0]

# Get trust from Crew Boss agent, burnout from human agent
human_row = conn.execute("SELECT burnout_score FROM agents WHERE id=?", (RYAN,)).fetchone()
rh_row = conn.execute("SELECT trust_score FROM agents WHERE id=?", (CHIEF,)).fetchone()

conn.close()

print(f"  Agents:      {agent_count} total ({active_count} active, {quarantined_count} quarantined)")
print(f"  Messages:    {msg_total} total ({msg_critical} critical, {msg_queued} queued)")
print(f"  Decisions:   {dec_total} total ({dec_overridden} overridden by human)")
print(f"  Knowledge:   {knowledge_total} entries")
print(f"  Audit log:   {audit_total} entries")
print(f"  Timing rules: {timing_total}")
print(f"  Trust score:  {rh_row['trust_score']}/10 (on Crew Boss)")
print(f"  Burnout:      {human_row['burnout_score']}/10 (on Human)")
print()
print("=" * 50)
print("  Dashboard ready at http://localhost:8420")
print("  Run: python dashboard.py")
print("=" * 50)
