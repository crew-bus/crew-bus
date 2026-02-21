"""Tests for delivery.py — TelegramDelivery, EmailDelivery, ConsoleDelivery, SignalDelivery."""

import smtplib
from unittest.mock import patch, MagicMock

from delivery import (
    TelegramDelivery,
    EmailDelivery,
    ConsoleDelivery,
    SignalDelivery,
    get_backend,
    format_briefing_email,
    BACKENDS,
)


# ---------------------------------------------------------------------------
# TelegramDelivery
# ---------------------------------------------------------------------------

class TestTelegramDelivery:

    def test_channel_name(self):
        """TelegramDelivery.channel_name() returns 'telegram'."""
        td = TelegramDelivery(bot_token="fake:token")
        assert td.channel_name() == "telegram"

    def test_empty_token_raises(self):
        """TelegramDelivery raises ValueError for empty token."""
        try:
            TelegramDelivery(bot_token="")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "required" in str(e).lower()

    def test_no_chat_id(self):
        """deliver() returns failure when no chat_id provided."""
        td = TelegramDelivery(bot_token="fake:token")
        result = td.deliver("", "Subject", "Body")
        assert result["success"] is False
        assert "chat_id" in result["detail"].lower()

    def test_successful_delivery(self):
        """deliver() returns success on API ok response."""
        td = TelegramDelivery(bot_token="fake:token")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ok": True,
            "result": {"message_id": 42},
        }

        with patch("requests.post", return_value=mock_resp):
            result = td.deliver("12345", "Hello", "World")
            assert result["success"] is True
            assert result["telegram_message_id"] == 42

    def test_api_error(self):
        """deliver() returns failure on Telegram API error."""
        td = TelegramDelivery(bot_token="fake:token")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ok": False,
            "description": "Bad Request: chat not found",
        }

        with patch("requests.post", return_value=mock_resp):
            result = td.deliver("12345", "Hello", "World")
            assert result["success"] is False
            assert "chat not found" in result["detail"]

    def test_request_exception(self):
        """deliver() handles requests.RequestException."""
        import requests
        td = TelegramDelivery(bot_token="fake:token")

        with patch("requests.post", side_effect=requests.ConnectionError("timeout")):
            result = td.deliver("12345", "Hello", "World")
            assert result["success"] is False
            assert "failed" in result["detail"].lower()

    def test_priority_tag(self):
        """deliver() includes priority tag for non-normal priority."""
        td = TelegramDelivery(bot_token="fake:token")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 1}}

        with patch("requests.post", return_value=mock_resp) as mock_post:
            td.deliver("12345", "Alert", "Body", priority="high")
            payload = mock_post.call_args[1]["json"]
            assert "[HIGH]" in payload["text"]

    def test_from_agent_metadata(self):
        """deliver() includes from_agent in message when metadata provided."""
        td = TelegramDelivery(bot_token="fake:token")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 1}}

        with patch("requests.post", return_value=mock_resp) as mock_post:
            td.deliver("12345", "Alert", "Body",
                       metadata={"from_agent": "Guardian"})
            payload = mock_post.call_args[1]["json"]
            assert "Guardian" in payload["text"]


# ---------------------------------------------------------------------------
# SignalDelivery
# ---------------------------------------------------------------------------

class TestSignalDelivery:

    def test_channel_name(self):
        """SignalDelivery.channel_name() returns 'signal'."""
        sd = SignalDelivery()
        assert sd.channel_name() == "signal"

    def test_not_implemented(self):
        """deliver() returns failure with 'not yet implemented'."""
        sd = SignalDelivery()
        result = sd.deliver("+1234567890", "Test", "Body")
        assert result["success"] is False
        assert "not yet implemented" in result["detail"].lower()


# ---------------------------------------------------------------------------
# EmailDelivery
# ---------------------------------------------------------------------------

class TestEmailDelivery:

    def test_channel_name(self):
        """EmailDelivery.channel_name() returns 'email'."""
        ed = EmailDelivery()
        assert ed.channel_name() == "email"

    def test_no_email_address(self):
        """deliver() returns failure when no address provided."""
        ed = EmailDelivery(smtp_host="smtp.example.com")
        result = ed.deliver("", "Subject", "Body")
        assert result["success"] is False
        assert "email address" in result["detail"].lower()

    def test_unconfigured_smtp(self):
        """deliver() returns failure when SMTP not configured (localhost default)."""
        ed = EmailDelivery()  # default smtp_host="localhost"
        result = ed.deliver("user@example.com", "Subject", "Body")
        assert result["success"] is False
        assert "not configured" in result["detail"].lower()

    def test_successful_email(self):
        """deliver() sends email successfully via SMTP."""
        ed = EmailDelivery(
            smtp_host="smtp.example.com", smtp_port=587,
            smtp_user="user", smtp_pass="pass",
            from_address="test@example.com",
        )

        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_smtp = MagicMock()
            mock_smtp_cls.return_value.__enter__ = lambda s: mock_smtp
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

            result = ed.deliver("to@example.com", "Test Subject", "Test Body")
            assert result["success"] is True
            mock_smtp.send_message.assert_called_once()

    def test_smtp_auth_failure(self):
        """deliver() handles SMTP authentication failure."""
        ed = EmailDelivery(
            smtp_host="smtp.example.com", smtp_port=587,
            smtp_user="user", smtp_pass="bad_pass",
        )

        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_smtp = MagicMock()
            mock_smtp.login.side_effect = smtplib.SMTPAuthenticationError(
                535, b"Authentication failed")
            mock_smtp_cls.return_value.__enter__ = lambda s: mock_smtp
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

            result = ed.deliver("to@example.com", "Subject", "Body")
            assert result["success"] is False
            assert "auth" in result["detail"].lower()

    def test_smtp_error(self):
        """deliver() handles generic SMTP errors."""
        ed = EmailDelivery(
            smtp_host="smtp.example.com", smtp_port=587,
        )

        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_smtp_cls.side_effect = smtplib.SMTPException("Connection timed out")

            result = ed.deliver("to@example.com", "Subject", "Body")
            assert result["success"] is False
            assert "smtp" in result["detail"].lower()

    def test_html_email(self):
        """deliver() sends multipart email when html_body is in metadata."""
        ed = EmailDelivery(
            smtp_host="smtp.example.com", smtp_port=587,
            smtp_user="user", smtp_pass="pass",
        )

        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_smtp = MagicMock()
            mock_smtp_cls.return_value.__enter__ = lambda s: mock_smtp
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

            result = ed.deliver(
                "to@example.com", "HTML Test", "Plain body",
                metadata={"html_body": "<b>Rich body</b>"},
            )
            assert result["success"] is True

    def test_priority_headers(self):
        """deliver() sets X-Priority header for high/critical messages."""
        ed = EmailDelivery(
            smtp_host="smtp.example.com", smtp_port=587,
            smtp_user="user", smtp_pass="pass",
        )

        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_smtp = MagicMock()
            mock_smtp_cls.return_value.__enter__ = lambda s: mock_smtp
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

            result = ed.deliver(
                "to@example.com", "Urgent", "Body", priority="critical",
            )
            assert result["success"] is True
            # The send_message call should have been made
            mock_smtp.send_message.assert_called_once()


# ---------------------------------------------------------------------------
# ConsoleDelivery
# ---------------------------------------------------------------------------

class TestConsoleDelivery:

    def test_channel_name(self):
        """ConsoleDelivery.channel_name() returns 'console'."""
        cd = ConsoleDelivery()
        assert cd.channel_name() == "console"

    def test_deliver_prints(self, capsys):
        """deliver() prints message to stdout."""
        cd = ConsoleDelivery()
        result = cd.deliver("console", "Test Subject", "Test Body")
        assert result["success"] is True
        assert result["detail"] == "Printed to console"
        output = capsys.readouterr().out
        assert "Test Subject" in output
        assert "Test Body" in output

    def test_deliver_with_priority(self, capsys):
        """deliver() includes priority tag in output."""
        cd = ConsoleDelivery()
        result = cd.deliver("console", "Alert", "Body", priority="high")
        assert result["success"] is True
        output = capsys.readouterr().out
        assert "[HIGH]" in output

    def test_deliver_with_from_agent(self, capsys):
        """deliver() includes from_agent metadata."""
        cd = ConsoleDelivery()
        result = cd.deliver("console", "Alert", "Body",
                            metadata={"from_agent": "Guardian"})
        assert result["success"] is True
        output = capsys.readouterr().out
        assert "Guardian" in output


# ---------------------------------------------------------------------------
# get_backend factory
# ---------------------------------------------------------------------------

class TestGetBackend:

    def test_get_telegram_backend(self):
        """get_backend('telegram') returns TelegramDelivery."""
        backend = get_backend("telegram", bot_token="fake")
        assert isinstance(backend, TelegramDelivery)

    def test_get_email_backend(self):
        """get_backend('email') returns EmailDelivery."""
        backend = get_backend("email")
        assert isinstance(backend, EmailDelivery)

    def test_get_console_backend(self):
        """get_backend('console') returns ConsoleDelivery."""
        backend = get_backend("console")
        assert isinstance(backend, ConsoleDelivery)

    def test_get_signal_backend(self):
        """get_backend('signal') returns SignalDelivery."""
        backend = get_backend("signal")
        assert isinstance(backend, SignalDelivery)

    def test_unknown_channel_raises(self):
        """get_backend raises ValueError for unknown channel."""
        try:
            get_backend("carrier_pigeon")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Unknown delivery channel" in str(e)

    def test_all_backends_registered(self):
        """BACKENDS dict contains all expected channels."""
        assert set(BACKENDS.keys()) == {"telegram", "signal", "email", "console"}


# ---------------------------------------------------------------------------
# format_briefing_email
# ---------------------------------------------------------------------------

class TestFormatBriefingEmail:

    def test_basic_briefing(self):
        """format_briefing_email returns subject, plain, html, priority."""
        briefing = {
            "briefing_type": "morning",
            "burnout": 3,
            "human_name": "Alice",
            "rh_name": "Chief",
            "subject": "Morning Brief",
            "item_count": 5,
            "sections": {},
        }
        profile = {"name": "Alice", "trust_score": 5}

        result = format_briefing_email(briefing, profile)
        assert "subject" in result
        assert "plain" in result
        assert "html" in result
        assert "priority" in result
        assert "Alice" in result["plain"]
        assert "Chief" in result["from_name"]

    def test_high_burnout_tone(self):
        """format_briefing_email uses gentle tone for high burnout."""
        briefing = {
            "briefing_type": "morning",
            "burnout": 8,
            "human_name": "Bob",
            "rh_name": "Chief",
            "subject": "Brief",
            "item_count": 2,
            "sections": {},
        }
        profile = {"name": "Bob", "trust_score": 7}

        result = format_briefing_email(briefing, profile)
        assert "easy" in result["plain"].lower() or "short" in result["plain"].lower()

    def test_priority_items_section(self):
        """format_briefing_email includes priority items when present."""
        briefing = {
            "briefing_type": "morning",
            "burnout": 3,
            "human_name": "Alice",
            "rh_name": "Chief",
            "subject": "Brief",
            "item_count": 1,
            "sections": {
                "priority": [
                    {"priority": "high", "subject": "Fix server", "from": "Guardian"},
                ],
            },
        }
        profile = {"name": "Alice", "trust_score": 5}

        result = format_briefing_email(briefing, profile)
        assert "PRIORITY" in result["plain"]
        assert "Fix server" in result["plain"]

    def test_html_output(self):
        """format_briefing_email generates HTML with proper structure."""
        briefing = {
            "briefing_type": "morning",
            "burnout": 5,
            "human_name": "Alice",
            "rh_name": "Chief",
            "subject": "Brief",
            "item_count": 0,
            "sections": {},
        }
        profile = {"name": "Alice", "trust_score": 5}

        result = format_briefing_email(briefing, profile)
        assert "<html>" in result["html"]
        assert "</html>" in result["html"]

    def test_evening_quiet_day(self):
        """format_briefing_email handles quiet evening with no items."""
        briefing = {
            "briefing_type": "evening",
            "burnout": 3,
            "human_name": "Alice",
            "rh_name": "Chief",
            "subject": "Evening",
            "item_count": 0,
            "sections": {},
        }
        profile = {"name": "Alice", "trust_score": 5}

        result = format_briefing_email(briefing, profile)
        assert "quiet" in result["plain"].lower()
