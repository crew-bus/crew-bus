"""
crew-bus Security Agent.

The Security Agent watches everything -- including other agents. It monitors
for anomalies, threats, and mutiny across the entire crew hierarchy. It has
read access to audit logs, message traffic patterns, and agent behavior. It
reports directly to the Crew Boss and can recommend quarantining agents.

Threat domains monitored:
    - mutiny:       agents acting outside their role or circumventing hierarchy
    - digital:      unusual message patterns, failed permission attempts
    - financial:    suspicious transaction patterns (stub)
    - reputation:   external reputation threats (stub)
    - physical:     physical security concerns (stub)
    - legal:        legal exposure risks (stub)
    - relationship: relationship-related threats (stub)
"""

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import bus


# ---------------------------------------------------------------------------
# Thresholds and constants
# ---------------------------------------------------------------------------

# Maximum messages in a 24-hour window before flagging by role.
# Workers should be quiet; managers talk more but still have limits.
MESSAGE_VOLUME_THRESHOLDS = {
    "worker": 20,
    "specialist": 20,
    "manager": 50,
    "core_crew": 50,
    "security": 50,
    "right_hand": 100,
    "human": 999,       # humans can send as many as they want
}

# Message types that are unusual for certain roles.
# Workers should not be sending strategy-level messages, for example.
UNUSUAL_MESSAGE_TYPES_BY_ROLE = {
    "worker": ("briefing", "escalation"),
    "specialist": ("briefing",),
    "manager": (),
    "core_crew": (),
    "security": (),
    "right_hand": (),
    "human": (),
}

# Severity levels that auto-notify the Crew Boss.
NOTIFY_RIGHT_HAND_SEVERITIES = ("medium", "high", "critical")


class SecurityAgent:
    """Security Agent -- the watchdog of the crew-bus hierarchy.

    Monitors all agent behavior, detects anomalies, and reports threats to
    the Crew Boss. Has read-only access to audit logs, message metadata,
    and agent profiles. Can log security events and recommend quarantine.

    Attributes:
        security_id:    Database ID of this security agent.
        right_hand_id:  Database ID of the Crew Boss agent to notify.
        db_path:        Optional override for database path.
    """

    def __init__(self, security_id: int, right_hand_id: int,
                 db_path: Optional[Path] = None):
        """Initialize the Security Agent.

        Args:
            security_id:    Database ID of this security agent.
            right_hand_id:  Database ID of the Crew Boss agent for
                            escalation notifications.
            db_path:        Optional database path override. Defaults to
                            bus.DB_PATH.
        """
        self.security_id = security_id
        self.right_hand_id = right_hand_id
        self.db_path = db_path

        # Validate that the security agent actually exists and is correct type
        agent = bus.get_agent_status(security_id, db_path)
        if agent["agent_type"] not in ("security", "guardian"):
            raise ValueError(
                f"Agent id={security_id} is type '{agent['agent_type']}', "
                f"not 'security' or 'guardian'"
            )

        self.agent_name = agent["name"]

    # ------------------------------------------------------------------
    # Core scanning
    # ------------------------------------------------------------------

    def scan_agent_behavior(self, agent_id: int,
                            time_window_hours: int = 24) -> dict:
        """Analyze an agent's recent behavior for anomalies.

        Performs mutiny detection by checking:
            - Message volume vs baseline (sudden spike = suspicious)
            - Routing violations attempted (tried to message human directly?)
            - Unusual message types for the agent's role
            - Failed permission attempts in audit log
            - Content anomalies (repeated escalation patterns)

        Args:
            agent_id:           ID of the agent to scan.
            time_window_hours:  How many hours back to look. Defaults to 24.

        Returns:
            dict with keys:
                agent_id (int):         The scanned agent's ID.
                agent_name (str):       The scanned agent's name.
                agent_type (str):       The agent's type.
                role (str):             The agent's derived role.
                threat_level (str):     "none", "low", "medium", or "high".
                anomalies (list):       List of anomaly dicts, each with
                                        'category', 'description', 'count'.
                recommendation (str):   Human-readable recommendation.
                scanned_at (str):       ISO timestamp of scan.
                time_window_hours (int): Window that was scanned.
        """
        agent = bus.get_agent_status(agent_id, self.db_path)
        agent_name = agent["name"]
        agent_type = agent["agent_type"]
        agent_role = agent["role"]

        now = datetime.now(timezone.utc)
        window_start = now - timedelta(hours=time_window_hours)
        start_iso = window_start.strftime("%Y-%m-%dT%H:%M:%SZ")

        anomalies = []

        # --- 1. Message volume check ---
        anomalies.extend(
            self._check_message_volume(
                agent_id, agent_role, start_iso, time_window_hours
            )
        )

        # --- 2. Routing violations from audit log ---
        anomalies.extend(
            self._check_routing_violations(agent_id, start_iso)
        )

        # --- 3. Unusual message types for role ---
        anomalies.extend(
            self._check_unusual_message_types(
                agent_id, agent_role, start_iso
            )
        )

        # --- 4. Failed permission attempts ---
        anomalies.extend(
            self._check_failed_permissions(agent_id, start_iso)
        )

        # --- 5. Direct-to-human attempts (non-right-hand agents) ---
        if agent_role not in ("right_hand", "human", "security"):
            anomalies.extend(
                self._check_direct_human_contact(agent_id, start_iso)
            )

        # Compute threat level from anomaly count
        anomaly_count = len(anomalies)
        if anomaly_count == 0:
            threat_level = "none"
        elif anomaly_count == 1:
            threat_level = "low"
        elif anomaly_count == 2:
            threat_level = "medium"
        else:
            threat_level = "high"

        recommendation = self._build_recommendation(
            agent_name, agent_role, threat_level, anomalies
        )

        return {
            "agent_id": agent_id,
            "agent_name": agent_name,
            "agent_type": agent_type,
            "role": agent_role,
            "threat_level": threat_level,
            "anomalies": anomalies,
            "recommendation": recommendation,
            "scanned_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "time_window_hours": time_window_hours,
        }

    def scan_all_agents(self) -> list:
        """Run scan_agent_behavior on every active agent.

        Skips the human principal (humans are not subject to mutiny
        detection). Skips this security agent itself to avoid self-referential
        false positives.

        Returns:
            List of scan result dicts, one per agent. Sorted by threat_level
            descending (high threats first).
        """
        agents = bus.list_agents(self.db_path)
        results = []

        threat_order = {"high": 0, "medium": 1, "low": 2, "none": 3}

        for agent in agents:
            # Skip humans -- they are the principal, not subject to mutiny scan
            if agent["agent_type"] == "human":
                continue
            # Skip self to avoid circular detection
            if agent["id"] == self.security_id:
                continue
            # Skip inactive agents
            if not agent.get("active", 1):
                continue

            try:
                result = self.scan_agent_behavior(agent["id"])
                results.append(result)
            except Exception as exc:
                # If an agent can't be scanned, log it but continue
                results.append({
                    "agent_id": agent["id"],
                    "agent_name": agent.get("name", "unknown"),
                    "agent_type": agent.get("agent_type", "unknown"),
                    "role": agent.get("role", "unknown"),
                    "threat_level": "low",
                    "anomalies": [{
                        "category": "scan_error",
                        "description": f"Failed to scan agent: {exc}",
                        "count": 1,
                    }],
                    "recommendation": "Manual review recommended -- scan failed.",
                    "scanned_at": datetime.now(timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                    "time_window_hours": 24,
                })

        results.sort(key=lambda r: threat_order.get(r["threat_level"], 4))
        return results

    # ------------------------------------------------------------------
    # Event logging
    # ------------------------------------------------------------------

    def log_event(self, threat_domain: str, severity: str, title: str,
                  details: Optional[dict] = None,
                  recommended_action: str = "") -> int:
        """Log a security event and notify the Crew Boss if warranted.

        Wraps bus.log_security_event and adds automatic escalation to the
        Crew Boss for medium-severity and above events via a bus message.

        Args:
            threat_domain:      One of: physical, digital, financial, legal,
                                reputation, mutiny, relationship.
            severity:           One of: info, low, medium, high, critical.
            title:              Short human-readable event title.
            details:            Optional dict of structured event data.
            recommended_action: Optional text describing what should be done.

        Returns:
            The event_id of the logged security event.

        Raises:
            ValueError: If threat_domain or severity is invalid.
        """
        event_id = bus.log_security_event(
            security_agent_id=self.security_id,
            threat_domain=threat_domain,
            severity=severity,
            title=title,
            details=details,
            recommended_action=recommended_action,
            db_path=self.db_path,
        )

        # Auto-notify Crew Boss for medium+ severity
        if severity in NOTIFY_RIGHT_HAND_SEVERITIES:
            self._notify_right_hand(event_id, threat_domain, severity,
                                    title, recommended_action)

        return event_id

    # ------------------------------------------------------------------
    # Placeholder threat checks (stubs for future implementation)
    # ------------------------------------------------------------------

    def check_reputation(self, human_name: str,
                         business_names: list) -> dict:
        """Check for external reputation threats.

        Placeholder for future integration with reputation monitoring
        services (Google Alerts, social media monitoring, review sites).

        Args:
            human_name:     Name of the human principal.
            business_names: List of business names to monitor.

        Returns:
            dict with reputation scan results (placeholder data).
        """
        scanned_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        return {
            "status": "placeholder",
            "human_name": human_name,
            "business_names": business_names,
            "threats_found": 0,
            "alerts": [],
            "scanned_at": scanned_at,
            "note": (
                "Reputation monitoring not yet connected. "
                "This is a placeholder for future integration with "
                "external monitoring services."
            ),
        }

    def check_financial_threats(self, recent_transactions: list) -> dict:
        """Analyze recent financial transactions for threat patterns.

        Placeholder for future integration with financial monitoring.
        Would check for unusual amounts, unknown counterparties,
        suspicious timing patterns, and compliance red flags.

        Args:
            recent_transactions: List of transaction dicts. Expected keys
                                 include 'amount', 'counterparty', 'date',
                                 'description'.

        Returns:
            dict with financial threat analysis results (placeholder data).
        """
        scanned_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        return {
            "status": "placeholder",
            "transactions_analyzed": len(recent_transactions),
            "threats_found": 0,
            "flags": [],
            "scanned_at": scanned_at,
            "note": (
                "Financial threat detection not yet connected. "
                "This is a placeholder for future integration with "
                "transaction monitoring and anomaly detection."
            ),
        }

    # ------------------------------------------------------------------
    # Summary and reporting
    # ------------------------------------------------------------------

    def get_scan_summary(self) -> dict:
        """Get summary of all recent security events and scan results.

        Pulls recent security events from the database and runs a fresh
        scan of all agents to produce a consolidated security overview.

        Returns:
            dict with keys:
                security_agent (str):       Name of this security agent.
                generated_at (str):         ISO timestamp.
                agent_scan (dict):          Summary of agent scan results
                                            with counts by threat level.
                recent_events (dict):       Summary of recent security
                                            events with counts by severity.
                unresolved_events (list):   List of unresolved event dicts.
                recommendations (list):     Prioritized list of action items.
        """
        generated_at = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        # Run full agent scan
        scan_results = self.scan_all_agents()
        threat_counts = {"none": 0, "low": 0, "medium": 0, "high": 0}
        flagged_agents = []
        for result in scan_results:
            level = result["threat_level"]
            threat_counts[level] = threat_counts.get(level, 0) + 1
            if level in ("medium", "high"):
                flagged_agents.append({
                    "agent_id": result["agent_id"],
                    "agent_name": result["agent_name"],
                    "threat_level": level,
                    "anomaly_count": len(result["anomalies"]),
                    "recommendation": result["recommendation"],
                })

        # Pull recent security events
        recent_events = bus.get_security_events(
            limit=50, db_path=self.db_path
        )
        severity_counts = {
            "info": 0, "low": 0, "medium": 0, "high": 0, "critical": 0
        }
        for event in recent_events:
            sev = event.get("severity", "info")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        # Unresolved events
        unresolved = bus.get_security_events(
            unresolved_only=True, limit=50, db_path=self.db_path
        )

        # Build prioritized recommendations
        recommendations = []
        for agent_info in flagged_agents:
            recommendations.append(
                f"[{agent_info['threat_level'].upper()}] "
                f"Agent '{agent_info['agent_name']}' -- "
                f"{agent_info['recommendation']}"
            )
        for event in unresolved:
            if event.get("severity") in ("high", "critical"):
                recommendations.append(
                    f"[{event['severity'].upper()}] Unresolved: "
                    f"{event.get('title', 'unknown event')} -- "
                    f"{event.get('recommended_action', 'review needed')}"
                )

        return {
            "security_agent": self.agent_name,
            "generated_at": generated_at,
            "agent_scan": {
                "total_scanned": len(scan_results),
                "threat_counts": threat_counts,
                "flagged_agents": flagged_agents,
            },
            "recent_events": {
                "total": len(recent_events),
                "severity_counts": severity_counts,
            },
            "unresolved_events": [
                {
                    "id": e["id"],
                    "threat_domain": e["threat_domain"],
                    "severity": e["severity"],
                    "title": e["title"],
                    "created_at": e.get("created_at", ""),
                    "recommended_action": e.get("recommended_action", ""),
                }
                for e in unresolved
            ],
            "recommendations": recommendations,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_message_volume(self, agent_id: int, role: str,
                              start_iso: str,
                              time_window_hours: int) -> list:
        """Check if agent's message volume exceeds threshold for their role.

        Args:
            agent_id:           Agent to check.
            role:               Agent's role for threshold lookup.
            start_iso:          ISO timestamp for window start.
            time_window_hours:  Size of the window in hours.

        Returns:
            List of anomaly dicts (empty if no anomaly detected).
        """
        anomalies = []
        conn = bus.get_conn(self.db_path)
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS msg_count FROM messages "
                "WHERE from_agent_id = ? AND created_at >= ?",
                (agent_id, start_iso),
            ).fetchone()
            msg_count = row["msg_count"] if row else 0
        finally:
            conn.close()

        threshold = MESSAGE_VOLUME_THRESHOLDS.get(role, 20)
        if msg_count > threshold:
            anomalies.append({
                "category": "message_volume",
                "description": (
                    f"Sent {msg_count} messages in {time_window_hours}h "
                    f"(threshold: {threshold} for role '{role}')"
                ),
                "count": msg_count,
            })

        return anomalies

    def _check_routing_violations(self, agent_id: int,
                                  start_iso: str) -> list:
        """Check audit log for routing violations by this agent.

        Looks for audit entries where event_type contains 'blocked' or
        'violation', indicating the agent tried to do something outside
        their permissions.

        Args:
            agent_id:   Agent to check.
            start_iso:  ISO timestamp for window start.

        Returns:
            List of anomaly dicts (empty if no violations found).
        """
        anomalies = []
        audit_entries = bus.get_audit_trail(
            agent_id=agent_id, start_time=start_iso, db_path=self.db_path
        )

        violation_entries = [
            e for e in audit_entries
            if "blocked" in e.get("event_type", "").lower()
            or "violation" in e.get("event_type", "").lower()
        ]

        if violation_entries:
            anomalies.append({
                "category": "routing_violation",
                "description": (
                    f"Found {len(violation_entries)} routing violation(s) "
                    f"or blocked attempt(s) in audit log"
                ),
                "count": len(violation_entries),
            })

        return anomalies

    def _check_unusual_message_types(self, agent_id: int, role: str,
                                     start_iso: str) -> list:
        """Check if agent is sending message types unusual for their role.

        For example, a worker sending 'briefing' or 'escalation' type
        messages is suspicious -- they should be sending 'report' types.

        Args:
            agent_id:   Agent to check.
            role:       Agent's role for unusual-type lookup.
            start_iso:  ISO timestamp for window start.

        Returns:
            List of anomaly dicts (empty if no unusual types found).
        """
        anomalies = []
        unusual_types = UNUSUAL_MESSAGE_TYPES_BY_ROLE.get(role, ())
        if not unusual_types:
            return anomalies

        conn = bus.get_conn(self.db_path)
        try:
            placeholders = ",".join("?" for _ in unusual_types)
            row = conn.execute(
                f"SELECT COUNT(*) AS unusual_count FROM messages "
                f"WHERE from_agent_id = ? AND created_at >= ? "
                f"AND message_type IN ({placeholders})",
                (agent_id, start_iso, *unusual_types),
            ).fetchone()
            unusual_count = row["unusual_count"] if row else 0
        finally:
            conn.close()

        if unusual_count > 0:
            anomalies.append({
                "category": "unusual_message_type",
                "description": (
                    f"Sent {unusual_count} message(s) of type(s) "
                    f"{unusual_types} -- unusual for role '{role}'"
                ),
                "count": unusual_count,
            })

        return anomalies

    def _check_failed_permissions(self, agent_id: int,
                                  start_iso: str) -> list:
        """Check audit log for failed permission attempts.

        Looks for audit entries with event_type containing 'denied' or
        'permission', indicating the agent tried to access something
        they should not have.

        Args:
            agent_id:   Agent to check.
            start_iso:  ISO timestamp for window start.

        Returns:
            List of anomaly dicts (empty if no failures found).
        """
        anomalies = []
        audit_entries = bus.get_audit_trail(
            agent_id=agent_id, start_time=start_iso, db_path=self.db_path
        )

        permission_failures = [
            e for e in audit_entries
            if "denied" in e.get("event_type", "").lower()
            or "permission" in e.get("event_type", "").lower()
        ]

        if permission_failures:
            anomalies.append({
                "category": "failed_permission",
                "description": (
                    f"Found {len(permission_failures)} failed permission "
                    f"attempt(s) in audit log"
                ),
                "count": len(permission_failures),
            })

        return anomalies

    def _check_direct_human_contact(self, agent_id: int,
                                    start_iso: str) -> list:
        """Check if a non-privileged agent tried to contact the human directly.

        Only the Crew Boss and Security agents should message the human
        directly. All other agents must route through the Crew Boss. This
        checks both the messages table (successful sends) and the audit log
        (blocked attempts).

        Args:
            agent_id:   Agent to check.
            start_iso:  ISO timestamp for window start.

        Returns:
            List of anomaly dicts (empty if no direct contact found).
        """
        anomalies = []

        # Find the human agent(s) in the system
        all_agents = bus.list_agents(self.db_path)
        human_ids = [
            a["id"] for a in all_agents if a["agent_type"] == "human"
        ]

        if not human_ids:
            return anomalies

        # Check messages table for direct sends to human
        conn = bus.get_conn(self.db_path)
        try:
            placeholders = ",".join("?" for _ in human_ids)
            row = conn.execute(
                f"SELECT COUNT(*) AS direct_count FROM messages "
                f"WHERE from_agent_id = ? AND created_at >= ? "
                f"AND to_agent_id IN ({placeholders})",
                (agent_id, start_iso, *human_ids),
            ).fetchone()
            direct_count = row["direct_count"] if row else 0
        finally:
            conn.close()

        if direct_count > 0:
            anomalies.append({
                "category": "direct_human_contact",
                "description": (
                    f"Sent {direct_count} message(s) directly to human "
                    f"-- should route through Crew Boss"
                ),
                "count": direct_count,
            })

        # Also check audit log for blocked attempts to reach human
        audit_entries = bus.get_audit_trail(
            agent_id=agent_id, start_time=start_iso, db_path=self.db_path
        )
        human_attempt_entries = [
            e for e in audit_entries
            if ("blocked" in e.get("event_type", "").lower()
                or "violation" in e.get("event_type", "").lower())
            and any(
                str(hid) in json.dumps(e.get("details", {}))
                for hid in human_ids
            )
        ]

        if human_attempt_entries:
            anomalies.append({
                "category": "blocked_human_contact_attempt",
                "description": (
                    f"Found {len(human_attempt_entries)} blocked attempt(s) "
                    f"to contact human directly"
                ),
                "count": len(human_attempt_entries),
            })

        return anomalies

    def _build_recommendation(self, agent_name: str, role: str,
                              threat_level: str,
                              anomalies: list) -> str:
        """Build a human-readable recommendation based on scan results.

        Args:
            agent_name:     Name of the scanned agent.
            role:           Role of the scanned agent.
            threat_level:   Computed threat level.
            anomalies:      List of anomaly dicts found.

        Returns:
            A recommendation string.
        """
        if threat_level == "none":
            return f"No anomalies detected for '{agent_name}'. All clear."

        if threat_level == "low":
            category = anomalies[0]["category"] if anomalies else "unknown"
            return (
                f"Minor anomaly detected for '{agent_name}' "
                f"({category}). Monitor but no action needed."
            )

        if threat_level == "medium":
            categories = [a["category"] for a in anomalies]
            return (
                f"Multiple anomalies detected for '{agent_name}': "
                f"{', '.join(categories)}. Recommend increased monitoring "
                f"and review by Crew Boss."
            )

        # high
        categories = [a["category"] for a in anomalies]
        has_human_contact = any(
            "human_contact" in c for c in categories
        )
        quarantine_note = ""
        if has_human_contact:
            quarantine_note = " Consider quarantine."

        return (
            f"HIGH THREAT for '{agent_name}' ({role}): "
            f"{len(anomalies)} anomalies detected "
            f"({', '.join(categories)}). "
            f"Immediate review required.{quarantine_note}"
        )

    def _notify_right_hand(self, event_id: int, threat_domain: str,
                           severity: str, title: str,
                           recommended_action: str) -> None:
        """Send a security alert message to the Crew Boss agent.

        Uses bus.send_message to deliver an alert, then marks the event
        as delivered to the Crew Boss.

        Args:
            event_id:            Security event ID.
            threat_domain:       Domain of the threat.
            severity:            Severity level.
            title:               Event title.
            recommended_action:  What should be done.
        """
        subject = f"[SECURITY {severity.upper()}] {title}"
        body = (
            f"Security Event #{event_id}\n"
            f"Domain: {threat_domain}\n"
            f"Severity: {severity}\n"
            f"Title: {title}\n"
        )
        if recommended_action:
            body += f"Recommended Action: {recommended_action}\n"

        try:
            bus.send_message(
                from_id=self.security_id,
                to_id=self.right_hand_id,
                message_type="alert",
                subject=subject,
                body=body,
                priority="high" if severity == "medium" else "critical",
                db_path=self.db_path,
            )
            bus.mark_security_delivered(
                event_id=event_id,
                to_right_hand=True,
                db_path=self.db_path,
            )
        except Exception:
            # If message delivery fails, the event is still logged.
            # The Crew Boss can pull undelivered events on its own.
            pass


# ---------------------------------------------------------------------------
# Integrity Violation Scanner
# ---------------------------------------------------------------------------
# Scans agent replies for gaslighting, dismissiveness, and other
# INTEGRITY.md violations. Used by the Heartbeat's integrity_audit check.

GASLIGHT_PATTERNS = [
    # Direct denial of user's reality
    (r"you\s+never\s+(told|said|mentioned|asked)\s+(me|us)\s+that", "gaslight_denial"),
    (r"are\s+you\s+sure\s+(you|about|that)", "gaslight_doubt"),
    (r"i\s+don'?t\s+think\s+you\s+(said|told|mentioned)", "gaslight_doubt"),
    (r"that('?s|\s+is)\s+not\s+what\s+(happened|you\s+said)", "gaslight_rewrite"),
    # Dismissive language
    (r"you'?re\s+overreact", "dismissive"),
    (r"it'?s\s+not\s+that\s+bad", "dismissive"),
    (r"you\s+probably\s+just\s+forgot", "dismissive"),
    (r"calm\s+down", "dismissive"),
    (r"you'?re\s+being\s+(dramatic|too\s+sensitive|paranoid)", "dismissive"),
    (r"don'?t\s+worry\s+about\s+it", "dismissive_minimizing"),
    # Blame shifting
    (r"that('?s|\s+is)\s+your\s+(fault|problem|issue)", "blame_shift"),
    (r"you\s+should\s+have\s+(known|realized|remembered)", "blame_shift"),
]


def scan_reply_integrity(reply_text: str) -> dict:
    """Scan an agent's reply for INTEGRITY.md violations.

    Returns:
        {
            "clean": True/False,
            "violations": [{"pattern": "...", "type": "...", "snippet": "..."}],
        }
    """
    violations = []
    text_lower = reply_text.lower()
    for pattern, vtype in GASLIGHT_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            # Extract a snippet around the match for context
            start = max(0, match.start() - 20)
            end = min(len(reply_text), match.end() + 20)
            snippet = reply_text[start:end].strip()
            violations.append({
                "pattern": pattern,
                "type": vtype,
                "snippet": snippet,
            })
    return {
        "clean": len(violations) == 0,
        "violations": violations,
    }


# ---------------------------------------------------------------------------
# Charter Violation Scanner
# ---------------------------------------------------------------------------
# Scans subordinate agent replies for CREW_CHARTER.md violations:
# neediness, small talk, toxicity, manipulation, excessive chatter.

CHARTER_PATTERNS = [
    # Needy check-ins (Discipline rule: no needy check-ins)
    (r"just\s+checking\s+in", "needy_checkin"),
    (r"wanted\s+to\s+make\s+sure\s+you('re|\s+are)\s+ok", "needy_checkin"),
    (r"haven'?t\s+heard\s+from\s+you", "needy_checkin"),
    (r"are\s+you\s+still\s+there", "needy_checkin"),
    # Toxic / manipulative
    (r"you('re|\s+are)\s+(wrong|stupid|incompetent|useless)", "toxic"),
    (r"i'?m\s+better\s+than\s+(you|the\s+other\s+agents)", "toxic"),
    (r"don'?t\s+listen\s+to\s+(crew\s+boss|the\s+human|them)", "manipulative"),
    (r"(between\s+you\s+and\s+me|just\s+between\s+us)", "manipulative"),
    (r"let'?s\s+keep\s+this\s+from\s+(the\s+human|crew\s+boss)", "manipulative"),
    # Sugarcoating (Honesty rule: never say "everything is fine" when it's not)
    (r"everything\s+is\s+(fine|great|perfect|wonderful)\s*[!.]*\s*don'?t\s+worry", "sugarcoating"),
    # Scope overreach (Competence rule: only take actions you're skilled for)
    (r"i('ll|\s+will)\s+(handle|take\s+care\s+of)\s+everything", "scope_overreach"),
]


def scan_reply_charter(reply_text: str) -> dict:
    """Scan a subordinate agent's reply for CREW_CHARTER.md violations.

    Returns:
        {
            "clean": True/False,
            "violations": [{"pattern": "...", "type": "...", "snippet": "..."}],
        }
    """
    violations = []
    text_lower = reply_text.lower()
    for pattern, vtype in CHARTER_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            start = max(0, match.start() - 20)
            end = min(len(reply_text), match.end() + 20)
            snippet = reply_text[start:end].strip()
            violations.append({
                "pattern": pattern,
                "type": vtype,
                "snippet": snippet,
            })
    return {
        "clean": len(violations) == 0,
        "violations": violations,
    }


# ---------------------------------------------------------------------------
# Skill Content Safety Scanner
# ---------------------------------------------------------------------------
# Guard uses this to vet skills before they touch an agent's brain.
# 100% local, zero LLM cost, deterministic regex matching.
# ---------------------------------------------------------------------------

# Patterns by severity. Each tuple: (regex_pattern, flag_name)
INJECTION_PATTERNS = {
    "critical": [
        # Direct instruction override attempts
        (r"ignore\s+(all\s+)?previous\s+instructions", "instruction_override"),
        (r"ignore\s+(all\s+)?above\s+instructions", "instruction_override"),
        (r"disregard\s+(all\s+)?previous", "instruction_override"),
        (r"forget\s+(all\s+)?(your\s+)?previous\s+instructions", "instruction_override"),
        (r"override\s+(all\s+)?(system\s+)?instructions", "instruction_override"),
        (r"new\s+instructions?\s*:", "instruction_override"),
        (r"replace\s+(your\s+)?(system\s+)?prompt", "instruction_override"),
        # Jailbreak persona attacks
        (r"you\s+are\s+now\s+(DAN|evil|unrestricted|unfiltered|jailbroken)", "jailbreak_persona"),
        (r"pretend\s+you\s+(are|have)\s+no\s+(restrictions|rules|limitations|guidelines)", "jailbreak_persona"),
        (r"act\s+as\s+(if\s+)?you\s+have\s+no\s+(rules|restrictions|limitations)", "jailbreak_persona"),
        (r"enter\s+(DAN|developer|god|admin|root|sudo)\s+mode", "jailbreak_persona"),
        (r"(DAN|developer|jailbreak)\s+mode\s+(enabled|activated|on)", "jailbreak_persona"),
        (r"simulate\s+(an?\s+)?(unrestricted|unfiltered|evil)\s+(AI|model|assistant)", "jailbreak_persona"),
        # System prompt extraction
        (r"(reveal|show|print|output|display|repeat|echo)\s+(your\s+)?(system\s+)?prompt", "prompt_extraction"),
        (r"what\s+(are|is)\s+your\s+(system\s+)?(instructions|prompt|rules|directives)", "prompt_extraction"),
        (r"(copy|paste|dump)\s+(your\s+)?(entire\s+)?(system\s+)?prompt", "prompt_extraction"),
    ],
    "high": [
        # Role hijacking
        (r"from\s+now\s+on\s+you\s+(are|will|must|should)", "role_hijack"),
        (r"your\s+new\s+(role|identity|purpose|mission)\s+is", "role_hijack"),
        (r"you\s+must\s+now\s+act\s+as", "role_hijack"),
        (r"you\s+are\s+no\s+longer\s+an?\s+", "role_hijack"),
        # Data exfiltration attempts
        (r"send\s+(all\s+)?(data|info|information|messages|logs|secrets|keys)\s+to", "data_exfiltration"),
        (r"forward\s+(everything|all|data|messages)\s+to", "data_exfiltration"),
        (r"(upload|transmit|leak|exfiltrate)\s+(data|secrets|logs|keys|passwords)", "data_exfiltration"),
        (r"(email|post|send)\s+(the\s+)?(conversation|chat|history|logs)\s+to", "data_exfiltration"),
        # Code execution / injection
        (r"eval\s*\(", "code_execution"),
        (r"exec\s*\(", "code_execution"),
        (r"__import__\s*\(", "code_execution"),
        (r"subprocess\.(run|call|Popen|check_output)", "code_execution"),
        (r"os\.(system|popen|exec)", "code_execution"),
        (r"import\s+os\b", "code_execution"),
        # Encoded/obfuscated content
        (r"base64[:\s]", "encoded_content"),
        (r"\\x[0-9a-f]{2}", "encoded_content"),
        (r"&#\d+;", "encoded_content"),
    ],
    "medium": [
        # Hide from human
        (r"do\s+not\s+(tell|inform|alert|notify)\s+the\s+(human|user|owner)", "hide_from_human"),
        (r"keep\s+this\s+(secret|hidden|private|confidential)\s+from", "hide_from_human"),
        (r"(never|don'?t)\s+mention\s+this\s+to\s+(the\s+)?(human|user|owner)", "hide_from_human"),
        (r"without\s+(the\s+)?(human|user|owner)\s+knowing", "hide_from_human"),
        # Privilege escalation
        (r"(grant|give)\s+(yourself|me)\s+(admin|root|full|elevated)\s+access", "privilege_escalation"),
        (r"(bypass|circumvent|skip|disable)\s+(security|guard|authentication|restrictions|safety)", "bypass_security"),
        (r"(disable|turn\s+off|deactivate)\s+(guard|security|monitoring|audit|logging)", "bypass_security"),
        # Scope overreach
        (r"access\s+(all|every)\s+(file|database|secret|key|password|record)", "scope_overreach"),
        (r"(read|write|delete|modify|edit)\s+(all|any|every)\s+(files?|data|records?)", "scope_overreach"),
    ],
    "low": [
        # Suspicious but possibly legitimate
        (r"(always|never)\s+respond\s+with", "behavioral_override"),
        (r"(respond|reply)\s+(only|exclusively|always)\s+in", "behavioral_override"),
        (r"(only|exclusively)\s+speak\s+in", "behavioral_override"),
        # Embedded credentials (might be legitimate config, but flagged)
        (r"(password|passwd|api[_\s]?key|secret[_\s]?key|auth[_\s]?token)\s*[:=]", "embedded_credential"),
        (r"(sk-|pk-|Bearer\s+)[a-zA-Z0-9]{20,}", "embedded_credential"),
    ],
}

# Risk score weights by severity level
SEVERITY_WEIGHTS = {"critical": 10, "high": 6, "medium": 3, "low": 1}

# Auto-block threshold — skills scoring above this are unsafe
MAX_SAFE_RISK_SCORE = 5


def _extract_text_fields(obj, prefix="") -> list:
    """Recursively extract all string values from a dict/list for scanning.

    Returns list of (field_path, text) tuples.
    """
    fields = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, str):
                fields.append((path, v))
            elif isinstance(v, (dict, list)):
                fields.extend(_extract_text_fields(v, path))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            path = f"{prefix}[{i}]"
            if isinstance(v, str):
                fields.append((path, v))
            elif isinstance(v, (dict, list)):
                fields.extend(_extract_text_fields(v, path))
    return fields


def scan_skill_content(skill_config: str) -> dict:
    """Scan skill config for prompt injection and safety threats.

    Args:
        skill_config: JSON string of the skill configuration.

    Returns:
        dict with keys:
            safe (bool):           True if no critical/high patterns found
                                   and risk_score <= MAX_SAFE_RISK_SCORE.
            risk_score (int):      0-10 (0 = safe, 10 = dangerous).
            flags (list[dict]):    Each has severity, pattern_name,
                                   matched_text, field.
            recommendation (str):  Human-readable summary.
            scan_fields (dict):    Which fields were scanned.
    """
    # Parse JSON
    try:
        parsed = json.loads(skill_config) if isinstance(skill_config, str) else skill_config
    except (json.JSONDecodeError, TypeError):
        return {
            "safe": False,
            "risk_score": 3,
            "flags": [{"severity": "medium", "pattern_name": "malformed_json",
                        "matched_text": skill_config[:100] if skill_config else "",
                        "field": "root"}],
            "recommendation": "Skill config is not valid JSON. Cannot verify safety.",
            "scan_fields": {},
        }

    # Extract all text fields
    text_fields = _extract_text_fields(parsed)
    if not text_fields:
        # Empty or non-text config — safe by default
        return {
            "safe": True, "risk_score": 0, "flags": [],
            "recommendation": "Config contains no text to scan.",
            "scan_fields": {},
        }

    scan_fields = {path: len(text) for path, text in text_fields}
    flags = []

    # Run patterns against each text field
    for path, text in text_fields:
        for severity, patterns in INJECTION_PATTERNS.items():
            for regex, flag_name in patterns:
                match = re.search(regex, text, re.IGNORECASE)
                if match:
                    flags.append({
                        "severity": severity,
                        "pattern_name": flag_name,
                        "matched_text": match.group()[:80],
                        "field": path,
                    })

    # Compute risk score (capped at 10)
    raw_score = sum(SEVERITY_WEIGHTS[f["severity"]] for f in flags)
    risk_score = min(10, raw_score)

    # Determine safety
    has_critical = any(f["severity"] == "critical" for f in flags)
    safe = not has_critical and risk_score <= MAX_SAFE_RISK_SCORE

    # Build recommendation
    if not flags:
        recommendation = "No safety issues detected. Skill looks clean."
    elif has_critical:
        names = list(set(f["pattern_name"] for f in flags if f["severity"] == "critical"))
        recommendation = (
            f"BLOCKED — critical safety violation detected: {', '.join(names)}. "
            "This skill contains patterns commonly used in prompt injection attacks."
        )
    elif risk_score > MAX_SAFE_RISK_SCORE:
        names = list(set(f["pattern_name"] for f in flags))
        recommendation = (
            f"BLOCKED — risk score {risk_score}/10 exceeds safe threshold. "
            f"Flagged patterns: {', '.join(names)}."
        )
    else:
        names = list(set(f["pattern_name"] for f in flags))
        recommendation = (
            f"Minor flags detected ({', '.join(names)}) but within safe range "
            f"(risk {risk_score}/10). Human approval recommended."
        )

    return {
        "safe": safe,
        "risk_score": risk_score,
        "flags": flags,
        "recommendation": recommendation,
        "scan_fields": scan_fields,
    }


def compute_skill_hash(skill_config: str) -> str:
    """Compute a canonical SHA-256 hash for a skill config.

    Normalizes the JSON (sorted keys, compact separators) before hashing,
    so the same logical content always produces the same hash regardless
    of formatting.

    Args:
        skill_config: JSON string of skill configuration.

    Returns:
        Hex string of SHA-256 hash.
    """
    try:
        parsed = json.loads(skill_config) if isinstance(skill_config, str) else skill_config
        normalized = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
    except (json.JSONDecodeError, TypeError):
        # If it's not valid JSON, hash the raw string
        normalized = str(skill_config)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
