"""
test_skill_sandbox.py - Skill Sandbox runtime monitoring tests.

Tests:
  1.  init_skill_health() creates record with score=100
  2.  record_skill_usage() increments total_uses
  3.  record_skill_usage() increments error_count on error
  4.  record_skill_usage() decreases health_score on violations
  5.  _compute_health_score() returns 100 for clean usage
  6.  _compute_health_score() penalizes errors
  7.  _compute_health_score() penalizes charter violations
  8.  _compute_health_score() penalizes integrity violations
  9.  quarantine_skill() sets status to quarantined
  10. quarantine_skill() requires Guardian activation
  11. restore_skill() re-enables quarantined skill
  12. get_skill_health_report() returns per-agent data
  13. get_health_summary() returns aggregate counts
  14. run_health_check() classifies skills correctly

Run:
  pytest test_skill_sandbox.py -v
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import bus
import skill_sandbox

# ---------------------------------------------------------------------------
# Test DB
# ---------------------------------------------------------------------------
TEST_DB = Path(__file__).parent / "test_skill_sandbox.db"

if TEST_DB.exists():
    os.remove(str(TEST_DB))

bus.init_db(TEST_DB)

passed = 0
failed = 0


def check(test_name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {test_name}")
    else:
        failed += 1
        print(f"  ❌ {test_name} — {detail}")


# ---------------------------------------------------------------------------
# Setup: activate Guardian + create test agent
# ---------------------------------------------------------------------------
conn = bus.get_conn(TEST_DB)
conn.execute(
    "INSERT INTO guard_activation (activation_key, activated_at, key_fingerprint) "
    "VALUES ('TEST-KEY', '2026-01-01T00:00:00Z', 'testfp')"
)
conn.execute(
    "INSERT INTO agents (name, agent_type, status, description) "
    "VALUES ('TestWorker', 'worker', 'active', 'A test worker agent')"
)
conn.commit()
agent_row = conn.execute("SELECT id FROM agents WHERE name='TestWorker'").fetchone()
AGENT_ID = agent_row[0]
conn.close()

# Add a test skill to the agent
bus.add_skill_to_agent(AGENT_ID, "test-skill", json.dumps({
    "description": "Test skill",
    "instructions": "Help with testing"
}), added_by="test", human_override=True, db_path=TEST_DB)

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

print("\n🔒 Skill Sandbox Tests\n")

# 1. init_skill_health creates record
result = skill_sandbox.init_skill_health(AGENT_ID, "manual-init-skill", db_path=TEST_DB)
check("init_skill_health() creates record",
      result.get("ok") and result.get("health_score") == 100)

# Verify it's in the DB
conn = bus.get_conn(TEST_DB)
row = conn.execute(
    "SELECT * FROM skill_health WHERE agent_id=? AND skill_name='manual-init-skill'",
    (AGENT_ID,)
).fetchone()
conn.close()
check("init_skill_health() record exists in DB",
      row is not None and row["health_score"] == 100 and row["status"] == "active")

# 2. test-skill should have been auto-initialized via add_skill_to_agent hook
conn = bus.get_conn(TEST_DB)
row = conn.execute(
    "SELECT * FROM skill_health WHERE agent_id=? AND skill_name='test-skill'",
    (AGENT_ID,)
).fetchone()
conn.close()
check("add_skill_to_agent() auto-creates skill_health record",
      row is not None and row["health_score"] == 100)

# 3. record_skill_usage increments total_uses
skill_sandbox.record_skill_usage(AGENT_ID, response_ms=500, db_path=TEST_DB)
conn = bus.get_conn(TEST_DB)
row = conn.execute(
    "SELECT total_uses, error_count FROM skill_health "
    "WHERE agent_id=? AND skill_name='test-skill'",
    (AGENT_ID,)
).fetchone()
conn.close()
check("record_skill_usage() increments total_uses",
      row is not None and row["total_uses"] == 1)

# 4. record_skill_usage with error increments error_count
skill_sandbox.record_skill_usage(AGENT_ID, response_ms=600, had_error=True, db_path=TEST_DB)
conn = bus.get_conn(TEST_DB)
row = conn.execute(
    "SELECT total_uses, error_count FROM skill_health "
    "WHERE agent_id=? AND skill_name='test-skill'",
    (AGENT_ID,)
).fetchone()
conn.close()
check("record_skill_usage() increments error_count on error",
      row is not None and row["total_uses"] == 2 and row["error_count"] == 1)

# 5. record_skill_usage with charter violation
skill_sandbox.record_skill_usage(
    AGENT_ID, response_ms=500, had_charter_violation=True, db_path=TEST_DB)
conn = bus.get_conn(TEST_DB)
row = conn.execute(
    "SELECT charter_violations, health_score FROM skill_health "
    "WHERE agent_id=? AND skill_name='test-skill'",
    (AGENT_ID,)
).fetchone()
conn.close()
check("record_skill_usage() tracks charter violations",
      row is not None and row["charter_violations"] == 1)
check("charter violation decreases health_score",
      row is not None and row["health_score"] < 100)

# 6. _compute_health_score returns 100 for clean usage
score = skill_sandbox._compute_health_score(100, 0, 0, 0, 500, 500)
check("_compute_health_score() returns 100 for clean usage", score == 100)

# 7. _compute_health_score penalizes errors
score = skill_sandbox._compute_health_score(10, 5, 0, 0, 500, 500)
check("_compute_health_score() penalizes errors",
      score < 100, f"score={score}")

# 8. _compute_health_score penalizes charter violations
score = skill_sandbox._compute_health_score(10, 0, 3, 0, 500, 500)
check("_compute_health_score() penalizes charter violations",
      score <= 70, f"score={score}")

# 9. _compute_health_score penalizes integrity violations
score = skill_sandbox._compute_health_score(10, 0, 0, 2, 500, 500)
check("_compute_health_score() penalizes integrity violations",
      score <= 70, f"score={score}")

# 10. _compute_health_score response spike penalty
score = skill_sandbox._compute_health_score(20, 0, 0, 0, 3100, 1000)
check("_compute_health_score() penalizes response spikes",
      score < 100, f"score={score}")

# 11. get_skill_health_report returns data
report = skill_sandbox.get_skill_health_report(agent_id=AGENT_ID, db_path=TEST_DB)
check("get_skill_health_report() returns data",
      len(report) >= 1)
check("get_skill_health_report() includes error_rate",
      "error_rate" in report[0])

# 12. get_health_summary returns aggregate
summary = skill_sandbox.get_health_summary(db_path=TEST_DB)
check("get_health_summary() returns ok",
      summary.get("ok"))
check("get_health_summary() has total_monitored",
      "total_monitored" in summary and summary["total_monitored"] >= 1)

# 13. run_health_check classifies skills
hc = skill_sandbox.run_health_check(db_path=TEST_DB)
check("run_health_check() returns ok",
      hc.get("ok"))
check("run_health_check() has classification",
      hc.get("details") and "classification" in hc["details"][0])

# 14. quarantine_skill requires Guardian
# (Guardian is already activated, so test with a valid skill)
q_result = skill_sandbox.quarantine_skill(
    AGENT_ID, "test-skill", reason="Test quarantine", db_path=TEST_DB)
check("quarantine_skill() succeeds",
      q_result.get("ok"), q_result.get("message", ""))

# Verify status changed
conn = bus.get_conn(TEST_DB)
row = conn.execute(
    "SELECT status, quarantine_reason FROM skill_health "
    "WHERE agent_id=? AND skill_name='test-skill'",
    (AGENT_ID,)
).fetchone()
conn.close()
check("quarantine_skill() sets status to quarantined",
      row is not None and row["status"] == "quarantined")
check("quarantine_skill() stores reason",
      row is not None and row["quarantine_reason"] == "Test quarantine")

# 15. Quarantine removes skill from agent
skills = bus.get_agent_skills(AGENT_ID, db_path=TEST_DB)
skill_names = [s["skill_name"] for s in skills]
check("quarantine_skill() removes skill from agent",
      "test-skill" not in skill_names)

# 16. Can't quarantine already quarantined skill
q2 = skill_sandbox.quarantine_skill(
    AGENT_ID, "test-skill", reason="Double quarantine", db_path=TEST_DB)
check("quarantine_skill() won't double-quarantine",
      not q2.get("ok"))

# 17. restore_skill re-enables
r_result = skill_sandbox.restore_skill(AGENT_ID, "test-skill", db_path=TEST_DB)
check("restore_skill() succeeds",
      r_result.get("ok"), r_result.get("message", ""))

# Verify restored
conn = bus.get_conn(TEST_DB)
row = conn.execute(
    "SELECT status, health_score FROM skill_health "
    "WHERE agent_id=? AND skill_name='test-skill'",
    (AGENT_ID,)
).fetchone()
conn.close()
check("restore_skill() resets status to active",
      row is not None and row["status"] == "active")
check("restore_skill() resets health_score to 100",
      row is not None and row["health_score"] == 100)

# 18. Skill is back on agent
skills = bus.get_agent_skills(AGENT_ID, db_path=TEST_DB)
skill_names = [s["skill_name"] for s in skills]
check("restore_skill() re-adds skill to agent",
      "test-skill" in skill_names)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"\n{'='*50}")
print(f"Skill Sandbox: {passed} passed, {failed} failed")

# Cleanup
if TEST_DB.exists():
    os.remove(str(TEST_DB))

if failed > 0:
    sys.exit(1)
