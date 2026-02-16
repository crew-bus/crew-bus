#!/usr/bin/env python3
"""
crew-bus CLI (v2) - command-line interface for the crew-bus message bus.

Usage:
    crew-bus init <config.yaml>         Initialize DB and load hierarchy
    crew-bus send <from> <to> <type> <subject> [body]  Send a message
    crew-bus inbox <agent>              Check agent inbox
    crew-bus status                     Show all agents
    crew-bus audit <agent>              Show audit trail
    crew-bus quarantine <agent>         Quarantine an agent
    crew-bus restore <agent>            Restore an agent
    crew-bus terminate <agent>          Terminate an agent
    crew-bus activate <agent>           Activate an inactive agent
    crew-bus deactivate <agent>         Deactivate an agent
    crew-bus report <agent>             Compile subordinate report
    crew-bus deliver <message_id>       Deliver a queued message
    crew-bus trust <human> <score>      Set Crew Boss trust score
    crew-bus burnout <human> <score>    Set human burnout score
    crew-bus briefing <human> <type>    Generate briefing (morning|evening|urgent)
    crew-bus autonomy <right_hand>      Show Crew Boss autonomy level and stats
    crew-bus decisions [--agent <id>]   Show decision history
    crew-bus learn <decision_id> <verdict> [note]  Record human feedback
    crew-bus knowledge add <cat> <subj> <content>  Store knowledge
    crew-bus knowledge search <query>   Search knowledge store
    crew-bus private start <agent>      Start private session
    crew-bus private end <agent>        End private session
    crew-bus private list               List active private sessions
    crew-bus private send <agent> <msg> Send private message
    crew-bus mailbox list <team>        Show team mailbox messages
    crew-bus mailbox read <msg_id>      Mark mailbox message as read
    crew-bus mailbox send <agent> <sev> <subj> <body>  Send to team mailbox
"""

import argparse
import json
import sys
from pathlib import Path

import bus
from delivery import ConsoleDelivery, get_backend


def _resolve_agent(identifier: str) -> dict:
    """Resolve an agent by name or numeric ID."""
    if identifier.isdigit():
        return bus.get_agent_status(int(identifier))
    agent = bus.get_agent_by_name(identifier)
    if not agent:
        print(f"Error: Agent '{identifier}' not found.", file=sys.stderr)
        sys.exit(1)
    return bus.get_agent_status(agent["id"])


# ---------------------------------------------------------------------------
# Original commands (Day 1)
# ---------------------------------------------------------------------------

def cmd_init(args):
    """Initialize the database and load a hierarchy config."""
    config_path = args.config
    if not Path(config_path).exists():
        print(f"Error: Config file '{config_path}' not found.", file=sys.stderr)
        sys.exit(1)

    bus.init_db()
    result = bus.load_hierarchy(config_path)
    print(f"Initialized crew-bus for org: {result['org']}")
    print(f"Agents loaded: {', '.join(result['agents_loaded'])}")
    print(f"Database: {bus.DB_PATH}")


def cmd_send(args):
    """Send a message between agents."""
    sender = _resolve_agent(args.sender)
    recipient = _resolve_agent(args.recipient)
    body = args.body or ""
    priority = args.priority or "normal"

    try:
        result = bus.send_message(
            from_id=sender["id"],
            to_id=recipient["id"],
            message_type=args.type,
            subject=args.subject,
            body=body,
            priority=priority,
        )
        print(f"Message #{result['message_id']} sent: {result['from']} -> {result['to']}")
        if result["require_approval"]:
            print("  ** This message requires approval before delivery **")
    except PermissionError as e:
        print(f"BLOCKED: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_inbox(args):
    """Display the inbox for an agent."""
    agent = _resolve_agent(args.agent)
    status_filter = args.filter if hasattr(args, "filter") and args.filter else None
    messages = bus.read_inbox(agent["id"], status_filter=status_filter)

    print(f"\nInbox for {agent['name']} ({agent['agent_type']}) - {len(messages)} message(s)")
    print("-" * 60)

    if not messages:
        print("  (empty)")
        return

    for msg in messages:
        pri = f" [{msg['priority'].upper()}]" if msg["priority"] != "normal" else ""
        status_icon = {"queued": "[ ]", "delivered": "[>]", "read": "[x]", "archived": "[-]"}.get(
            msg["status"], "[?]"
        )
        from_type = msg.get("from_agent_type", msg.get("from_role", "?"))
        print(f"  {status_icon} #{msg['id']}  [{msg['message_type']}]{pri}  "
              f"from {msg['from_name']} ({from_type})")
        print(f"    Subject: {msg['subject']}")
        print(f"    Status: {msg['status']}  |  Sent: {msg['created_at']}")
        if msg["body"]:
            preview = msg["body"][:120]
            if len(msg["body"]) > 120:
                preview += "..."
            print(f"    Body: {preview}")
        print()


def cmd_status(args):
    """Show all agents and their status."""
    agents = bus.list_agents()

    print(f"\nCrew Bus - {len(agents)} agent(s)")
    print("-" * 90)
    print(f"  {'Name':<22} {'Type':<16} {'Status':<14} {'Active':<8} {'Channel':<10} {'Parent'}")
    print("-" * 90)

    for a in agents:
        status_disp = {
            "active": "ok",
            "quarantined": "QUARANTINE",
            "terminated": "TERMINATED",
        }.get(a["status"], a["status"])

        active_disp = "yes" if a["active"] else "no"
        parent = a.get("parent_name") or "--"

        # Add trust/burnout info for special types
        extra = ""
        if a["agent_type"] == "right_hand":
            extra = f" [trust:{a['trust_score']}]"
        elif a["agent_type"] == "human":
            extra = f" [burnout:{a['burnout_score']}]"

        print(f"  {a['name']:<22} {a['agent_type']:<16} {status_disp:<14} "
              f"{active_disp:<8} {a['channel']:<10} {parent}{extra}")

    print()


def cmd_audit(args):
    """Show audit trail for an agent."""
    agent = _resolve_agent(args.agent)
    entries = bus.get_audit_trail(agent_id=agent["id"])

    print(f"\nAudit trail for {agent['name']} - {len(entries)} entries")
    print("-" * 60)

    for entry in entries:
        details = entry["details"]
        detail_str = json.dumps(details, indent=None) if isinstance(details, dict) else str(details)
        if len(detail_str) > 80:
            detail_str = detail_str[:80] + "..."
        print(f"  [{entry['timestamp']}] {entry['event_type']}")
        print(f"    {detail_str}")
        print()


def cmd_quarantine(args):
    """Quarantine an agent."""
    agent = _resolve_agent(args.agent)
    try:
        result = bus.quarantine_agent(agent["id"])
        print(f"Agent '{result['name']}' quarantined. All messages blocked.")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_restore(args):
    """Restore a quarantined agent."""
    agent = _resolve_agent(args.agent)
    try:
        result = bus.restore_agent(agent["id"])
        print(f"Agent '{result['name']}' restored to active.")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_terminate(args):
    """Terminate an agent."""
    agent = _resolve_agent(args.agent)
    try:
        result = bus.terminate_agent(agent["id"])
        print(f"Agent '{result['name']}' terminated. All messages archived.")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_activate(args):
    """Activate an inactive agent."""
    agent = _resolve_agent(args.agent)
    try:
        result = bus.activate_agent(agent["id"])
        print(f"Agent '{result['name']}' activated.")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_deactivate(args):
    """Deactivate an active agent."""
    agent = _resolve_agent(args.agent)
    try:
        result = bus.deactivate_agent(agent["id"])
        print(f"Agent '{result['name']}' deactivated.")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_report(args):
    """Compile a subordinate report."""
    agent = _resolve_agent(args.director)
    hours = args.hours if hasattr(args, "hours") and args.hours else 24
    try:
        report = bus.compile_director_report(agent["id"], hours=hours)
        print(report["summary"])
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_deliver(args):
    """Deliver a queued message through the recipient's channel."""
    conn = bus.get_conn()
    msg = conn.execute("SELECT * FROM messages WHERE id=?", (args.message_id,)).fetchone()
    if not msg:
        print(f"Error: Message #{args.message_id} not found.", file=sys.stderr)
        sys.exit(1)

    recipient = conn.execute("SELECT * FROM agents WHERE id=?", (msg["to_agent_id"],)).fetchone()
    sender = conn.execute("SELECT * FROM agents WHERE id=?", (msg["from_agent_id"],)).fetchone()
    conn.close()

    channel = recipient["channel"]
    address = recipient["channel_address"]

    try:
        if channel == "telegram" and args.bot_token:
            backend = get_backend("telegram", bot_token=args.bot_token)
        elif channel == "console" or not address:
            backend = ConsoleDelivery()
        else:
            backend = get_backend(channel)
    except (ValueError, TypeError):
        backend = ConsoleDelivery()

    result = backend.deliver(
        recipient_address=address or recipient["name"],
        subject=msg["subject"],
        body=msg["body"],
        priority=msg["priority"],
        metadata={"from_agent": sender["name"], "message_id": msg["id"]},
    )

    if result["success"]:
        bus.mark_delivered(msg["id"])
        print(f"Message #{msg['id']} delivered via {channel}: {result['detail']}")
    else:
        print(f"Delivery failed: {result['detail']}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Day 2 commands
# ---------------------------------------------------------------------------

def cmd_trust(args):
    """Set the Crew Boss trust score for a human."""
    agent = _resolve_agent(args.human)
    try:
        bus.update_trust_score(agent["id"], args.score)
        print(f"Trust score for {agent['name']}'s Crew Boss set to {args.score}/10")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_burnout(args):
    """Update burnout score for a human."""
    agent = _resolve_agent(args.human)
    try:
        bus.update_burnout_score(agent["id"], args.score)
        print(f"Burnout score for {agent['name']} set to {args.score}/10")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_briefing(args):
    """Generate a briefing for the human."""
    from right_hand import RightHand
    from email_formatter import format_morning_brief, format_evening_summary, format_urgent_alert

    agent = _resolve_agent(args.human)
    # Find the Crew Boss
    rh = bus.get_agent_by_name("Crew-Boss")
    if not rh:
        conn = bus.get_conn()
        rh_row = conn.execute(
            "SELECT * FROM agents WHERE parent_agent_id=? AND agent_type='right_hand'",
            (agent["id"],),
        ).fetchone()
        conn.close()
        if not rh_row:
            print("Error: No Crew Boss found for this human.", file=sys.stderr)
            sys.exit(1)
        rh = dict(rh_row)

    engine = RightHand(rh["id"], agent["id"])
    briefing = engine.compile_briefing(args.type)

    # Format as email
    burnout = agent.get("burnout_score", 5)
    if args.type == "morning":
        email = format_morning_brief(briefing, agent["name"], burnout)
    elif args.type == "evening":
        email = format_evening_summary(briefing, agent["name"], burnout)
    elif args.type == "urgent":
        email = format_urgent_alert(briefing, agent["name"])
    else:
        email = {"subject": briefing["subject"], "plain": briefing["body_plain"]}

    print(f"\n{'='*60}")
    print(f"  {email['subject']}")
    print(f"{'='*60}")
    print(email["plain"])
    print(f"{'='*60}\n")


def cmd_autonomy(args):
    """Show the autonomy level for a Crew Boss."""
    agent = _resolve_agent(args.right_hand)
    try:
        auto = bus.get_autonomy_level(agent["id"])
        print(f"\nAutonomy Summary: {auto['right_hand']}")
        print("-" * 50)
        print(f"  Trust Score:   {auto['trust_score']}/10")
        print(f"  Level:         {auto['level']}")
        print(f"  Description:   {auto['description']}")
        print(f"  Decisions:     {auto['total_decisions']}")
        print(f"  Overrides:     {auto['overrides']}")
        print(f"  Accuracy:      {auto['accuracy_pct']}%")
        if auto["trust_recommendation"]:
            print(f"  Recommendation: {auto['trust_recommendation']}")
        print(f"\n  Abilities:")
        for ability, allowed in auto["abilities"].items():
            status = "YES" if allowed else "no"
            print(f"    {ability:<30} {status}")
        print()
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_decisions(args):
    """Show decision history."""
    human_id = None
    if args.agent:
        agent = _resolve_agent(args.agent)
        human_id = agent["id"]

    decisions = bus.get_decision_history(
        human_id=human_id, limit=args.limit,
    )

    print(f"\nDecision History - {len(decisions)} entries")
    print("-" * 70)

    for d in decisions:
        ctx = d["context"]
        override_mark = " [OVERRIDDEN]" if d["human_override"] else ""
        print(f"  #{d['id']} [{d['decision_type']}]{override_mark}  {d['created_at']}")
        print(f"    Subject: {ctx.get('subject', 'N/A')}")
        print(f"    Action: {d['right_hand_action']}")
        if d["human_action"]:
            print(f"    Human action: {d['human_action']}")
        if d["feedback_note"]:
            print(f"    Note: {d['feedback_note']}")
        print()


def cmd_learn(args):
    """Record human feedback on a decision."""
    override = args.verdict.lower() in ("overridden", "override", "no", "rejected")
    note = args.note or None

    try:
        bus.record_human_feedback(
            args.decision_id,
            override=override,
            human_action=args.verdict if override else None,
            note=note,
        )
        status = "OVERRIDDEN" if override else "APPROVED"
        print(f"Decision #{args.decision_id} marked as {status}")
        if note:
            print(f"  Note: {note}")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_knowledge_add(args):
    """Store a knowledge entry."""
    # Find the knowledge agent, or fall back to Crew Boss
    km = bus.get_agent_by_name("Memory")
    if not km:
        km = bus.get_agent_by_name("Crew-Boss")
    if not km:
        print("Error: No knowledge agent or Crew Boss found.", file=sys.stderr)
        sys.exit(1)

    try:
        content = json.loads(args.content)
    except json.JSONDecodeError:
        content = {"text": args.content}

    tags = args.tags or ""

    kid = bus.store_knowledge(
        agent_id=km["id"],
        category=args.category,
        subject=args.subject,
        content=content,
        tags=tags,
    )
    print(f"Knowledge #{kid} stored: [{args.category}] {args.subject}")
    if tags:
        print(f"  Tags: {tags}")


def cmd_knowledge_search(args):
    """Search the knowledge store."""
    category = args.category if hasattr(args, "category") and args.category else None
    results = bus.search_knowledge(args.query, category_filter=category)

    print(f"\nKnowledge search: '{args.query}' - {len(results)} result(s)")
    print("-" * 60)

    for entry in results:
        content_preview = json.dumps(entry["content"])
        if len(content_preview) > 80:
            content_preview = content_preview[:80] + "..."
        print(f"  #{entry['id']} [{entry['category']}] {entry['subject']}")
        print(f"    Agent: {entry['agent_name']} | Tags: {entry['tags'] or '(none)'}")
        print(f"    Content: {content_preview}")
        print(f"    Updated: {entry['updated_at']}")
        print()


def cmd_accuracy(args):
    """Show decision accuracy stats for a Crew Boss."""
    agent = _resolve_agent(args.right_hand)
    days = args.days or 30

    try:
        auto = bus.get_autonomy_level(agent["id"])
        total = auto["total_decisions"]
        overrides = auto["overrides"]
        correct = total - overrides
        accuracy = auto["accuracy_pct"]

        print(f"\nDecision Accuracy: {agent['name']}")
        print(f"  Period:       last {days} days")
        print(f"  Total:        {total}")
        print(f"  Correct:      {correct}")
        print(f"  Overridden:   {overrides}")
        print(f"  Accuracy:     {accuracy}%")
        print(f"  Trust Score:  {auto['trust_score']}/10")
        if auto["trust_recommendation"]:
            print(f"  Suggestion:   {auto['trust_recommendation']}")
        print()
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Day 2 commands: state, security, relationships, profile
# ---------------------------------------------------------------------------

def cmd_state(args):
    """Show current human state (burnout, energy, activity, mood)."""
    agent = _resolve_agent(args.human)
    state = bus.get_human_state(agent["id"])
    print(f"  Human State: {agent['name']}")
    print(f"  Burnout:        {state['burnout_score']}/10")
    print(f"  Energy:         {state['energy_level']}")
    print(f"  Activity:       {state['current_activity']}")
    print(f"  Mood:           {state['mood_indicator']}")
    print(f"  Work streak:    {state['consecutive_work_days']} days")
    print(f"  Last social:    {state.get('last_social_activity') or 'unknown'}")
    print(f"  Last family:    {state.get('last_family_contact') or 'unknown'}")
    print(f"  Updated by:     {state.get('updated_by', 'system')}")
    print(f"  Updated at:     {state['updated_at']}")


def cmd_security_scan(args):
    """Run security scan on one or all agents."""
    from security import SecurityAgent

    # Find the security agent
    conn = bus.get_conn()
    sec = conn.execute("SELECT id FROM agents WHERE agent_type='security'").fetchone()
    rh = conn.execute("SELECT id FROM agents WHERE agent_type='right_hand'").fetchone()
    conn.close()
    if not sec or not rh:
        print("  ERROR: No security agent or Crew Boss found")
        return

    sa = SecurityAgent(sec["id"], rh["id"])

    if args.agent:
        agent = _resolve_agent(args.agent)
        result = sa.scan_agent_behavior(agent["id"])
        print(f"  Security scan: {result['agent_name']}")
        print(f"  Threat level:  {result['threat_level']}")
        if result["anomalies"]:
            for a in result["anomalies"]:
                print(f"    [{a['type']}] {a['description']}")
        else:
            print("    No anomalies detected")
        print(f"  Recommendation: {result['recommendation']}")
    else:
        results = sa.scan_all_agents()
        print(f"  Security scan: all agents ({len(results)} scanned)")
        for r in results:
            flag = " !!!" if r["threat_level"] in ("medium", "high") else ""
            print(f"    {r['agent_name']:20s}  threat={r['threat_level']}{flag}")
            for a in r["anomalies"]:
                print(f"      [{a['type']}] {a['description']}")
        clean = sum(1 for r in results if r["threat_level"] == "none")
        print(f"\n  Summary: {clean}/{len(results)} clean")


def cmd_security_events(args):
    """Show security events."""
    events = bus.get_security_events(
        severity_filter=args.severity,
        unresolved_only=args.unresolved,
        limit=args.limit,
    )
    if not events:
        print("  No security events found")
        return
    print(f"  Security events: {len(events)}")
    for e in events:
        resolved = "RESOLVED" if e.get("resolved_at") else "OPEN"
        print(f"  #{e['id']} [{e['severity'].upper()}] [{e['threat_domain']}] {e['title']} ({resolved})")
        if e.get("recommended_action"):
            print(f"    Action: {e['recommended_action']}")
        if e.get("resolution"):
            print(f"    Resolution: {e['resolution']}")


def cmd_relationships(args):
    """Show relationship health for a human."""
    agent = _resolve_agent(args.human)
    rels = bus.get_relationships(agent["id"])
    if not rels:
        print("  No tracked relationships")
        return
    print(f"  Relationships for {agent['name']}: {len(rels)}")
    for r in rels:
        status = r.get("computed_status", r["status"])
        flag = ""
        if status == "stale":
            flag = " [STALE]"
        elif status == "at_risk":
            flag = " [AT RISK]"
        elif status == "attention_needed":
            flag = " [NEEDS ATTENTION]"
        days = r.get("days_since_contact", "?")
        print(f"    {r['contact_name']:25s} [{r['contact_type']}] imp={r['importance']}/10  "
              f"last={days}d ago (goal: {r['preferred_frequency_days']}d){flag}")
        if r.get("notes"):
            print(f"      Notes: {r['notes']}")


def cmd_profile(args):
    """Show human profile."""
    agent = _resolve_agent(args.human)
    profile = bus.get_human_profile(agent["id"])
    if not profile:
        print(f"  No profile set for {agent['name']}")
        return
    print(f"  Human Profile: {agent['name']}")
    print(f"  Personality:   {profile.get('personality_type', '?')}")
    print(f"  Work style:    {profile.get('work_style', '?')}")
    print(f"  Recharge:      {profile.get('social_recharge', '?')}")
    print(f"  Timezone:      {profile.get('timezone', '?')}")
    print(f"  Quiet hours:   {profile.get('quiet_hours_start', '?')} - {profile.get('quiet_hours_end', '?')}")
    comms = profile.get("communication_preferences", {})
    if comms:
        print(f"  Communication: channel={comms.get('preferred_channel', '?')} "
              f"length={comms.get('message_length', '?')} "
              f"formality={comms.get('formality', '?')}")
    triggers = profile.get("known_triggers", [])
    if triggers:
        print(f"  Triggers:      {', '.join(triggers)}")


# ---------------------------------------------------------------------------
# Private Session commands
# ---------------------------------------------------------------------------

def cmd_private_start(args):
    """Start a private session with an agent."""
    agent = _resolve_agent(args.agent)
    # Find the human
    conn = bus.get_conn()
    human = conn.execute("SELECT * FROM agents WHERE agent_type='human'").fetchone()
    conn.close()
    if not human:
        print("Error: No human agent found.", file=sys.stderr)
        sys.exit(1)
    result = bus.start_private_session(
        human["id"], agent["id"],
        channel=args.channel or "web",
        timeout_minutes=args.timeout or 30,
    )
    print(f"  Private session started with {agent['name']}")
    print(f"  Session ID: {result['session_id']}")
    print(f"  Channel:    {result['channel']}")
    print(f"  Expires:    {result['expires_at']}")


def cmd_private_end(args):
    """End a private session with an agent."""
    agent = _resolve_agent(args.agent)
    conn = bus.get_conn()
    human = conn.execute("SELECT * FROM agents WHERE agent_type='human'").fetchone()
    conn.close()
    if not human:
        print("Error: No human agent found.", file=sys.stderr)
        sys.exit(1)
    session = bus.get_active_private_session(human["id"], agent["id"])
    if not session:
        print(f"  No active private session with {agent['name']}")
        return
    result = bus.end_private_session(session["id"], ended_by="human")
    if result.get("ok"):
        print(f"  Private session with {agent['name']} ended.")
    else:
        print(f"  Error: {result.get('error')}", file=sys.stderr)


def cmd_private_list(args):
    """List active private sessions."""
    conn = bus.get_conn()
    sessions = conn.execute(
        "SELECT ps.*, h.name AS human_name, a.name AS agent_name "
        "FROM private_sessions ps "
        "JOIN agents h ON ps.human_id = h.id "
        "JOIN agents a ON ps.agent_id = a.id "
        "WHERE ps.active = 1 ORDER BY ps.started_at DESC"
    ).fetchall()
    conn.close()

    if not sessions:
        print("  No active private sessions.")
        return

    print(f"  Active private sessions ({len(sessions)}):")
    for s in sessions:
        print(f"    #{s['id']} {s['human_name']} <-> {s['agent_name']} "
              f"[{s['channel']}] msgs={s['message_count']} expires={s['expires_at']}")


def cmd_private_send(args):
    """Send a private message."""
    agent = _resolve_agent(args.agent)
    conn = bus.get_conn()
    human = conn.execute("SELECT * FROM agents WHERE agent_type='human'").fetchone()
    conn.close()
    if not human:
        print("Error: No human agent found.", file=sys.stderr)
        sys.exit(1)
    session = bus.get_active_private_session(human["id"], agent["id"])
    if not session:
        print(f"  No active private session with {agent['name']}. Start one first.")
        return
    result = bus.send_private_message(session["id"], human["id"], args.message)
    if result.get("ok"):
        print(f"  Private message sent to {agent['name']} (msg_id={result['message_id']})")
    else:
        print(f"  Error: {result.get('error')}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Team Mailbox commands
# ---------------------------------------------------------------------------

def cmd_mailbox_list(args):
    """Show team mailbox messages."""
    agent = _resolve_agent(args.team)
    # Resolve team_id: if it's a manager, use their id; otherwise find parent manager
    if agent["agent_type"] == "manager":
        team_id = agent["id"]
    elif agent.get("parent_agent_id"):
        team_id = agent["parent_agent_id"]
    else:
        print(f"  Error: {agent['name']} is not part of a team.", file=sys.stderr)
        sys.exit(1)

    messages = bus.get_team_mailbox(team_id, unread_only=args.unread)
    if not messages:
        print(f"  No {'unread ' if args.unread else ''}mailbox messages for team.")
        return

    summary = bus.get_team_mailbox_summary(team_id)
    print(f"  Team mailbox: {summary['unread_count']} unread "
          f"({summary['code_red_count']} code_red, {summary['warning_count']} warning)")
    print()
    for m in messages:
        sev = m["severity"].upper()
        read_mark = " " if m["read"] else "*"
        print(f"  {read_mark} #{m['id']} [{sev:8s}] {m['subject']} "
              f"(from {m['from_agent_name']}, {m['created_at']})")
        if args.verbose:
            for line in m["body"].split("\n")[:3]:
                print(f"      {line}")


def cmd_mailbox_read(args):
    """Mark a mailbox message as read."""
    result = bus.mark_mailbox_read(args.message_id)
    if result.get("ok"):
        print(f"  Message #{args.message_id} marked as read.")
    else:
        print(f"  Error: {result.get('error')}", file=sys.stderr)


def cmd_mailbox_send(args):
    """Send a message to a team mailbox."""
    agent = _resolve_agent(args.agent)
    result = bus.send_to_team_mailbox(
        from_agent_id=agent["id"],
        subject=args.subject,
        body=args.body,
        severity=args.severity,
    )
    if result.get("ok"):
        print(f"  Mailbox message sent: #{result['mailbox_id']} [{result['severity']}]")
    else:
        print(f"  Error: {result.get('error')}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Techie Marketplace
# ---------------------------------------------------------------------------

def cmd_techie_list(args):
    """List authorized techies."""
    status = getattr(args, "status", "verified")
    standing = getattr(args, "standing", "good")
    techies = bus.list_techies(status=status, standing=standing)
    if not techies:
        print("  No techies found.")
        return
    print(f"\n  {'ID':<20s} {'Name':<20s} {'KYC':<10s} {'Standing':<10s} {'Rating':<8s} {'Jobs':<6s}")
    print(f"  {'-'*20} {'-'*20} {'-'*10} {'-'*10} {'-'*8} {'-'*6}")
    for t in techies:
        rating = f"{t['rating_avg']:.1f}" if t["rating_count"] > 0 else "N/A"
        print(f"  {t['techie_id']:<20s} {t['display_name']:<20s} "
              f"{t['kyc_status']:<10s} {t['standing']:<10s} {rating:<8s} {t['total_jobs_completed']:<6d}")


def cmd_techie_verify(args):
    """Verify a techie's KYC."""
    try:
        result = bus.verify_techie_kyc(args.techie_id)
        print(f"  Techie '{result['techie_id']}' KYC verified at {result['kyc_verified_at']}")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_techie_revoke(args):
    """Revoke a techie's authorization."""
    try:
        result = bus.revoke_techie(args.techie_id, args.reason)
        print(f"  Techie '{result['techie_id']}' revoked. Reason: {result['reason']}")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_techie_profile(args):
    """View a techie's profile."""
    profile = bus.get_techie_profile(args.techie_id)
    if not profile:
        print(f"Error: Techie '{args.techie_id}' not found.", file=sys.stderr)
        sys.exit(1)
    print(f"\n  Techie Profile: {profile['display_name']}")
    print(f"  {'='*40}")
    print(f"  ID:           {profile['techie_id']}")
    print(f"  Email:        {profile['email']}")
    print(f"  KYC Status:   {profile['kyc_status']}")
    print(f"  Standing:     {profile['standing']}")
    rating = f"{profile['rating_avg']:.1f} ({profile['rating_count']} reviews)" if profile["rating_count"] > 0 else "No reviews"
    print(f"  Rating:       {rating}")
    print(f"  Keys Purchased: {profile['total_keys_purchased']}")
    print(f"  Jobs Completed: {profile['total_jobs_completed']}")
    print(f"  Joined:       {profile['created_at']}")
    if profile.get("revoked_at"):
        print(f"  Revoked:      {profile['revoked_at']} ({profile.get('revocation_reason', '')})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="crew-bus",
        description="Local message bus for AI agent coordination (Human-First Architecture)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # init
    p = sub.add_parser("init", help="Initialize DB and load hierarchy")
    p.add_argument("config", help="Path to YAML config file")
    p.set_defaults(func=cmd_init)

    # send
    p = sub.add_parser("send", help="Send a message")
    p.add_argument("sender", help="Sender name or ID")
    p.add_argument("recipient", help="Recipient name or ID")
    p.add_argument("type", choices=bus.VALID_MESSAGE_TYPES, help="Message type")
    p.add_argument("subject", help="Message subject")
    p.add_argument("body", nargs="?", default="", help="Message body")
    p.add_argument("-p", "--priority", choices=bus.VALID_PRIORITIES, default="normal")
    p.set_defaults(func=cmd_send)

    # inbox
    p = sub.add_parser("inbox", help="Check agent inbox")
    p.add_argument("agent", help="Agent name or ID")
    p.add_argument("-f", "--filter", choices=bus.VALID_MESSAGE_STATUSES, help="Filter by status")
    p.set_defaults(func=cmd_inbox)

    # status
    p = sub.add_parser("status", help="Show all agents")
    p.set_defaults(func=cmd_status)

    # audit
    p = sub.add_parser("audit", help="Show audit trail")
    p.add_argument("agent", help="Agent name or ID")
    p.set_defaults(func=cmd_audit)

    # quarantine
    p = sub.add_parser("quarantine", help="Quarantine an agent")
    p.add_argument("agent", help="Agent name or ID")
    p.set_defaults(func=cmd_quarantine)

    # restore
    p = sub.add_parser("restore", help="Restore a quarantined agent")
    p.add_argument("agent", help="Agent name or ID")
    p.set_defaults(func=cmd_restore)

    # terminate
    p = sub.add_parser("terminate", help="Terminate an agent")
    p.add_argument("agent", help="Agent name or ID")
    p.set_defaults(func=cmd_terminate)

    # activate
    p = sub.add_parser("activate", help="Activate an inactive agent")
    p.add_argument("agent", help="Agent name or ID")
    p.set_defaults(func=cmd_activate)

    # deactivate
    p = sub.add_parser("deactivate", help="Deactivate an agent")
    p.add_argument("agent", help="Agent name or ID")
    p.set_defaults(func=cmd_deactivate)

    # report
    p = sub.add_parser("report", help="Compile subordinate report")
    p.add_argument("director", help="Director/Crew Boss/Manager name or ID")
    p.add_argument("--hours", type=int, default=24, help="Lookback hours (default 24)")
    p.set_defaults(func=cmd_report)

    # deliver
    p = sub.add_parser("deliver", help="Deliver a queued message")
    p.add_argument("message_id", type=int, help="Message ID to deliver")
    p.add_argument("--bot-token", help="Telegram bot token (for telegram delivery)")
    p.set_defaults(func=cmd_deliver)

    # trust
    p = sub.add_parser("trust", help="Set Crew Boss trust score")
    p.add_argument("human", help="Human agent name or ID")
    p.add_argument("score", type=int, help="Trust score (1-10)")
    p.set_defaults(func=cmd_trust)

    # burnout
    p = sub.add_parser("burnout", help="Set human burnout score")
    p.add_argument("human", help="Human agent name or ID")
    p.add_argument("score", type=int, help="Burnout score (1-10)")
    p.set_defaults(func=cmd_burnout)

    # briefing
    p = sub.add_parser("briefing", help="Generate briefing for human")
    p.add_argument("human", help="Human agent name or ID")
    p.add_argument("type", choices=["morning", "evening", "urgent"], help="Briefing type")
    p.set_defaults(func=cmd_briefing)

    # autonomy
    p = sub.add_parser("autonomy", help="Show Crew Boss autonomy level")
    p.add_argument("right_hand", help="Crew Boss agent name or ID")
    p.set_defaults(func=cmd_autonomy)

    # decisions
    p = sub.add_parser("decisions", help="Show decision history")
    p.add_argument("--agent", help="Filter by human agent name or ID")
    p.add_argument("--limit", type=int, default=20, help="Max entries (default 20)")
    p.set_defaults(func=cmd_decisions)

    # learn
    p = sub.add_parser("learn", help="Record human feedback on a decision")
    p.add_argument("decision_id", type=int, help="Decision ID")
    p.add_argument("verdict", help="approved or overridden")
    p.add_argument("note", nargs="?", default=None, help="Feedback note")
    p.set_defaults(func=cmd_learn)

    # knowledge (subcommands)
    p_know = sub.add_parser("knowledge", help="Knowledge store operations")
    know_sub = p_know.add_subparsers(dest="knowledge_cmd", required=True)

    # knowledge add
    p_ka = know_sub.add_parser("add", help="Store knowledge entry")
    p_ka.add_argument("category", choices=bus.VALID_KNOWLEDGE_CATEGORIES, help="Category")
    p_ka.add_argument("subject", help="Subject line")
    p_ka.add_argument("content", help="Content (JSON or plain text)")
    p_ka.add_argument("--tags", help="Comma-separated tags")
    p_ka.set_defaults(func=cmd_knowledge_add)

    # knowledge search
    p_ks = know_sub.add_parser("search", help="Search knowledge store")
    p_ks.add_argument("query", help="Search query")
    p_ks.add_argument("--category", choices=bus.VALID_KNOWLEDGE_CATEGORIES, help="Filter by category")
    p_ks.set_defaults(func=cmd_knowledge_search)

    # accuracy
    p = sub.add_parser("accuracy", help="Show decision accuracy stats")
    p.add_argument("right_hand", help="Crew Boss agent name or ID")
    p.add_argument("--days", type=int, default=30, help="Period in days (default 30)")
    p.set_defaults(func=cmd_accuracy)

    # --- Day 2 commands ---

    # state
    p = sub.add_parser("state", help="Show current human state")
    p.add_argument("human", help="Human agent name or ID")
    p.set_defaults(func=cmd_state)

    # security scan
    p_sec = sub.add_parser("security", help="Security operations")
    sec_sub = p_sec.add_subparsers(dest="security_cmd", required=True)

    p_scan = sec_sub.add_parser("scan", help="Run security scan")
    p_scan.add_argument("agent", nargs="?", help="Agent to scan (omit for all)")
    p_scan.set_defaults(func=cmd_security_scan)

    p_events = sec_sub.add_parser("events", help="Show security events")
    p_events.add_argument("--severity", choices=bus.VALID_SEVERITY_LEVELS, help="Filter severity")
    p_events.add_argument("--unresolved", action="store_true", help="Only unresolved")
    p_events.add_argument("--limit", type=int, default=50, help="Max entries")
    p_events.set_defaults(func=cmd_security_events)

    # relationships
    p = sub.add_parser("relationships", help="Show relationship health")
    p.add_argument("human", help="Human agent name or ID")
    p.set_defaults(func=cmd_relationships)

    # profile
    p = sub.add_parser("profile", help="Show human profile")
    p.add_argument("human", help="Human agent name or ID")
    p.set_defaults(func=cmd_profile)

    # --- Private Sessions ---

    p_priv = sub.add_parser("private", help="Private session operations")
    priv_sub = p_priv.add_subparsers(dest="private_cmd", required=True)

    p_ps = priv_sub.add_parser("start", help="Start private session")
    p_ps.add_argument("agent", help="Agent name or ID")
    p_ps.add_argument("--channel", default="web", help="Channel (web, telegram, signal, app)")
    p_ps.add_argument("--timeout", type=int, default=30, help="Timeout in minutes (default 30)")
    p_ps.set_defaults(func=cmd_private_start)

    p_pe = priv_sub.add_parser("end", help="End private session")
    p_pe.add_argument("agent", help="Agent name or ID")
    p_pe.set_defaults(func=cmd_private_end)

    p_pl = priv_sub.add_parser("list", help="List active private sessions")
    p_pl.set_defaults(func=cmd_private_list)

    p_pm = priv_sub.add_parser("send", help="Send private message")
    p_pm.add_argument("agent", help="Agent name or ID")
    p_pm.add_argument("message", help="Message text")
    p_pm.set_defaults(func=cmd_private_send)

    # --- Team Mailbox ---

    p_mb = sub.add_parser("mailbox", help="Team mailbox operations")
    mb_sub = p_mb.add_subparsers(dest="mailbox_cmd", required=True)

    p_ml = mb_sub.add_parser("list", help="Show mailbox messages")
    p_ml.add_argument("team", help="Team manager name or worker name")
    p_ml.add_argument("--unread", action="store_true", help="Only unread")
    p_ml.add_argument("--verbose", "-v", action="store_true", help="Show message body")
    p_ml.set_defaults(func=cmd_mailbox_list)

    p_mr = mb_sub.add_parser("read", help="Mark message as read")
    p_mr.add_argument("message_id", type=int, help="Mailbox message ID")
    p_mr.set_defaults(func=cmd_mailbox_read)

    p_ms = mb_sub.add_parser("send", help="Send to team mailbox")
    p_ms.add_argument("agent", help="Sending agent name or ID")
    p_ms.add_argument("severity", choices=bus.VALID_MAILBOX_SEVERITIES, help="Severity level")
    p_ms.add_argument("subject", help="Message subject")
    p_ms.add_argument("body", help="Message body")
    p_ms.set_defaults(func=cmd_mailbox_send)

    # --- Techie Marketplace ---

    p_techie = sub.add_parser("techie", help="Techie marketplace operations")
    techie_sub = p_techie.add_subparsers(dest="techie_cmd", required=True)

    p_tl = techie_sub.add_parser("list", help="List authorized techies")
    p_tl.add_argument("--status", default="verified", help="KYC status filter (default: verified)")
    p_tl.add_argument("--standing", default="good", help="Standing filter (default: good)")
    p_tl.set_defaults(func=cmd_techie_list)

    p_tv = techie_sub.add_parser("verify", help="Verify a techie's KYC")
    p_tv.add_argument("techie_id", help="Techie ID to verify")
    p_tv.set_defaults(func=cmd_techie_verify)

    p_tr = techie_sub.add_parser("revoke", help="Revoke techie authorization")
    p_tr.add_argument("techie_id", help="Techie ID to revoke")
    p_tr.add_argument("reason", help="Reason for revocation")
    p_tr.set_defaults(func=cmd_techie_revoke)

    p_tp = techie_sub.add_parser("profile", help="View techie profile")
    p_tp.add_argument("techie_id", help="Techie ID to view")
    p_tp.set_defaults(func=cmd_techie_profile)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
