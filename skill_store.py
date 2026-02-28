"""
Skill Store — Guardian's intelligent skill discovery and installation engine.

The Guardian is the expert at finding perfect skills.  Not a dumb catalog —
an intelligent matcher that analyzes what an agent needs and recommends
the best skill, vets it, and assigns it.

Gated behind Guardian activation ($29 key).

Sources:
  1. Local catalog (skills/catalog.json) — curated, always available
  2. GitHub raw URLs — community skills, fetched on demand

Flow:
  Agent needs capability → Guardian analyzes needs →
  recommend_skills() finds matches → human approves →
  install_skill() downloads + vet_skill() + add_skill_to_agent()
"""

import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import bus

# ---------------------------------------------------------------------------
# Catalog cache
# ---------------------------------------------------------------------------
_CATALOG_CACHE: list = []
_CATALOG_LOADED: bool = False


def load_catalog(db_path: Optional[Path] = None) -> list:
    """Load the curated skill catalog from skills/catalog.json.

    Caches in memory after first load. Returns empty list if file not found.
    """
    global _CATALOG_CACHE, _CATALOG_LOADED
    if _CATALOG_LOADED:
        return _CATALOG_CACHE

    catalog_path = Path(__file__).parent / "skills" / "catalog.json"
    try:
        with open(catalog_path, "r", encoding="utf-8") as f:
            _CATALOG_CACHE = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _CATALOG_CACHE = []

    _CATALOG_LOADED = True
    return _CATALOG_CACHE


def reload_catalog() -> list:
    """Force-reload the catalog from disk (clears cache)."""
    global _CATALOG_LOADED
    _CATALOG_LOADED = False
    return load_catalog()


# ---------------------------------------------------------------------------
# Search and recommendation
# ---------------------------------------------------------------------------

def search_catalog(query: str, category: str = "", agent_type: str = "",
                   db_path: Optional[Path] = None) -> list:
    """Search the skill catalog with relevance scoring.

    Returns top 10 results sorted by relevance score.
    """
    if not bus.is_guard_activated(db_path):
        return []

    if not query or not query.strip():
        return []

    catalog = load_catalog(db_path)
    query_lower = query.strip().lower()
    query_words = set(query_lower.split())

    scored = []
    for skill in catalog:
        score = 0
        name = skill.get("skill_name", "").lower()
        desc = skill.get("description", "").lower()
        tags = [t.lower() for t in skill.get("tags", [])]
        s_category = skill.get("category", "").lower()
        compat = [t.lower() for t in skill.get("compatible_agent_types", [])]

        # Exact name match
        if query_lower in name:
            score += 15

        # Word-level matching in name
        for word in query_words:
            if word in name:
                score += 10

        # Description matching
        for word in query_words:
            if word in desc:
                score += 5

        # Tag matching (best signal)
        for word in query_words:
            if word in tags:
                score += 8

        # Category filter/boost
        if category:
            if s_category == category.lower():
                score += 5
            else:
                score -= 2  # mild penalty for wrong category when filter is set

        # Agent type compatibility boost
        if agent_type and agent_type.lower() in compat:
            score += 3

        if score > 0:
            result = {
                "skill_name": skill.get("skill_name", ""),
                "description": skill.get("description", ""),
                "category": skill.get("category", ""),
                "tags": skill.get("tags", []),
                "compatible_agent_types": skill.get("compatible_agent_types", []),
                "author": skill.get("author", "crew-bus"),
                "version": skill.get("version", "1.0"),
                "source": "catalog",
                "relevance_score": score,
            }
            scored.append(result)

    # Sort by relevance, take top 10
    scored.sort(key=lambda x: x["relevance_score"], reverse=True)
    return scored[:10]


def recommend_skills(agent_id: int, task_description: str = "",
                     db_path: Optional[Path] = None) -> dict:
    """Analyze what an agent needs and recommend the best skills.

    The Guardian uses this to intelligently match skills to agents.
    Excludes skills the agent already has.
    """
    if not bus.is_guard_activated(db_path):
        return {"ok": False, "error": "Guardian activation required"}

    # Get agent info
    conn = bus.get_conn(db_path)
    agent = conn.execute(
        "SELECT id, name, agent_type, description FROM agents WHERE id = ?",
        (agent_id,),
    ).fetchone()
    conn.close()

    if not agent:
        return {"ok": False, "error": f"Agent id={agent_id} not found"}

    # Get existing skills to exclude
    existing = bus.get_agent_skills(agent_id, db_path=db_path)
    existing_names = {s["skill_name"] for s in existing}

    # Build search terms from agent context
    search_parts = []
    if task_description:
        search_parts.append(task_description)
    if agent["description"]:
        # Extract keywords from description (first 100 chars)
        search_parts.append(agent["description"][:100])
    if agent["agent_type"]:
        search_parts.append(agent["agent_type"])

    search_query = " ".join(search_parts)

    # Search catalog
    results = search_catalog(
        search_query,
        agent_type=agent["agent_type"] or "",
        db_path=db_path,
    )

    # Filter out existing skills
    recommendations = [
        r for r in results
        if r["skill_name"] not in existing_names
    ]

    return {
        "ok": True,
        "agent_name": agent["name"],
        "agent_type": agent["agent_type"],
        "recommendations": recommendations[:5],
        "existing_skills": [s["skill_name"] for s in existing],
    }


# ---------------------------------------------------------------------------
# Fetch from external sources
# ---------------------------------------------------------------------------

def fetch_skill_from_url(url: str,
                         db_path: Optional[Path] = None) -> dict:
    """Download a skill config from a trusted HTTPS URL.

    Only allows HTTPS URLs. Returns parsed skill config.
    """
    if not bus.is_guard_activated(db_path):
        return {"ok": False, "error": "Guardian activation required"}

    if not url or not url.strip():
        return {"ok": False, "error": "URL is required"}

    url = url.strip()
    if not url.startswith("https://"):
        return {"ok": False, "error": "Only HTTPS URLs are allowed for skill downloads"}

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "CrewBus/1.0 (Skill Store)",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read(500_000).decode("utf-8", errors="replace")

        parsed = json.loads(raw)

        # Validate required fields
        if not isinstance(parsed, dict):
            return {"ok": False, "error": "Skill must be a JSON object"}
        if not parsed.get("instructions") and not parsed.get("description"):
            return {"ok": False, "error": "Skill must have 'instructions' or 'description'"}

        return {
            "ok": True,
            "skill_config": json.dumps(parsed),
            "source": "github",
            "source_url": url,
        }

    except json.JSONDecodeError:
        return {"ok": False, "error": "URL did not return valid JSON"}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"URL error: {e.reason}"}
    except Exception as e:
        return {"ok": False, "error": f"Fetch error: {e}"}


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

def install_skill(agent_id: int, skill_name: str, skill_config: str = "",
                  source: str = "catalog", source_url: str = "",
                  db_path: Optional[Path] = None) -> dict:
    """Full installation pipeline: lookup → download → vet → assign.

    The Guardian's primary skill installation command.
    """
    if not bus.is_guard_activated(db_path):
        return {"ok": False, "error": "Guardian activation required"}

    # Get agent info
    conn = bus.get_conn(db_path)
    agent = conn.execute(
        "SELECT id, name FROM agents WHERE id = ?", (agent_id,),
    ).fetchone()
    conn.close()

    if not agent:
        return {"ok": False, "error": f"Agent id={agent_id} not found",
                "message": f"Agent id={agent_id} not found"}

    # Step 1: Get the skill config
    if not skill_config or skill_config.strip() == "{}":
        if source == "catalog":
            # Look up in local catalog
            catalog = load_catalog(db_path)
            found = None
            for s in catalog:
                if s.get("skill_name", "").lower() == skill_name.lower():
                    found = s
                    break
            if found:
                skill_config = json.dumps({
                    "description": found.get("description", ""),
                    "instructions": found.get("instructions", ""),
                })
            else:
                return {
                    "ok": False,
                    "message": f"Skill '{skill_name}' not found in catalog",
                }
        elif source_url:
            # Download from URL
            fetch_result = fetch_skill_from_url(source_url, db_path=db_path)
            if not fetch_result.get("ok"):
                return {
                    "ok": False,
                    "message": f"Failed to download: {fetch_result.get('error')}",
                }
            skill_config = fetch_result["skill_config"]

    # Step 2: Vet the skill
    vet_result = bus.vet_skill(skill_name, skill_config, db_path=db_path)

    # Step 3: Add to agent (includes Guardian gate check)
    success, message = bus.add_skill_to_agent(
        agent_id, skill_name, skill_config,
        added_by="guardian", human_override=True,
        db_path=db_path,
    )

    # Audit the installation
    try:
        with bus.db_write(db_path or bus.DB_PATH) as wconn:
            wconn.execute(
                "INSERT INTO audit_log (event_type, agent_id, details) "
                "VALUES (?, ?, ?)",
                ("skill_installed", agent_id, json.dumps({
                    "skill_name": skill_name,
                    "source": source,
                    "source_url": source_url,
                    "vet_status": vet_result.get("registry_status", "unknown"),
                    "risk_score": vet_result.get("scan_result", {}).get("risk_score", 0),
                    "success": success,
                })),
            )
    except Exception:
        pass

    return {
        "ok": success,
        "skill_name": skill_name,
        "agent_name": agent["name"],
        "vet_result": {
            "registry_status": vet_result.get("registry_status"),
            "risk_score": vet_result.get("scan_result", {}).get("risk_score", 0),
            "can_add": vet_result.get("can_add"),
        },
        "message": message,
    }


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_catalog_stats(db_path: Optional[Path] = None) -> dict:
    """Return catalog metadata — total skills, category counts, etc."""
    catalog = load_catalog(db_path)
    categories = {}
    for skill in catalog:
        cat = skill.get("category", "uncategorized")
        categories[cat] = categories.get(cat, 0) + 1

    return {
        "total_skills": len(catalog),
        "categories": categories,
    }
