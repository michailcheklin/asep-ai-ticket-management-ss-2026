"""ORM models for backend-owned durable state."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for backend tables."""


class TransmissionStatus(StrEnum):
    """Lifecycle of an email ticket transmission attempt."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


class EmailTicketTransmission(Base):
    """Persistent record ensuring at most one transmission per ticket+recipient.

    The unique constraint on ``(ticket_id, recipient_normalized)`` is the
    atomic duplicate guard: a second concurrent insert fails and must not
    send another email.
    """

    __tablename__ = "email_ticket_transmissions"
    __table_args__ = (
        UniqueConstraint(
            "ticket_id",
            "recipient_normalized",
            name="uq_email_transmission_ticket_recipient",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    recipient_normalized: Mapped[str] = mapped_column(String(320), nullable=False)
    triggering_article_id: Mapped[int] = mapped_column(Integer, nullable=False)
    message_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=TransmissionStatus.PENDING.value
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
