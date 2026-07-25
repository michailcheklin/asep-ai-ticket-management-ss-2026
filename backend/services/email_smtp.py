"""Outbound SMTP helper for backend-controlled email ticket transmission."""

from __future__ import annotations

import re
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from ..config import (
    EMAIL_SMTP_FROM,
    EMAIL_SMTP_HOST,
    EMAIL_SMTP_PASSWORD,
    EMAIL_SMTP_PORT,
    EMAIL_SMTP_USE_TLS,
    EMAIL_SMTP_USER,
)
from ..services.BackendLoggingService import BackendLogger

mail_logger = BackendLogger("EmailSMTP")

_HEADER_INJECTION_RE = re.compile(r"[\r\n]")


@dataclass(frozen=True)
class OutboundMail:
    """A prepared outbound message (no secrets or full PII in logs)."""

    to_address: str
    subject: str
    text_body: str
    html_body: str | None
    message_id: str


class EmailSendError(Exception):
    """Raised when SMTP delivery fails before the server accepts the message."""


class EmailUncertainError(Exception):
    """Raised when the message may already have been accepted by the SMTP server."""


def sanitize_header_value(value: str) -> str:
    """Strip CR/LF to prevent header injection."""
    return _HEADER_INJECTION_RE.sub(" ", (value or "").strip())


def build_message_id(ticket_id: int, domain: str | None = None) -> str:
    """Create a stable-looking Message-ID for idempotent SMTP retries."""
    host = (domain or EMAIL_SMTP_FROM.split("@")[-1] or "localhost").strip() or "localhost"
    # make_msgid already adds angle brackets; keep a ticket hint in the local part.
    return make_msgid(idstring=f"ticket-{ticket_id}", domain=host)


def build_email_message(mail: OutboundMail, from_address: str | None = None) -> EmailMessage:
    """Build a multipart/alternative EmailMessage with a fixed Message-ID."""
    msg = EmailMessage()
    sender = sanitize_header_value(from_address or EMAIL_SMTP_FROM)
    msg["From"] = formataddr(("IT-Support", sender)) if sender else sender
    msg["To"] = sanitize_header_value(mail.to_address)
    msg["Subject"] = sanitize_header_value(mail.subject)
    msg["Message-ID"] = mail.message_id if mail.message_id.startswith("<") else f"<{mail.message_id}>"
    msg.set_content(mail.text_body or "")
    if mail.html_body:
        msg.add_alternative(mail.html_body, subtype="html")
    return msg


def send_email(mail: OutboundMail) -> None:
    """
    Send ``mail`` via the configured SMTP server.

    Raises:
        EmailSendError: clear failure before/during handshake or rejected send
        EmailUncertainError: ambiguous state after the SMTP DATA phase may have succeeded
    """
    message = build_email_message(mail)
    host = EMAIL_SMTP_HOST
    port = EMAIL_SMTP_PORT

    mail_logger.info(
        f"Sending transmission mail message_id={mail.message_id!r} "
        f"via {host}:{port}"
    )

    try:
        if EMAIL_SMTP_USE_TLS:
            context = ssl.create_default_context()
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
                if EMAIL_SMTP_USER:
                    smtp.login(EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                if EMAIL_SMTP_USER:
                    smtp.login(EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD)
                smtp.send_message(message)
    except smtplib.SMTPServerDisconnected as exc:
        # Connection dropped after DATA may mean the server accepted the message.
        raise EmailUncertainError(str(exc)) from exc
    except smtplib.SMTPResponseException as exc:
        # 2xx after send is success; other codes are failures. If we somehow get
        # here after a partial send, treat 4xx timeouts as uncertain.
        if 400 <= int(getattr(exc, "smtp_code", 0) or 0) < 500:
            raise EmailUncertainError(str(exc)) from exc
        raise EmailSendError(str(exc)) from exc
    except (smtplib.SMTPException, OSError, TimeoutError) as exc:
        raise EmailSendError(str(exc)) from exc
