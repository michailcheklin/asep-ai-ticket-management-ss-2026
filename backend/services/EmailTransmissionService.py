"""Email ticket transmission: first public support article → external recipient.

Architecture decision
---------------------
Outbound mail is sent by the **backend** (SMTP), not via Zammad's notification
channel. Zammad cannot provide durable per-ticket/per-recipient duplicate
protection without tags or custom fields, and must not mutate the ticket for
this feature. The backend therefore:

1. Receives an article-created webhook,
2. Re-fetches ticket + article from Zammad (do not trust webhook visibility),
3. Atomically reserves a SQLite transmission row (unique ticket+recipient),
4. Sends a controlled multipart email via SMTP,
5. Never writes tags, articles, or status changes back to Zammad.
"""

from __future__ import annotations

import html
import re
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parseaddr

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ..api.zammad import get_ticket, get_ticket_article, get_user
from ..config import (
    EMAIL_TICKET_TRANSMISSION_ENABLED,
    EMAIL_TICKET_TRANSMISSION_RECIPIENT,
    ZAMMAD_PUBLIC_URL,
)
from ..db.models import EmailTicketTransmission, TransmissionStatus
from ..db.session import get_session_factory, init_db
from ..services.BackendLoggingService import BackendLogger
from ..services.email_smtp import (
    EmailSendError,
    EmailUncertainError,
    OutboundMail,
    build_message_id,
    send_email,
)

transmission_logger = BackendLogger("EmailTransmission")

_MATRIKEL_TITLE_RE = re.compile(r"^\s*\[([^\]]+)\]\s*")
_MATRIKEL_BODY_RE = re.compile(
    r"Matrikelnummer\s*:\s*([^\n\r<]+)", re.IGNORECASE
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)

# Public chatbot articles use these markers; they are not human support replies.
_BOT_ARTICLE_MARKERS = (
    "VOM BOT ANGEBOTENE LÖSUNGEN",
    "GESPRÄCHSZUSAMMENFASSUNG",
    "Das Gespräch mit dem Chatbot wurde abgeschlossen",
)


class EmailTransmissionConfigError(Exception):
    """Raised when the feature is enabled but misconfigured."""


@dataclass(frozen=True)
class TransmissionResult:
    """Outcome of handling an article-created event (safe for API responses)."""

    status: str
    reason: str
    ticket_id: int | None = None
    article_id: int | None = None
    transmission_id: int | None = None


def normalize_recipient(address: str) -> str:
    """Normalize an email address for storage and uniqueness checks."""
    _, addr = parseaddr((address or "").strip())
    return addr.lower()


def strip_html_to_text(raw: str) -> str:
    """Convert HTML article bodies to plain text without executing markup."""
    text = _BR_RE.sub("\n", raw or "")
    text = _HTML_TAG_RE.sub("", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def extract_matrikelnummer(ticket: dict, article_body: str = "") -> str | None:
    """Best-effort matrikel extraction from title/body; missing is OK."""
    title = str(ticket.get("title") or "")
    match = _MATRIKEL_TITLE_RE.match(title)
    if match:
        value = match.group(1).strip()
        if value and value.lower() != "unknown":
            return value

    for source in (article_body, title):
        body_match = _MATRIKEL_BODY_RE.search(source or "")
        if body_match:
            value = body_match.group(1).strip()
            if value and value.lower() != "unknown":
                return value
    return None


def ticket_link(ticket_id: int) -> str | None:
    """Return a zoom URL when a public Zammad base URL is configured."""
    if not ZAMMAD_PUBLIC_URL:
        return None
    return f"{ZAMMAD_PUBLIC_URL}/#ticket/zoom/{ticket_id}"


def is_public_support_article(article: dict) -> bool:
    """
    Return True when the article is a customer-visible support-staff reply.

    Criteria (after Zammad re-fetch):
    - exists and belongs to a ticket
    - public (internal is false)
    - sender is Agent (not Customer / System)
    - not a known chatbot handoff/solutions article
    """
    if not isinstance(article, dict):
        return False
    if article.get("ticket_id") in (None, ""):
        return False

    internal = article.get("internal")
    if internal is True or str(internal).lower() in {"true", "1"}:
        return False
    # Treat missing/None as non-public to avoid accidental transmission.
    if internal is not False and str(internal).lower() not in {"false", "0"}:
        return False

    sender = str(article.get("sender") or "").strip()
    if sender != "Agent":
        return False

    body_text = strip_html_to_text(str(article.get("body") or ""))
    if any(marker in body_text for marker in _BOT_ARTICLE_MARKERS):
        return False

    return True


def parse_article_webhook_ids(payload: dict) -> tuple[int | None, int | None]:
    """Extract ticket_id and article_id from a Zammad webhook payload."""
    if not isinstance(payload, dict):
        return None, None

    article = payload.get("article") if isinstance(payload.get("article"), dict) else {}
    ticket = payload.get("ticket") if isinstance(payload.get("ticket"), dict) else {}

    article_id = (
        article.get("id")
        or payload.get("article_id")
        or payload.get("id")
    )
    ticket_id = (
        article.get("ticket_id")
        or ticket.get("id")
        or payload.get("ticket_id")
    )

    def _as_int(value) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    return _as_int(ticket_id), _as_int(article_id)


def require_transmission_config() -> str:
    """
    Validate feature configuration when enabled.

    :return: Normalized recipient address
    :raises EmailTransmissionConfigError: when enabled without a valid recipient
    """
    if not EMAIL_TICKET_TRANSMISSION_ENABLED:
        raise EmailTransmissionConfigError("Email ticket transmission is disabled")

    recipient = normalize_recipient(EMAIL_TICKET_TRANSMISSION_RECIPIENT)
    if not recipient or "@" not in recipient:
        raise EmailTransmissionConfigError(
            "EMAIL_TICKET_TRANSMISSION_ENABLED is true but "
            "EMAIL_TICKET_TRANSMISSION_RECIPIENT is missing or invalid. "
            "Set a valid recipient address in the deployment configuration."
        )
    return recipient


def _customer_display(user: dict | None, ticket: dict) -> tuple[str, str]:
    """Return (display_name, email) for the ticket customer without logging PII."""
    if user:
        firstname = str(user.get("firstname") or "").strip()
        lastname = str(user.get("lastname") or "").strip()
        name = f"{firstname} {lastname}".strip() or str(user.get("login") or "").strip()
        email = str(user.get("email") or "").strip()
        if name or email:
            return name or email, email

    # Fallback: Zammad sometimes embeds "guess:email" in customer_id
    customer_id = ticket.get("customer_id")
    if isinstance(customer_id, str) and customer_id.startswith("guess:"):
        email = customer_id.split(":", 1)[1].strip()
        return email, email
    return "", ""


def build_transmission_bodies(
    *,
    user_name: str,
    user_email: str,
    matrikelnummer: str | None,
    ticket_number: str,
    ticket_id: int,
    ticket_title: str,
    article_body: str,
    link: str | None,
) -> tuple[str, str]:
    """Build plain-text and HTML bodies containing only allowed fields."""
    plain_article = strip_html_to_text(article_body)
    lines = [
        "Ticket-Übertragung (öffentlicher Support-Artikel)",
        "",
        f"Name: {user_name or '(nicht angegeben)'}",
        f"E-Mail: {user_email or '(nicht angegeben)'}",
    ]
    if matrikelnummer:
        lines.append(f"Matrikelnummer: {matrikelnummer}")
    lines.extend(
        [
            f"Ticketnummer: {ticket_number or ticket_id}",
            f"Ticket-ID: {ticket_id}",
            f"Betreff: {ticket_title}",
        ]
    )
    if link:
        lines.append(f"Zammad-Link: {link}")
    lines.extend(["", "Inhalt des öffentlichen Support-Artikels:", plain_article])
    text_body = "\n".join(lines)

    html_lines = [
        "<p><strong>Ticket-Übertragung</strong> (öffentlicher Support-Artikel)</p>",
        "<ul>",
        f"<li><strong>Name:</strong> {html.escape(user_name or '(nicht angegeben)')}</li>",
        f"<li><strong>E-Mail:</strong> {html.escape(user_email or '(nicht angegeben)')}</li>",
    ]
    if matrikelnummer:
        html_lines.append(
            f"<li><strong>Matrikelnummer:</strong> {html.escape(matrikelnummer)}</li>"
        )
    html_lines.extend(
        [
            f"<li><strong>Ticketnummer:</strong> {html.escape(str(ticket_number or ticket_id))}</li>",
            f"<li><strong>Ticket-ID:</strong> {html.escape(str(ticket_id))}</li>",
            f"<li><strong>Betreff:</strong> {html.escape(ticket_title)}</li>",
        ]
    )
    if link:
        safe_link = html.escape(link, quote=True)
        html_lines.append(
            f'<li><strong>Zammad-Link:</strong> <a href="{safe_link}">{safe_link}</a></li>'
        )
    html_lines.append("</ul>")
    html_lines.append("<p><strong>Inhalt des öffentlichen Support-Artikels:</strong></p>")
    # Escape article content — never embed raw HTML from Zammad.
    html_lines.append(f"<pre>{html.escape(plain_article)}</pre>")
    return text_body, "\n".join(html_lines)


class EmailTransmissionService:
    """Orchestrates eligibility checks, atomic reservation, and SMTP send."""

    def __init__(
        self,
        session_factory: sessionmaker[Session] | None = None,
        mail_sender=send_email,
    ) -> None:
        if session_factory is None:
            init_db()
            self._session_factory = get_session_factory()
        else:
            self._session_factory = session_factory
        self._mail_sender = mail_sender

    def handle_article_created(self, payload: dict) -> TransmissionResult:
        """Process a Zammad article-created webhook payload."""
        if not EMAIL_TICKET_TRANSMISSION_ENABLED:
            return TransmissionResult(status="ignored", reason="disabled")

        try:
            recipient = require_transmission_config()
        except EmailTransmissionConfigError as exc:
            transmission_logger.error(f"Configuration error: {exc}")
            raise

        ticket_id, article_id = parse_article_webhook_ids(payload)
        if ticket_id is None or article_id is None:
            transmission_logger.warning(
                "Article webhook missing ticket_id or article_id"
            )
            return TransmissionResult(
                status="ignored",
                reason="missing_ids",
                ticket_id=ticket_id,
                article_id=article_id,
            )

        return self.process_article(ticket_id=ticket_id, article_id=article_id, recipient=recipient)

    def process_article(
        self,
        *,
        ticket_id: int,
        article_id: int,
        recipient: str | None = None,
    ) -> TransmissionResult:
        """Validate, reserve, and send for a concrete ticket/article pair."""
        try:
            recipient_normalized = recipient or require_transmission_config()
        except EmailTransmissionConfigError:
            raise

        ticket = get_ticket(ticket_id)
        if not ticket:
            transmission_logger.error(
                f"Transmission aborted: ticket {ticket_id} not found "
                f"(article_id={article_id})"
            )
            return TransmissionResult(
                status="error",
                reason="ticket_not_found",
                ticket_id=ticket_id,
                article_id=article_id,
            )

        article = get_ticket_article(article_id)
        if not article:
            transmission_logger.error(
                f"Transmission aborted: article {article_id} not found "
                f"(ticket_id={ticket_id})"
            )
            return TransmissionResult(
                status="error",
                reason="article_not_found",
                ticket_id=ticket_id,
                article_id=article_id,
            )

        article_ticket_id = article.get("ticket_id")
        try:
            article_ticket_id = int(article_ticket_id) if article_ticket_id is not None else None
        except (TypeError, ValueError):
            article_ticket_id = None
        if article_ticket_id != ticket_id:
            transmission_logger.warning(
                f"Article {article_id} does not belong to ticket {ticket_id}"
            )
            return TransmissionResult(
                status="ignored",
                reason="article_ticket_mismatch",
                ticket_id=ticket_id,
                article_id=article_id,
            )

        if not is_public_support_article(article):
            transmission_logger.info(
                f"Skipping non-eligible article article_id={article_id} "
                f"ticket_id={ticket_id}"
            )
            return TransmissionResult(
                status="ignored",
                reason="not_eligible",
                ticket_id=ticket_id,
                article_id=article_id,
            )

        message_id = build_message_id(ticket_id)
        reserved = self._reserve_transmission(
            ticket_id=ticket_id,
            recipient_normalized=recipient_normalized,
            article_id=article_id,
            message_id=message_id,
        )
        if reserved is None:
            transmission_logger.info(
                f"Duplicate transmission skipped ticket_id={ticket_id} "
                f"article_id={article_id}"
            )
            return TransmissionResult(
                status="ignored",
                reason="already_reserved_or_sent",
                ticket_id=ticket_id,
                article_id=article_id,
            )

        return self._send_reserved(
            record=reserved,
            ticket=ticket,
            article=article,
            recipient=recipient_normalized,
        )

    def _reserve_transmission(
        self,
        *,
        ticket_id: int,
        recipient_normalized: str,
        article_id: int,
        message_id: str,
    ) -> EmailTicketTransmission | None:
        """Atomically insert a pending row; return None if already reserved."""
        session = self._session_factory()
        try:
            record = EmailTicketTransmission(
                ticket_id=ticket_id,
                recipient_normalized=recipient_normalized,
                triggering_article_id=article_id,
                message_id=message_id,
                status=TransmissionStatus.PENDING.value,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            transmission_logger.info(
                f"Reserved transmission id={record.id} ticket_id={ticket_id} "
                f"article_id={article_id} status={record.status}"
            )
            # Detach for use outside the session
            session.expunge(record)
            return record
        except IntegrityError:
            session.rollback()
            return None
        except Exception as exc:
            session.rollback()
            transmission_logger.error(
                f"Database error while reserving transmission "
                f"ticket_id={ticket_id} article_id={article_id}: {exc}"
            )
            raise
        finally:
            session.close()

    def _send_reserved(
        self,
        *,
        record: EmailTicketTransmission,
        ticket: dict,
        article: dict,
        recipient: str,
    ) -> TransmissionResult:
        """Send mail for an already-reserved transmission and update status."""
        ticket_id = record.ticket_id
        article_id = record.triggering_article_id

        customer_id = ticket.get("customer_id")
        user = None
        if isinstance(customer_id, int) or (
            isinstance(customer_id, str) and customer_id.isdigit()
        ):
            user = get_user(int(customer_id))

        user_name, user_email = _customer_display(user, ticket)
        article_body = str(article.get("body") or "")
        matrikel = extract_matrikelnummer(ticket, article_body)
        ticket_number = str(ticket.get("number") or "")
        ticket_title = str(ticket.get("title") or "")
        link = ticket_link(ticket_id)

        text_body, html_body = build_transmission_bodies(
            user_name=user_name,
            user_email=user_email,
            matrikelnummer=matrikel,
            ticket_number=ticket_number,
            ticket_id=ticket_id,
            ticket_title=ticket_title,
            article_body=article_body,
            link=link,
        )

        subject = f"Ticket-Übertragung #{ticket_number or ticket_id}: {ticket_title}"
        mail = OutboundMail(
            to_address=recipient,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            message_id=record.message_id,
        )

        try:
            self._mail_sender(mail)
            self._update_status(
                record.id,
                TransmissionStatus.SENT,
                sent_at=datetime.now(timezone.utc),
            )
            transmission_logger.info(
                f"Transmission sent id={record.id} ticket_id={ticket_id} "
                f"article_id={article_id} status=sent"
            )
            return TransmissionResult(
                status="sent",
                reason="ok",
                ticket_id=ticket_id,
                article_id=article_id,
                transmission_id=record.id,
            )
        except EmailUncertainError as exc:
            self._update_status(
                record.id,
                TransmissionStatus.UNCERTAIN,
                error_message=_safe_error(exc),
            )
            transmission_logger.error(
                f"Transmission uncertain id={record.id} ticket_id={ticket_id} "
                f"article_id={article_id} cause={exc.__class__.__name__}"
            )
            return TransmissionResult(
                status="uncertain",
                reason="smtp_uncertain",
                ticket_id=ticket_id,
                article_id=article_id,
                transmission_id=record.id,
            )
        except EmailSendError as exc:
            self._update_status(
                record.id,
                TransmissionStatus.FAILED,
                error_message=_safe_error(exc),
            )
            transmission_logger.error(
                f"Transmission failed id={record.id} ticket_id={ticket_id} "
                f"article_id={article_id} cause={exc.__class__.__name__}"
            )
            return TransmissionResult(
                status="failed",
                reason="smtp_error",
                ticket_id=ticket_id,
                article_id=article_id,
                transmission_id=record.id,
            )

    def _update_status(
        self,
        transmission_id: int,
        status: TransmissionStatus,
        *,
        sent_at: datetime | None = None,
        error_message: str | None = None,
    ) -> None:
        session = self._session_factory()
        try:
            record = session.get(EmailTicketTransmission, transmission_id)
            if record is None:
                transmission_logger.error(
                    f"Could not update missing transmission id={transmission_id}"
                )
                return
            record.status = status.value
            if sent_at is not None:
                record.sent_at = sent_at
            if error_message is not None:
                record.error_message = error_message
            session.commit()
        except Exception as exc:
            session.rollback()
            transmission_logger.error(
                f"Database error updating transmission id={transmission_id}: {exc}"
            )
        finally:
            session.close()


def _safe_error(exc: BaseException) -> str:
    """Store a short technical fault code without SMTP payloads or credentials."""
    if isinstance(exc, smtplib.SMTPResponseException):
        code = getattr(exc, "smtp_code", None)
        return f"SMTPResponseException code={code}"
    # Never persist full exception strings — they may contain envelope or auth hints.
    return exc.__class__.__name__[:120]
