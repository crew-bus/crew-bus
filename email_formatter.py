"""
crew-bus email formatter.

Formats Crew Boss briefings as professional emails. The tone is a competent
chief of staff who knows the human personally - professional but warm.
"""

import json
from datetime import datetime, timezone


def format_morning_brief(briefing_data: dict, human_name: str,
                         burnout_score: int) -> dict:
    """Format a morning briefing as a professional email.

    Args:
        briefing_data: Output from RightHand.compile_briefing("morning").
        human_name: The human's name.
        burnout_score: Current burnout score (1-10).

    Returns:
        {subject: str, plain: str, html: str}
    """
    subject = briefing_data["subject"]
    rh_name = briefing_data.get("rh_name", "Chief")
    sections = briefing_data.get("sections", {})

    # Build plain text
    lines = []

    # Greeting based on burnout
    if burnout_score >= 7:
        lines.append(f"Light day ahead, {human_name}. Only the essentials today.")
    elif burnout_score >= 4:
        lines.append(f"Good morning, {human_name}. Here's your rundown.")
    else:
        lines.append(f"Productive day ahead, {human_name}. Here's your full rundown.")
    lines.append("")

    # Priority items
    priority_items = sections.get("priority_items", [])
    if priority_items:
        lines.append("=" * 50)
        lines.append("PRIORITY ITEMS")
        lines.append("=" * 50)
        for item in priority_items:
            pri = item.get("priority", "normal").upper()
            lines.append(f"  ACTION: [{pri}] {item.get('subject', 'N/A')}")
            lines.append(f"    From: {item.get('from_name', 'Unknown')}")
            body = item.get("body", "")
            if body:
                for bl in body.split("\n")[:3]:
                    lines.append(f"    {bl}")
            lines.append("")

    # Overnight activity
    overnight = sections.get("overnight", [])
    non_priority = [m for m in overnight
                    if m.get("priority") not in ("high", "critical")]
    if non_priority and burnout_score < 7:
        lines.append("-" * 50)
        lines.append(f"OVERNIGHT ACTIVITY ({len(overnight)} messages)")
        lines.append("-" * 50)
        for item in non_priority[:10]:
            mtype = item.get("message_type", "report")
            lines.append(f"  * {item.get('subject', 'N/A')} ({item.get('from_name', '?')}, {mtype})")
        if len(non_priority) > 10:
            lines.append(f"  ... and {len(non_priority) - 10} more")
        lines.append("")

    # Queued for review
    queued = sections.get("queued", [])
    if queued:
        lines.append("-" * 50)
        lines.append(f"QUEUED FOR YOUR REVIEW ({len(queued)})")
        lines.append("-" * 50)
        for item in queued:
            lines.append(f"  * {item.get('subject', 'N/A')} (from {item.get('from_name', '?')})")
        lines.append("")

    # Autonomous decisions summary
    auto = sections.get("auto_handled", [])
    if auto and burnout_score < 7:
        lines.append("-" * 50)
        lines.append(f"HANDLED AUTONOMOUSLY ({len(auto)} decisions)")
        lines.append("-" * 50)
        for d in auto[:5]:
            ctx = d.get("context", {})
            if isinstance(ctx, str):
                ctx = json.loads(ctx)
            lines.append(f"  * [{d.get('decision_type', '?')}] "
                         f"{ctx.get('subject', 'N/A')} -> {d.get('right_hand_action', '?')}")
        if len(auto) > 5:
            lines.append(f"  ... and {len(auto) - 5} more")
        lines.append("")

    # Sign-off
    lines.append("")
    lines.append(f"Best,")
    lines.append(f"{rh_name}")
    lines.append("")
    lines.append(_build_footer(briefing_data))

    plain = "\n".join(lines)

    # Build HTML version
    html = _plain_to_html(plain, subject)

    return {"subject": subject, "plain": plain, "html": html}


def format_evening_summary(briefing_data: dict, human_name: str,
                           burnout_score: int) -> dict:
    """Format an evening summary as a professional email.

    Args:
        briefing_data: Output from RightHand.compile_briefing("evening").
        human_name: The human's name.
        burnout_score: Current burnout score (1-10).

    Returns:
        {subject: str, plain: str, html: str}
    """
    subject = briefing_data["subject"]
    rh_name = briefing_data.get("rh_name", "Chief")
    sections = briefing_data.get("sections", {})

    lines = []

    if burnout_score >= 7:
        lines.append(f"Quick wrap-up, {human_name}. Rest up tonight.")
    else:
        lines.append(f"End of day summary, {human_name}.")
    lines.append("")

    # Handled today
    auto = sections.get("auto_handled", [])
    if auto:
        lines.append("=" * 50)
        lines.append(f"HANDLED TODAY ({len(auto)} decisions)")
        lines.append("=" * 50)
        for d in auto:
            ctx = d.get("context", {})
            if isinstance(ctx, str):
                ctx = json.loads(ctx)
            lines.append(f"  * {ctx.get('subject', 'N/A')} -> {d.get('right_hand_action', '?')}")
        lines.append("")

    # Needs decision tomorrow
    needs = sections.get("needs_input", [])
    if needs:
        lines.append("-" * 50)
        lines.append(f"NEEDS YOUR DECISION TOMORROW ({len(needs)})")
        lines.append("-" * 50)
        for d in needs:
            ctx = d.get("context", {})
            if isinstance(ctx, str):
                ctx = json.loads(ctx)
            lines.append(f"  ACTION: {ctx.get('subject', 'N/A')}")
        lines.append("")

    if not auto and not needs:
        lines.append("Quiet day. Nothing to report.")
        lines.append("")

    # Sign-off
    lines.append(f"Best,")
    lines.append(f"{rh_name}")
    lines.append("")
    lines.append(_build_footer(briefing_data))

    plain = "\n".join(lines)
    html = _plain_to_html(plain, subject)

    return {"subject": subject, "plain": plain, "html": html}


def format_urgent_alert(briefing_data: dict, human_name: str) -> dict:
    """Format an urgent alert as a professional email.

    Args:
        briefing_data: Output from RightHand.compile_briefing("urgent").
        human_name: The human's name.

    Returns:
        {subject: str, plain: str, html: str}
    """
    subject = briefing_data["subject"]
    rh_name = briefing_data.get("rh_name", "Chief")
    sections = briefing_data.get("sections", {})

    lines = [f"{human_name} - items requiring immediate attention:", ""]

    critical = sections.get("critical", [])
    for item in critical:
        lines.append(f"  [CRITICAL] {item.get('subject', 'N/A')}")
        lines.append(f"    From: {item.get('from_name', 'Unknown')}")
        body = item.get("body", "")
        if body:
            for bl in body.split("\n")[:5]:
                lines.append(f"    {bl}")
        lines.append("")

    if not critical:
        lines.append("  No critical items at this time.")
        lines.append("")

    lines.append(f"- {rh_name}")
    lines.append("")
    lines.append(_build_footer(briefing_data))

    plain = "\n".join(lines)
    html = _plain_to_html(plain, subject)

    return {"subject": subject, "plain": plain, "html": html}


def _build_footer(briefing_data: dict) -> str:
    """Build the standard email footer with stats."""
    rh_name = briefing_data.get("rh_name", "Chief")
    # Get stats from briefing data
    item_count = briefing_data.get("item_count", 0)
    briefing_type = briefing_data.get("briefing_type", "briefing")

    # We include available stats in footer
    footer_parts = [
        f"This briefing was compiled by {rh_name}, your AI Chief of Staff.",
    ]
    return " ".join(footer_parts)


def _plain_to_html(plain_text: str, title: str) -> str:
    """Convert plain text briefing to simple HTML email."""
    # Escape HTML entities
    escaped = (plain_text
               .replace("&", "&amp;")
               .replace("<", "&lt;")
               .replace(">", "&gt;"))

    # Style ACTION: lines
    lines = escaped.split("\n")
    styled_lines = []
    for line in lines:
        if line.strip().startswith("ACTION:"):
            styled_lines.append(f'<span style="color:#c0392b;font-weight:bold">{line}</span>')
        elif line.strip().startswith("[CRITICAL]"):
            styled_lines.append(f'<span style="color:#e74c3c;font-weight:bold">{line}</span>')
        elif "=" * 20 in line:
            styled_lines.append(f'<hr style="border:1px solid #2c3e50">')
        elif "-" * 20 in line:
            styled_lines.append(f'<hr style="border:1px solid #bdc3c7">')
        else:
            styled_lines.append(line)

    body = "<br>\n".join(styled_lines)

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{title}</title></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
             max-width: 600px; margin: 0 auto; padding: 20px; color: #2c3e50;
             line-height: 1.6; font-size: 14px;">
{body}
</body>
</html>"""
    return html
