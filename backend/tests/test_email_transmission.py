"""
Unit tests for email ticket transmission (Issue #195).

No real SMTP or Zammad calls — Zammad helpers and the mail sender are mocked.
Uses an isolated temporary SQLite database for duplicate-protection tests.

Run from repository root:
    pytest backend/tests/test_email_transmission.py -q
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Isolate DB before importing persistence helpers.
_TMP_DB_DIR = tempfile.mkdtemp(prefix="email_transmission_test_")
_TMP_DB = os.path.join(_TMP_DB_DIR, "transmissions.sqlite3")
os.environ["EMAIL_TICKET_TRANSMISSION_DB_PATH"] = _TMP_DB
os.environ["EMAIL_TICKET_TRANSMISSION_ENABLED"] = "true"
os.environ["EMAIL_TICKET_TRANSMISSION_RECIPIENT"] = "recipient@example.com"
os.environ["EMAIL_TICKET_TRANSMISSION_WEBHOOK_SECRET"] = "test-webhook-secret"
os.environ["ZAMMAD_PUBLIC_URL"] = "http://zammad.test"

from backend.db.models import EmailTicketTransmission, TransmissionStatus  # noqa: E402
from backend.db.session import get_engine, init_db, reset_engine_for_tests  # noqa: E402
from backend.services.EmailTransmissionService import (  # noqa: E402
    EmailTransmissionConfigError,
    EmailTransmissionService,
    build_transmission_bodies,
    is_public_support_article,
    normalize_recipient,
    require_transmission_config,
    strip_html_to_text,
)
from backend.services.email_smtp import EmailSendError  # noqa: E402


TICKET = {
    "id": 42,
    "number": "10042",
    "title": "[1234567] VPN funktioniert nicht",
    "customer_id": 7,
    "state": "open",
}
CUSTOMER = {
    "id": 7,
    "firstname": "Max",
    "lastname": "Mustermann",
    "email": "max.mustermann@example.com",
}
PUBLIC_AGENT_ARTICLE = {
    "id": 501,
    "ticket_id": 42,
    "internal": False,
    "sender": "Agent",
    "type": "note",
    "body": "<p>Bitte prüfen Sie Ihre VPN-Einstellungen.</p>",
}
INTERNAL_AGENT_ARTICLE = {
    "id": 502,
    "ticket_id": 42,
    "internal": True,
    "sender": "Agent",
    "type": "note",
    "body": "Interne Notiz: Kunde an Netze eskalieren.",
}
PUBLIC_CUSTOMER_ARTICLE = {
    "id": 503,
    "ticket_id": 42,
    "internal": False,
    "sender": "Customer",
    "type": "web",
    "body": "Hallo, mein VPN geht immer noch nicht.",
}
SECOND_PUBLIC_AGENT_ARTICLE = {
    "id": 504,
    "ticket_id": 42,
    "internal": False,
    "sender": "Agent",
    "type": "note",
    "body": "Zweite öffentliche Antwort.",
}


@pytest.fixture(autouse=True)
def _fresh_db(monkeypatch):
    """Reset SQLite DB and feature flags before each test."""
    reset_engine_for_tests()
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    os.environ["EMAIL_TICKET_TRANSMISSION_DB_PATH"] = path
    monkeypatch.setattr(
        "backend.config.EMAIL_TICKET_TRANSMISSION_DB_PATH", path
    )
    monkeypatch.setattr(
        "backend.db.session.EMAIL_TICKET_TRANSMISSION_DB_PATH", path
    )
    monkeypatch.setattr(
        "backend.services.EmailTransmissionService.EMAIL_TICKET_TRANSMISSION_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "backend.services.EmailTransmissionService.EMAIL_TICKET_TRANSMISSION_RECIPIENT",
        "recipient@example.com",
    )
    monkeypatch.setattr(
        "backend.config.EMAIL_TICKET_TRANSMISSION_ENABLED", True
    )
    monkeypatch.setattr(
        "backend.config.EMAIL_TICKET_TRANSMISSION_RECIPIENT",
        "recipient@example.com",
    )
    init_db(path)
    yield
    reset_engine_for_tests()
    try:
        os.unlink(path)
    except OSError:
        pass


def _service(mail_sender=None) -> EmailTransmissionService:
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return EmailTransmissionService(
        session_factory=factory,
        mail_sender=mail_sender or MagicMock(),
    )


def _patch_zammad(ticket=TICKET, article=PUBLIC_AGENT_ARTICLE, user=CUSTOMER):
    return patch.multiple(
        "backend.services.EmailTransmissionService",
        get_ticket=MagicMock(return_value=ticket),
        get_ticket_article=MagicMock(return_value=article),
        get_user=MagicMock(return_value=user),
    )


def test_public_support_article_sends_exactly_one_email():
    """1. Öffentlicher Support-Artikel löst genau eine E-Mail aus."""
    mail_sender = MagicMock()
    service = _service(mail_sender)
    with _patch_zammad():
        result = service.process_article(ticket_id=42, article_id=501)

    assert result.status == "sent"
    assert mail_sender.call_count == 1
    sent = mail_sender.call_args.args[0]
    assert "Bitte prüfen Sie Ihre VPN-Einstellungen." in sent.text_body
    assert "Max Mustermann" in sent.text_body
    assert "1234567" in sent.text_body


def test_internal_article_does_not_send():
    """2. Interner Artikel löst keine E-Mail aus."""
    mail_sender = MagicMock()
    service = _service(mail_sender)
    with _patch_zammad(article=INTERNAL_AGENT_ARTICLE):
        result = service.process_article(ticket_id=42, article_id=502)

    assert result.status == "ignored"
    assert result.reason == "not_eligible"
    mail_sender.assert_not_called()


def test_public_customer_message_does_not_send():
    """3. Öffentliche Kundennachricht löst keine E-Mail aus."""
    mail_sender = MagicMock()
    service = _service(mail_sender)
    with _patch_zammad(article=PUBLIC_CUSTOMER_ARTICLE):
        result = service.process_article(ticket_id=42, article_id=503)

    assert result.status == "ignored"
    assert result.reason == "not_eligible"
    mail_sender.assert_not_called()


def test_second_public_support_article_does_not_send_again():
    """4. Zweiter öffentlicher Support-Artikel desselben Tickets → keine zweite Mail."""
    mail_sender = MagicMock()
    service = _service(mail_sender)
    with _patch_zammad():
        first = service.process_article(ticket_id=42, article_id=501)
    with _patch_zammad(article=SECOND_PUBLIC_AGENT_ARTICLE):
        second = service.process_article(ticket_id=42, article_id=504)

    assert first.status == "sent"
    assert second.status == "ignored"
    assert second.reason == "already_reserved_or_sent"
    assert mail_sender.call_count == 1


def test_identical_event_replay_does_not_send_again():
    """5. Wiederholt zugestelltes identisches Event erzeugt keine zweite E-Mail."""
    mail_sender = MagicMock()
    service = _service(mail_sender)
    payload = {"ticket": {"id": 42}, "article": {"id": 501, "ticket_id": 42}}
    with _patch_zammad():
        first = service.handle_article_created(payload)
        second = service.handle_article_created(payload)

    assert first.status == "sent"
    assert second.status == "ignored"
    assert second.reason == "already_reserved_or_sent"
    assert mail_sender.call_count == 1


def test_parallel_events_deduplicated_by_unique_constraint():
    """6. Parallele Events werden durch Unique-Constraint dedupliziert."""
    mail_sender = MagicMock()
    service = _service(mail_sender)
    results: list = []
    lock = threading.Lock()

    def run():
        with _patch_zammad():
            result = service.process_article(ticket_id=42, article_id=501)
        with lock:
            results.append(result)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run) for _ in range(2)]
        for fut in futures:
            fut.result(timeout=10)

    statuses = [r.status for r in results]
    assert statuses.count("sent") == 1
    assert statuses.count("ignored") == 1
    assert mail_sender.call_count == 1

    session = sessionmaker(bind=get_engine(), future=True)()
    try:
        rows = session.scalars(
            select(EmailTicketTransmission).where(EmailTicketTransmission.ticket_id == 42)
        ).all()
        assert len(rows) == 1
    finally:
        session.close()


def test_missing_matrikel_still_sends():
    """7. Fehlende Matrikelnummer verhindert den Versand nicht."""
    ticket = dict(TICKET)
    ticket["title"] = "VPN funktioniert nicht"
    mail_sender = MagicMock()
    service = _service(mail_sender)
    with _patch_zammad(ticket=ticket):
        result = service.process_article(ticket_id=42, article_id=501)

    assert result.status == "sent"
    body = mail_sender.call_args.args[0].text_body
    assert "Matrikelnummer:" not in body
    assert "VPN funktioniert nicht" in body


def test_missing_recipient_config_raises_clear_error(monkeypatch):
    """8. Fehlende Empfängerkonfiguration wird verständlich behandelt."""
    monkeypatch.setattr(
        "backend.services.EmailTransmissionService.EMAIL_TICKET_TRANSMISSION_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "backend.services.EmailTransmissionService.EMAIL_TICKET_TRANSMISSION_RECIPIENT",
        "",
    )
    with pytest.raises(EmailTransmissionConfigError) as exc:
        require_transmission_config()
    assert "EMAIL_TICKET_TRANSMISSION_RECIPIENT" in str(exc.value)


def test_email_error_does_not_mutate_ticket():
    """9. E-Mail-Fehler verändert das Ticket nicht (keine Zammad-Writes)."""
    mail_sender = MagicMock(side_effect=EmailSendError("SMTP refused"))
    service = _service(mail_sender)

    with patch(
        "backend.services.EmailTransmissionService.get_ticket",
        return_value=TICKET,
    ), patch(
        "backend.services.EmailTransmissionService.get_ticket_article",
        return_value=PUBLIC_AGENT_ARTICLE,
    ), patch(
        "backend.services.EmailTransmissionService.get_user",
        return_value=CUSTOMER,
    ), patch(
        "backend.api.zammad.add_article_to_ticket",
        MagicMock(),
    ) as add_article, patch(
        "backend.api.zammad.add_tag_to_ticket",
        MagicMock(),
    ) as add_tag, patch(
        "backend.api.zammad.mark_ticket_as_closed",
        MagicMock(),
    ) as close_ticket:
        result = service.process_article(ticket_id=42, article_id=501)

    assert result.status == "failed"
    add_article.assert_not_called()
    add_tag.assert_not_called()
    close_ticket.assert_not_called()

    session = sessionmaker(bind=get_engine(), future=True)()
    try:
        row = session.scalars(select(EmailTicketTransmission)).one()
        assert row.status == TransmissionStatus.FAILED.value
        assert row.error_message
        assert "SMTP" in row.error_message or "EmailSendError" in row.error_message
        # Must not persist raw SMTP refusal text / credentials
        assert "refused" not in (row.error_message or "").lower()
    finally:
        session.close()


def test_internal_articles_never_appear_in_email_content():
    """10. Interne Artikel erscheinen niemals im E-Mail-Inhalt."""
    mail_sender = MagicMock()
    service = _service(mail_sender)
    with _patch_zammad():
        service.process_article(ticket_id=42, article_id=501)

    sent = mail_sender.call_args.args[0]
    assert "Interne Notiz" not in sent.text_body
    assert "Kunde an Netze" not in sent.text_body
    assert "Bitte prüfen Sie Ihre VPN-Einstellungen." in sent.text_body
    # HTML body must escape/contain only the triggering public article text
    assert "Interne Notiz" not in (sent.html_body or "")


def test_webhook_rejects_missing_or_invalid_auth(monkeypatch):
    """11. Webhook lehnt ungültige oder fehlende Authentifizierung ab."""
    from fastapi import FastAPI

    import backend.api.article_transmission_webhook as webhook_module

    monkeypatch.setattr(
        webhook_module, "EMAIL_TICKET_TRANSMISSION_WEBHOOK_SECRET", "test-webhook-secret"
    )
    monkeypatch.setattr(webhook_module, "EMAIL_TICKET_TRANSMISSION_ENABLED", True)

    app = FastAPI()
    app.include_router(webhook_module.router)
    client = TestClient(app)
    payload = {"ticket": {"id": 42}, "article": {"id": 501}}

    missing = client.post("/webhook/article-created", json=payload)
    assert missing.status_code == 401

    wrong = client.post(
        "/webhook/article-created",
        json=payload,
        headers={"X-Webhook-Secret": "wrong-secret"},
    )
    assert wrong.status_code == 401


def test_webhook_accepts_valid_secret_and_does_not_touch_ticket(monkeypatch):
    """11b/12. Gültiges Secret akzeptiert; Tags/Artikel/Status unverändert."""
    from fastapi import FastAPI

    import backend.api.article_transmission_webhook as webhook_module

    monkeypatch.setattr(
        webhook_module, "EMAIL_TICKET_TRANSMISSION_WEBHOOK_SECRET", "test-webhook-secret"
    )
    monkeypatch.setattr(webhook_module, "EMAIL_TICKET_TRANSMISSION_ENABLED", True)

    mock_service = MagicMock()
    mock_service.handle_article_created.return_value = MagicMock(
        status="sent",
        reason="ok",
        ticket_id=42,
        article_id=501,
        transmission_id=1,
    )
    monkeypatch.setattr(webhook_module, "email_transmission_service", mock_service)

    with patch("backend.api.zammad.add_tag_to_ticket") as add_tag, patch(
        "backend.api.zammad.add_article_to_ticket"
    ) as add_article, patch(
        "backend.api.zammad.mark_ticket_as_closed"
    ) as close_ticket:
        app = FastAPI()
        app.include_router(webhook_module.router)
        client = TestClient(app)
        response = client.post(
            "/webhook/article-created",
            json={"ticket": {"id": 42}, "article": {"id": 501}},
            headers={"X-Webhook-Secret": "test-webhook-secret"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    mock_service.handle_article_created.assert_called_once()
    add_tag.assert_not_called()
    add_article.assert_not_called()
    close_ticket.assert_not_called()


def test_eligibility_helpers():
    assert is_public_support_article(PUBLIC_AGENT_ARTICLE) is True
    assert is_public_support_article(INTERNAL_AGENT_ARTICLE) is False
    assert is_public_support_article(PUBLIC_CUSTOMER_ARTICLE) is False
    assert normalize_recipient("  Alice@Example.COM ") == "alice@example.com"
    text, html_body = build_transmission_bodies(
        user_name="A",
        user_email="a@example.com",
        matrikelnummer=None,
        ticket_number="1",
        ticket_id=1,
        ticket_title="T",
        article_body="<b>Hi</b>",
        link=None,
    )
    assert "Matrikelnummer" not in text
    assert "<b>" not in html_body  # escaped
    assert strip_html_to_text("<p>x<br>y</p>") == "x\ny"


def test_bot_public_article_is_not_eligible():
    """Chatbot public solutions articles must not trigger transmission."""
    bot_article = {
        "id": 900,
        "ticket_id": 42,
        "internal": False,
        "sender": "Agent",
        "body": "VOM BOT ANGEBOTENE LÖSUNGEN\n\n1. Restart",
    }
    assert is_public_support_article(bot_article) is False


def test_webhook_config_error_when_enabled_without_recipient(monkeypatch):
    """8b. Webhook returns a clear 503 when recipient is missing."""
    from fastapi import FastAPI

    import backend.api.article_transmission_webhook as webhook_module
    from backend.services.EmailTransmissionService import EmailTransmissionConfigError

    monkeypatch.setattr(
        webhook_module, "EMAIL_TICKET_TRANSMISSION_WEBHOOK_SECRET", "test-webhook-secret"
    )
    monkeypatch.setattr(webhook_module, "EMAIL_TICKET_TRANSMISSION_ENABLED", True)

    mock_service = MagicMock()
    mock_service.handle_article_created.side_effect = EmailTransmissionConfigError(
        "EMAIL_TICKET_TRANSMISSION_ENABLED is true but "
        "EMAIL_TICKET_TRANSMISSION_RECIPIENT is missing or invalid."
    )
    monkeypatch.setattr(webhook_module, "email_transmission_service", mock_service)

    app = FastAPI()
    app.include_router(webhook_module.router)
    client = TestClient(app)
    response = client.post(
        "/webhook/article-created",
        json={"ticket": {"id": 42}, "article": {"id": 501}},
        headers={"X-Webhook-Secret": "test-webhook-secret"},
    )
    assert response.status_code == 503
    assert "EMAIL_TICKET_TRANSMISSION_RECIPIENT" in response.json()["detail"]
