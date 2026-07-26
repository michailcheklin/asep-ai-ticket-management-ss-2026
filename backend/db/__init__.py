"""Application persistence for features that need durable local state.

Tickets and articles remain in Zammad. This package only stores
backend-owned records such as email transmission deduplication.
"""

from .models import EmailTicketTransmission, TransmissionStatus
from .session import get_session_factory, init_db

__all__ = [
    "EmailTicketTransmission",
    "TransmissionStatus",
    "get_session_factory",
    "init_db",
]
