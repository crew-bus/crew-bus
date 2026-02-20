"""
Discord Webhook Bridge for Crew Bus agents.

Posts messages to Discord channels via webhooks — zero bot hosting needed.
Each channel gets its own webhook URL stored in crew_config.

Credentials stored in crew_config table (never in code):
  - discord_webhook_general   (main announcements channel)
  - discord_webhook_updates   (release/changelog channel)
  - discord_webhook_community (community chat channel)

Flow:
  Agent drafts content → social_drafts table → human approves →
  discord_bridge.post_approved_draft() sends it live.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
import time
from pathlib import Path
from typing import Optional

import bus

# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------

# At minimum, one webhook must be configured
_DEFAULT_WEBHOOK_KEY = "discord_webhook_general"

_WEBHOOK_KEYS = (
    "discord_webhook_general",
    "discord_webhook_updates",
    "discord_webhook_community",
)


def setup_discord_webhook(channel: str, webhook_url: str,
                          db_path: Optional[Path] = None) -> dict:
    """Store a Discord webhook URL for a channel.

    channel: 'general', 'updates', or 'community'
    webhook_url: The full Discord webhook URL
    """
    key = f"discord_webhook_{channel}"
    if key not in _WEBHOOK_KEYS:
        return {"ok": False, "error": f"Unknown channel: {channel}. Use: general, updates, community"}
    bus.set_config(key, webhook_url, db_path)
    return {"ok": True, "message": f"Discord webhook for #{channel} saved"}


def is_configured(db_path: Optional[Path] = None) -> bool:
    """Check if at least one Discord webhook is set up."""
    for k in _WEBHOOK_KEYS:
        if bus.get_config(k, "", db_path):
            return True
    return False


def _get_webhook(channel: str = "general",
                 db_path: Optional[Path] = None) -> str:
    """Get webhook URL for a channel."""
    key = f"discord_webhook_{channel}"
    url = bus.get_config(key, "", db_path)
    if not url:
        raise ValueError(f"No Discord webhook for #{channel}. Run setup_discord_webhook() first.")
    return url


# ---------------------------------------------------------------------------
# Posting
# ---------------------------------------------------------------------------

def _send_webhook(webhook_url: str, content: str = None,
                  embeds: list = None, username: str = "Crew Bus",
                  avatar_url: str = None) -> dict:
    """Send a message via Discord webhook."""
    payload = {"username": username}
    if content:
        payload["content"] = content[:2000]  # Discord limit
    if embeds:
        payload["embeds"] = embeds[:10]  # Max 10 embeds
    if avatar_url:
        payload["avatar_url"] = avatar_url

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(webhook_url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "CrewBus/1.0")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status == 204:
                return {"ok": True}
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {"ok": True}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:500]
        return {"ok": False, "error": f"HTTP {e.code}", "detail": err}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def post_message(content: str, channel: str = "general",
                 db_path: Optional[Path] = None) -> dict:
    """Post a simple text message to a Discord channel."""
    webhook_url = _get_webhook(channel, db_path)
    result = _send_webhook(webhook_url, content=content)

    if result.get("ok"):
        try:
            conn = bus.get_conn(db_path)
            conn.execute(
                "INSERT INTO audit_log (event_type, agent_id, details) VALUES (?, ?, ?)",
                ("discord_posted", 1, json.dumps({"channel": channel, "text": content[:100]})),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass
    return result


def post_embed(title: str, description: str, color: int = 0x3498db,
               url: str = None, channel: str = "general",
               fields: list = None,
               db_path: Optional[Path] = None) -> dict:
    """Post a rich embed to a Discord channel.

    fields: list of {"name": str, "value": str, "inline": bool}
    """
    webhook_url = _get_webhook(channel, db_path)
    embed = {
        "title": title,
        "description": description[:4096],
        "color": color,
    }
    if url:
        embed["url"] = url
    if fields:
        embed["fields"] = fields[:25]

    result = _send_webhook(webhook_url, embeds=[embed])

    if result.get("ok"):
        try:
            conn = bus.get_conn(db_path)
            conn.execute(
                "INSERT INTO audit_log (event_type, agent_id, details) VALUES (?, ?, ?)",
                ("discord_posted", 1, json.dumps({"channel": channel, "title": title[:100]})),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass
    return result


def post_announcement(title: str, body: str, link: str = None,
                      db_path: Optional[Path] = None) -> dict:
    """Post a formatted announcement to the general channel.

    Convenience method for launch announcements, releases, etc.
    """
    return post_embed(
        title=title,
        description=body,
        color=0xf0883e,  # Crew Bus orange
        url=link,
        channel="general",
        db_path=db_path,
    )


# ---------------------------------------------------------------------------
# Draft → Post flow (integrates with social_drafts system)
# ---------------------------------------------------------------------------

def post_approved_draft(draft_id: int, db_path: Optional[Path] = None) -> dict:
    """Post an approved social draft to Discord. Marks it 'posted' on success."""
    conn = bus.get_conn(db_path)
    draft = conn.execute(
        "SELECT * FROM social_drafts WHERE id=? AND platform='discord'",
        (draft_id,),
    ).fetchone()
    conn.close()

    if not draft:
        return {"ok": False, "error": f"Draft {draft_id} not found or not a Discord draft"}
    if draft["status"] != "approved":
        return {"ok": False, "error": f"Draft {draft_id} status is '{draft['status']}', must be 'approved'"}

    # target = channel name (default: general)
    channel = (draft.get("target") or "general").strip()

    # If there's a title, post as embed. Otherwise plain text.
    if draft.get("title"):
        result = post_embed(
            title=draft["title"],
            description=draft["body"],
            channel=channel,
            db_path=db_path,
        )
    else:
        result = post_message(draft["body"], channel=channel, db_path=db_path)

    if result.get("ok"):
        bus.update_draft_status(draft_id, "posted", db_path)
        result["draft_id"] = draft_id
    return result


def post_all_approved(db_path: Optional[Path] = None) -> dict:
    """Post ALL approved Discord drafts. Returns summary."""
    drafts = bus.get_social_drafts(platform="discord", status="approved", db_path=db_path)
    if not drafts:
        return {"ok": True, "message": "No approved Discord drafts to post", "posted": 0}

    results = []
    for d in drafts:
        r = post_approved_draft(d["id"], db_path)
        results.append(r)
        time.sleep(1)

    posted = sum(1 for r in results if r.get("ok"))
    return {"ok": True, "posted": posted, "total": len(drafts), "results": results}


# ---------------------------------------------------------------------------
# Status / health check
# ---------------------------------------------------------------------------

def status(db_path: Optional[Path] = None) -> dict:
    """Check Discord bridge status."""
    configured = is_configured(db_path)
    channels = {}
    for k in _WEBHOOK_KEYS:
        ch = k.replace("discord_webhook_", "")
        channels[ch] = bool(bus.get_config(k, "", db_path))

    drafts = bus.get_social_drafts(platform="discord", db_path=db_path) if configured else []
    draft_counts = {}
    for d in drafts:
        s = d.get("status", "unknown")
        draft_counts[s] = draft_counts.get(s, 0) + 1

    return {
        "configured": configured,
        "channels": channels,
        "draft_counts": draft_counts,
        "total_drafts": len(drafts),
    }
