"""
Twitter/X API Bridge for Crew Bus agents.

Lets agents post tweets, upload media (profile pic, banner),
follow accounts, and like tweets — all through the X API v2.

Credentials stored in crew_config table (never in code):
  - twitter_api_key
  - twitter_api_secret
  - twitter_access_token
  - twitter_access_secret
  - twitter_bearer_token

Flow:
  Agent drafts content → social_drafts table → human approves →
  twitter_bridge.post_tweet() sends it live.
"""

import base64
import hashlib
import hmac
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
    "twitter_api_key",
    "twitter_api_secret",
    "twitter_access_token",
    "twitter_access_secret",
)


def _get_creds(db_path: Optional[Path] = None) -> dict:
    """Load Twitter creds from crew_config table."""
    creds = {}
    for k in _REQUIRED_KEYS:
        val = bus.get_config(k, "", db_path)
        if not val:
            raise ValueError(f"Missing Twitter credential: {k}. Run setup_twitter_keys() first.")
        creds[k] = val
    # Bearer token optional (for v2 read endpoints)
    creds["twitter_bearer_token"] = bus.get_config("twitter_bearer_token", "", db_path)
    return creds


def setup_twitter_keys(api_key: str, api_secret: str,
                       access_token: str, access_secret: str,
                       bearer_token: str = "",
                       db_path: Optional[Path] = None) -> dict:
    """Store Twitter API credentials in the DB (one-time setup)."""
    bus.set_config("twitter_api_key", api_key, db_path)
    bus.set_config("twitter_api_secret", api_secret, db_path)
    bus.set_config("twitter_access_token", access_token, db_path)
    bus.set_config("twitter_access_secret", access_secret, db_path)
    if bearer_token:
        bus.set_config("twitter_bearer_token", bearer_token, db_path)
    return {"ok": True, "message": "Twitter keys saved to crew_config"}


def is_configured(db_path: Optional[Path] = None) -> bool:
    """Check if Twitter API keys are set up."""
    try:
        _get_creds(db_path)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# OAuth 1.0a signature (required for tweets, media upload, profile updates)
# ---------------------------------------------------------------------------

def _percent_encode(s: str) -> str:
    return urllib.parse.quote(str(s), safe="")


def _oauth_signature(method: str, url: str, params: dict, creds: dict) -> str:
    """Generate OAuth 1.0a signature."""
    sorted_params = "&".join(
        f"{_percent_encode(k)}={_percent_encode(v)}"
        for k, v in sorted(params.items())
    )
    base_string = f"{method.upper()}&{_percent_encode(url)}&{_percent_encode(sorted_params)}"
    signing_key = f"{_percent_encode(creds['twitter_api_secret'])}&{_percent_encode(creds['twitter_access_secret'])}"
    sig = hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1)
    return base64.b64encode(sig.digest()).decode()


def _oauth_header(method: str, url: str, creds: dict, extra_params: dict = None) -> str:
    """Build the Authorization: OAuth header."""
    import uuid as _uuid
    oauth_params = {
        "oauth_consumer_key": creds["twitter_api_key"],
        "oauth_nonce": _uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": creds["twitter_access_token"],
        "oauth_version": "1.0",
    }
    all_params = {**oauth_params, **(extra_params or {})}
    oauth_params["oauth_signature"] = _oauth_signature(method, url, all_params, creds)

    header_parts = ", ".join(
        f'{_percent_encode(k)}="{_percent_encode(v)}"'
        for k, v in sorted(oauth_params.items())
    )
    return f"OAuth {header_parts}"


def _api_request(method: str, url: str, creds: dict,
                 json_body: dict = None, data: bytes = None,
                 extra_headers: dict = None,
                 form_params: dict = None) -> dict:
    """Make an authenticated request to the Twitter API."""
    # For form-encoded params, include in signature
    oauth_extra = form_params or {}
    auth_header = _oauth_header(method, url, creds, oauth_extra)

    headers = {
        "Authorization": auth_header,
        "User-Agent": "CrewBus/1.0",
    }
    if extra_headers:
        headers.update(extra_headers)

    body = None
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif form_params is not None:
        body = urllib.parse.urlencode(form_params).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif data is not None:
        body = data

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {"ok": True}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:500]
        return {"ok": False, "error": f"HTTP {e.code}", "detail": err_body}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Tweet operations
# ---------------------------------------------------------------------------

def post_tweet(text: str, reply_to: str = None,
               media_ids: list = None,
               db_path: Optional[Path] = None) -> dict:
    """Post a tweet to X. Returns tweet ID on success."""
    creds = _get_creds(db_path)
    url = "https://api.x.com/2/tweets"

    payload = {"text": text}
    if reply_to:
        payload["reply"] = {"in_reply_to_tweet_id": reply_to}
    if media_ids:
        payload["media"] = {"media_ids": media_ids}

    result = _api_request("POST", url, creds, json_body=payload)

    # Log to audit
    if result.get("data", {}).get("id"):
        tweet_id = result["data"]["id"]
        try:
            conn = bus.get_conn(db_path)
            conn.execute(
                "INSERT INTO audit_log (event_type, agent_id, details) VALUES (?, ?, ?)",
                ("tweet_posted", 1, json.dumps({"tweet_id": tweet_id, "text": text[:100]})),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass
        return {"ok": True, "tweet_id": tweet_id, "text": text}

    return result


def post_thread(tweets: list, db_path: Optional[Path] = None) -> dict:
    """Post a thread (list of tweet texts). Each replies to the previous."""
    results = []
    reply_to = None
    for i, text in enumerate(tweets):
        result = post_tweet(text, reply_to=reply_to, db_path=db_path)
        results.append(result)
        if result.get("ok") and result.get("tweet_id"):
            reply_to = result["tweet_id"]
        else:
            return {"ok": False, "error": f"Thread failed at tweet {i+1}", "results": results}
    return {"ok": True, "thread_length": len(tweets), "results": results}


def delete_tweet(tweet_id: str, db_path: Optional[Path] = None) -> dict:
    """Delete a tweet by ID."""
    creds = _get_creds(db_path)
    url = f"https://api.x.com/2/tweets/{tweet_id}"
    return _api_request("DELETE", url, creds)


# ---------------------------------------------------------------------------
# Media upload (for images — profile pic, banner, tweet images)
# ---------------------------------------------------------------------------

def upload_media(file_path: str, db_path: Optional[Path] = None) -> dict:
    """Upload an image to Twitter and return media_id.

    Uses the v1.1 media/upload endpoint (chunked not needed for <5MB images).
    """
    creds = _get_creds(db_path)
    url = "https://upload.twitter.com/1.1/media/upload.json"

    img_path = Path(file_path)
    if not img_path.exists():
        return {"ok": False, "error": f"File not found: {file_path}"}

    img_data = img_path.read_bytes()
    media_b64 = base64.b64encode(img_data).decode("utf-8")

    result = _api_request("POST", url, creds, form_params={
        "media_data": media_b64,
    })

    if result.get("media_id_string"):
        return {"ok": True, "media_id": result["media_id_string"]}
    return result


# ---------------------------------------------------------------------------
# Profile management
# ---------------------------------------------------------------------------

def update_profile(name: str = None, description: str = None,
                   url: str = None, location: str = None,
                   db_path: Optional[Path] = None) -> dict:
    """Update the X profile (display name, bio, website, location)."""
    creds = _get_creds(db_path)
    api_url = "https://api.x.com/1.1/account/update_profile.json"

    params = {}
    if name is not None:
        params["name"] = name
    if description is not None:
        params["description"] = description
    if url is not None:
        params["url"] = url
    if location is not None:
        params["location"] = location

    if not params:
        return {"ok": False, "error": "No fields to update"}

    return _api_request("POST", api_url, creds, form_params=params)


def update_profile_image(file_path: str, db_path: Optional[Path] = None) -> dict:
    """Update the X profile picture."""
    creds = _get_creds(db_path)
    url = "https://api.x.com/1.1/account/update_profile_image.json"

    img_data = Path(file_path).read_bytes()
    img_b64 = base64.b64encode(img_data).decode("utf-8")

    return _api_request("POST", url, creds, form_params={
        "image": img_b64,
    })


def update_profile_banner(file_path: str, db_path: Optional[Path] = None) -> dict:
    """Update the X profile banner/header image."""
    creds = _get_creds(db_path)
    url = "https://api.x.com/1.1/account/update_profile_banner.json"

    img_data = Path(file_path).read_bytes()
    img_b64 = base64.b64encode(img_data).decode("utf-8")

    return _api_request("POST", url, creds, form_params={
        "banner": img_b64,
    })


# ---------------------------------------------------------------------------
# Follow / unfollow / like
# ---------------------------------------------------------------------------

def get_my_user_id(db_path: Optional[Path] = None) -> str:
    """Get the authenticated user's Twitter ID."""
    cached = bus.get_config("twitter_user_id", "", db_path)
    if cached:
        return cached

    creds = _get_creds(db_path)
    url = "https://api.x.com/2/users/me"
    result = _api_request("GET", url, creds)
    if result.get("data", {}).get("id"):
        uid = result["data"]["id"]
        bus.set_config("twitter_user_id", uid, db_path)
        return uid
    raise ValueError(f"Failed to get user ID: {result}")


def follow_user(target_username: str, db_path: Optional[Path] = None) -> dict:
    """Follow a user by their @username."""
    creds = _get_creds(db_path)
    my_id = get_my_user_id(db_path)

    # First lookup the target user ID
    lookup_url = f"https://api.x.com/2/users/by/username/{target_username}"
    lookup = _api_request("GET", lookup_url, creds)
    target_id = lookup.get("data", {}).get("id")
    if not target_id:
        return {"ok": False, "error": f"User @{target_username} not found"}

    # Follow
    url = f"https://api.x.com/2/users/{my_id}/following"
    result = _api_request("POST", url, creds, json_body={"target_user_id": target_id})

    if result.get("data", {}).get("following"):
        return {"ok": True, "followed": target_username}
    return result


def follow_users(usernames: list, db_path: Optional[Path] = None) -> dict:
    """Follow multiple users. Returns summary."""
    results = {"followed": [], "failed": [], "total": len(usernames)}
    for username in usernames:
        username = username.lstrip("@")
        r = follow_user(username, db_path)
        if r.get("ok"):
            results["followed"].append(username)
        else:
            results["failed"].append({"username": username, "error": r.get("error", "unknown")})
        time.sleep(1)  # Rate limit courtesy
    results["ok"] = True
    return results


def like_tweet(tweet_id: str, db_path: Optional[Path] = None) -> dict:
    """Like a tweet by ID."""
    creds = _get_creds(db_path)
    my_id = get_my_user_id(db_path)
    url = f"https://api.x.com/2/users/{my_id}/likes"
    return _api_request("POST", url, creds, json_body={"tweet_id": tweet_id})


def retweet(tweet_id: str, db_path: Optional[Path] = None) -> dict:
    """Retweet a tweet by ID."""
    creds = _get_creds(db_path)
    my_id = get_my_user_id(db_path)
    url = f"https://api.x.com/2/users/{my_id}/retweets"
    return _api_request("POST", url, creds, json_body={"tweet_id": tweet_id})


# ---------------------------------------------------------------------------
# Draft → Post flow (integrates with social_drafts system)
# ---------------------------------------------------------------------------

def post_approved_draft(draft_id: int, db_path: Optional[Path] = None) -> dict:
    """Post an approved social draft to Twitter. Marks it 'posted' on success."""
    conn = bus.get_conn(db_path)
    draft = conn.execute(
        "SELECT * FROM social_drafts WHERE id=? AND platform='twitter'",
        (draft_id,),
    ).fetchone()
    conn.close()

    if not draft:
        return {"ok": False, "error": f"Draft {draft_id} not found or not a Twitter draft"}
    if draft["status"] != "approved":
        return {"ok": False, "error": f"Draft {draft_id} status is '{draft['status']}', must be 'approved'"}

    # Post the tweet
    result = post_tweet(draft["body"], db_path=db_path)

    if result.get("ok"):
        # Mark as posted
        bus.update_draft_status(draft_id, "posted", db_path)
        result["draft_id"] = draft_id
    return result


def post_all_approved(db_path: Optional[Path] = None) -> dict:
    """Post ALL approved Twitter drafts. Returns summary."""
    drafts = bus.get_social_drafts(platform="twitter", status="approved", db_path=db_path)
    if not drafts:
        return {"ok": True, "message": "No approved Twitter drafts to post", "posted": 0}

    results = []
    for d in drafts:
        r = post_approved_draft(d["id"], db_path)
        results.append(r)
        time.sleep(2)  # Respect rate limits

    posted = sum(1 for r in results if r.get("ok"))
    return {"ok": True, "posted": posted, "total": len(drafts), "results": results}


# ---------------------------------------------------------------------------
# Convenience: draft + auto-approve + post in one call
# ---------------------------------------------------------------------------

def quick_tweet(text: str, agent_id: int = 1, db_path: Optional[Path] = None) -> dict:
    """Create a draft, auto-approve it, and post immediately.

    Use this for urgent posts. For normal flow, use draft → review → approve → post.
    """
    draft = bus.create_social_draft(agent_id, "twitter", text, db_path=db_path)
    if not draft.get("ok"):
        return draft
    bus.update_draft_status(draft["draft_id"], "approved", db_path)
    return post_approved_draft(draft["draft_id"], db_path)


# ---------------------------------------------------------------------------
# Status / health check
# ---------------------------------------------------------------------------

def status(db_path: Optional[Path] = None) -> dict:
    """Check Twitter bridge status."""
    configured = is_configured(db_path)
    drafts = bus.get_social_drafts(platform="twitter", db_path=db_path) if configured else []
    draft_counts = {}
    for d in drafts:
        s = d.get("status", "unknown")
        draft_counts[s] = draft_counts.get(s, 0) + 1

    return {
        "configured": configured,
        "draft_counts": draft_counts,
        "total_drafts": len(drafts),
    }
