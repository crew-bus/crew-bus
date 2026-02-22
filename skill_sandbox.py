"""
Skill Sandbox — Guardian's runtime monitoring engine for installed skills.

The Guardian stands watch at all times after downloading a skill.
Monitors agent behavior for anomalies, glitches, and security violations.
Tracks per-skill health metrics and can quarantine/disable problematic skills.

This is NOT code execution sandboxing — skills are text prompts.
This IS behavioral monitoring: error rates, response anomalies,
charter violations, performance degradation.

Gated behind Guardian activation ($29 key).
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import bus

# ---------------------------------------------------------------------------
# Health score computation constants
# ---------------------------------------------------------------------------
_ERROR_PENALTY = 5          # per error
_CHARTER_VIOLATION_PENALTY = 10
_INTEGRITY_VIOLATION_PENALTY = 15
_RESPONSE_SPIKE_PENALTY = 10  # avg > 3x baseline
_BASELINE_SAMPLE_SIZE = 10    # first N uses to establish baseline
_MIN_HEALTH_SCORE = 0
_MAX_HEALTH_SCORE = 100


# ---------------------------------------------------------------------------
# Skill health lifecycle
# ---------------------------------------------------------------------------

def init_skill_health(agent_id: int, skill_name: str,
                      db_path: Optional[Path] = None) -> dict:
    """Create a health monitoring record for a newly installed skill.

    Called automatically when a skill is added to an agent.
    Safe to call multiple times (INSERT OR IGNORE).
    """
    db = db_path or bus.DB_PATH
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with bus.db_write(db) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO skill_health "
                "(agent_id, skill_name, status, installed_at, health_score) "
                "VALUES (?, ?, 'active', ?, 100)",
                (agent_id, skill_name.strip(), now),
            )
    except Exception:
        pass  # Table might not exist in older DBs
    return {"ok": True, "skill_name": skill_name, "health_score": 100}


def record_skill_usage(agent_id: int, response_ms: int = 0,
                       had_error: bool = False, error_type: str = "",
                       had_charter_violation: bool = False,
                       had_integrity_violation: bool = False,
                       db_path: Optional[Path] = None) -> None:
    """Record a usage event for all active skills on an agent.

    Called after each LLM response for agents that have skills.
    Updates total_uses, error/violation counts, response timing,
    and recalculates health_score.
    """
    db = db_path or bus.DB_PATH
    try:
        conn = bus.get_conn(db)
        rows = conn.execute(
            "SELECT id, skill_name, total_uses, error_count, anomaly_count, "
            "avg_response_ms, baseline_response_ms, charter_violations, "
            "integrity_violations, health_score "
            "FROM skill_health WHERE agent_id = ? AND status = 'active'",
            (agent_id,),
        ).fetchall()
        conn.close()

        if not rows:
            return

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        for row in rows:
            total = row["total_uses"] + 1
            errors = row["error_count"] + (1 if had_error else 0)
            charter_v = row["charter_violations"] + (1 if had_charter_violation else 0)
            integrity_v = row["integrity_violations"] + (1 if had_integrity_violation else 0)
            anomalies = row["anomaly_count"]

            # Update running average response time
            old_avg = row["avg_response_ms"]
            if total == 1:
                new_avg = response_ms
            else:
                new_avg = int(old_avg + (response_ms - old_avg) / total)

            # Establish baseline from first N samples
            baseline = row["baseline_response_ms"]
            if total <= _BASELINE_SAMPLE_SIZE:
                baseline = new_avg

            # Check for response time anomaly (>3x baseline)
            if baseline > 0 and new_avg > baseline * 3 and total > _BASELINE_SAMPLE_SIZE:
                anomalies += 1

            # Recalculate health score
            score = _compute_health_score(
                total, errors, charter_v, integrity_v,
                new_avg, baseline,
            )

            with bus.db_write(db) as wconn:
                wconn.execute(
                    "UPDATE skill_health SET "
                    "total_uses = ?, error_count = ?, anomaly_count = ?, "
                    "avg_response_ms = ?, baseline_response_ms = ?, "
                    "charter_violations = ?, integrity_violations = ?, "
                    "health_score = ?, last_check = ? "
                    "WHERE id = ?",
                    (total, errors, anomalies, new_avg, baseline,
                     charter_v, integrity_v, score, now, row["id"]),
                )

    except Exception:
        pass  # Never break the reply pipeline


def _compute_health_score(total_uses: int, errors: int,
                          charter_violations: int,
                          integrity_violations: int,
                          avg_response_ms: int,
                          baseline_response_ms: int) -> int:
    """Compute a 0-100 health score from usage metrics."""
    score = _MAX_HEALTH_SCORE

    # Error penalty (capped at -40)
    if total_uses > 0:
        error_rate = errors / total_uses
        error_deduction = min(int(error_rate * 100), 40)
        score -= error_deduction

    # Charter violation penalty
    score -= min(charter_violations * _CHARTER_VIOLATION_PENALTY, 30)

    # Integrity violation penalty (more severe)
    score -= min(integrity_violations * _INTEGRITY_VIOLATION_PENALTY, 45)

    # Response time spike penalty
    if (baseline_response_ms > 0 and
            avg_response_ms > baseline_response_ms * 3 and
            total_uses > _BASELINE_SAMPLE_SIZE):
        score -= _RESPONSE_SPIKE_PENALTY

    return max(_MIN_HEALTH_SCORE, min(_MAX_HEALTH_SCORE, score))


# ---------------------------------------------------------------------------
# Health checks and reports
# ---------------------------------------------------------------------------

def run_health_check(db_path: Optional[Path] = None) -> dict:
    """Sweep all active skills and evaluate health thresholds.

    Returns a summary with healthy/warning/critical counts and details.
    """
    if not bus.is_guard_activated(db_path):
        return {"ok": False, "error": "Guardian activation required"}

    db = db_path or bus.DB_PATH
    conn = bus.get_conn(db)
    rows = conn.execute(
        "SELECT sh.*, a.name as agent_name FROM skill_health sh "
        "JOIN agents a ON a.id = sh.agent_id "
        "WHERE sh.status = 'active' "
        "ORDER BY sh.health_score ASC",
    ).fetchall()
    conn.close()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    healthy = 0
    warning = 0
    critical = 0
    details = []

    for row in rows:
        d = dict(row)
        score = d.get("health_score", 100)
        total = d.get("total_uses", 0)
        errors = d.get("error_count", 0)

        # Classify
        if score >= 70:
            d["classification"] = "healthy"
            healthy += 1
        elif score >= 30:
            d["classification"] = "warning"
            warning += 1
        else:
            d["classification"] = "critical"
            critical += 1

        # Compute error rate
        d["error_rate"] = round(errors / total, 3) if total > 0 else 0.0

        # Compute response ratio
        baseline = d.get("baseline_response_ms", 0)
        d["response_ratio"] = (
            round(d.get("avg_response_ms", 0) / baseline, 2)
            if baseline > 0 else 0.0
        )

        details.append(d)

    # Update last_check for all
    try:
        with bus.db_write(db) as wconn:
            wconn.execute(
                "UPDATE skill_health SET last_check = ? WHERE status = 'active'",
                (now,),
            )
    except Exception:
        pass

    return {
        "ok": True,
        "total_skills": len(rows),
        "healthy": healthy,
        "warning": warning,
        "critical": critical,
        "details": details,
    }


def get_skill_health_report(agent_id: Optional[int] = None,
                            db_path: Optional[Path] = None) -> list:
    """Get health metrics for skills, optionally filtered by agent."""
    if not bus.is_guard_activated(db_path):
        return []

    db = db_path or bus.DB_PATH
    conn = bus.get_conn(db)

    if agent_id is not None:
        rows = conn.execute(
            "SELECT sh.*, a.name as agent_name FROM skill_health sh "
            "JOIN agents a ON a.id = sh.agent_id "
            "WHERE sh.agent_id = ? ORDER BY sh.health_score ASC",
            (agent_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT sh.*, a.name as agent_name FROM skill_health sh "
            "JOIN agents a ON a.id = sh.agent_id "
            "ORDER BY sh.health_score ASC",
        ).fetchall()

    conn.close()

    result = []
    for row in rows:
        d = dict(row)
        total = d.get("total_uses", 0)
        errors = d.get("error_count", 0)
        baseline = d.get("baseline_response_ms", 0)
        d["error_rate"] = round(errors / total, 3) if total > 0 else 0.0
        d["response_ratio"] = (
            round(d.get("avg_response_ms", 0) / baseline, 2)
            if baseline > 0 else 0.0
        )
        result.append(d)

    return result


def get_health_summary(db_path: Optional[Path] = None) -> dict:
    """Aggregate health report across all agents and skills."""
    if not bus.is_guard_activated(db_path):
        return {"ok": False, "error": "Guardian activation required"}

    db = db_path or bus.DB_PATH
    conn = bus.get_conn(db)

    total = conn.execute("SELECT COUNT(*) FROM skill_health").fetchone()[0]
    active = conn.execute(
        "SELECT COUNT(*) FROM skill_health WHERE status='active'"
    ).fetchone()[0]
    quarantined = conn.execute(
        "SELECT COUNT(*) FROM skill_health WHERE status='quarantined'"
    ).fetchone()[0]

    avg_score_row = conn.execute(
        "SELECT AVG(health_score) FROM skill_health WHERE status='active'"
    ).fetchone()
    avg_score = round(avg_score_row[0], 1) if avg_score_row[0] is not None else 100.0

    healthy = conn.execute(
        "SELECT COUNT(*) FROM skill_health "
        "WHERE status='active' AND health_score >= 70"
    ).fetchone()[0]
    warning = conn.execute(
        "SELECT COUNT(*) FROM skill_health "
        "WHERE status='active' AND health_score < 70 AND health_score >= 30"
    ).fetchone()[0]
    critical = conn.execute(
        "SELECT COUNT(*) FROM skill_health "
        "WHERE status='active' AND health_score < 30"
    ).fetchone()[0]

    conn.close()

    return {
        "ok": True,
        "total_monitored": total,
        "active": active,
        "healthy": healthy,
        "warning": warning,
        "critical": critical,
        "quarantined": quarantined,
        "avg_health_score": avg_score,
    }


# ---------------------------------------------------------------------------
# Quarantine / Restore
# ---------------------------------------------------------------------------

def quarantine_skill(agent_id: int, skill_name: str, reason: str = "",
                     db_path: Optional[Path] = None) -> dict:
    """Quarantine a problematic skill — removes from agent, marks quarantined.

    The Guardian uses this when a skill causes glitches or anomalies.
    """
    if not bus.is_guard_activated(db_path):
        return {"ok": False, "error": "Guardian activation required"}

    db = db_path or bus.DB_PATH
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Update health record
    with bus.db_write(db) as conn:
        cur = conn.execute(
            "UPDATE skill_health SET status='quarantined', "
            "quarantined_at=?, quarantine_reason=? "
            "WHERE agent_id=? AND skill_name=? AND status='active'",
            (now, reason, agent_id, skill_name),
        )
        if cur.rowcount == 0:
            return {"ok": False, "message": f"Skill '{skill_name}' not found or already quarantined"}

        # Audit log
        conn.execute(
            "INSERT INTO audit_log (event_type, agent_id, details) VALUES (?, ?, ?)",
            ("skill_quarantined", agent_id, json.dumps({
                "skill_name": skill_name,
                "reason": reason,
            })),
        )

    # Remove from agent's active skills
    bus.remove_skill_from_agent(agent_id, skill_name, db_path=db)

    return {
        "ok": True,
        "message": f"🔒 Skill '{skill_name}' quarantined: {reason}",
        "skill_name": skill_name,
        "agent_id": agent_id,
    }


def restore_skill(agent_id: int, skill_name: str,
                   db_path: Optional[Path] = None) -> dict:
    """Restore a quarantined skill — re-vets, re-adds, resets health metrics.

    Only restores if the skill still passes safety vetting.
    """
    if not bus.is_guard_activated(db_path):
        return {"ok": False, "error": "Guardian activation required"}

    db = db_path or bus.DB_PATH

    # Get quarantined record
    conn = bus.get_conn(db)
    row = conn.execute(
        "SELECT * FROM skill_health "
        "WHERE agent_id=? AND skill_name=? AND status='quarantined'",
        (agent_id, skill_name),
    ).fetchone()
    conn.close()

    if not row:
        return {"ok": False, "message": f"No quarantined skill '{skill_name}' found"}

    # Get skill config from registry
    conn = bus.get_conn(db)
    reg = conn.execute(
        "SELECT skill_config FROM skill_registry WHERE skill_name=? "
        "ORDER BY vetted_at DESC LIMIT 1",
        (skill_name,),
    ).fetchone()
    conn.close()

    skill_config = reg["skill_config"] if reg else "{}"

    # Re-vet the skill before restoring
    vet_result = bus.vet_skill(skill_name, skill_config, db_path=db)
    if not vet_result.get("can_add"):
        return {
            "ok": False,
            "message": f"Skill '{skill_name}' failed re-vetting: {vet_result.get('reason')}",
        }

    # Re-add to agent
    success, msg = bus.add_skill_to_agent(
        agent_id, skill_name, skill_config,
        added_by="guardian_restore", human_override=True, db_path=db,
    )

    if not success:
        return {"ok": False, "message": f"Failed to restore: {msg}"}

    # Reset health metrics
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with bus.db_write(db) as wconn:
        wconn.execute(
            "UPDATE skill_health SET "
            "status='active', total_uses=0, error_count=0, "
            "anomaly_count=0, avg_response_ms=0, baseline_response_ms=0, "
            "charter_violations=0, integrity_violations=0, "
            "health_score=100, quarantined_at=NULL, quarantine_reason='', "
            "last_check=? "
            "WHERE agent_id=? AND skill_name=?",
            (now, agent_id, skill_name),
        )

        # Audit log
        wconn.execute(
            "INSERT INTO audit_log (event_type, agent_id, details) VALUES (?, ?, ?)",
            ("skill_restored", agent_id, json.dumps({
                "skill_name": skill_name,
                "vet_status": vet_result.get("registry_status", "unknown"),
            })),
        )

    return {
        "ok": True,
        "message": f"✅ Skill '{skill_name}' restored and health reset",
        "skill_name": skill_name,
        "agent_id": agent_id,
    }
