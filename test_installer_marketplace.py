"""
test_installer_marketplace.py - Certified Installer Marketplace backend tests.

Tests:
  1.  installer_signup() creates installer with free permit
  2.  installer_signup() rejects duplicate email
  3.  installer_signup() rejects short password
  4.  installer_login() authenticates valid credentials
  5.  installer_login() rejects wrong password
  6.  installer_get_session() validates session
  7.  installer_logout() invalidates session
  8.  installer_verify_kyc() updates status
  9.  installer_search() finds verified installers by location
  10. installer_search() excludes unverified installers
  11. installer_search() respects distance radius
  12. installer_purchase_permit() issues new permit
  13. installer_activate_permit() marks permit used
  14. installer_activate_permit() rejects double activation
  15. installer_add_review() stores review as hidden
  16. installer_update_profile() updates allowed fields
  17. installer_update_password() changes password
  18. installer_request_password_reset() + reset flow
  19. installer_get_profile() returns public profile
  20. installer_get_permits() returns all permits
  21. _haversine_km() distance calculation

Run:
  python test_installer_marketplace.py
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

TEST_DB = Path(__file__).parent / "test_installer_marketplace.db"

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


# ---------------------------------------------------------------------------
# Init DB
# ---------------------------------------------------------------------------

bus.init_db(db_path=TEST_DB)
print("Database initialized.")


# ---------------------------------------------------------------------------
# 1. Signup
# ---------------------------------------------------------------------------
section("1. installer_signup() creates installer with free permit + guard key")

result = bus.installer_signup(
    full_name="Alice Johnson",
    email="alice@example.com",
    password="securepass123",
    phone="+1-555-0100",
    country="United States",
    service_lat=40.7128,
    service_lon=-74.0060,
    specialties=["Linux", "Docker", "Networking"],
    kyc_document_hash="abc123def456",
    db_path=TEST_DB,
)
check("signup returns installer_id", "installer_id" in result)
check("signup returns email", result.get("email") == "alice@example.com")
check("signup returns free_permit_key", "free_permit_key" in result)
check("signup returns free_guard_key", "free_guard_key" in result)
check("guard key starts with CREWBUS", result["free_guard_key"].startswith("CREWBUS-"))
check("signup kyc_status is pending", result.get("kyc_status") == "pending")

# Verify the guard key payload has 6-month expiry
import base64
_gk = result["free_guard_key"]
_rem = _gk[len("CREWBUS-"):]
_pb64 = _rem[:_rem.rfind("-")]
_payload = json.loads(base64.b64decode(_pb64))
check("guard key has expires field", "expires" in _payload)
check("guard key has installer_grant", _payload.get("installer_grant") is True)
check("guard key has installer_id", _payload.get("installer_id") == result["installer_id"])

# Verify the guard key is actually valid
_ok, _msg = bus.activate_guard(result["free_guard_key"], db_path=TEST_DB)
check("guard key activates successfully", _ok, _msg)

ALICE_ID = result["installer_id"]
ALICE_FREE_PERMIT = result["free_permit_key"]


# ---------------------------------------------------------------------------
# 2. Duplicate email
# ---------------------------------------------------------------------------
section("2. installer_signup() rejects duplicate email")

try:
    bus.installer_signup("Alice Dup", "alice@example.com", "password123",
                         db_path=TEST_DB)
    check("duplicate email", False, "should have raised ValueError")
except ValueError as e:
    check("duplicate email raises ValueError", "already exists" in str(e))


# ---------------------------------------------------------------------------
# 3. Short password
# ---------------------------------------------------------------------------
section("3. installer_signup() rejects short password")

try:
    bus.installer_signup("Bob Short", "bob@example.com", "short",
                         db_path=TEST_DB)
    check("short password", False, "should have raised ValueError")
except ValueError as e:
    check("short password raises ValueError", "8 characters" in str(e))


# ---------------------------------------------------------------------------
# 4. Login success
# ---------------------------------------------------------------------------
section("4. installer_login() authenticates valid credentials")

result = bus.installer_login("alice@example.com", "securepass123",
                             db_path=TEST_DB)
check("login returns session_id", "session_id" in result)
check("login returns installer profile", "installer" in result)
check("login profile has full_name", result["installer"]["full_name"] == "Alice Johnson")
check("login profile excludes password_hash", "password_hash" not in result["installer"])
SESSION_ID = result["session_id"]


# ---------------------------------------------------------------------------
# 5. Login wrong password
# ---------------------------------------------------------------------------
section("5. installer_login() rejects wrong password")

try:
    bus.installer_login("alice@example.com", "wrongpassword",
                        db_path=TEST_DB)
    check("wrong password", False, "should have raised ValueError")
except ValueError as e:
    check("wrong password raises ValueError", "Invalid" in str(e))


# ---------------------------------------------------------------------------
# 6. Session validation
# ---------------------------------------------------------------------------
section("6. installer_get_session() validates session")

profile = bus.installer_get_session(SESSION_ID, db_path=TEST_DB)
check("session returns profile", profile is not None)
check("session has full_name", profile.get("full_name") == "Alice Johnson")
check("session excludes password_hash", "password_hash" not in profile)

invalid = bus.installer_get_session("invalid_session_id", db_path=TEST_DB)
check("invalid session returns None", invalid is None)


# ---------------------------------------------------------------------------
# 7. Logout
# ---------------------------------------------------------------------------
section("7. installer_logout() invalidates session")

# Login again for a fresh session
result = bus.installer_login("alice@example.com", "securepass123",
                             db_path=TEST_DB)
temp_session = result["session_id"]
check("logout returns True", bus.installer_logout(temp_session, db_path=TEST_DB))
check("session invalid after logout",
      bus.installer_get_session(temp_session, db_path=TEST_DB) is None)


# ---------------------------------------------------------------------------
# 8. KYC verification
# ---------------------------------------------------------------------------
section("8. installer_verify_kyc() updates status")

result = bus.installer_verify_kyc(ALICE_ID, db_path=TEST_DB)
check("verify returns verified status", result.get("kyc_status") == "verified")

profile = bus.installer_get_profile(ALICE_ID, db_path=TEST_DB)
check("profile shows verified", profile.get("kyc_status") == "verified")


# ---------------------------------------------------------------------------
# 9. Search finds verified installers
# ---------------------------------------------------------------------------
section("9. installer_search() finds verified installers by location")

results = bus.installer_search(40.7, -74.0, db_path=TEST_DB)
check("search returns 1 result", len(results) == 1)
check("result is Alice", results[0]["full_name"] == "Alice Johnson")
check("result has distance", "distance_km" in results[0])
check("distance is reasonable", results[0]["distance_km"] < 5)
check("result has specialties list", isinstance(results[0]["specialties"], list))


# ---------------------------------------------------------------------------
# 10. Search excludes unverified
# ---------------------------------------------------------------------------
section("10. installer_search() excludes unverified installers")

bus.installer_signup("Bob Pending", "bob@example.com", "password123",
                     service_lat=40.72, service_lon=-73.99,
                     country="United States", db_path=TEST_DB)
results = bus.installer_search(40.7, -74.0, db_path=TEST_DB)
check("only verified returned", len(results) == 1)
check("unverified Bob excluded", results[0]["full_name"] == "Alice Johnson")


# ---------------------------------------------------------------------------
# 11. Search respects distance
# ---------------------------------------------------------------------------
section("11. installer_search() respects distance radius")

# Sign up a verified installer far away (London)
r = bus.installer_signup("Charlie London", "charlie@example.com", "password123",
                         service_lat=51.5074, service_lon=-0.1278,
                         country="UK", db_path=TEST_DB)
bus.installer_verify_kyc(r["installer_id"], db_path=TEST_DB)

# Search near NYC - should only find Alice
results = bus.installer_search(40.7, -74.0, radius_km=50, db_path=TEST_DB)
check("far installer excluded", len(results) == 1)
check("only local Alice found", results[0]["full_name"] == "Alice Johnson")

# Search near London - should find Charlie
results = bus.installer_search(51.5, -0.1, radius_km=50, db_path=TEST_DB)
check("London search finds Charlie", len(results) == 1)
check("Charlie found", results[0]["full_name"] == "Charlie London")


# ---------------------------------------------------------------------------
# 12. Purchase permit
# ---------------------------------------------------------------------------
section("12. installer_purchase_permit() issues new permit")

result = bus.installer_purchase_permit(ALICE_ID,
                                       stripe_payment_id="stripe_test_123",
                                       db_path=TEST_DB)
check("purchase returns permit_key", "permit_key" in result)
check("purchase returns permit_id", "permit_id" in result)
check("purchase is not free", result["is_free"] is False)
PAID_PERMIT = result["permit_key"]


# ---------------------------------------------------------------------------
# 13. Activate permit
# ---------------------------------------------------------------------------
section("13. installer_activate_permit() marks permit used")

result = bus.installer_activate_permit(ALICE_FREE_PERMIT, "client-xyz",
                                       db_path=TEST_DB)
check("activate returns permit_key", result["permit_key"] == ALICE_FREE_PERMIT)
check("activate records client", result["activated_for_client"] == "client-xyz")
check("activate has timestamp", "activated_at" in result)


# ---------------------------------------------------------------------------
# 14. Double activation rejected
# ---------------------------------------------------------------------------
section("14. installer_activate_permit() rejects double activation")

try:
    bus.installer_activate_permit(ALICE_FREE_PERMIT, "another-client",
                                  db_path=TEST_DB)
    check("double activation", False, "should have raised ValueError")
except ValueError as e:
    check("double activation raises ValueError", "already been activated" in str(e))


# ---------------------------------------------------------------------------
# 15. Review stored as hidden
# ---------------------------------------------------------------------------
section("15. installer_add_review() stores review as hidden")

result = bus.installer_add_review(
    ALICE_ID, "Client One", "client1@example.com", 5,
    review_text="Excellent setup!", job_date="2026-02-15",
    db_path=TEST_DB,
)
check("review returns review_id", "review_id" in result)
check("review rating recorded", result["rating"] == 5)
check("review is hidden", result["visible"] is False)


# ---------------------------------------------------------------------------
# 16. Update profile
# ---------------------------------------------------------------------------
section("16. installer_update_profile() updates allowed fields")

result = bus.installer_update_profile(ALICE_ID, {
    "phone": "+1-555-9999",
    "specialties": ["AI", "ML", "Hardware"],
}, db_path=TEST_DB)
check("phone updated", result["phone"] == "+1-555-9999")
check("password_hash excluded", "password_hash" not in result)

# Disallowed field
try:
    bus.installer_update_profile(ALICE_ID, {"email": "hack@evil.com"},
                                 db_path=TEST_DB)
    check("disallowed field", False, "should have raised ValueError")
except ValueError as e:
    check("disallowed field rejected", "No valid fields" in str(e))


# ---------------------------------------------------------------------------
# 17. Change password
# ---------------------------------------------------------------------------
section("17. installer_update_password() changes password")

bus.installer_update_password(ALICE_ID, "securepass123", "newpass12345",
                              db_path=TEST_DB)
# Old password should fail
try:
    bus.installer_login("alice@example.com", "securepass123", db_path=TEST_DB)
    check("old password fails", False, "should have raised ValueError")
except ValueError:
    check("old password correctly rejected", True)

# New password should work
result = bus.installer_login("alice@example.com", "newpass12345", db_path=TEST_DB)
check("new password works", "session_id" in result)


# ---------------------------------------------------------------------------
# 18. Password reset flow
# ---------------------------------------------------------------------------
section("18. installer_request_password_reset() + reset flow")

token = bus.installer_request_password_reset("alice@example.com", db_path=TEST_DB)
check("reset token generated", token is not None and len(token) > 0)

# Nonexistent email returns None (no enumeration)
no_token = bus.installer_request_password_reset("nobody@example.com", db_path=TEST_DB)
check("unknown email returns None", no_token is None)

# Reset password
bus.installer_reset_password(token, "resetpass999", db_path=TEST_DB)
result = bus.installer_login("alice@example.com", "resetpass999", db_path=TEST_DB)
check("login works after reset", "session_id" in result)

# Token is single-use
try:
    bus.installer_reset_password(token, "anotherpass", db_path=TEST_DB)
    check("token reuse", False, "should have raised ValueError")
except ValueError:
    check("token is single-use", True)


# ---------------------------------------------------------------------------
# 19. Get public profile
# ---------------------------------------------------------------------------
section("19. installer_get_profile() returns public profile")

profile = bus.installer_get_profile(ALICE_ID, db_path=TEST_DB)
check("profile has full_name", profile["full_name"] == "Alice Johnson")
check("profile has country", profile["country"] == "United States")
check("profile specialties is list", isinstance(profile["specialties"], list))
check("profile excludes password_hash", "password_hash" not in profile)

# Nonexistent
none_profile = bus.installer_get_profile("nonexistent-id", db_path=TEST_DB)
check("nonexistent returns None", none_profile is None)


# ---------------------------------------------------------------------------
# 20. Get permits
# ---------------------------------------------------------------------------
section("20. installer_get_permits() returns all permits")

permits = bus.installer_get_permits(ALICE_ID, db_path=TEST_DB)
check("Alice has 2 permits", len(permits) == 2)
free_permits = [p for p in permits if p["is_free"]]
paid_permits = [p for p in permits if not p["is_free"]]
check("1 free permit", len(free_permits) == 1)
check("1 paid permit", len(paid_permits) == 1)


# ---------------------------------------------------------------------------
# 21. Haversine distance
# ---------------------------------------------------------------------------
section("21. _haversine_km() distance calculation")

# NYC to London ~ 5570 km
dist = bus._haversine_km(40.7128, -74.0060, 51.5074, -0.1278)
check("NYC-London ~5570km", 5500 < dist < 5600, f"got {dist:.0f}km")

# Same point = 0
dist = bus._haversine_km(0, 0, 0, 0)
check("same point = 0km", dist == 0.0)

# Equator quarter = ~10000km
dist = bus._haversine_km(0, 0, 0, 90)
check("equator quarter ~10000km", 9900 < dist < 10100, f"got {dist:.0f}km")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print(f"\n{'='*60}")
print(f"  RESULTS: {passed} passed, {failed} failed, {passed+failed} total")
print(f"{'='*60}")

# Cleanup
if TEST_DB.exists():
    os.remove(str(TEST_DB))

sys.exit(1 if failed else 0)
