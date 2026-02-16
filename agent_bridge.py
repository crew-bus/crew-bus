"""
crew-bus Agent Bridge -- OpenClaw integration layer.

Provides CrewBridge, a single class that any OpenClaw-compatible agent uses
to talk to the crew-bus. Agents don't touch SQLite directly; they call
bridge methods which translate to bus operations.

Usage:
    from agent_bridge import CrewBridge

    bridge = CrewBridge("Lead-Tracker")
    bridge.report("New Lead Logged", "Dave Wilson, 250-334-5678, pressure tank")
    msgs = bridge.check_inbox()
    bridge.mark_done(msgs[0]["id"])

Every method is synchronous and returns plain dicts/lists.
No external dependencies beyond crew-bus core (bus.py).

Error handling: If the bus DB doesn't exist, agent is quarantined, or
routing is blocked, methods return a clear error dict instead of crashing.

FREE AND OPEN SOURCE -- crew-bus is free infrastructure for the world.
Security Guard module available separately (paid activation key).
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
import bus


class CrewBridge:
    """Bridge for OpenClaw agents to interact with crew-bus.

    Each agent creates one CrewBridge instance with its own name.
    The bridge resolves the agent's ID from the database and provides
    clean methods for all bus operations.

    Args:
        agent_name: Name of this agent (must exist in agents table).
        db_path: Path to crew_bus.db. Defaults to bus.DB_PATH.

    Raises:
        ValueError: If agent_name is not found in the database.
    """

    def __init__(self, agent_name: str, db_path: Optional[Path] = None):
        self.agent_name = agent_name
        self.db_path = db_path or bus.DB_PATH
        bus.init_db(db_path=self.db_path)

        agent = bus.get_agent_by_name(agent_name, db_path=self.db_path)
        if not agent:
            raise ValueError(f"Agent '{agent_name}' not found in database")

        self.agent_id = agent["id"]
        self.agent_type = agent["agent_type"]
        self.role = agent["role"]
        self.parent_agent_id = agent.get("parent_agent_id")

    # ── Messaging ───────────────────────────────────────────────────

    def report(self, subject: str, body: str, priority: str = "normal") -> dict:
        """Send a report to this agent's direct parent.

        Automatically determines parent from hierarchy.

        Args:
            subject: Report subject line.
            body: Report content.
            priority: low/normal/high/critical.

        Returns:
            Dict with message_id on success, or error dict on failure.
        """
        parent_id = self._get_parent_id()
        if isinstance(parent_id, dict):
            return parent_id  # error dict

        return self._safe_send(
            to_id=parent_id,
            message_type="report",
            subject=subject,
            body=body,
            priority=priority,
        )

    def alert(self, subject: str, body: str, priority: str = "high") -> dict:
        """Send an alert to the director level (Crew Boss).

        Args:
            subject: Alert subject.
            body: Alert details.
            priority: Defaults to high.

        Returns:
            Dict with message_id on success, or error dict on failure.
        """
        rh_id = self._get_right_hand_id()
        if isinstance(rh_id, dict):
            return rh_id  # error dict

        return self._safe_send(
            to_id=rh_id,
            message_type="alert",
            subject=subject,
            body=body,
            priority=priority,
        )

    def escalate(self, subject: str, body: str) -> dict:
        """Safety escalation direct to the human's Crew Boss, bypasses all hierarchy.

        This is for genuine safety or ethical concerns only.

        Args:
            subject: Escalation subject.
            body: Detailed description of the concern.

        Returns:
            Dict with message_id on success, or error dict on failure.
        """
        rh_id = self._get_right_hand_id()
        if isinstance(rh_id, dict):
            return rh_id  # error dict

        return self._safe_send(
            to_id=rh_id,
            message_type="escalation",
            subject=subject,
            body=body,
            priority="critical",
        )

    # ── Inbox ──────────────────────────────────────────────────────

    def check_inbox(self, unread_only: bool = True) -> list[dict]:
        """Return messages addressed to this agent.

        Args:
            unread_only: If True, only return queued/delivered messages.

        Returns:
            List of message dicts: {id, from_name, message_type, subject,
            body, priority, created_at, status}. Returns empty list on error.
        """
        try:
            status_filter = "queued" if unread_only else None
            messages = bus.read_inbox(
                self.agent_id, status_filter=status_filter,
                db_path=self.db_path,
            )
            # Also get 'delivered' messages if unread_only
            if unread_only:
                delivered = bus.read_inbox(
                    self.agent_id, status_filter="delivered",
                    db_path=self.db_path,
                )
                messages.extend(delivered)
                # Sort by created_at descending
                messages.sort(key=lambda m: m.get("created_at", ""), reverse=True)

            return [
                {
                    "id": m["id"],
                    "from": m.get("from_name", str(m.get("from_agent_id", "?"))),
                    "type": m["message_type"],
                    "subject": m["subject"],
                    "body": m["body"],
                    "priority": m["priority"],
                    "time": m["created_at"],
                    "status": m["status"],
                }
                for m in messages
            ]
        except Exception as e:
            return []

    def get_tasks(self) -> list[dict]:
        """Return only unread task-type messages.

        Returns:
            List of task message dicts with same shape as check_inbox.
        """
        all_msgs = self.check_inbox(unread_only=True)
        return [m for m in all_msgs if m["type"] == "task"]

    def mark_done(self, message_id: int) -> dict:
        """Mark a message as read (completed).

        Args:
            message_id: The message ID to mark done.

        Returns:
            Dict with ok=True on success, or error dict.
        """
        try:
            result = bus.mark_read(message_id, db_path=self.db_path)
            return {"ok": result, "message_id": message_id}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Knowledge Store ─────────────────────────────────────────────

    def post_knowledge(self, category: str, subject: str, content: str,
                       tags: Optional[list] = None) -> dict:
        """Store something in the knowledge base.

        Args:
            category: One of: decision, contact, lesson, preference, rejection.
            subject: Knowledge key/title.
            content: Knowledge content (will be stored as JSON).
            tags: Optional list of tags for searchability.

        Returns:
            Dict with knowledge_id on success, or error dict.

        Example:
            bridge.post_knowledge("contact", "Dave Wilson",
                "Needs pressure tank, Black Creek",
                tags=["lead", "plumbing"])
        """
        try:
            tags_str = ",".join(tags) if tags else ""
            content_dict = {"text": content} if isinstance(content, str) else content
            kid = bus.store_knowledge(
                agent_id=self.agent_id,
                category=category,
                subject=subject,
                content=content_dict,
                tags=tags_str,
                db_path=self.db_path,
            )
            return {"ok": True, "knowledge_id": kid}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def search_knowledge(self, query: str, category: Optional[str] = None) -> list[dict]:
        """Search the knowledge base.

        Args:
            query: Search term (matched against subject, content, tags).
            category: Optional category filter.

        Returns:
            List of knowledge entry dicts.
        """
        try:
            results = bus.search_knowledge(
                query=query,
                category_filter=category,
                db_path=self.db_path,
            )
            return results
        except Exception as e:
            return []

    # ── Wellness (wellness-type agents only) ────────────────────────

    def update_wellness(self, burnout_score: int, notes: Optional[str] = None) -> dict:
        """Update the human's burnout score. Only for wellness-type agents.

        Args:
            burnout_score: New burnout score (1-10).
            notes: Optional note about the update.

        Returns:
            Dict with ok=True on success, or error dict.
        """
        if self.agent_type != "wellness":
            return {"ok": False, "error": f"Only wellness agents can update burnout. You are '{self.agent_type}'."}

        try:
            # Find the human (top of hierarchy)
            conn = bus.get_conn(self.db_path)
            try:
                human = conn.execute(
                    "SELECT id FROM agents WHERE agent_type='human' LIMIT 1"
                ).fetchone()
            finally:
                conn.close()

            if not human:
                return {"ok": False, "error": "No human agent found"}

            bus.update_burnout_score(human["id"], burnout_score, db_path=self.db_path)

            if notes:
                self.report(
                    subject=f"Burnout Update: {burnout_score}/10",
                    body=f"Burnout score updated to {burnout_score}/10. {notes}",
                    priority="high" if burnout_score >= 7 else "normal",
                )

            return {"ok": True, "burnout_score": burnout_score}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Strategy Ideas (strategy-type agents only) ──────────────────

    def submit_idea(self, subject: str, body: str, category: Optional[str] = None) -> dict:
        """Submit a strategy idea to Crew Boss for filtering.

        Only for strategy-type agents.

        Args:
            subject: Idea title.
            body: Detailed idea description.
            category: Optional category tag.

        Returns:
            Dict with message_id on success, or error dict.
        """
        if self.agent_type != "strategy":
            return {"ok": False, "error": f"Only strategy agents can submit ideas. You are '{self.agent_type}'."}

        rh_id = self._get_right_hand_id()
        if isinstance(rh_id, dict):
            return rh_id

        tag = f" [{category}]" if category else ""
        return self._safe_send(
            to_id=rh_id,
            message_type="idea",
            subject=subject + tag,
            body=body,
            priority="normal",
        )

    # ── Status ──────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """Return this agent's current status, parent, unread count.

        Returns:
            Dict with agent details including status, trust_score,
            inbox_unread, etc.
        """
        try:
            status = bus.get_agent_status(self.agent_id, db_path=self.db_path)
            # Add parent name
            if status.get("parent_agent_id"):
                conn = bus.get_conn(self.db_path)
                try:
                    parent = conn.execute(
                        "SELECT name FROM agents WHERE id=?",
                        (status["parent_agent_id"],)
                    ).fetchone()
                    status["parent_name"] = parent["name"] if parent else None
                finally:
                    conn.close()
            return status
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Internal ────────────────────────────────────────────────────

    def _get_parent_id(self) -> int | dict:
        """Resolve this agent's parent ID.

        Returns agent_id int or error dict.
        """
        if self.parent_agent_id:
            return self.parent_agent_id
        return {"ok": False, "error": f"Agent '{self.agent_name}' has no parent in hierarchy"}

    def _get_right_hand_id(self) -> int | dict:
        """Find the Crew Boss agent in the hierarchy.

        Returns agent_id int or error dict.
        """
        try:
            conn = bus.get_conn(self.db_path)
            try:
                rh = conn.execute(
                    "SELECT id FROM agents WHERE agent_type='right_hand' AND status='active' LIMIT 1"
                ).fetchone()
            finally:
                conn.close()

            if not rh:
                return {"ok": False, "error": "No active Crew Boss agent found"}
            return rh["id"]
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _safe_send(self, to_id: int, message_type: str, subject: str,
                   body: str, priority: str) -> dict:
        """Send a message with error handling.

        Returns dict with message_id on success, or error dict on failure.
        """
        try:
            result = bus.send_message(
                from_id=self.agent_id,
                to_id=to_id,
                message_type=message_type,
                subject=subject,
                body=body,
                priority=priority,
                db_path=self.db_path,
            )
            return {"ok": True, "message_id": result["message_id"]}
        except PermissionError as e:
            return {"ok": False, "error": str(e), "blocked": True}
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def __repr__(self):
        return f"CrewBridge(agent_name={self.agent_name!r}, agent_id={self.agent_id})"
