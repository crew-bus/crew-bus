"""
Feedback collector for Crew Bus — monitors App Store reviews + GitHub issues.

Polls public sources, auto-categorizes items, deduplicates via the
feedback_items DB table, and escalates severity 4-5 to Crew Boss via DM.

App Store App ID: 6759645608 (Crew Bus)
GitHub repo: crew-bus/crew-bus (public, no auth needed)
"""

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

import bus

DEFAULT_DB = None

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get_json(url: str, headers: dict = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    req.add_header("User-Agent", "CrewBus/1.0 FeedbackCollector")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}"}
    except Exception as e:
        return {"_error": str(e)}


# ---------------------------------------------------------------------------
# Auto-categorization
# ---------------------------------------------------------------------------

def _auto_categorize(title: str, body: str, rating: int = None) -> Tuple[str, int]:
    """Classify feedback and assign severity 1-5.

    Returns (category, severity).

    Severity scale:
      1 = Praise (great/love/amazing)
      2 = Feature request (wish/want/suggestion)
      3 = Minor bug / confusion
      4 = Serious bug / crash / broken flow
      5 = Critical (crash, data loss, 1-2 star + serious complaint)
    """
    text = f"{title} {body}".lower()

    # 1-2 star review is always high severity
    if rating is not None and rating <= 2:
        category = "bug" if any(w in text for w in ["crash", "broke", "error", "doesn't work", "not working"]) else "ux"
        severity = 5 if rating == 1 else 4
        return category, severity

    # Crash / critical keywords
    if any(w in text for w in ["crash", "crashes", "crashing", "data loss", "lost my", "corrupt"]):
        return "bug", 5

    # Broken / serious bugs
    if any(w in text for w in ["broken", "doesn't work", "doesn't open", "error", "exception",
                                "can't login", "cannot login", "not working", "stopped working",
                                "fails", "failed"]):
        return "bug", 4

    # Minor bugs / confusion
    if any(w in text for w in ["bug", "issue", "problem", "glitch", "weird", "wrong", "incorrect"]):
        return "bug", 3

    # Feature requests
    if any(w in text for w in ["wish", "would be nice", "feature request", "suggestion",
                                "please add", "could you add", "should have", "need", "want"]):
        return "feature", 2

    # Praise
    if any(w in text for w in ["love", "amazing", "awesome", "great", "perfect", "excellent",
                                "fantastic", "brilliant", "best app"]):
        return "praise", 1

    # 3 star = neutral → moderate
    if rating is not None and rating == 3:
        return "ux", 3

    # High star rating → praise
    if rating is not None and rating >= 4:
        return "praise", 1

    # Default: moderate UX feedback
    return "ux", 3


# ---------------------------------------------------------------------------
# Escalation
# ---------------------------------------------------------------------------

def _escalate_to_crew_boss(agent_id: int, item: dict, db_path: Optional[Path] = None):
    """DM Crew Boss about a severity 4-5 feedback item."""
    # Find Crew Boss (right_hand type)
    conn = bus.get_conn(db_path)
    boss = conn.execute(
        "SELECT id FROM agents WHERE agent_type='right_hand' LIMIT 1"
    ).fetchone()
    conn.close()
    if not boss:
        return

    msg = (
        f"🚨 High-severity feedback (severity {item['severity']}/5)\n\n"
        f"**Source:** {item['source'].upper()}\n"
        f"**Category:** {item['category']}\n"
        f"**Summary:** {item['summary']}\n"
    )
    if item.get("author"):
        msg += f"**Author:** {item['author']}\n"
    if item.get("url"):
        msg += f"**Link:** {item['url']}\n"
    if item.get("body"):
        body_preview = item["body"][:200] + ("…" if len(item["body"]) > 200 else "")
        msg += f"\n{body_preview}"

    bus.send_message(
        sender_id=agent_id,
        recipient_id=boss["id"],
        content=msg,
        message_type="alert",
        priority="high",
        db_path=db_path,
    )
    bus.flag_feedback_item(item["id"], db_path)


# ---------------------------------------------------------------------------
# App Store RSS poller
# ---------------------------------------------------------------------------

APPSTORE_RSS = (
    "https://itunes.apple.com/us/rss/customerreviews/"
    "id=6759645608/sortBy=mostRecent/json"
)


def poll_appstore_reviews(agent_id: int = None, db_path: Optional[Path] = None) -> int:
    """Fetch App Store reviews RSS and insert new items into feedback_items.

    Returns count of new items inserted.
    """
    data = _get_json(APPSTORE_RSS)
    if data.get("_error"):
        return 0

    entries = data.get("feed", {}).get("entry", [])
    if not entries:
        return 0

    # First entry is the app metadata (not a review) — skip if no rating
    new_count = 0
    for entry in entries:
        # Extract fields from iTunes RSS JSON
        review_id = entry.get("id", {}).get("label", "")
        title = entry.get("title", {}).get("label", "")
        body = entry.get("content", {}).get("label", "") or entry.get("summary", {}).get("label", "")
        author = entry.get("author", {}).get("name", {}).get("label", "")
        rating_str = entry.get("im:rating", {}).get("label", "")
        rating = int(rating_str) if rating_str.isdigit() else None
        version = entry.get("im:version", {}).get("label", "")

        if not review_id or not title:
            continue

        # Build URL to App Store listing (no direct review URL in RSS)
        url = "https://apps.apple.com/us/app/crew-bus/id6759645608"

        category, severity = _auto_categorize(title, body, rating=rating)

        summary = f"[{rating}★] {title}" if rating else title

        item_id = bus.add_feedback_item(
            source="appstore",
            source_id=review_id,
            category=category,
            severity=severity,
            summary=summary,
            body=body,
            author=author,
            url=url,
            db_path=db_path,
        )

        if item_id is not None:
            new_count += 1
            # Escalate high-severity to Crew Boss
            if severity >= 4 and agent_id:
                item = {
                    "id": item_id,
                    "source": "appstore",
                    "category": category,
                    "severity": severity,
                    "summary": summary,
                    "body": body,
                    "author": author,
                    "url": url,
                }
                _escalate_to_crew_boss(agent_id, item, db_path)

    return new_count


# ---------------------------------------------------------------------------
# GitHub Issues poller
# ---------------------------------------------------------------------------

GITHUB_ISSUES_URL = (
    "https://api.github.com/repos/crew-bus/crew-bus/issues"
    "?state=open&sort=created&direction=desc&per_page=50"
)


def poll_github_issues(agent_id: int = None, db_path: Optional[Path] = None) -> int:
    """Fetch open GitHub issues and insert new items into feedback_items.

    Returns count of new items inserted.
    """
    issues = _get_json(GITHUB_ISSUES_URL, headers={"Accept": "application/vnd.github.v3+json"})
    if isinstance(issues, dict) and issues.get("_error"):
        return 0
    if not isinstance(issues, list):
        return 0

    new_count = 0
    for issue in issues:
        # Skip pull requests (they appear in issues API)
        if issue.get("pull_request"):
            continue

        issue_number = str(issue.get("number", ""))
        title = issue.get("title", "")
        body = issue.get("body", "") or ""
        author = issue.get("user", {}).get("login", "")
        url = issue.get("html_url", "")
        labels = [lb.get("name", "").lower() for lb in issue.get("labels", [])]

        if not issue_number or not title:
            continue

        # Use labels to influence categorization
        label_text = " ".join(labels)
        if "bug" in label_text:
            category, severity = "bug", 4
        elif "enhancement" in label_text or "feature" in label_text:
            category, severity = "feature", 2
        elif "critical" in label_text or "urgent" in label_text:
            category, severity = "bug", 5
        else:
            category, severity = _auto_categorize(title, body)

        summary = f"#{issue_number}: {title}"

        item_id = bus.add_feedback_item(
            source="github",
            source_id=issue_number,
            category=category,
            severity=severity,
            summary=summary,
            body=body[:1000],  # Cap at 1000 chars
            author=author,
            url=url,
            db_path=db_path,
        )

        if item_id is not None:
            new_count += 1
            if severity >= 4 and agent_id:
                item = {
                    "id": item_id,
                    "source": "github",
                    "category": category,
                    "severity": severity,
                    "summary": summary,
                    "body": body[:500],
                    "author": author,
                    "url": url,
                }
                _escalate_to_crew_boss(agent_id, item, db_path)

    return new_count


# ---------------------------------------------------------------------------
# Run all sources
# ---------------------------------------------------------------------------

def poll_all(agent_id: int = None, db_path: Optional[Path] = None) -> dict:
    """Poll all feedback sources. Returns counts of new items per source."""
    appstore_new = poll_appstore_reviews(agent_id=agent_id, db_path=db_path)
    github_new = poll_github_issues(agent_id=agent_id, db_path=db_path)
    return {
        "appstore": appstore_new,
        "github": github_new,
        "total_new": appstore_new + github_new,
    }
