"""
test_techie_marketplace.py - Techie marketplace backend tests.

Tests:
  1.  register_techie() creates pending techie
  2.  verify_techie_kyc() updates status
  3.  purchase_techie_key() fails for unverified techie
  4.  purchase_techie_key() succeeds for verified techie
  5.  purchase_techie_key() fails for revoked techie
  6.  use_techie_key() marks key as used
  7.  use_techie_key() fails for already-used key
  8.  revoke_techie() sets standing to revoked
  9.  add_techie_review() updates average rating
  10. list_techies() filters correctly

Run:
  python test_techie_marketplace.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import bus

# ---------------------------------------------------------------------------
# Test DB
# ---------------------------------------------------------------------------

TEST_DB = Path(__file__).parent / "test_techie_marketplace.db"
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
# Setup
# ============================================================

section("Setup: Initialize DB")
bus.init_db(TEST_DB)
result = bus.load_hierarchy(str(CONFIG), TEST_DB)
print(f"  Loaded {len(result.get('agents_loaded', []))} agents.")


# ============================================================
# Test 1: register_techie() creates pending techie
# ============================================================

section("Test 1: register_techie() creates pending techie")
t1 = bus.register_techie("techie-001", "Alice Builder", "alice@example.com", db_path=TEST_DB)
check("1a", t1["techie_id"] == "techie-001", f"Techie ID should match: {t1}")
check("1b", t1["kyc_status"] == "pending", f"Should be pending: {t1}")

# Verify in DB
profile = bus.get_techie_profile("techie-001", db_path=TEST_DB)
check("1c", profile is not None, "Profile should exist")
check("1d", profile["display_name"] == "Alice Builder", f"Name: {profile['display_name']}")
check("1e", profile["standing"] == "good", f"Standing: {profile['standing']}")

# Test duplicate registration fails
try:
    bus.register_techie("techie-001", "Duplicate", "dup@test.com", db_path=TEST_DB)
    check("1f", False, "Duplicate should raise ValueError")
except ValueError:
    check("1f", True, "Duplicate correctly raises ValueError")


# ============================================================
# Test 2: verify_techie_kyc() updates status
# ============================================================

section("Test 2: verify_techie_kyc() updates status")
v2 = bus.verify_techie_kyc("techie-001", db_path=TEST_DB)
check("2a", v2["kyc_status"] == "verified", f"Should be verified: {v2}")
check("2b", v2["kyc_verified_at"] is not None, f"Should have timestamp: {v2}")

# Verify in DB
profile2 = bus.get_techie_profile("techie-001", db_path=TEST_DB)
check("2c", profile2["kyc_status"] == "verified", f"DB status: {profile2['kyc_status']}")

# Non-existent techie
try:
    bus.verify_techie_kyc("nonexistent", db_path=TEST_DB)
    check("2d", False, "Nonexistent should raise ValueError")
except ValueError:
    check("2d", True, "Nonexistent correctly raises ValueError")


# ============================================================
# Test 3: purchase_techie_key() fails for unverified techie
# ============================================================

section("Test 3: purchase_techie_key() fails for unverified techie")

# Register an unverified techie
bus.register_techie("techie-unverified", "Unverified Bob", "bob@test.com", db_path=TEST_DB)

try:
    bus.purchase_techie_key("techie-unverified", db_path=TEST_DB)
    check("3", False, "Unverified should raise PermissionError")
except PermissionError as e:
    check("3", True, f"Unverified correctly rejected: {e}")


# ============================================================
# Test 4: purchase_techie_key() succeeds for verified techie
# ============================================================

section("Test 4: purchase_techie_key() succeeds for verified techie")
key4 = bus.purchase_techie_key("techie-001", db_path=TEST_DB)
check("4a", key4.startswith("TECHIE-"), f"Key format: {key4}")
check("4b", len(key4) > 10, f"Key should have substance: {key4}")

# Check keys_purchased incremented
profile4 = bus.get_techie_profile("techie-001", db_path=TEST_DB)
check("4c", profile4["total_keys_purchased"] == 1, f"Keys: {profile4['total_keys_purchased']}")

# Purchase another key
key4b = bus.purchase_techie_key("techie-001", db_path=TEST_DB)
check("4d", key4b != key4, "Keys should be unique")

profile4b = bus.get_techie_profile("techie-001", db_path=TEST_DB)
check("4e", profile4b["total_keys_purchased"] == 2, f"Keys: {profile4b['total_keys_purchased']}")


# ============================================================
# Test 5: purchase_techie_key() fails for revoked techie
# ============================================================

section("Test 5: purchase_techie_key() fails for revoked techie")

# Register and verify a techie, then revoke
bus.register_techie("techie-revoked", "Revoked Charlie", "charlie@test.com", db_path=TEST_DB)
bus.verify_techie_kyc("techie-revoked", db_path=TEST_DB)
bus.revoke_techie("techie-revoked", "Terms violation", db_path=TEST_DB)

try:
    bus.purchase_techie_key("techie-revoked", db_path=TEST_DB)
    check("5", False, "Revoked should raise PermissionError")
except PermissionError as e:
    check("5", True, f"Revoked correctly rejected: {e}")


# ============================================================
# Test 6: use_techie_key() marks key as used
# ============================================================

section("Test 6: use_techie_key() marks key as used")
result6 = bus.use_techie_key(key4, "user-ryan-001", db_path=TEST_DB)
check("6a", result6["key_value"] == key4, f"Key should match: {result6}")
check("6b", result6["used_for_user"] == "user-ryan-001", f"User: {result6['used_for_user']}")
check("6c", result6["used_at"] is not None, "Should have timestamp")

# Verify jobs_completed incremented
profile6 = bus.get_techie_profile("techie-001", db_path=TEST_DB)
check("6d", profile6["total_jobs_completed"] == 1, f"Jobs: {profile6['total_jobs_completed']}")


# ============================================================
# Test 7: use_techie_key() fails for already-used key
# ============================================================

section("Test 7: use_techie_key() fails for already-used key")
try:
    bus.use_techie_key(key4, "user-other", db_path=TEST_DB)
    check("7", False, "Already-used key should raise ValueError")
except ValueError as e:
    check("7", True, f"Already-used correctly rejected: {e}")

# Non-existent key
try:
    bus.use_techie_key("TECHIE-NONEXISTENT", "user", db_path=TEST_DB)
    check("7b", False, "Nonexistent key should raise ValueError")
except ValueError:
    check("7b", True, "Nonexistent key correctly raises ValueError")


# ============================================================
# Test 8: revoke_techie() sets standing to revoked
# ============================================================

section("Test 8: revoke_techie() sets standing to revoked")
profile8 = bus.get_techie_profile("techie-revoked", db_path=TEST_DB)
check("8a", profile8["standing"] == "revoked", f"Standing: {profile8['standing']}")
check("8b", profile8["revoked_at"] is not None, "Should have revoked_at")
check("8c", profile8["revocation_reason"] == "Terms violation",
      f"Reason: {profile8['revocation_reason']}")

# Non-existent techie
try:
    bus.revoke_techie("nonexistent", "test", db_path=TEST_DB)
    check("8d", False, "Nonexistent should raise ValueError")
except ValueError:
    check("8d", True, "Nonexistent correctly raises ValueError")


# ============================================================
# Test 9: add_techie_review() updates average rating
# ============================================================

section("Test 9: add_techie_review() updates average rating")

r9a = bus.add_techie_review("techie-001", "reviewer-a", 5, "Excellent work!", db_path=TEST_DB)
check("9a", r9a["rating"] == 5, f"Rating: {r9a}")
check("9b", r9a["new_avg"] == 5.0, f"Avg should be 5.0: {r9a['new_avg']}")
check("9c", r9a["total_reviews"] == 1, f"Count: {r9a['total_reviews']}")

r9d = bus.add_techie_review("techie-001", "reviewer-b", 3, "Decent.", db_path=TEST_DB)
check("9d", r9d["new_avg"] == 4.0, f"Avg should be 4.0: {r9d['new_avg']}")
check("9e", r9d["total_reviews"] == 2, f"Count: {r9d['total_reviews']}")

# Verify in profile
profile9 = bus.get_techie_profile("techie-001", db_path=TEST_DB)
check("9f", profile9["rating_avg"] == 4.0, f"Profile avg: {profile9['rating_avg']}")
check("9g", profile9["rating_count"] == 2, f"Profile count: {profile9['rating_count']}")

# Invalid rating
try:
    bus.add_techie_review("techie-001", "reviewer-c", 6, db_path=TEST_DB)
    check("9h", False, "Rating > 5 should raise ValueError")
except ValueError:
    check("9h", True, "Rating > 5 correctly raises ValueError")

try:
    bus.add_techie_review("techie-001", "reviewer-c", 0, db_path=TEST_DB)
    check("9i", False, "Rating < 1 should raise ValueError")
except ValueError:
    check("9i", True, "Rating < 1 correctly raises ValueError")


# ============================================================
# Test 10: list_techies() filters correctly
# ============================================================

section("Test 10: list_techies() filters correctly")

# Default filter: verified + good standing
verified_good = bus.list_techies(status="verified", standing="good", db_path=TEST_DB)
check("10a", len(verified_good) == 1, f"Should have 1 verified+good techie, got {len(verified_good)}")
check("10b", verified_good[0]["techie_id"] == "techie-001",
      f"Should be techie-001: {verified_good[0]['techie_id']}")

# Filter by pending
pending = bus.list_techies(status="pending", standing="good", db_path=TEST_DB)
check("10c", len(pending) == 1, f"Should have 1 pending techie, got {len(pending)}")
check("10d", pending[0]["techie_id"] == "techie-unverified",
      f"Should be techie-unverified: {pending[0]['techie_id']}")

# Filter by revoked standing
revoked = bus.list_techies(status="verified", standing="revoked", db_path=TEST_DB)
check("10e", len(revoked) == 1, f"Should have 1 revoked techie, got {len(revoked)}")
check("10f", revoked[0]["techie_id"] == "techie-revoked",
      f"Should be techie-revoked: {revoked[0]['techie_id']}")

# No results for impossible filter
none_found = bus.list_techies(status="pending", standing="revoked", db_path=TEST_DB)
check("10g", len(none_found) == 0, f"Should have 0, got {len(none_found)}")


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
