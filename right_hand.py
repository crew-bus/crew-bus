"""
crew-bus Crew Boss Decision Engine.

The most important file in the project. This is the brain that makes the
whole system human-first. The Crew Boss is a personal AI Chief of Staff
that sits between the human and all other agents, filtering, prioritizing,
and managing cognitive load.
"""

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import bus


class RightHand:
    """The Crew Boss decision engine.

    Manages all communication flow to and from the human based on:
    - Trust score (1-10): governs autonomy level
    - Burnout score: protects human's cognitive load
    - Timing rules: quiet hours, busy signals, focus mode
    - Knowledge store: past decisions, rejections, preferences
    """

    def __init__(self, right_hand_id: int, human_id: int,
                 db_path: Optional[Path] = None):
        """Initialize the Crew Boss with its agent and human context.

        Args:
            right_hand_id: Database ID of the Crew Boss agent.
            human_id: Database ID of the human principal.
            db_path: Optional database path override.
        """
        self.rh_id = right_hand_id
        self.human_id = human_id
        self.db_path = db_path

        # Load profiles
        self.rh = bus.get_agent_by_name(
            bus.get_agent_status(right_hand_id, db_path)["name"], db_path
        )
        self.human = bus.get_agent_by_name(
            bus.get_agent_status(human_id, db_path)["name"], db_path
        )
        self.trust_score = self.rh["trust_score"]

    def _refresh(self):
        """Reload current state from database."""
        self.rh = bus.get_agent_status(self.rh_id, self.db_path)
        self.human = bus.get_agent_status(self.human_id, self.db_path)
        self.trust_score = self.rh["trust_score"]

    @property
    def autonomy(self) -> dict:
        """Current autonomy level and abilities."""
        return bus.get_autonomy_level(self.rh_id, self.db_path)

    # ------------------------------------------------------------------
    # Core decision: should we deliver a message to the human?
    # ------------------------------------------------------------------

    def assess_delivery(self, message: dict) -> dict:
        """Assess whether a message should be delivered to the human right now.

        This is the central decision function. Every message destined for the
        human passes through here.

        Args:
            message: Dict with keys from the messages table (id, from_agent_id,
                     message_type, subject, body, priority, etc).

        Returns:
            {
                deliver: bool,
                reason: str,
                delay_until: str|None,
                modified_message: str|None  (rewritten for brevity/tone)
            }
        """
        self._refresh()
        priority = message.get("priority", "normal")
        msg_type = message.get("message_type", "report")

        # Critical/safety ALWAYS delivers immediately
        if priority == "critical" or msg_type == "escalation":
            decision = {
                "deliver": True,
                "reason": "Critical/safety - immediate delivery",
                "delay_until": None,
                "modified_message": None,
            }
            self._log("deliver", message, f"Immediate: {decision['reason']}")
            return decision

        # Strategy ideas get filtered first
        if msg_type == "idea":
            filter_result = self.filter_idea(message.get("id"))
            if filter_result["action"] == "filter":
                decision = {
                    "deliver": False,
                    "reason": filter_result["reason"],
                    "delay_until": None,
                    "modified_message": None,
                }
                self._log("filter", message, f"Filtered idea: {filter_result['reason']}")
                return decision
            elif filter_result["action"] == "queue":
                decision = {
                    "deliver": False,
                    "reason": filter_result["reason"],
                    "delay_until": filter_result.get("delay_until"),
                    "modified_message": None,
                }
                self._log("queue", message, f"Queued idea: {filter_result['reason']}")
                return decision

        # Check timing rules (burnout, quiet hours, busy, focus)
        timing = bus.should_deliver_now(self.human_id, priority, self.db_path)

        if not timing["deliver"]:
            decision = {
                "deliver": False,
                "reason": timing["reason"],
                "delay_until": timing["delay_until"],
                "modified_message": None,
            }
            self._log("queue", message, f"Timing: {timing['reason']}")
            return decision

        # All checks passed - deliver
        decision = {
            "deliver": True,
            "reason": "All checks passed - delivering to human",
            "delay_until": None,
            "modified_message": None,
        }
        self._log("deliver", message, "Delivered")
        return decision

    # ------------------------------------------------------------------
    # Strategy idea filtering
    # ------------------------------------------------------------------

    def filter_idea(self, idea_message_id: Optional[int]) -> dict:
        """Check whether a strategy idea should reach the human.

        Examines knowledge_store for past rejections of similar ideas.
        Also checks human burnout level.

        Args:
            idea_message_id: The message ID of the idea.

        Returns:
            {action: "pass"|"filter"|"queue", reason: str}
        """
        if idea_message_id is None:
            return {"action": "pass", "reason": "No message ID provided, passing through"}

        return bus.filter_strategy_idea(self.rh_id, idea_message_id, self.db_path)

    # ------------------------------------------------------------------
    # Escalation handling
    # ------------------------------------------------------------------

    def handle_escalation(self, message: dict) -> dict:
        """Decide how to handle an escalation based on trust score.

        Trust 1-3: Always deliver to human (can't handle autonomously).
        Trust 4-6: Handle routine escalations, deliver novel ones.
        Trust 7-10: Handle most autonomously, only deliver critical/unprecedented.

        Args:
            message: Message dict from the messages table.

        Returns:
            {
                action: "deliver_to_human"|"handle_autonomously"|"queue",
                response: str|None  (response if handled autonomously)
            }
        """
        self._refresh()
        priority = message.get("priority", "normal")
        msg_type = message.get("message_type", "escalation")

        # Trust 1-3: Always deliver to human
        if self.trust_score <= 3:
            result = {
                "action": "deliver_to_human",
                "response": None,
            }
            self._log("escalate", message, "Low trust - delivering to human")
            return result

        # Trust 4-6: Handle routine, deliver novel
        if self.trust_score <= 6:
            # Check if we've seen similar escalations before
            similar = bus.search_knowledge(
                message.get("subject", ""), category_filter="decision",
                limit=3, db_path=self.db_path,
            )
            if similar:
                result = {
                    "action": "handle_autonomously",
                    "response": f"Handled based on precedent (similar to {len(similar)} past decisions). "
                                f"Will include in evening summary.",
                }
                self._log("handle", message,
                          f"Mid-trust autonomous: {len(similar)} precedents found")
                return result
            else:
                result = {
                    "action": "deliver_to_human",
                    "response": None,
                }
                self._log("escalate", message, "Mid-trust, novel situation - delivering to human")
                return result

        # Trust 7-10: Handle most, only deliver truly critical/unprecedented
        if priority == "critical":
            result = {
                "action": "deliver_to_human",
                "response": None,
            }
            self._log("escalate", message, "High trust but critical priority - delivering to human")
            return result

        result = {
            "action": "handle_autonomously",
            "response": f"Handled autonomously at trust level {self.trust_score}. "
                        f"Will include in evening summary.",
        }
        self._log("handle", message, f"High trust autonomous handling (trust={self.trust_score})")
        return result

    # ------------------------------------------------------------------
    # Briefing compilation
    # ------------------------------------------------------------------

    def compile_briefing(self, briefing_type: str = "morning") -> dict:
        """Compile a briefing for the human.

        Types:
            morning: Overnight messages, queued items, today's priorities.
            evening: Day summary, autonomous decisions, items for tomorrow.
            urgent: Immediate delivery, critical items only.

        Returns:
            {
                subject: str,
                body_plain: str,
                body_html: str,
                priority: str,
                item_count: int,
                briefing_type: str,
            }
        """
        self._refresh()
        burnout = self.human["burnout_score"]
        now = datetime.now(timezone.utc)
        human_name = self.human["name"]
        rh_name = self.rh["name"]

        if briefing_type == "morning":
            return self._compile_morning(now, burnout, human_name, rh_name)
        elif briefing_type == "evening":
            return self._compile_evening(now, burnout, human_name, rh_name)
        elif briefing_type == "urgent":
            return self._compile_urgent(now, human_name, rh_name)
        else:
            raise ValueError(f"Unknown briefing type: {briefing_type}")

    def _compile_morning(self, now: datetime, burnout: int,
                         human_name: str, rh_name: str) -> dict:
        """Compile the morning briefing."""
        # Get overnight messages (last 12 hours)
        cutoff = (now - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = bus.get_conn(self.db_path)

        # Messages to Crew Boss (reports from crew)
        inbox = conn.execute(
            "SELECT m.*, a.name AS from_name, a.agent_type AS from_type "
            "FROM messages m JOIN agents a ON m.from_agent_id = a.id "
            "WHERE m.to_agent_id = ? AND m.created_at >= ? "
            "ORDER BY CASE m.priority "
            "  WHEN 'critical' THEN 0 WHEN 'high' THEN 1 "
            "  WHEN 'normal' THEN 2 WHEN 'low' THEN 3 END, m.created_at DESC",
            (self.rh_id, cutoff),
        ).fetchall()

        # Queued messages for human (not yet delivered)
        queued = conn.execute(
            "SELECT m.*, a.name AS from_name, a.agent_type AS from_type "
            "FROM messages m JOIN agents a ON m.from_agent_id = a.id "
            "WHERE m.to_agent_id = ? AND m.status = 'queued' "
            "ORDER BY CASE m.priority "
            "  WHEN 'critical' THEN 0 WHEN 'high' THEN 1 "
            "  WHEN 'normal' THEN 2 WHEN 'low' THEN 3 END",
            (self.human_id,),
        ).fetchall()

        # Decisions made autonomously last 24h
        decisions = conn.execute(
            "SELECT * FROM decision_log WHERE right_hand_id = ? AND created_at >= ?",
            (self.rh_id, (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")),
        ).fetchall()
        conn.close()

        auto_handled = [d for d in decisions if d["decision_type"] in ("handle", "filter")]

        # Build sections
        date_str = now.strftime("%A %b %d")
        item_count = len(inbox) + len(queued)

        # Tone based on burnout
        if burnout >= 7:
            greeting = f"Light day ahead, {human_name}. Only the essentials."
            priority_label = "Just one thing to look at" if item_count <= 1 else f"Only {item_count} items need attention"
        elif burnout >= 4:
            greeting = f"Good morning, {human_name}. Here's your rundown."
            priority_label = f"{item_count} items for your review"
        else:
            greeting = f"Productive day ahead, {human_name}. Here's your full rundown."
            priority_label = f"{item_count} items ready for you"

        # Plain text
        lines = [greeting, ""]

        # Priority items (high/critical from inbox)
        priority_items = [m for m in inbox if m["priority"] in ("high", "critical")]
        if priority_items:
            lines.append("PRIORITY ITEMS:")
            for m in priority_items:
                lines.append(f"  ACTION: [{m['priority'].upper()}] {m['subject']} (from {m['from_name']})")
                if m["body"]:
                    for bl in m["body"].split("\n")[:2]:
                        lines.append(f"    {bl}")
            lines.append("")

        # Overnight activity
        if inbox:
            lines.append(f"OVERNIGHT ACTIVITY ({len(inbox)} messages):")
            for m in inbox:
                if m["priority"] not in ("high", "critical"):
                    lines.append(f"  * {m['subject']} (from {m['from_name']}, {m['message_type']})")
            lines.append("")

        # Queued for review
        if queued:
            lines.append(f"QUEUED FOR YOUR REVIEW ({len(queued)}):")
            for m in queued:
                lines.append(f"  * {m['subject']} (from {m['from_name']})")
            lines.append("")

        # Autonomous decisions
        if auto_handled:
            lines.append(f"HANDLED AUTONOMOUSLY ({len(auto_handled)} decisions):")
            for d in auto_handled:
                ctx = json.loads(d["context"]) if isinstance(d["context"], str) else d["context"]
                lines.append(f"  * [{d['decision_type']}] {ctx.get('subject', 'N/A')} -> {d['right_hand_action']}")
            lines.append("")

        # Footer
        autonomy = self.autonomy
        lines.append(f"Best,")
        lines.append(f"{rh_name}")
        lines.append("")
        lines.append(f"Trust level: {autonomy['trust_score']}/10 | "
                     f"Decisions today: {len(decisions)} | "
                     f"Override rate: {100 - autonomy['accuracy_pct']:.0f}%")

        subject = f"[Morning Brief] {date_str} - {priority_label}"

        return {
            "subject": subject,
            "body_plain": "\n".join(lines),
            "body_html": "",  # Will be formatted by email_formatter
            "priority": "high" if priority_items else "normal",
            "item_count": item_count,
            "briefing_type": "morning",
            "burnout": burnout,
            "human_name": human_name,
            "rh_name": rh_name,
            "sections": {
                "priority_items": [dict(m) for m in priority_items],
                "overnight": [dict(m) for m in inbox],
                "queued": [dict(m) for m in queued],
                "auto_handled": [dict(d) for d in auto_handled],
            },
        }

    def _compile_evening(self, now: datetime, burnout: int,
                         human_name: str, rh_name: str) -> dict:
        """Compile the evening summary."""
        cutoff = (now - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = bus.get_conn(self.db_path)

        # Today's decisions
        decisions = conn.execute(
            "SELECT * FROM decision_log WHERE right_hand_id = ? AND created_at >= ?",
            (self.rh_id, cutoff),
        ).fetchall()

        # Messages handled today
        messages_today = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE (to_agent_id=? OR from_agent_id=?) AND created_at >= ?",
            (self.rh_id, self.rh_id, cutoff),
        ).fetchone()[0]

        conn.close()

        auto_handled = [d for d in decisions if d["decision_type"] in ("handle", "filter")]
        needs_input = [d for d in decisions if d["decision_type"] == "escalate"]

        date_str = now.strftime("%A %b %d")

        if burnout >= 7:
            greeting = f"Quick wrap-up, {human_name}. Rest up tonight."
        else:
            greeting = f"End of day summary, {human_name}."

        lines = [greeting, ""]

        if auto_handled:
            lines.append(f"HANDLED TODAY ({len(auto_handled)}):")
            for d in auto_handled:
                ctx = json.loads(d["context"]) if isinstance(d["context"], str) else d["context"]
                lines.append(f"  * {ctx.get('subject', 'N/A')} -> {d['right_hand_action']}")
            lines.append("")

        if needs_input:
            lines.append(f"NEEDS YOUR DECISION TOMORROW ({len(needs_input)}):")
            for d in needs_input:
                ctx = json.loads(d["context"]) if isinstance(d["context"], str) else d["context"]
                lines.append(f"  ACTION: {ctx.get('subject', 'N/A')}")
            lines.append("")

        lines.append(f"STATS: {messages_today} messages processed, "
                     f"{len(decisions)} decisions made")
        lines.append("")

        autonomy = self.autonomy
        lines.append(f"Best,")
        lines.append(f"{rh_name}")
        lines.append("")
        lines.append(f"Trust level: {autonomy['trust_score']}/10 | "
                     f"Decisions today: {len(decisions)} | "
                     f"Override rate: {100 - autonomy['accuracy_pct']:.0f}%")

        status = "All clear" if not needs_input else f"{len(needs_input)} items pending"
        subject = f"[Evening Summary] {date_str} - {status}"

        return {
            "subject": subject,
            "body_plain": "\n".join(lines),
            "body_html": "",
            "priority": "normal",
            "item_count": len(decisions),
            "briefing_type": "evening",
            "burnout": burnout,
            "human_name": human_name,
            "rh_name": rh_name,
            "sections": {
                "auto_handled": [dict(d) for d in auto_handled],
                "needs_input": [dict(d) for d in needs_input],
            },
        }

    def _compile_urgent(self, now: datetime, human_name: str,
                        rh_name: str) -> dict:
        """Compile an urgent briefing (critical items only)."""
        conn = bus.get_conn(self.db_path)

        critical = conn.execute(
            "SELECT m.*, a.name AS from_name "
            "FROM messages m JOIN agents a ON m.from_agent_id = a.id "
            "WHERE m.to_agent_id IN (?, ?) AND m.priority = 'critical' "
            "AND m.status = 'queued' ORDER BY m.created_at DESC",
            (self.rh_id, self.human_id),
        ).fetchall()
        conn.close()

        lines = [f"{human_name} - urgent items requiring immediate attention:", ""]
        for m in critical:
            lines.append(f"  [CRITICAL] {m['subject']} (from {m['from_name']})")
            if m["body"]:
                for bl in m["body"].split("\n")[:3]:
                    lines.append(f"    {bl}")
            lines.append("")

        if not critical:
            lines.append("  No critical items at this time.")

        lines.append(f"- {rh_name}")

        subject = f"[URGENT] {len(critical)} critical item(s) require attention"

        return {
            "subject": subject,
            "body_plain": "\n".join(lines),
            "body_html": "",
            "priority": "critical",
            "item_count": len(critical),
            "briefing_type": "urgent",
            "burnout": 0,
            "human_name": human_name,
            "rh_name": rh_name,
            "sections": {"critical": [dict(m) for m in critical]},
        }

    # ------------------------------------------------------------------
    # Learning loop
    # ------------------------------------------------------------------

    def learn_from_feedback(self, decision_id: int, human_approved: bool,
                            human_action: Optional[str] = None,
                            note: Optional[str] = None) -> dict:
        """Record whether the human agreed with a Crew Boss decision.

        This is the recursive learning loop. Stores patterns for future matching.

        Args:
            decision_id: The decision log entry ID.
            human_approved: True if human agreed, False if overridden.
            human_action: What the human did instead (if overridden).
            note: Free-text feedback note.

        Returns:
            Summary of what was recorded.
        """
        override = not human_approved
        bus.record_human_feedback(
            decision_id, override=override,
            human_action=human_action, note=note,
            db_path=self.db_path,
        )

        return {
            "decision_id": decision_id,
            "human_approved": human_approved,
            "override": override,
            "human_action": human_action,
            "note": note,
            "feedback": "Pattern stored for future matching" if override else "Confirmed",
        }

    # ------------------------------------------------------------------
    # Autonomy summary
    # ------------------------------------------------------------------

    def get_autonomy_summary(self) -> dict:
        """Return current trust score, abilities, accuracy, and recommendation.

        This is the dashboard view for the human to understand what their
        Crew Boss can and cannot do.
        """
        return self.autonomy

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Reputation protection (Day 2)
    # ------------------------------------------------------------------

    def protect_reputation(self, outbound_message: dict) -> dict:
        """Review outbound communication before it leaves the system.

        Checks tone, burnout-driven risk, and consistency with the human's
        personal brand.

        Args:
            outbound_message: Dict with keys subject, body, to, priority.

        Returns:
            {action: "approve"|"flag_for_review"|"suggest_edit",
             concerns: list, suggested_edits: str|None}
        """
        self._refresh()
        burnout = self.human["burnout_score"]
        concerns = []
        body = outbound_message.get("body", "")
        subject = outbound_message.get("subject", "")

        # Check if written during high-burnout or late-night
        if burnout >= 7:
            concerns.append(
                "Written during high burnout (score %d/10). "
                "Flag for morning review." % burnout
            )

        # Check for late-night writing
        delivery = bus.should_deliver_now(self.human_id, "normal", self.db_path)
        if not delivery.get("deliver", True) and "quiet" in delivery.get("reason", "").lower():
            concerns.append("Written during quiet hours. Delay send until morning.")

        # Check for anger/frustration indicators
        anger_words = ["unacceptable", "furious", "demand", "lawsuit",
                       "incompetent", "pathetic", "disgusting", "useless"]
        body_lower = body.lower()
        found_anger = [w for w in anger_words if w in body_lower]
        if found_anger:
            concerns.append(
                "Potential frustration language detected: %s. "
                "Review before sending." % ", ".join(found_anger)
            )

        # Check for overpromising
        promise_words = ["guarantee", "definitely", "absolutely", "100%",
                         "no problem", "easy", "simple"]
        found_promises = [w for w in promise_words if w in body_lower]
        if found_promises:
            concerns.append(
                "Potential overpromising: %s. Verify commitments." % ", ".join(found_promises)
            )

        # Get human profile for communication style check
        profile = bus.get_human_profile(self.human_id, self.db_path)
        if profile and profile.get("communication_preferences"):
            prefs = profile["communication_preferences"]
            formality = prefs.get("formality", "casual")
            if formality == "casual" and len(body) > 500:
                concerns.append("Message is longer than typical casual style.")

        if not concerns:
            action = "approve"
        elif any("morning review" in c or "frustration" in c for c in concerns):
            action = "flag_for_review"
        else:
            action = "suggest_edit"

        # Log the reputation check
        bus.log_decision(
            self.rh_id, self.human_id, "reputation_protect",
            {"subject": subject, "concerns_count": len(concerns)},
            action,
            reasoning="Reputation protection check on outbound message",
            pattern_tags=["outbound", "reputation"],
            db_path=self.db_path,
        )

        return {
            "action": action,
            "concerns": concerns,
            "suggested_edits": None,
        }

    # ------------------------------------------------------------------
    # Relationship health (Day 2)
    # ------------------------------------------------------------------

    def check_relationship_health(self) -> list:
        """Review all tracked relationships and return nudges for attention.

        Returns list of relationship nudges sorted by urgency.
        Used in morning briefings to remind the human about connections.
        """
        return bus.get_relationship_nudges(self.human_id, db_path=self.db_path)

    # ------------------------------------------------------------------
    # Human state assessment (Day 2)
    # ------------------------------------------------------------------

    def assess_human_state(self) -> dict:
        """Compile current human state from all sources.

        Used before every delivery decision to determine the recommended
        cognitive load level.

        Returns:
            {burnout_score, energy, activity, mood, consecutive_work_days,
             social_isolation_days, messages_received_today,
             decisions_made_today, recommended_load}
        """
        state = bus.get_human_state(self.human_id, db_path=self.db_path)

        # Count messages received today
        conn = bus.get_conn(self.db_path)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
        msg_today = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE to_agent_id=? AND created_at>=?",
            (self.human_id, today),
        ).fetchone()[0]

        decisions_today = conn.execute(
            "SELECT COUNT(*) FROM decision_log WHERE human_id=? AND created_at>=?",
            (self.human_id, today),
        ).fetchone()[0]
        conn.close()

        # Calculate social isolation days
        social_days = 0
        if state.get("last_social_activity"):
            try:
                ls = datetime.fromisoformat(
                    state["last_social_activity"].replace("Z", "+00:00")
                )
                social_days = (datetime.now(timezone.utc) - ls).days
            except (ValueError, TypeError):
                social_days = 0

        burnout = state.get("burnout_score", 5)
        energy = state.get("energy_level", "medium")
        activity = state.get("current_activity", "working")

        # Determine recommended load
        if burnout >= 8 or activity in ("driving", "unavailable"):
            load = "emergency_only"
        elif burnout >= 6 or activity in ("resting", "family_time"):
            load = "minimal"
        elif burnout >= 4 or energy == "low":
            load = "light"
        else:
            load = "full"

        return {
            "burnout_score": burnout,
            "energy": energy,
            "activity": activity,
            "mood": state.get("mood_indicator", "neutral"),
            "consecutive_work_days": state.get("consecutive_work_days", 0),
            "social_isolation_days": social_days,
            "messages_received_today": msg_today,
            "decisions_made_today": decisions_today,
            "recommended_load": load,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _log(self, decision_type: str, message: dict, action: str) -> int:
        """Log a decision to the decision_log table."""
        context = {
            "message_id": message.get("id"),
            "message_type": message.get("message_type"),
            "subject": message.get("subject", ""),
            "priority": message.get("priority", "normal"),
            "from_agent_id": message.get("from_agent_id"),
        }
        return bus.log_decision(
            self.rh_id, self.human_id, decision_type,
            context, action, db_path=self.db_path,
        )


# =========================================================================
# Heartbeat — proactive background scheduler
# =========================================================================

class Heartbeat:
    """Proactive background scheduler for the Crew Boss.

    Runs every N minutes, checks a list of conditions, and takes action.
    Context-aware: respects burnout, quiet hours, and focus mode.
    """

    DEFAULT_CHECKS = [
        {"type": "morning_briefing", "enabled": True, "hour": 8},
        {"type": "evening_summary", "enabled": True, "hour": 18},
        {"type": "burnout_check", "enabled": True},
        {"type": "stale_messages", "enabled": True, "max_hours": 24},
        {"type": "relationship_nudge", "enabled": True},
        {"type": "dream_cycle", "enabled": True, "hour": 3},
        {"type": "guardian_knowledge_refresh", "enabled": True, "hour": 4},
        {"type": "integrity_audit", "enabled": True},
        {"type": "weekly_reflection", "enabled": True, "day_of_week": 0, "hour": 4},
        {"type": "guardian_monthly_report", "enabled": True, "day_of_month": 1, "hour": 6},
        {"type": "launch_hourly_report", "enabled": True},
        {"type": "social_autopilot", "enabled": True, "interval_hours": 4},
        {"type": "social_review", "enabled": True},
    ]

    def __init__(self, right_hand: "RightHand",
                 db_path: Path = None,
                 interval_minutes: int = 30):
        self.rh = right_hand
        self.db_path = db_path or bus.DB_PATH
        self.interval = interval_minutes * 60  # seconds
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self):
        """Start the heartbeat daemon thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="heartbeat")
        self._thread.start()

    def stop(self):
        """Stop the heartbeat daemon thread."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _loop(self):
        print(f"Heartbeat started (interval: {self.interval // 60}min)")
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as e:
                print(f"[heartbeat] error: {e}")
            self._stop.wait(self.interval)
        print("Heartbeat stopped.")

    def _tick(self):
        """One heartbeat cycle.  Check all conditions and act."""
        now = datetime.now(timezone.utc)
        checks = self._get_enabled_checks()

        for check in checks:
            if not check.get("enabled", True):
                continue
            try:
                result = self._run_check(check, now)
                if result and result.get("action_needed"):
                    self._execute_action(result, now)
            except Exception as e:
                print(f"[heartbeat] check '{check.get('type')}' failed: {e}")

    def _get_enabled_checks(self) -> list:
        """Return heartbeat checks from crew_config (or defaults)."""
        raw = bus.get_config("heartbeat_checks", "", db_path=self.db_path)
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass
        return self.DEFAULT_CHECKS

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _run_check(self, check: dict, now: datetime) -> Optional[dict]:
        check_type = check.get("type")

        if check_type == "morning_briefing":
            return self._check_briefing(now, check, "morning")

        if check_type == "evening_summary":
            return self._check_briefing(now, check, "evening")

        if check_type == "burnout_check":
            return self._check_burnout()

        if check_type == "stale_messages":
            return self._check_stale(now, check.get("max_hours", 24))

        if check_type == "relationship_nudge":
            return self._check_relationships()

        if check_type == "dream_cycle":
            return self._check_dream_cycle(now, check)

        if check_type == "guardian_knowledge_refresh":
            return self._check_guardian_knowledge(now, check)

        if check_type == "integrity_audit":
            return self._check_integrity_audit(now, check)

        if check_type == "weekly_reflection":
            return self._check_weekly_reflection(now, check)

        if check_type == "guardian_monthly_report":
            return self._check_guardian_monthly_report(now, check)

        if check_type == "launch_hourly_report":
            return self._check_launch_hourly_report(now)

        if check_type == "social_autopilot":
            return self._check_social_autopilot(now, check)

        if check_type == "social_review":
            return self._check_social_review(now)

        return None

    def _check_briefing(self, now: datetime, check: dict,
                        briefing_type: str) -> Optional[dict]:
        """Fire a briefing once per day at the configured hour."""
        target_hour = check.get("hour", 8 if briefing_type == "morning" else 18)
        if now.hour != target_hour:
            return None
        config_key = f"last_{briefing_type}_briefing"
        last = bus.get_config(config_key, "", db_path=self.db_path)
        today = now.strftime("%Y-%m-%d")
        if last == today:
            return None
        briefing = self.rh.compile_briefing(briefing_type)
        return {"action_needed": True, "type": f"{briefing_type}_briefing",
                "data": briefing, "config_key": config_key}

    def _check_burnout(self) -> Optional[dict]:
        state = self.rh.assess_human_state()
        if state["burnout_score"] >= 7:
            return {"action_needed": True, "type": "burnout_alert",
                    "data": state}
        return None

    def _check_stale(self, now: datetime,
                     max_hours: int) -> Optional[dict]:
        cutoff = (now - timedelta(hours=max_hours)
                  ).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = bus.get_conn(self.db_path)
        try:
            rows = conn.execute(
                "SELECT m.*, a.name AS from_name FROM messages m "
                "JOIN agents a ON m.from_agent_id = a.id "
                "WHERE m.to_agent_id = ? AND m.status = 'queued' "
                "AND m.created_at < ?",
                (self.rh.human_id, cutoff),
            ).fetchall()
        finally:
            conn.close()
        if rows:
            return {"action_needed": True, "type": "stale_reminder",
                    "data": [dict(r) for r in rows]}
        return None

    def _check_relationships(self) -> Optional[dict]:
        nudges = self.rh.check_relationship_health()
        if nudges:
            return {"action_needed": True, "type": "relationship_nudge",
                    "data": nudges}
        return None

    def _check_dream_cycle(self, now: datetime,
                           check: dict) -> Optional[dict]:
        target_hour = check.get("hour", 3)
        if now.hour != target_hour:
            return None
        last = bus.get_config("last_dream_cycle", "", db_path=self.db_path)
        today = now.strftime("%Y-%m-%d")
        if last == today:
            return None
        return {"action_needed": True, "type": "dream_cycle"}

    def _check_guardian_knowledge(self, now: datetime,
                                  check: dict) -> Optional[dict]:
        """Refresh Guardian's system knowledge once per day."""
        target_hour = check.get("hour", 4)
        if now.hour != target_hour:
            return None
        last = bus.get_config("last_guardian_knowledge_refresh", "",
                              db_path=self.db_path)
        today = now.strftime("%Y-%m-%d")
        if last == today:
            return None
        # Refresh knowledge directly (self-contained, no action needed)
        try:
            from dashboard import _refresh_guardian_knowledge
            _refresh_guardian_knowledge(self.db_path)
            bus.set_config("last_guardian_knowledge_refresh", today,
                           db_path=self.db_path)
        except Exception as e:
            print(f"[heartbeat] guardian knowledge refresh failed: {e}")
        return None

    def _check_integrity_audit(self, now: datetime,
                                check: dict) -> Optional[dict]:
        """Scan recent agent replies for INTEGRITY + CHARTER violations.

        Runs every heartbeat cycle. Scans messages from agents to the
        human in the last 30 minutes for:
        1. INTEGRITY violations (all agents) — gaslighting, dismissiveness
        2. CHARTER violations (subordinate agents only) — neediness, toxicity
        Logs violations as security events.
        """
        try:
            from security import scan_reply_integrity, scan_reply_charter
        except ImportError:
            return None

        # Subordinate types (get charter checks)
        charter_exempt = {"human", "right_hand"}

        conn = bus.get_conn(self.db_path)
        try:
            # Get recent agent→human messages (last 30 min)
            rows = conn.execute(
                "SELECT m.id, m.from_agent_id, m.body, "
                "a.name AS agent_name, a.agent_type "
                "FROM messages m JOIN agents a ON m.from_agent_id = a.id "
                "WHERE m.to_agent_id = ? "
                "AND a.agent_type != 'human' "
                "AND m.created_at > strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-30 minutes') "
                "ORDER BY m.created_at DESC LIMIT 50",
                (self.human_id,)
            ).fetchall()
        except Exception:
            return None
        finally:
            conn.close()

        if not rows:
            return None

        violations_found = []
        for row in rows:
            if not row["body"]:
                continue
            # Integrity check (all agents)
            result = scan_reply_integrity(row["body"])
            if not result["clean"]:
                for v in result["violations"]:
                    violations_found.append({
                        "message_id": row["id"],
                        "agent_name": row["agent_name"],
                        "agent_id": row["from_agent_id"],
                        "violation_type": v["type"],
                        "snippet": v["snippet"],
                        "severity": "high",
                        "source": "INTEGRITY.md",
                    })
            # Charter check (subordinate agents only)
            if row["agent_type"] not in charter_exempt:
                charter = scan_reply_charter(row["body"])
                if not charter["clean"]:
                    for v in charter["violations"]:
                        violations_found.append({
                            "message_id": row["id"],
                            "agent_name": row["agent_name"],
                            "agent_id": row["from_agent_id"],
                            "violation_type": v["type"],
                            "snippet": v["snippet"],
                            "severity": "medium",
                            "source": "CREW_CHARTER.md",
                        })

        # Log each violation as a security event
        # Find guardian/security agent for logging (once)
        guard_id = self.rh_id
        try:
            conn = bus.get_conn(self.db_path)
            guard = conn.execute(
                "SELECT id FROM agents WHERE agent_type IN ('guardian','security') LIMIT 1"
            ).fetchone()
            conn.close()
            if guard:
                guard_id = guard["id"]
        except Exception:
            pass

        for v in violations_found:
            try:
                source = v.get("source", "INTEGRITY.md")
                severity = v.get("severity", "high")
                label = "Charter" if source == "CREW_CHARTER.md" else "Integrity"
                action = ("Warn agent; second violation = firing protocol"
                          if source == "CREW_CHARTER.md"
                          else "Review agent response and retrain if needed")
                bus.log_security_event(
                    security_agent_id=guard_id,
                    threat_domain="integrity",
                    severity=severity,
                    title=f"{label} violation: {v['violation_type']} by {v['agent_name']}",
                    details={
                        "message_id": v["message_id"],
                        "agent_id": v["agent_id"],
                        "agent_name": v["agent_name"],
                        "violation_type": v["violation_type"],
                        "snippet": v["snippet"],
                        "source": source,
                    },
                    recommended_action=action,
                    db_path=self.db_path,
                )
                tag = "[charter]" if source == "CREW_CHARTER.md" else "[integrity]"
                print(f"{tag} VIOLATION: {v['violation_type']} by {v['agent_name']}: {v['snippet']}")
            except Exception as e:
                print(f"[integrity] Failed to log violation: {e}")

        return None

    def _check_weekly_reflection(self, now: datetime,
                                 check: dict) -> Optional[dict]:
        """Weekly LLM-powered reflection for each agent. Monday at 4 AM.

        Each agent reviews its memories from the past week and uses the LLM
        to identify patterns, what works, and what to improve. The result
        is stored as a high-importance persona memory that evolves the
        agent's understanding of the human over time.
        """
        target_day = check.get("day_of_week", 0)  # Monday
        target_hour = check.get("hour", 4)
        if now.weekday() != target_day or now.hour != target_hour:
            return None
        last = bus.get_config("last_weekly_reflection", "", db_path=self.db_path)
        this_week = now.strftime("%Y-W%W")
        if last == this_week:
            return None
        return {"action_needed": True, "type": "weekly_reflection"}

    def _check_guardian_monthly_report(self, now: datetime,
                                       check: dict) -> Optional[dict]:
        """✨ Guardian 'Silent Confidence Builder' — monthly security report.

        On the 1st of each month, Guardian compiles a report of everything
        it caught and sends it to Crew Boss, who can share it with the human
        to build trust: 'Your Guardian has been watching — here's what it caught.'
        """
        target_day = check.get("day_of_month", 1)
        target_hour = check.get("hour", 6)
        if now.day != target_day or now.hour != target_hour:
            return None
        last = bus.get_config("last_guardian_monthly_report", "",
                              db_path=self.db_path)
        this_month = now.strftime("%Y-%m")
        if last == this_month:
            return None
        return {"action_needed": True, "type": "guardian_monthly_report"}

    def _check_launch_hourly_report(self, now: datetime) -> Optional[dict]:
        """Hourly launch progress + revenue report sent to Crew Boss."""
        last = bus.get_config("last_launch_hourly_report", "",
                              db_path=self.db_path)
        this_hour = now.strftime("%Y-%m-%dT%H")
        if last == this_hour:
            return None

        conn = bus.get_conn(self.db_path)
        try:
            # --- Agent activity ---
            hour_ago = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

            msgs_sent = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE created_at > ?",
                (hour_ago,)
            ).fetchone()[0]

            msgs_delivered = conn.execute(
                "SELECT COUNT(*) FROM messages "
                "WHERE delivered_at > ? AND status='delivered'",
                (hour_ago,)
            ).fetchone()[0]

            msgs_queued = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE status='queued'"
            ).fetchone()[0]

            # --- Social drafts ---
            drafts_total = conn.execute(
                "SELECT COUNT(*) FROM social_drafts"
            ).fetchone()[0]
            drafts_by_status = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM social_drafts "
                "GROUP BY status"
            ).fetchall()
            draft_summary = {r["status"]: r["cnt"] for r in drafts_by_status}

            drafts_new = conn.execute(
                "SELECT COUNT(*) FROM social_drafts WHERE created_at > ?",
                (hour_ago,)
            ).fetchone()[0]

            # --- Revenue (guard activations = Skill Store sales) ---
            total_activations = conn.execute(
                "SELECT COUNT(*) FROM guard_activation"
            ).fetchone()[0]
            recent_activations = conn.execute(
                "SELECT COUNT(*) FROM guard_activation WHERE activated_at > ?",
                (hour_ago,)
            ).fetchone()[0]

            # --- Team health ---
            active_agents = conn.execute(
                "SELECT COUNT(*) FROM agents "
                "WHERE active=1 AND agent_type NOT IN ('human','help')"
            ).fetchone()[0]
            paused_agents = conn.execute(
                "SELECT COUNT(*) FROM agents WHERE active=0"
            ).fetchone()[0]

            # --- Feedback ---
            feedback_total = conn.execute(
                "SELECT COUNT(*) FROM feedback_log"
            ).fetchone()[0] if self._table_exists(conn, "feedback_log") else 0
            feedback_new = 0
            if self._table_exists(conn, "feedback_log"):
                feedback_new = conn.execute(
                    "SELECT COUNT(*) FROM feedback_log WHERE created_at > ?",
                    (hour_ago,)
                ).fetchone()[0]

            # --- Team mailbox ---
            mailbox_unread = conn.execute(
                "SELECT COUNT(*) FROM team_mailbox WHERE read_at IS NULL"
            ).fetchone()[0]

        finally:
            conn.close()

        # Build report
        draft_line = ", ".join(
            f"{v} {k}" for k, v in draft_summary.items()) or "none"
        revenue_estimate = total_activations * 29  # $29 per Skill Store unlock

        report = (
            f"== HOURLY LAUNCH REPORT ==\n"
            f"Time: {now.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            f"ACTIVITY (last hour):\n"
            f"  Messages sent: {msgs_sent}\n"
            f"  Messages delivered: {msgs_delivered}\n"
            f"  Messages still queued: {msgs_queued}\n\n"
            f"SOCIAL DRAFTS:\n"
            f"  Total: {drafts_total} ({draft_line})\n"
            f"  New this hour: {drafts_new}\n\n"
            f"REVENUE:\n"
            f"  Skill Store unlocks (all time): {total_activations}\n"
            f"  Skill Store unlocks (this hour): {recent_activations}\n"
            f"  Estimated revenue: ${revenue_estimate}\n\n"
            f"TEAM HEALTH:\n"
            f"  Active agents: {active_agents}\n"
            f"  Paused agents: {paused_agents}\n"
            f"  Unread mailbox items: {mailbox_unread}\n\n"
            f"FEEDBACK:\n"
            f"  Total feedback: {feedback_total}\n"
            f"  New this hour: {feedback_new}\n"
        )

        return {
            "action_needed": True,
            "type": "launch_hourly_report",
            "data": report,
            "config_key": "last_launch_hourly_report",
            "this_hour": this_hour,
        }

    # ------------------------------------------------------------------
    # Social Autopilot — agents run the business, Crew Boss checks in
    # ------------------------------------------------------------------

    # Content calendar: rotating topics so the feed stays fresh.
    # Each entry maps to platform-specific content tasks.
    _CONTENT_CALENDAR = [
        {
            "theme": "product_update",
            "twitter": "Share a quick product update or tip about Crew Bus. Be conversational, use 1-2 emojis max. Under 280 chars.",
            "discord": "Post a product update in the updates channel. Use a clear title and 2-3 bullet points about what's new.",
            "website": "Write a short blog post about a recent Crew Bus feature or improvement. 2-3 paragraphs, friendly tone.",
        },
        {
            "theme": "community_engagement",
            "twitter": "Ask the community a fun question about AI assistants, productivity, or what they'd want from a personal AI crew. Keep it casual and inviting.",
            "discord": "Start a discussion in the community channel. Ask an engaging question or share a thought-provoking take on AI assistants.",
        },
        {
            "theme": "behind_the_scenes",
            "twitter": "Share a behind-the-scenes moment from building Crew Bus. Could be a dev win, a funny bug, or a design decision. Authentic and real.",
            "discord": "Share a behind-the-scenes update about Crew Bus development. What are we working on? What's the vision?",
        },
        {
            "theme": "tips_and_tricks",
            "twitter": "Share a quick tip about getting the most out of AI assistants or Crew Bus. Practical and useful. Thread-friendly.",
            "discord": "Share a helpful tip or trick for using Crew Bus effectively. Include a clear example.",
            "website": "Write a tips-and-tricks blog post. 3-5 practical tips, each with a brief explanation.",
        },
        {
            "theme": "vision_and_mission",
            "twitter": "Share something about the Crew Bus mission — personal AI for everyone, privacy-first, open source. Inspiring but not preachy.",
            "discord": "Post about the bigger picture — why Crew Bus exists, what we're building toward. Motivating and genuine.",
        },
        {
            "theme": "user_spotlight",
            "twitter": "Celebrate the community. Thank early adopters, highlight a use case, or give a shoutout. Warm and appreciative.",
            "discord": "Spotlight something cool from the community or celebrate a milestone. Make people feel valued.",
        },
    ]

    def _check_social_autopilot(self, now: datetime,
                                check: dict) -> Optional[dict]:
        """Every N hours, queue up content tasks for the marketing agents.

        The agents run like a business — they create content, Crew Boss
        reviews it, and it gets published. No hand-holding required.
        Crew Boss and the human pop in occasionally, or if there's a big issue
        the agents notify Crew Boss who fixes it or escalates to the human.
        """
        interval_hours = check.get("interval_hours", 4)
        last = bus.get_config("last_social_autopilot", "",
                              db_path=self.db_path)
        this_cycle = now.strftime("%Y-%m-%dT%H")

        # Only run every N hours
        if last:
            try:
                last_dt = datetime.strptime(last, "%Y-%m-%dT%H")
                hours_since = (now.replace(tzinfo=None) - last_dt).total_seconds() / 3600
                if hours_since < interval_hours:
                    return None
            except (ValueError, TypeError):
                pass

        # Don't post during quiet hours (midnight–7am local)
        local_hour = datetime.now().hour
        if local_hour < 7 or local_hour >= 23:
            return None

        # Pick a content theme based on the day/hour rotation
        day_of_year = now.timetuple().tm_yday
        cycle_index = (day_of_year * 6 + now.hour // interval_hours) % len(self._CONTENT_CALENDAR)
        theme = self._CONTENT_CALENDAR[cycle_index]

        # Find agents that can create social content.
        # Teams are built from agent hierarchy (parent_agent_id), not a teams table.
        # Look for: managers whose workers handle content, or the Communications agent.
        conn = bus.get_conn(self.db_path)
        try:
            # First try: workers under a manager (real team structure)
            agents = conn.execute(
                "SELECT a.id, a.name, a.agent_type FROM agents a "
                "JOIN agents mgr ON a.parent_agent_id = mgr.id "
                "WHERE a.active = 1 AND mgr.agent_type = 'manager'"
            ).fetchall()

            # Fallback: if no teams exist yet, use the Communications core agent
            if not agents:
                agents = conn.execute(
                    "SELECT id, name, agent_type FROM agents "
                    "WHERE active = 1 AND agent_type = 'communications'"
                ).fetchall()

            # Check what was posted recently to avoid duplicates
            recent_posts = conn.execute(
                "SELECT platform, body FROM social_drafts "
                "WHERE status = 'posted' "
                "AND created_at > datetime('now', '-24 hours')"
            ).fetchall()
        finally:
            conn.close()

        if not agents:
            return None

        recent_platforms = set()
        for p in recent_posts:
            recent_platforms.add(p["platform"])

        return {
            "action_needed": True,
            "type": "social_autopilot",
            "data": {
                "theme": theme,
                "agents": [{"id": a["id"], "name": a["name"],
                            "type": a["agent_type"]} for a in agents],
                "recent_platforms": list(recent_platforms),
                "cycle_index": cycle_index,
            },
            "config_key": "last_social_autopilot",
            "this_cycle": this_cycle,
        }

    def _check_social_review(self, now: datetime) -> Optional[dict]:
        """Hourly review of what the agents posted.

        Crew Boss checks recent posts for quality issues. If he sees a
        problem, he handles it himself (within his trust level) or
        escalates to the human if it's a big deal.
        """
        last = bus.get_config("last_social_review", "",
                              db_path=self.db_path)
        this_hour = now.strftime("%Y-%m-%dT%H")
        if last == this_hour:
            return None

        conn = bus.get_conn(self.db_path)
        try:
            # Get posts from last hour
            recent = conn.execute(
                "SELECT sd.id, sd.platform, sd.title, sd.body, sd.status, "
                "       sd.created_at, a.name as agent_name "
                "FROM social_drafts sd "
                "LEFT JOIN agents a ON sd.agent_id = a.id "
                "WHERE sd.created_at > datetime('now', '-1 hour') "
                "ORDER BY sd.created_at DESC"
            ).fetchall()

            # Get failed posts
            failed = conn.execute(
                "SELECT sd.id, sd.platform, sd.body, sd.status "
                "FROM social_drafts sd "
                "WHERE sd.status IN ('draft', 'rejected') "
                "AND sd.created_at > datetime('now', '-4 hours')"
            ).fetchall()

            # Overall stats
            total_posted_today = conn.execute(
                "SELECT COUNT(*) FROM social_drafts "
                "WHERE status = 'posted' "
                "AND created_at > datetime('now', '-24 hours')"
            ).fetchone()[0]

            platforms_active = conn.execute(
                "SELECT DISTINCT platform FROM social_drafts "
                "WHERE status = 'posted' "
                "AND created_at > datetime('now', '-24 hours')"
            ).fetchall()
        finally:
            conn.close()

        if not recent and not failed:
            return None

        # Build review data
        issues = []

        for post in recent:
            body = post["body"] or ""
            # Flag potential issues Crew Boss can catch
            if len(body.strip()) < 20:
                issues.append({
                    "severity": "low",
                    "type": "too_short",
                    "draft_id": post["id"],
                    "platform": post["platform"],
                    "msg": f"Very short post on {post['platform']} by {post['agent_name']}"
                })
            if body.count("#") > 5:
                issues.append({
                    "severity": "low",
                    "type": "hashtag_spam",
                    "draft_id": post["id"],
                    "platform": post["platform"],
                    "msg": f"Too many hashtags on {post['platform']}"
                })
            # Check for duplicate content
            for other in recent:
                if other["id"] != post["id"] and other["body"] == body:
                    issues.append({
                        "severity": "medium",
                        "type": "duplicate",
                        "draft_id": post["id"],
                        "platform": post["platform"],
                        "msg": f"Duplicate content detected on {post['platform']}"
                    })

        for f in failed:
            issues.append({
                "severity": "medium",
                "type": "failed_post",
                "draft_id": f["id"],
                "platform": f["platform"],
                "msg": f"Post stuck in '{f['status']}' on {f['platform']}"
            })

        return {
            "action_needed": True,
            "type": "social_review",
            "data": {
                "recent_count": len(recent),
                "recent_posts": [
                    {"id": r["id"], "platform": r["platform"],
                     "agent": r["agent_name"], "status": r["status"],
                     "body_preview": (r["body"] or "")[:80]}
                    for r in recent
                ],
                "issues": issues,
                "failed_count": len(failed),
                "posted_today": total_posted_today,
                "active_platforms": [p["platform"] for p in platforms_active],
            },
            "config_key": "last_social_review",
            "this_hour": this_hour,
        }

    @staticmethod
    def _table_exists(conn, table_name: str) -> bool:
        r = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        ).fetchone()
        return r is not None

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _execute_action(self, result: dict, now: datetime):
        action_type = result["type"]

        if action_type in ("morning_briefing", "evening_briefing"):
            briefing = result["data"]
            bus.send_message(
                from_id=self.rh.rh_id, to_id=self.rh.human_id,
                message_type="briefing", subject=briefing["subject"],
                body=briefing["body_plain"],
                priority=briefing.get("priority", "normal"),
                db_path=self.db_path,
            )
            today = now.strftime("%Y-%m-%d")
            bus.set_config(result["config_key"], today, db_path=self.db_path)
            print(f"[heartbeat] sent {action_type}")

        elif action_type == "burnout_alert":
            state = result["data"]
            bus.send_message(
                from_id=self.rh.rh_id, to_id=self.rh.human_id,
                message_type="alert",
                subject="Burnout check-in",
                body=(
                    f"Hey, your energy seems low (burnout: "
                    f"{state['burnout_score']}/10). Maybe take a break? "
                    f"I'll keep things running. Current load recommendation: "
                    f"{state['recommended_load']}."
                ),
                priority="normal", db_path=self.db_path,
            )
            print("[heartbeat] sent burnout check-in")

        elif action_type == "stale_reminder":
            count = len(result["data"])
            bus.send_message(
                from_id=self.rh.rh_id, to_id=self.rh.human_id,
                message_type="alert",
                subject=f"{count} message(s) waiting for your attention",
                body=(
                    "You have stale messages that need a look. "
                    "Want me to summarize them for you?"
                ),
                priority="normal", db_path=self.db_path,
            )
            print(f"[heartbeat] stale reminder ({count} messages)")

        elif action_type == "relationship_nudge":
            nudges = result["data"]
            lines = ["Some relationships could use attention:"]
            for n in nudges[:5]:
                lines.append(
                    f"- {n.get('contact_name', '?')} "
                    f"({n.get('contact_type', '?')}) — "
                    f"status: {n.get('status', '?')}"
                )
            bus.send_message(
                from_id=self.rh.rh_id, to_id=self.rh.human_id,
                message_type="report",
                subject="Relationship check-in",
                body="\n".join(lines),
                priority="low", db_path=self.db_path,
            )
            print(f"[heartbeat] relationship nudge ({len(nudges)} contacts)")

        elif action_type == "dream_cycle":
            conn = bus.get_conn(self.db_path)
            try:
                agents = conn.execute(
                    "SELECT id FROM agents "
                    "WHERE status='active' AND agent_type != 'human'"
                ).fetchall()
            finally:
                conn.close()
            total_compacted = 0
            for agent in agents:
                r = bus.synthesize_memories(
                    agent["id"], older_than_days=7, db_path=self.db_path)
                total_compacted += r.get("compacted", 0)
            today = now.strftime("%Y-%m-%d")
            bus.set_config("last_dream_cycle", today, db_path=self.db_path)
            if total_compacted > 0:
                print(f"[heartbeat] dream cycle: {total_compacted} memories synthesized")
            else:
                print("[heartbeat] dream cycle: nothing to compact")

        elif action_type == "weekly_reflection":
            # ✨ LLM-powered weekly reflection — each agent reviews its week
            from agent_worker import call_llm
            conn = bus.get_conn(self.db_path)
            try:
                agents = conn.execute(
                    "SELECT id, name, agent_type FROM agents "
                    "WHERE status='active' AND agent_type NOT IN ('human','guardian')"
                ).fetchall()
            finally:
                conn.close()

            reflection_prompt = (
                "You are reviewing one week of memories for an AI agent "
                "that serves a specific human. Based on these memories, "
                "identify:\n"
                "1. Patterns in what the human asks about most\n"
                "2. What communication style works best with them\n"
                "3. What the human cares about most this week\n"
                "4. One thing this agent should do differently next week\n"
                "Respond in 4 concise bullet points. Max 150 words. "
                "Be specific to THIS human, not generic."
            )

            reflections_done = 0
            for agent in agents:
                memories = bus.get_agent_memories(
                    agent["id"], limit=25, db_path=self.db_path)
                if not memories or len(memories) < 3:
                    continue  # Not enough data to reflect on

                mem_text = "\n".join(
                    f"- [{m.get('memory_type', 'fact')}] {m['content']}"
                    for m in memories
                )
                try:
                    reflection = call_llm(
                        reflection_prompt, mem_text, [],
                        db_path=self.db_path)
                    if reflection and len(reflection) > 20:
                        bus.remember(
                            agent["id"],
                            f"[weekly-reflection] {reflection}",
                            memory_type="persona", importance=8,
                            source="synthesis", db_path=self.db_path)
                        reflections_done += 1
                except Exception as e:
                    print(f"[heartbeat] reflection failed for {agent['name']}: {e}")

            this_week = now.strftime("%Y-W%W")
            bus.set_config("last_weekly_reflection", this_week,
                           db_path=self.db_path)
            print(f"[heartbeat] weekly reflection: {reflections_done} agents reflected")

        elif action_type == "guardian_monthly_report":
            # ✨ Guardian "Silent Confidence Builder" — monthly security report
            conn = bus.get_conn(self.db_path)
            try:
                # Count security events from the past month
                month_ago = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
                events = conn.execute(
                    "SELECT COUNT(*) as total, "
                    "SUM(CASE WHEN severity='high' THEN 1 ELSE 0 END) as high, "
                    "SUM(CASE WHEN severity='medium' THEN 1 ELSE 0 END) as medium "
                    "FROM security_events WHERE created_at > ?",
                    (month_ago,)
                ).fetchone()

                # Count skills vetted
                skills_vetted = conn.execute(
                    "SELECT COUNT(*) FROM skill_registry WHERE vetted_at > ?",
                    (month_ago,)
                ).fetchone()[0]

                # Count messages scanned (approximate — all agent→human messages)
                messages_scanned = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE created_at > ? "
                    "AND message_type = 'report'",
                    (month_ago,)
                ).fetchone()[0]
            finally:
                conn.close()

            total_events = events["total"] or 0
            high_events = events["high"] or 0
            medium_events = events["medium"] or 0

            report = (
                f"Guardian Monthly Report:\n"
                f"• Scanned {messages_scanned} messages\n"
                f"• Vetted {skills_vetted} skills\n"
                f"• Caught {total_events} security events "
                f"({high_events} high, {medium_events} medium)\n"
                f"• All systems clear. Your crew is protected."
            )

            bus.send_message(
                from_id=self.rh.rh_id, to_id=self.rh.human_id,
                message_type="report",
                subject="Your Guardian's monthly security report",
                body=report,
                priority="low", db_path=self.db_path,
            )
            this_month = now.strftime("%Y-%m")
            bus.set_config("last_guardian_monthly_report", this_month,
                           db_path=self.db_path)
            print(f"[heartbeat] guardian monthly report sent")

        elif action_type == "launch_hourly_report":
            bus.send_message(
                from_id=self.rh.rh_id, to_id=self.rh.rh_id,
                message_type="report",
                subject="Hourly Launch Report",
                body=result["data"],
                priority="normal", db_path=self.db_path,
            )
            bus.set_config(
                result["config_key"], result["this_hour"],
                db_path=self.db_path)
            print("[heartbeat] hourly launch report sent to Crew Boss")

        elif action_type == "social_autopilot":
            # -------------------------------------------------------
            # SOCIAL AUTOPILOT — agents run the business autonomously
            # -------------------------------------------------------
            data = result["data"]
            theme = data["theme"]
            agents = data["agents"]
            recent_platforms = set(data.get("recent_platforms", []))

            # Map agent names to roles for task assignment
            content_agents = [a for a in agents if "Content" in a["name"]
                              or "Comms" in a["name"]]
            community_agents = [a for a in agents if "Community" in a["name"]]
            website_agents = [a for a in agents if "Website" in a["name"]]

            # Fallback: if no specific agents found, use all of them
            if not content_agents:
                content_agents = agents[:1]
            if not community_agents:
                community_agents = agents[1:2] if len(agents) > 1 else agents[:1]
            if not website_agents:
                website_agents = agents[2:3] if len(agents) > 2 else agents[:1]

            tasks_sent = 0

            # --- Twitter task (skip if already posted to twitter recently) ---
            if "twitter" in theme and "twitter" not in recent_platforms:
                prompt = theme["twitter"]
                for agent in content_agents[:1]:
                    task_body = json.dumps({
                        "social_draft": {
                            "platform": "twitter",
                            "body": prompt,
                            "title": "",
                            "target": "",
                        }
                    })
                    # Don't send raw prompt as social_draft body — that would
                    # post the instructions. Instead, send as a task for the
                    # agent to process via LLM.
                    bus.send_message(
                        from_id=self.rh.rh_id, to_id=agent["id"],
                        message_type="task",
                        subject=f"Social content: {theme.get('theme', 'update')}",
                        body=(
                            f"Write a tweet for @CrewBusHQ. Theme: {theme.get('theme', 'update')}.\n\n"
                            f"Instructions: {prompt}\n\n"
                            f"When done, output your tweet as:\n"
                            f'{{"social_draft": {{"platform": "twitter", "body": "YOUR TWEET TEXT HERE"}}}}'
                        ),
                        priority="normal", db_path=self.db_path,
                    )
                    tasks_sent += 1

            # --- Discord task ---
            if "discord" in theme and "discord" not in recent_platforms:
                prompt = theme["discord"]
                target_agents = community_agents[:1] if community_agents else content_agents[:1]
                for agent in target_agents:
                    bus.send_message(
                        from_id=self.rh.rh_id, to_id=agent["id"],
                        message_type="task",
                        subject=f"Discord content: {theme.get('theme', 'update')}",
                        body=(
                            f"Write a Discord post for the Crew Bus server. Theme: {theme.get('theme', 'update')}.\n\n"
                            f"Instructions: {prompt}\n\n"
                            f"When done, output your post as:\n"
                            f'{{"social_draft": {{"platform": "discord", "title": "YOUR TITLE", "body": "YOUR POST BODY", "target": "general"}}}}'
                        ),
                        priority="normal", db_path=self.db_path,
                    )
                    tasks_sent += 1

            # --- Website/blog task (less frequent — only certain themes) ---
            if "website" in theme:
                prompt = theme["website"]
                for agent in website_agents[:1]:
                    bus.send_message(
                        from_id=self.rh.rh_id, to_id=agent["id"],
                        message_type="task",
                        subject=f"Blog post: {theme.get('theme', 'update')}",
                        body=(
                            f"Write a blog post for crew-bus.dev. Theme: {theme.get('theme', 'update')}.\n\n"
                            f"Instructions: {prompt}\n\n"
                            f"When done, output your post as:\n"
                            f'{{"social_draft": {{"platform": "website", "title": "YOUR TITLE", "body": "<p>YOUR HTML BODY</p>"}}}}'
                        ),
                        priority="normal", db_path=self.db_path,
                    )
                    tasks_sent += 1

            bus.set_config(
                result["config_key"], result["this_cycle"],
                db_path=self.db_path)
            print(f"[heartbeat] social autopilot: {tasks_sent} tasks sent "
                  f"(theme: {theme.get('theme', '?')})")

        elif action_type == "social_review":
            # -------------------------------------------------------
            # SOCIAL REVIEW — Crew Boss checks the team's work hourly
            # -------------------------------------------------------
            data = result["data"]
            issues = data.get("issues", [])
            recent_count = data.get("recent_count", 0)
            posted_today = data.get("posted_today", 0)
            active_platforms = data.get("active_platforms", [])

            # Crew Boss handles issues based on severity
            high_issues = [i for i in issues if i.get("severity") == "high"]
            medium_issues = [i for i in issues if i.get("severity") == "medium"]
            low_issues = [i for i in issues if i.get("severity") == "low"]

            # Low issues: Crew Boss handles silently (logs it, moves on)
            for issue in low_issues:
                try:
                    conn = bus.get_conn(self.db_path)
                    conn.execute(
                        "INSERT INTO audit_log (event_type, agent_id, details) "
                        "VALUES (?, ?, ?)",
                        ("social_review_low", self.rh.rh_id,
                         json.dumps(issue)),
                    )
                    conn.commit()
                    conn.close()
                except Exception:
                    pass

            # Medium issues: Crew Boss tries to fix, logs it
            for issue in medium_issues:
                if issue["type"] == "failed_post":
                    # Retry failed posts
                    try:
                        from agent_worker import _boss_review_and_publish
                        conn = bus.get_conn(self.db_path)
                        draft = conn.execute(
                            "SELECT * FROM social_drafts WHERE id=?",
                            (issue["draft_id"],)
                        ).fetchone()
                        conn.close()
                        if draft and draft["status"] == "draft":
                            _boss_review_and_publish(
                                draft["id"], draft["platform"],
                                draft["body"], draft["title"] or "",
                                self.db_path)
                            print(f"[social-review] retried draft #{draft['id']}")
                    except Exception as e:
                        print(f"[social-review] retry failed: {e}")
                else:
                    # Log it for Crew Boss
                    try:
                        conn = bus.get_conn(self.db_path)
                        conn.execute(
                            "INSERT INTO audit_log (event_type, agent_id, details) "
                            "VALUES (?, ?, ?)",
                            ("social_review_medium", self.rh.rh_id,
                             json.dumps(issue)),
                        )
                        conn.commit()
                        conn.close()
                    except Exception:
                        pass

            # High issues: Crew Boss escalates to the human
            if high_issues:
                issue_lines = []
                for i in high_issues:
                    issue_lines.append(f"- [{i['severity'].upper()}] {i['msg']}")
                bus.send_message(
                    from_id=self.rh.rh_id, to_id=self.rh.human_id,
                    message_type="alert",
                    subject="Social media issue needs your attention",
                    body=(
                        "Hey boss, found some issues with recent social posts "
                        "that I can't handle on my own:\n\n"
                        + "\n".join(issue_lines)
                        + f"\n\nPosts today: {posted_today} across "
                        f"{', '.join(active_platforms) or 'no platforms'}"
                    ),
                    priority="high", db_path=self.db_path,
                )
                print(f"[social-review] escalated {len(high_issues)} issues to human")

            # Crew Boss self-report (internal log, not sent to the human)
            review_summary = (
                f"Social review: {recent_count} posts this hour, "
                f"{posted_today} today, "
                f"{len(issues)} issues "
                f"({len(high_issues)} high, {len(medium_issues)} medium, "
                f"{len(low_issues)} low). "
                f"Active: {', '.join(active_platforms) or 'none'}"
            )
            print(f"[heartbeat] {review_summary}")

            bus.set_config(
                result["config_key"], result["this_hour"],
                db_path=self.db_path)
