"""
test_guard_activation.py - Guard activation and skill-add gating tests.

Tests:
  1.  is_guard_activated() returns False on fresh DB
  2.  activate_guard() with valid key succeeds
  3.  activate_guard() with invalid format fails
  4.  activate_guard() with invalid signature fails
  5.  activate_guard() with duplicate key fails
  6.  is_guard_activated() returns True after activation
  7.  add_skill_to_agent() fails when Guard not activated
  8.  add_skill_to_agent() succeeds when Guard is activated
  9.  add_skill_to_agent() with duplicate skill name fails
  10. get_guard_activation_status() returns correct data

Run:
  python test_guard_activation.py
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import bus

# ---------------------------------------------------------------------------
# Test DB
# ---------------------------------------------------------------------------

TEST_DB = Path(__file__).parent / "test_guard_activation.db"
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
# Setup: Initialize DB and load config
# ============================================================

section("Setup: Initialize DB")
bus.init_db(TEST_DB)
result = bus.load_hierarchy(str(CONFIG), TEST_DB)
agents_loaded = result.get("agents_loaded", [])
print(f"  Loaded {len(agents_loaded)} agents.")

# Get a test agent ID for skill tests (agent name is "Security", displayed as "Guard")
guard_agent = bus.get_agent_by_name("Security", TEST_DB)
assert guard_agent is not None, "Security agent must exist"
guard_id = guard_agent["id"]

# Get any other agent for skill tests
boss = bus.get_agent_by_name("Crew-Boss", TEST_DB)
assert boss is not None, "Crew Boss must exist"
boss_id = boss["id"]


# ============================================================
# Test 1: is_guard_activated() returns False on fresh DB
# ============================================================

section("Test 1: is_guard_activated() returns False on fresh DB")
check("1", bus.is_guard_activated(TEST_DB) is False,
      "Fresh DB should not have Guard activated")


# ============================================================
# Test 2: activate_guard() with valid key succeeds
# ============================================================

section("Test 2: activate_guard() with valid key succeeds")
valid_key = bus.generate_test_activation_key()
print(f"  Generated test key: {valid_key[:30]}...")
success, message = bus.activate_guard(valid_key, TEST_DB)
check("2", success is True, f"activate_guard should succeed: {message}")


# ============================================================
# Test 3: activate_guard() with invalid format fails
# ============================================================

section("Test 3: activate_guard() with invalid format fails")

# No CREWBUS- prefix
s3a, m3a = bus.activate_guard("INVALID-KEY-HERE", TEST_DB)
check("3a", s3a is False, f"Missing prefix should fail: {m3a}")

# Empty key
s3b, m3b = bus.activate_guard("", TEST_DB)
check("3b", s3b is False, f"Empty key should fail: {m3b}")

# Only prefix, no payload or sig
s3c, m3c = bus.activate_guard("CREWBUS-", TEST_DB)
check("3c", s3c is False, f"Missing payload should fail: {m3c}")

# Prefix with payload but no signature
s3d, m3d = bus.activate_guard("CREWBUS-somepayload", TEST_DB)
check("3d", s3d is False, f"Missing signature should fail: {m3d}")


# ============================================================
# Test 4: activate_guard() with invalid signature fails
# ============================================================

section("Test 4: activate_guard() with invalid signature fails")

import base64
payload = base64.b64encode(json.dumps({"type": "guard", "issued": "2026-01-01", "id": "test"}).encode()).decode()
bad_key = f"CREWBUS-{payload}-deadbeef1234567890abcdef1234567890abcdef1234567890abcdef12345678"
s4, m4 = bus.activate_guard(bad_key, TEST_DB)
check("4", s4 is False, f"Bad signature should fail: {m4}")
check("4b", "signature" in m4.lower(), "Error should mention signature")


# ============================================================
# Test 5: activate_guard() with duplicate key fails
# ============================================================

section("Test 5: activate_guard() with duplicate key fails")

# Use a fresh DB for this test to avoid the already-activated state
TEST_DB_DUP = Path(__file__).parent / "test_guard_dup.db"
if TEST_DB_DUP.exists():
    os.remove(str(TEST_DB_DUP))
bus.init_db(TEST_DB_DUP)
bus.load_hierarchy(str(CONFIG), TEST_DB_DUP)

dup_key = bus.generate_test_activation_key()
s5a, m5a = bus.activate_guard(dup_key, TEST_DB_DUP)
check("5a", s5a is True, f"First activation should succeed: {m5a}")

s5b, m5b = bus.activate_guard(dup_key, TEST_DB_DUP)
check("5b", s5b is False, f"Duplicate key should fail: {m5b}")
check("5c", "already" in m5b.lower(), "Error should mention already used")

# Clean up
if TEST_DB_DUP.exists():
    os.remove(str(TEST_DB_DUP))


# ============================================================
# Test 6: is_guard_activated() returns True after activation
# ============================================================

section("Test 6: is_guard_activated() returns True after activation")
check("6", bus.is_guard_activated(TEST_DB) is True,
      "Should be activated after valid key")


# ============================================================
# Test 7: add_skill_to_agent() fails when Guard not activated
# ============================================================

section("Test 7: add_skill_to_agent() fails when Guard not activated")

# Use a fresh DB without activation
TEST_DB_NOGUARD = Path(__file__).parent / "test_guard_noguard.db"
if TEST_DB_NOGUARD.exists():
    os.remove(str(TEST_DB_NOGUARD))
bus.init_db(TEST_DB_NOGUARD)
bus.load_hierarchy(str(CONFIG), TEST_DB_NOGUARD)

ng_guard = bus.get_agent_by_name("Security", TEST_DB_NOGUARD)
s7, m7 = bus.add_skill_to_agent(ng_guard["id"], "test-skill", db_path=TEST_DB_NOGUARD)
check("7", s7 is False, f"Should fail without Guard activation: {m7}")
check("7b", "activation required" in m7.lower(), f"Error should mention activation: {m7}")

if TEST_DB_NOGUARD.exists():
    os.remove(str(TEST_DB_NOGUARD))


# ============================================================
# Test 8: add_skill_to_agent() succeeds when Guard is activated
# ============================================================

section("Test 8: add_skill_to_agent() succeeds when Guard is activated")
s8, m8 = bus.add_skill_to_agent(guard_id, "threat-detection", db_path=TEST_DB)
check("8", s8 is True, f"Should succeed with Guard activated: {m8}")

# Verify it was stored
skills = bus.get_agent_skills(guard_id, db_path=TEST_DB)
check("8b", len(skills) == 1, f"Should have 1 skill, got {len(skills)}")
check("8c", skills[0]["skill_name"] == "threat-detection",
      f"Skill name should match: {skills[0]['skill_name']}")


# ============================================================
# Test 9: add_skill_to_agent() with duplicate skill name fails
# ============================================================

section("Test 9: add_skill_to_agent() with duplicate skill name fails")
s9, m9 = bus.add_skill_to_agent(guard_id, "threat-detection", db_path=TEST_DB)
check("9", s9 is False, f"Duplicate skill should fail: {m9}")
check("9b", "already exists" in m9.lower(), f"Error should mention exists: {m9}")


# ============================================================
# Test 10: get_guard_activation_status() returns correct data
# ============================================================

section("Test 10: get_guard_activation_status() returns correct data")
status = bus.get_guard_activation_status(TEST_DB)
check("10a", status is not None, "Status should not be None")
check("10b", status["activated"] is True, f"Should be activated: {status}")
check("10c", status["activated_at"] is not None, f"Should have timestamp: {status}")
check("10d", status["key_fingerprint"] is not None, f"Should have fingerprint: {status}")

# Check status on fresh DB returns None
TEST_DB_FRESH = Path(__file__).parent / "test_guard_fresh.db"
if TEST_DB_FRESH.exists():
    os.remove(str(TEST_DB_FRESH))
bus.init_db(TEST_DB_FRESH)
fresh_status = bus.get_guard_activation_status(TEST_DB_FRESH)
check("10e", fresh_status is None, "Fresh DB should return None")
if TEST_DB_FRESH.exists():
    os.remove(str(TEST_DB_FRESH))


# ============================================================
# Summary
# ============================================================

section("RESULTS")
total = passed + failed
print(f"\n  Total: {total}  Passed: {passed}  Failed: {failed}")
if failed > 0:
    print(f"\n  *** {failed} TEST(S) FAILED ***")
    sys.exit(1)
else:
    print("\n  ALL TESTS PASSED!")

# Clean up
if TEST_DB.exists():
    os.remove(str(TEST_DB))
