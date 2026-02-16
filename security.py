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

import json
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
        if agent["agent_type"] != "security":
            raise ValueError(
                f"Agent id={security_id} is type '{agent['agent_type']}', "
                f"not 'security'"
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
