"""
test_web_bridge.py - Web Search Bridge tests.

Tests:
  1.  search_web() requires Guardian activation
  2.  search_web() rejects empty query
  3.  search_web() returns correct result structure
  4.  read_url() requires Guardian activation
  5.  read_url() rejects empty URL
  6.  read_url() rejects non-http URLs
  7.  read_url() blocks localhost/internal IPs
  8.  is_configured() returns True when Guardian activated
  9.  is_configured() returns False when not activated
  10. status() returns expected fields
  11. _strip_html() removes script/style/tags
  12. _parse_ddg_results() handles empty HTML
  13. _extract_ddg_url() extracts from DDG redirect

Run:
  pytest test_web_bridge.py -v
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import bus
import web_bridge

# ---------------------------------------------------------------------------
# Test DB
# ---------------------------------------------------------------------------
TEST_DB = Path(__file__).parent / "test_web_bridge.db"

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
# Tests
# ---------------------------------------------------------------------------

print("\n🔍 Web Bridge Tests\n")

# 1. search_web requires Guardian activation
result = web_bridge.search_web("test query", db_path=TEST_DB)
check("search_web() requires Guardian activation",
      not result["ok"] and "activation" in result["error"].lower())

# 2. read_url requires Guardian activation
result = web_bridge.read_url("https://example.com", db_path=TEST_DB)
check("read_url() requires Guardian activation",
      not result["ok"] and "activation" in result["error"].lower())

# 3. is_configured returns False without activation
check("is_configured() is False without activation",
      not web_bridge.is_configured(db_path=TEST_DB))

# Activate Guardian for remaining tests
conn = bus.get_conn(TEST_DB)
conn.execute(
    "INSERT INTO guard_activation (activation_key, activated_at, key_fingerprint) "
    "VALUES ('TEST-KEY', '2026-01-01T00:00:00Z', 'testfp')"
)
conn.commit()
conn.close()

# 4. is_configured returns True with activation
check("is_configured() is True with activation",
      web_bridge.is_configured(db_path=TEST_DB))

# 5. status() returns expected fields
st = web_bridge.status(db_path=TEST_DB)
check("status() has configured field",
      "configured" in st and "guard_activated" in st and "web_search_enabled" in st)

# 6. search_web rejects empty query
result = web_bridge.search_web("", db_path=TEST_DB)
check("search_web() rejects empty query",
      not result["ok"] and "required" in result["error"].lower())

# 7. search_web rejects whitespace-only query
result = web_bridge.search_web("   ", db_path=TEST_DB)
check("search_web() rejects whitespace query",
      not result["ok"])

# 8. read_url rejects empty URL
result = web_bridge.read_url("", db_path=TEST_DB)
check("read_url() rejects empty URL",
      not result["ok"] and "required" in result["error"].lower())

# 9. read_url rejects non-http URLs
result = web_bridge.read_url("ftp://example.com", db_path=TEST_DB)
check("read_url() rejects ftp:// URL",
      not result["ok"] and "http" in result["error"].lower())

# 10. read_url blocks localhost
result = web_bridge.read_url("http://localhost:8080/test", db_path=TEST_DB)
check("read_url() blocks localhost",
      not result["ok"] and "internal" in result["error"].lower())

# 11. read_url blocks 127.0.0.1
result = web_bridge.read_url("http://127.0.0.1/test", db_path=TEST_DB)
check("read_url() blocks 127.0.0.1",
      not result["ok"] and "internal" in result["error"].lower())

# 12. read_url blocks 192.168.x.x
result = web_bridge.read_url("http://192.168.1.1/admin", db_path=TEST_DB)
check("read_url() blocks 192.168.x.x",
      not result["ok"] and "internal" in result["error"].lower())

# 13. read_url blocks 10.x.x.x
result = web_bridge.read_url("http://10.0.0.1/", db_path=TEST_DB)
check("read_url() blocks 10.x.x.x",
      not result["ok"] and "internal" in result["error"].lower())

# 14. _strip_html removes script tags
cleaned = web_bridge._strip_html("<p>Hello</p><script>alert('xss')</script><p>World</p>")
check("_strip_html() removes script tags",
      "alert" not in cleaned and "Hello" in cleaned and "World" in cleaned)

# 15. _strip_html removes style tags
cleaned = web_bridge._strip_html("<style>.foo{color:red}</style><p>Text</p>")
check("_strip_html() removes style tags",
      "color" not in cleaned and "Text" in cleaned)

# 16. _parse_ddg_results handles empty HTML
results = web_bridge._parse_ddg_results("", 5)
check("_parse_ddg_results() handles empty HTML",
      results == [])

# 17. _extract_ddg_url extracts from redirect
url = web_bridge._extract_ddg_url("//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com&more=stuff")
check("_extract_ddg_url() extracts from DDG redirect",
      url == "https://example.com")

# 18. _extract_ddg_url handles direct URL
url = web_bridge._extract_ddg_url("https://example.com/page")
check("_extract_ddg_url() handles direct URL",
      url == "https://example.com/page")

# 19. _extract_ddg_url handles empty
url = web_bridge._extract_ddg_url("")
check("_extract_ddg_url() handles empty string",
      url == "")

# 20. Disabled web search returns error
bus.set_config("web_search_enabled", "false", TEST_DB)
result = web_bridge.search_web("test", db_path=TEST_DB)
check("search_web() respects disabled config",
      not result["ok"] and "disabled" in result["error"].lower())
bus.set_config("web_search_enabled", "true", TEST_DB)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"\n{'='*50}")
print(f"Web Bridge: {passed} passed, {failed} failed")

# Cleanup
if TEST_DB.exists():
    os.remove(str(TEST_DB))

if failed > 0:
    sys.exit(1)
