"""
Web Search Bridge for Crew Bus agents.

Gives agents internet access — web search via DuckDuckGo HTML scraping
+ URL content fetching.  Zero external dependencies — stdlib only.

Gated behind Guardian activation ($29 key).

Flow:
  Guardian or agent decides search is needed →
  guardian_action "web_search" or "web_read_url" →
  web_bridge.search_web(query) / web_bridge.read_url(url) →
  results returned as context for the agent.
"""

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import bus

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_USER_AGENT = "CrewBus/1.0 (Personal AI Crew; +https://crew-bus.dev)"
_SEARCH_TIMEOUT = 10  # seconds
_READ_TIMEOUT = 15    # seconds
_DEFAULT_MAX_RESULTS = 5
_DEFAULT_MAX_CHARS = 8000

# Internal / private IP prefixes that must never be fetched
_BLOCKED_HOSTS = (
    "localhost", "127.0.0.1", "0.0.0.0", "::1",
    "10.", "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
    "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
    "172.30.", "172.31.", "192.168.",
)


# ---------------------------------------------------------------------------
# Bridge interface (matches twitter_bridge / reddit_bridge pattern)
# ---------------------------------------------------------------------------

def setup_keys(db_path: Optional[Path] = None) -> dict:
    """Enable web search.  No API keys needed (DuckDuckGo HTML)."""
    bus.set_config("web_search_enabled", "true", db_path)
    return {"ok": True, "message": "Web search enabled (DuckDuckGo — no API key needed)"}


def is_configured(db_path: Optional[Path] = None) -> bool:
    """Web search is configured when Guardian is activated."""
    return bus.is_guard_activated(db_path)


def status(db_path: Optional[Path] = None) -> dict:
    """Return web bridge status."""
    activated = bus.is_guard_activated(db_path)
    enabled = bus.get_config("web_search_enabled", "true", db_path) == "true"
    return {
        "configured": activated and enabled,
        "guard_activated": activated,
        "web_search_enabled": enabled,
    }


# ---------------------------------------------------------------------------
# Core: web search
# ---------------------------------------------------------------------------

def search_web(query: str, max_results: int = _DEFAULT_MAX_RESULTS,
               db_path: Optional[Path] = None) -> dict:
    """Search the web via DuckDuckGo HTML (no API key needed).

    Returns {"ok": True, "query": ..., "results": [...], "count": N}
    Each result: {"title": ..., "url": ..., "snippet": ...}
    """
    if not bus.is_guard_activated(db_path):
        return {"ok": False, "error": "Guardian activation required. Visit crew-bus.dev/activate"}

    if not query or not query.strip():
        return {"ok": False, "error": "Search query is required"}

    enabled = bus.get_config("web_search_enabled", "true", db_path)
    if enabled != "true":
        return {"ok": False, "error": "Web search is disabled in crew_config"}

    try:
        encoded = urllib.parse.urlencode({"q": query.strip()})
        url = f"https://html.duckduckgo.com/html/?{encoded}"

        req = urllib.request.Request(url, headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html",
            "Accept-Language": "en-US,en;q=0.9",
        })

        with urllib.request.urlopen(req, timeout=_SEARCH_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")

        results = _parse_ddg_results(raw, max_results)

        # Audit log
        try:
            conn = bus.get_conn(db_path)
            conn.execute(
                "INSERT INTO audit_log (event_type, details) VALUES (?, ?)",
                ("web_search", json.dumps({"query": query.strip(), "count": len(results)})),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

        return {
            "ok": True,
            "query": query.strip(),
            "results": results,
            "count": len(results),
        }

    except urllib.error.URLError as e:
        return {"ok": False, "error": f"Search failed: {e.reason}"}
    except Exception as e:
        return {"ok": False, "error": f"Search error: {e}"}


def _parse_ddg_results(html_text: str, max_results: int) -> list:
    """Parse DuckDuckGo HTML search results using regex (stdlib only)."""
    results = []

    # DuckDuckGo HTML wraps each result in <div class="result ...">
    # Links are <a class="result__a" href="...">title</a>
    # Snippets are <a class="result__snippet" ...>text</a>

    # Find all result blocks
    result_blocks = re.findall(
        r'<div[^>]*class="[^"]*result[^"]*results_links[^"]*"[^>]*>(.*?)</div>\s*</div>',
        html_text, re.DOTALL,
    )

    if not result_blocks:
        # Fallback: try finding links directly
        result_blocks = re.findall(
            r'<div[^>]*class="[^"]*result\b[^"]*"[^>]*>(.*?)</div>',
            html_text, re.DOTALL,
        )

    for block in result_blocks[:max_results * 2]:  # scan extra to fill quota
        if len(results) >= max_results:
            break

        # Extract link and title
        link_match = re.search(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            block, re.DOTALL,
        )
        if not link_match:
            continue

        raw_url = link_match.group(1)
        raw_title = link_match.group(2)

        # DuckDuckGo wraps URLs in a redirect — extract actual URL
        actual_url = _extract_ddg_url(raw_url)
        if not actual_url:
            continue

        # Clean title (strip HTML tags)
        title = re.sub(r'<[^>]+>', '', raw_title).strip()
        title = html.unescape(title)

        # Extract snippet
        snippet = ""
        snippet_match = re.search(
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            block, re.DOTALL,
        )
        if snippet_match:
            snippet = re.sub(r'<[^>]+>', '', snippet_match.group(1)).strip()
            snippet = html.unescape(snippet)

        if title and actual_url:
            results.append({
                "title": title[:200],
                "url": actual_url[:500],
                "snippet": snippet[:400],
            })

    return results


def _extract_ddg_url(raw_url: str) -> str:
    """Extract the actual URL from DuckDuckGo's redirect wrapper."""
    if not raw_url:
        return ""
    # DDG redirect format: //duckduckgo.com/l/?uddg=ENCODED_URL&...
    if "uddg=" in raw_url:
        match = re.search(r'uddg=([^&]+)', raw_url)
        if match:
            return urllib.parse.unquote(match.group(1))
    # Direct URL
    if raw_url.startswith("http"):
        return raw_url
    if raw_url.startswith("//"):
        return "https:" + raw_url
    return ""


# ---------------------------------------------------------------------------
# Core: URL reading
# ---------------------------------------------------------------------------

def read_url(url: str, max_chars: int = _DEFAULT_MAX_CHARS,
             db_path: Optional[Path] = None) -> dict:
    """Fetch and read a URL, returning cleaned text content.

    Returns {"ok": True, "url": ..., "content": ..., "content_length": N, "truncated": bool}
    """
    if not bus.is_guard_activated(db_path):
        return {"ok": False, "error": "Guardian activation required. Visit crew-bus.dev/activate"}

    if not url or not url.strip():
        return {"ok": False, "error": "URL is required"}

    url = url.strip()

    # Validate URL scheme
    if not url.startswith("http://") and not url.startswith("https://"):
        return {"ok": False, "error": "URL must start with http:// or https://"}

    # Block internal/private IPs
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    for blocked in _BLOCKED_HOSTS:
        if host == blocked or host.startswith(blocked):
            return {"ok": False, "error": "Cannot fetch internal/private URLs"}

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,text/plain,application/json",
            "Accept-Language": "en-US,en;q=0.9",
        })

        with urllib.request.urlopen(req, timeout=_READ_TIMEOUT) as resp:
            # Read up to 1MB to avoid memory issues
            raw_bytes = resp.read(1_000_000)
            content_type = resp.headers.get("Content-Type", "")

        # Decode
        encoding = "utf-8"
        if "charset=" in content_type:
            charset_match = re.search(r'charset=([^\s;]+)', content_type)
            if charset_match:
                encoding = charset_match.group(1)
        text = raw_bytes.decode(encoding, errors="replace")

        # Strip HTML tags
        text = _strip_html(text)

        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        original_len = len(text)
        truncated = original_len > max_chars
        if truncated:
            text = text[:max_chars]

        # Audit log
        try:
            conn = bus.get_conn(db_path)
            conn.execute(
                "INSERT INTO audit_log (event_type, details) VALUES (?, ?)",
                ("web_read_url", json.dumps({"url": url, "content_length": original_len})),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

        return {
            "ok": True,
            "url": url,
            "content": text,
            "content_length": original_len,
            "truncated": truncated,
        }

    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"URL error: {e.reason}"}
    except Exception as e:
        return {"ok": False, "error": f"Read error: {e}"}


def _strip_html(text: str) -> str:
    """Remove HTML tags, scripts, styles, and decode entities."""
    # Remove script and style blocks entirely
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML comments
    text = re.sub(r'<!--.*?-->', ' ', text, flags=re.DOTALL)
    # Remove all remaining tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Decode HTML entities
    text = html.unescape(text)
    return text
