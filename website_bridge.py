"""
Website Bridge for Crew Bus agents.

Lets agents create and manage content on the Crew Bus public website
(static files in public/). Manages blog posts, changelogs, and page updates.

Content is written as HTML files under public/blog/ and public/changelog/.
The website is static — agents write files, and the site serves them directly.

Flow:
  Agent drafts content → social_drafts table (platform='website') →
  human approves → website_bridge writes the HTML file to public/.
"""

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import bus

# ---------------------------------------------------------------------------
# Directory setup
# ---------------------------------------------------------------------------

def _public_dir(db_path: Optional[Path] = None) -> Path:
    """Find the public/ directory."""
    # Try relative to this file
    here = Path(__file__).parent / "public"
    if here.is_dir():
        return here
    # Try common locations
    for p in [Path("public"), Path.home() / "crew-bus" / "public"]:
        if p.is_dir():
            return p
    raise FileNotFoundError("Cannot find public/ directory")


def _ensure_dirs(db_path: Optional[Path] = None):
    """Ensure blog/ and changelog/ directories exist under public/."""
    pub = _public_dir(db_path)
    (pub / "blog").mkdir(exist_ok=True)
    (pub / "changelog").mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Credential / config helpers
# ---------------------------------------------------------------------------

def setup_website(site_url: str = "https://crew-bus.dev",
                  db_path: Optional[Path] = None) -> dict:
    """Configure the website bridge."""
    bus.set_config("site_url", site_url, db_path)
    _ensure_dirs(db_path)
    return {"ok": True, "message": f"Website bridge configured for {site_url}"}


def is_configured(db_path: Optional[Path] = None) -> bool:
    """Check if website bridge is set up."""
    try:
        _public_dir(db_path)
        return True
    except FileNotFoundError:
        return False


# ---------------------------------------------------------------------------
# Blog post management
# ---------------------------------------------------------------------------

_BLOG_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Crew Bus</title>
<link rel="stylesheet" href="/css/site.css">
<style>
.blog-post {{ max-width: 720px; margin: 2rem auto; padding: 0 1rem; }}
.blog-post h1 {{ font-size: 2rem; margin-bottom: 0.5rem; }}
.blog-meta {{ color: #8b949e; font-size: 0.9rem; margin-bottom: 2rem; }}
.blog-body {{ line-height: 1.7; }}
.blog-body p {{ margin-bottom: 1.2rem; }}
.blog-body a {{ color: #58a6ff; }}
</style>
</head>
<body>
<article class="blog-post">
<h1>{title}</h1>
<div class="blog-meta">{date} · {author}</div>
<div class="blog-body">
{body}
</div>
</article>
</body>
</html>
"""


def _slugify(title: str) -> str:
    """Convert title to URL-friendly slug."""
    slug = title.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s-]+', '-', slug)
    return slug[:80].strip('-')


def create_blog_post(title: str, body_html: str, author: str = "Crew Bus",
                     db_path: Optional[Path] = None) -> dict:
    """Create a blog post as an HTML file in public/blog/.

    body_html: The post content as HTML (paragraphs, links, etc.)
    Returns the file path and URL.
    """
    _ensure_dirs(db_path)
    pub = _public_dir(db_path)

    slug = _slugify(title)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{date_str}-{slug}.html"
    filepath = pub / "blog" / filename

    html = _BLOG_TEMPLATE.format(
        title=title,
        date=date_str,
        author=author,
        body=body_html,
    )
    filepath.write_text(html, encoding="utf-8")

    site_url = bus.get_config("site_url", "https://crew-bus.dev", db_path)
    post_url = f"{site_url}/blog/{filename}"

    # Audit log
    try:
        conn = bus.get_conn(db_path)
        conn.execute(
            "INSERT INTO audit_log (event_type, agent_id, details) VALUES (?, ?, ?)",
            ("blog_published", 1, json.dumps({"title": title[:100], "url": post_url})),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    return {"ok": True, "path": str(filepath), "url": post_url, "slug": slug}


def list_blog_posts(db_path: Optional[Path] = None) -> list:
    """List all blog posts in public/blog/."""
    try:
        pub = _public_dir(db_path)
        blog_dir = pub / "blog"
        if not blog_dir.exists():
            return []
        posts = sorted(blog_dir.glob("*.html"), reverse=True)
        return [{"filename": p.name, "path": str(p)} for p in posts]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Changelog management
# ---------------------------------------------------------------------------

_CHANGELOG_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Changelog — Crew Bus</title>
<link rel="stylesheet" href="/css/site.css">
<style>
.changelog {{ max-width: 720px; margin: 2rem auto; padding: 0 1rem; }}
.changelog h1 {{ font-size: 2rem; margin-bottom: 2rem; }}
.cl-entry {{ margin-bottom: 2rem; padding-bottom: 1rem; border-bottom: 1px solid #30363d; }}
.cl-version {{ font-size: 1.2rem; font-weight: 700; color: #f0883e; }}
.cl-date {{ color: #8b949e; font-size: 0.85rem; margin-left: 0.5rem; }}
.cl-body {{ margin-top: 0.5rem; line-height: 1.6; }}
.cl-body li {{ margin-bottom: 0.3rem; }}
</style>
</head>
<body>
<div class="changelog">
<h1>Changelog</h1>
{entries}
</div>
</body>
</html>
"""

_CHANGELOG_ENTRY = """<div class="cl-entry">
<span class="cl-version">{version}</span>
<span class="cl-date">{date}</span>
<div class="cl-body">{body}</div>
</div>
"""


def add_changelog_entry(version: str, body_html: str,
                        db_path: Optional[Path] = None) -> dict:
    """Add an entry to the changelog page.

    version: e.g. "v1.0.0"
    body_html: HTML content (typically a <ul> of changes)
    """
    _ensure_dirs(db_path)
    pub = _public_dir(db_path)
    changelog_path = pub / "changelog" / "index.html"

    date_str = datetime.now().strftime("%Y-%m-%d")
    new_entry = _CHANGELOG_ENTRY.format(
        version=version,
        date=date_str,
        body=body_html,
    )

    if changelog_path.exists():
        # Insert new entry after <h1>Changelog</h1>
        existing = changelog_path.read_text(encoding="utf-8")
        marker = "<h1>Changelog</h1>"
        if marker in existing:
            parts = existing.split(marker, 1)
            updated = parts[0] + marker + "\n" + new_entry + parts[1]
            changelog_path.write_text(updated, encoding="utf-8")
        else:
            # Fallback: write fresh
            html = _CHANGELOG_TEMPLATE.format(entries=new_entry)
            changelog_path.write_text(html, encoding="utf-8")
    else:
        html = _CHANGELOG_TEMPLATE.format(entries=new_entry)
        changelog_path.write_text(html, encoding="utf-8")

    return {"ok": True, "version": version, "path": str(changelog_path)}


# ---------------------------------------------------------------------------
# Draft → Publish flow (integrates with social_drafts system)
# ---------------------------------------------------------------------------

def post_approved_draft(draft_id: int, db_path: Optional[Path] = None) -> dict:
    """Publish an approved website draft. Creates blog post. Marks 'posted'."""
    conn = bus.get_conn(db_path)
    draft = conn.execute(
        "SELECT * FROM social_drafts WHERE id=? AND platform IN ('website', 'other')",
        (draft_id,),
    ).fetchone()
    conn.close()

    if not draft:
        return {"ok": False, "error": f"Draft {draft_id} not found or not a website draft"}
    if draft["status"] != "approved":
        return {"ok": False, "error": f"Draft {draft_id} status is '{draft['status']}', must be 'approved'"}

    result = create_blog_post(
        title=draft["title"] or "Crew Bus Update",
        body_html=draft["body"],
        db_path=db_path,
    )

    if result.get("ok"):
        bus.update_draft_status(draft_id, "posted", db_path)
        result["draft_id"] = draft_id
    return result


def post_all_approved(db_path: Optional[Path] = None) -> dict:
    """Publish ALL approved website drafts. Returns summary."""
    drafts = bus.get_social_drafts(platform="website", status="approved", db_path=db_path)
    if not drafts:
        return {"ok": True, "message": "No approved website drafts to publish", "posted": 0}

    results = []
    for d in drafts:
        r = post_approved_draft(d["id"], db_path)
        results.append(r)

    posted = sum(1 for r in results if r.get("ok"))
    return {"ok": True, "posted": posted, "total": len(drafts), "results": results}


# ---------------------------------------------------------------------------
# Status / health check
# ---------------------------------------------------------------------------

def status(db_path: Optional[Path] = None) -> dict:
    """Check website bridge status."""
    configured = is_configured(db_path)
    blog_count = len(list_blog_posts(db_path)) if configured else 0

    drafts = []
    if configured:
        drafts = bus.get_social_drafts(platform="website", db_path=db_path)
    draft_counts = {}
    for d in drafts:
        s = d.get("status", "unknown")
        draft_counts[s] = draft_counts.get(s, 0) + 1

    return {
        "configured": configured,
        "blog_posts": blog_count,
        "draft_counts": draft_counts,
        "total_drafts": len(drafts),
    }
