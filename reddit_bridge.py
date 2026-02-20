"""
Reddit API Bridge for Crew Bus agents.

Lets agents post to subreddits, reply to threads, and manage
the Crew Bus Reddit presence — all through Reddit's OAuth2 API.

Credentials stored in crew_config table (never in code):
  - reddit_client_id
  - reddit_client_secret
  - reddit_username
  - reddit_password

Flow:
  Agent drafts content → social_drafts table → human approves →
  reddit_bridge.post_approved_draft() sends it live.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

import bus

# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = (
    "reddit_client_id",
    "reddit_client_secret",
    "reddit_username",
    "reddit_password",
)

_access_token = None
_token_expires = 0


def _get_creds(db_path: Optional[Path] = None) -> dict:
    """Load Reddit creds from crew_config table."""
    creds = {}
    for k in _REQUIRED_KEYS:
        val = bus.get_config(k, "", db_path)
        if not val:
            raise ValueError(f"Missing Reddit credential: {k}. Run setup_reddit_keys() first.")
        creds[k] = val
    return creds


def setup_reddit_keys(client_id: str, client_secret: str,
                      username: str, password: str,
                      db_path: Optional[Path] = None) -> dict:
    """Store Reddit API credentials in the DB (one-time setup)."""
    bus.set_config("reddit_client_id", client_id, db_path)
    bus.set_config("reddit_client_secret", client_secret, db_path)
    bus.set_config("reddit_username", username, db_path)
    bus.set_config("reddit_password", password, db_path)
    return {"ok": True, "message": "Reddit keys saved to crew_config"}


def is_configured(db_path: Optional[Path] = None) -> bool:
    """Check if Reddit API keys are set up."""
    try:
        _get_creds(db_path)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# OAuth2 token (script-type app, password grant)
# ---------------------------------------------------------------------------

def _get_token(db_path: Optional[Path] = None) -> str:
    """Get a valid OAuth2 access token, refreshing if needed."""
    global _access_token, _token_expires
    if _access_token and time.time() < _token_expires - 60:
        return _access_token

    creds = _get_creds(db_path)
    url = "https://www.reddit.com/api/v1/access_token"

    data = urllib.parse.urlencode({
        "grant_type": "password",
        "username": creds["reddit_username"],
        "password": creds["reddit_password"],
    }).encode("utf-8")

    # Basic auth with client_id:client_secret
    import base64
    auth = base64.b64encode(
        f"{creds['reddit_client_id']}:{creds['reddit_client_secret']}".encode()
    ).decode()

    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Basic {auth}")
    req.add_header("User-Agent", "CrewBus/1.0 (by /u/" + creds["reddit_username"] + ")")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if "access_token" in result:
            _access_token = result["access_token"]
            _token_expires = time.time() + result.get("expires_in", 3600)
            return _access_token
        raise ValueError(f"Token error: {result}")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:300]
        raise ValueError(f"Reddit auth failed: HTTP {e.code} — {err}")


def _api_request(method: str, endpoint: str, data: dict = None,
                 db_path: Optional[Path] = None) -> dict:
    """Make an authenticated request to the Reddit API."""
    token = _get_token(db_path)
    creds = _get_creds(db_path)
    url = f"https://oauth.reddit.com{endpoint}"

    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")

    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"bearer {token}")
    req.add_header("User-Agent", "CrewBus/1.0 (by /u/" + creds["reddit_username"] + ")")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {"ok": True}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:500]
        return {"ok": False, "error": f"HTTP {e.code}", "detail": err}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Post operations
# ---------------------------------------------------------------------------

def submit_post(subreddit: str, title: str, body: str = "",
                url: str = None, flair_id: str = None,
                db_path: Optional[Path] = None) -> dict:
    """Submit a post to a subreddit. Text post if body given, link post if url given."""
    data = {
        "sr": subreddit,
        "title": title,
        "kind": "link" if url else "self",
        "resubmit": "true",
    }
    if url:
        data["url"] = url
    else:
        data["text"] = body
    if flair_id:
        data["flair_id"] = flair_id

    result = _api_request("POST", "/api/submit", data, db_path)

    # Audit log
    post_url = ""
    if result.get("json", {}).get("data", {}).get("url"):
        post_url = result["json"]["data"]["url"]
    elif result.get("json", {}).get("data", {}).get("name"):
        post_url = result["json"]["data"]["name"]

    if post_url:
        try:
            conn = bus.get_conn(db_path)
            conn.execute(
                "INSERT INTO audit_log (event_type, agent_id, details) VALUES (?, ?, ?)",
                ("reddit_posted", 1, json.dumps({"subreddit": subreddit, "title": title[:100], "url": post_url})),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass
        return {"ok": True, "url": post_url, "subreddit": subreddit, "title": title}

    # Check for errors
    errors = result.get("json", {}).get("errors", [])
    if errors:
        return {"ok": False, "error": str(errors)}
    return result


def reply_to_post(thing_id: str, body: str,
                  db_path: Optional[Path] = None) -> dict:
    """Reply to a post or comment. thing_id is the fullname (t3_ for post, t1_ for comment)."""
    data = {
        "thing_id": thing_id,
        "text": body,
    }
    return _api_request("POST", "/api/comment", data, db_path)


def delete_post(thing_id: str, db_path: Optional[Path] = None) -> dict:
    """Delete a post or comment by fullname."""
    return _api_request("POST", "/api/del", {"id": thing_id}, db_path)


# ---------------------------------------------------------------------------
# Draft → Post flow (integrates with social_drafts system)
# ---------------------------------------------------------------------------

def post_approved_draft(draft_id: int, db_path: Optional[Path] = None) -> dict:
    """Post an approved social draft to Reddit. Marks it 'posted' on success."""
    conn = bus.get_conn(db_path)
    draft = conn.execute(
        "SELECT * FROM social_drafts WHERE id=? AND platform='reddit'",
        (draft_id,),
    ).fetchone()
    conn.close()

    if not draft:
        return {"ok": False, "error": f"Draft {draft_id} not found or not a Reddit draft"}
    if draft["status"] != "approved":
        return {"ok": False, "error": f"Draft {draft_id} status is '{draft['status']}', must be 'approved'"}

    # target = subreddit name (e.g. "r/opensource" or "opensource")
    subreddit = (draft.get("target") or "").strip()
    if not subreddit:
        return {"ok": False, "error": "Draft has no target subreddit set"}
    subreddit = subreddit.lstrip("r/").lstrip("/")

    result = submit_post(subreddit, draft["title"], draft["body"], db_path=db_path)

    if result.get("ok"):
        bus.update_draft_status(draft_id, "posted", db_path)
        result["draft_id"] = draft_id
    return result


def post_all_approved(db_path: Optional[Path] = None) -> dict:
    """Post ALL approved Reddit drafts. Returns summary."""
    drafts = bus.get_social_drafts(platform="reddit", status="approved", db_path=db_path)
    if not drafts:
        return {"ok": True, "message": "No approved Reddit drafts to post", "posted": 0}

    results = []
    for d in drafts:
        r = post_approved_draft(d["id"], db_path)
        results.append(r)
        time.sleep(3)  # Reddit rate limits are stricter

    posted = sum(1 for r in results if r.get("ok"))
    return {"ok": True, "posted": posted, "total": len(drafts), "results": results}


# ---------------------------------------------------------------------------
# Status / health check
# ---------------------------------------------------------------------------

def status(db_path: Optional[Path] = None) -> dict:
    """Check Reddit bridge status."""
    configured = is_configured(db_path)
    drafts = bus.get_social_drafts(platform="reddit", db_path=db_path) if configured else []
    draft_counts = {}
    for d in drafts:
        s = d.get("status", "unknown")
        draft_counts[s] = draft_counts.get(s, 0) + 1

    return {
        "configured": configured,
        "draft_counts": draft_counts,
        "total_drafts": len(drafts),
    }
