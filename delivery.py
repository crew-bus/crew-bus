"""
crew-bus delivery abstraction (v2).

Pluggable delivery backends for routing messages to agents through their
configured channel (Telegram, Signal, Email, or console stdout).
"""

import smtplib
from abc import ABC, abstractmethod
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import requests


class DeliveryBackend(ABC):
    """Abstract base class for message delivery backends."""

    @abstractmethod
    def deliver(self, recipient_address: str, subject: str,
                body: str, priority: str = "normal",
                metadata: Optional[dict] = None) -> dict:
        """Deliver a message through this channel.

        Args:
            recipient_address: Channel-specific address (chat ID, phone, email).
            subject: Message subject line.
            body: Message body text.
            priority: Message priority level.
            metadata: Optional extra data (from_agent, message_id, html_body, etc).

        Returns:
            Dict with at least {"success": bool, "detail": str}.
        """
        ...

    @abstractmethod
    def channel_name(self) -> str:
        """Return the channel identifier (telegram, signal, email, console)."""
        ...


class TelegramDelivery(DeliveryBackend):
    """Deliver messages via Telegram Bot API.

    Requires a bot token. The recipient_address is the Telegram chat_id.
    """

    API_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, bot_token: str):
        if not bot_token:
            raise ValueError("Telegram bot_token is required")
        self.bot_token = bot_token
        self._url = self.API_URL.format(token=bot_token)

    def channel_name(self) -> str:
        return "telegram"

    def deliver(self, recipient_address: str, subject: str,
                body: str, priority: str = "normal",
                metadata: Optional[dict] = None) -> dict:
        """Send a message via Telegram.

        Formats the message with subject as bold header, priority tag if
        non-normal, and body text below.
        """
        if not recipient_address:
            return {"success": False, "detail": "No chat_id provided"}

        pri_tag = f" [{priority.upper()}]" if priority != "normal" else ""
        from_tag = ""
        if metadata and metadata.get("from_agent"):
            from_tag = f"\nFrom: {metadata['from_agent']}"

        text = f"<b>{subject}</b>{pri_tag}{from_tag}\n\n{body}"

        payload = {
            "chat_id": recipient_address,
            "text": text,
            "parse_mode": "HTML",
        }

        try:
            resp = requests.post(self._url, json=payload, timeout=10)
            data = resp.json()
            if data.get("ok"):
                return {"success": True, "detail": f"Delivered to chat {recipient_address}",
                        "telegram_message_id": data["result"]["message_id"]}
            return {"success": False, "detail": data.get("description", "Unknown Telegram error")}
        except requests.RequestException as e:
            return {"success": False, "detail": f"Telegram request failed: {e}"}


class SignalDelivery(DeliveryBackend):
    """Deliver messages via signal-cli.

    TODO: Implement actual signal-cli integration.
    The recipient_address is the phone number in E.164 format.
    """

    def __init__(self, signal_cli_path: str = "signal-cli",
                 sender_number: str = ""):
        self.signal_cli_path = signal_cli_path
        self.sender_number = sender_number

    def channel_name(self) -> str:
        return "signal"

    def deliver(self, recipient_address: str, subject: str,
                body: str, priority: str = "normal",
                metadata: Optional[dict] = None) -> dict:
        """Send a message via Signal.

        TODO: Shell out to signal-cli or use signal-cli JSON-RPC daemon.
        Expected implementation:
            import subprocess
            pri_tag = f" [{priority.upper()}]" if priority != "normal" else ""
            text = f"{subject}{pri_tag}\n\n{body}"
            cmd = [self.signal_cli_path, "-a", self.sender_number,
                   "send", "-m", text, recipient_address]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return {"success": True, "detail": f"Sent via Signal to {recipient_address}"}
            return {"success": False, "detail": result.stderr}
        """
        return {
            "success": False,
            "detail": "Signal delivery not yet implemented - message queued only",
        }


class EmailDelivery(DeliveryBackend):
    """Deliver messages via SMTP with TLS support.

    Sends both plain text and optional HTML (for briefings).
    The recipient_address is the email address.
    """

    def __init__(self, smtp_host: str = "localhost", smtp_port: int = 587,
                 smtp_user: str = "", smtp_pass: str = "",
                 from_address: str = "crew-bus@localhost",
                 use_tls: bool = True):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_pass = smtp_pass
        self.from_address = from_address
        self.use_tls = use_tls

    def channel_name(self) -> str:
        return "email"

    def deliver(self, recipient_address: str, subject: str,
                body: str, priority: str = "normal",
                metadata: Optional[dict] = None) -> dict:
        """Send a message via SMTP email.

        Supports HTML body via metadata["html_body"].
        Sets X-Priority header for high/critical messages.
        """
        if not recipient_address:
            return {"success": False, "detail": "No email address provided"}
        if not self.smtp_host or self.smtp_host == "localhost":
            return {"success": False, "detail": "SMTP not configured - message queued only"}

        html_body = (metadata or {}).get("html_body")

        try:
            if html_body:
                msg = MIMEMultipart("alternative")
                msg.attach(MIMEText(body, "plain", "utf-8"))
                msg.attach(MIMEText(html_body, "html", "utf-8"))
            else:
                msg = MIMEText(body, "plain", "utf-8")

            msg["Subject"] = subject
            msg["From"] = self.from_address
            msg["To"] = recipient_address

            # Set priority header
            if priority in ("high", "critical"):
                msg["X-Priority"] = "1" if priority == "critical" else "2"
                msg["Importance"] = "high"

            if metadata and metadata.get("from_agent"):
                msg["X-CrewBus-Agent"] = metadata["from_agent"]

            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as server:
                if self.use_tls:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                if self.smtp_user and self.smtp_pass:
                    server.login(self.smtp_user, self.smtp_pass)
                server.send_message(msg)

            return {"success": True, "detail": f"Email sent to {recipient_address}"}

        except smtplib.SMTPAuthenticationError as e:
            return {"success": False, "detail": f"SMTP auth failed: {e}"}
        except smtplib.SMTPException as e:
            return {"success": False, "detail": f"SMTP error: {e}"}
        except Exception as e:
            return {"success": False, "detail": f"Email delivery failed: {e}"}


class ConsoleDelivery(DeliveryBackend):
    """Deliver messages by printing to stdout. Used for local testing."""

    def channel_name(self) -> str:
        return "console"

    def deliver(self, recipient_address: str, subject: str,
                body: str, priority: str = "normal",
                metadata: Optional[dict] = None) -> dict:
        """Print message to stdout."""
        pri_tag = f" [{priority.upper()}]" if priority != "normal" else ""
        from_tag = ""
        if metadata and metadata.get("from_agent"):
            from_tag = f" (from {metadata['from_agent']})"

        print(f"\n{'='*60}")
        print(f"  CREW-BUS MESSAGE{pri_tag}{from_tag}")
        print(f"  To: {recipient_address or 'console'}")
        print(f"  Subject: {subject}")
        print(f"{'='*60}")
        if body:
            for line in body.split("\n"):
                print(f"  {line}")
        print(f"{'='*60}\n")

        return {"success": True, "detail": "Printed to console"}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

BACKENDS: dict[str, type[DeliveryBackend]] = {
    "telegram": TelegramDelivery,
    "signal": SignalDelivery,
    "email": EmailDelivery,
    "console": ConsoleDelivery,
}


def get_backend(channel: str, **kwargs) -> DeliveryBackend:
    """Factory function to get a delivery backend by channel name.

    Args:
        channel: One of 'telegram', 'signal', 'email', 'console'.
        **kwargs: Channel-specific config (bot_token, smtp_host, etc).

    Returns:
        An instantiated DeliveryBackend.
    """
    cls = BACKENDS.get(channel)
    if not cls:
        raise ValueError(f"Unknown delivery channel '{channel}'. Options: {list(BACKENDS.keys())}")
    return cls(**kwargs)


# ---------------------------------------------------------------------------
# Briefing Email Formatting
# ---------------------------------------------------------------------------

def format_briefing_email(briefing_data: dict, human_profile: dict) -> dict:
    """Format a Crew Boss briefing as a professional email.

    Creates a competent chief-of-staff email from briefing data produced by
    RightHand.compile_briefing(). Tone adapts to burnout level:
      - Low burnout: direct and efficient
      - High burnout: gentler, recommends delegation

    Args:
        briefing_data: Dict from RightHand.compile_briefing() with keys:
            subject, body_plain, body_html, priority, item_count,
            briefing_type, burnout, human_name, rh_name, sections.
        human_profile: Dict with human details. Expected keys:
            name (str), trust_score (int), channel (str).

    Returns:
        Dict with keys:
            subject (str):     Email subject line.
            plain (str):       Plain text body.
            html (str):        HTML body.
            priority (str):    Email priority.
            from_name (str):   Crew Boss's name.
    """
    briefing_type = briefing_data.get("briefing_type", "morning")
    burnout = briefing_data.get("burnout", 5)
    human_name = briefing_data.get("human_name", human_profile.get("name", "Boss"))
    rh_name = briefing_data.get("rh_name", "Chief")
    sections = briefing_data.get("sections", {})
    subject = briefing_data.get("subject", "Briefing")
    item_count = briefing_data.get("item_count", 0)

    # Build plain text body
    lines = []

    # Greeting (burnout-adaptive)
    if burnout >= 7:
        lines.append(f"Hey {human_name}. Taking it easy today — here's the short version.\n")
    elif burnout >= 5:
        lines.append(f"Good morning, {human_name}. Here's your rundown.\n")
    else:
        lines.append(f"Morning, {human_name}. Full speed ahead.\n")

    # Priority items
    priority_items = sections.get("priority", [])
    if priority_items:
        lines.append("=" * 50)
        lines.append("PRIORITY ITEMS")
        lines.append("=" * 50)
        for item in priority_items:
            tag = item.get("priority", "HIGH").upper()
            lines.append(f"  ACTION: [{tag}] {item.get('subject', 'Untitled')}")
            if item.get("from"):
                lines.append(f"    From: {item['from']}")
            body_preview = item.get("body", "")
            if body_preview:
                # Truncate long bodies
                preview = body_preview[:200]
                if len(body_preview) > 200:
                    preview += "..."
                lines.append(f"    {preview}")
            lines.append("")
        lines.append("-" * 40)
        lines.append("")

    # Overnight / queued items
    queued = sections.get("queued", [])
    if queued:
        lines.append("=" * 50)
        lines.append("QUEUED FOR REVIEW")
        lines.append("=" * 50)
        for item in queued:
            lines.append(f"  - [{item.get('priority', 'normal').upper()}] {item.get('subject', '')}")
            if item.get("from"):
                lines.append(f"    From: {item['from']}")
        lines.append("")

    # Handled autonomously
    autonomous = sections.get("autonomous", [])
    if autonomous and burnout < 7:
        lines.append("=" * 50)
        lines.append("HANDLED AUTONOMOUSLY")
        lines.append("=" * 50)
        for item in autonomous:
            lines.append(f"  - {item.get('action', '')} — {item.get('subject', '')}")
        lines.append("")

    # Needs human decision
    needs_decision = sections.get("needs_decision", [])
    if needs_decision:
        lines.append("=" * 50)
        lines.append("NEEDS YOUR DECISION")
        lines.append("=" * 50)
        for item in needs_decision:
            lines.append(f"  - {item.get('subject', '')}")
            if item.get("context"):
                lines.append(f"    Context: {item['context']}")
        lines.append("")

    # Evening summary specifics
    if briefing_type == "evening":
        if not priority_items and not queued and not needs_decision:
            lines.append("Quiet day. Nothing to report.\n")

    # Footer
    trust_score = human_profile.get("trust_score", 1)
    decisions_today = sections.get("decisions_today", 0)
    autonomous_count = sections.get("autonomous_count", 0)
    escalated_count = sections.get("escalated_count", 0)
    accuracy_pct = sections.get("accuracy_pct", 0)

    lines.append(f"Best,")
    lines.append(f"{rh_name}\n")
    lines.append(f"This briefing was compiled by {rh_name}, your AI Chief of Staff.")

    if decisions_today > 0:
        lines.append(
            f"Trust Level: {trust_score}/10 | "
            f"Decisions today: {decisions_today} "
            f"({autonomous_count} autonomous, {escalated_count} escalated) | "
            f"Accuracy this week: {accuracy_pct}%"
        )

    plain = "\n".join(lines)

    # Build HTML from plain text
    html = _plain_to_html_briefing(plain, subject)

    return {
        "subject": subject,
        "plain": plain,
        "html": html,
        "priority": briefing_data.get("priority", "normal"),
        "from_name": rh_name,
    }


def _plain_to_html_briefing(plain_text: str, title: str) -> str:
    """Convert plain-text briefing to styled HTML email."""
    import html as html_mod
    escaped = html_mod.escape(plain_text)

    # Style ACTION: lines
    styled = escaped.replace(
        "ACTION:", '<span style="color:#c0392b;font-weight:bold">ACTION:</span>'
    )
    # Style [CRITICAL] tags
    styled = styled.replace(
        "[CRITICAL]", '<span style="color:#e74c3c;font-weight:bold">[CRITICAL]</span>'
    )
    styled = styled.replace(
        "[HIGH]", '<span style="color:#e67e22;font-weight:bold">[HIGH]</span>'
    )

    # Convert section dividers to HR tags
    for divider in ("=" * 50, "-" * 40):
        escaped_div = html_mod.escape(divider)
        styled = styled.replace(escaped_div, "<hr>")

    return f"""\
<html>
<head><title>{html_mod.escape(title)}</title></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
             max-width: 600px; margin: 0 auto; padding: 20px;
             color: #2c3e50; line-height: 1.6;">
<pre style="white-space: pre-wrap; font-family: inherit;">{styled}</pre>
</body>
</html>"""
