"""Central, configurable settings for the backend.

All values can be overridden via environment variables (or the .env file)
so thresholds and feature flags can be adjusted without changing code.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _get_int(name: str, default: int) -> int:
    """
    Convert an environment variable to a Python int.
    :param name: Environment variable name
    :param default: Default value if unset or invalid
    :return: The value as int
    """
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _get_float(name: str, default: float) -> float:
    """
    Convert an environment variable to a Python float.
    :param name: Environment variable name
    :param default: Default value if unset or invalid
    :return: The value as float
    """
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _get_bool(name: str, default: bool = False) -> bool:
    """
    Convert an environment variable to a Python bool.
    Accepts common truthy/falsy string forms.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Minimum number of thematically identical open incidents (including the new one)
# required before a problem ticket is created.
INCIDENT_ESCALATION_MIN_COUNT: int = _get_int("INCIDENT_ESCALATION_MIN_COUNT", 5)

# Time window in hours within which incidents are considered "recent".
INCIDENT_RECENCY_WINDOW_HOURS: float = _get_float("INCIDENT_RECENCY_WINDOW_HOURS", 8.0)

# Similarity threshold (cosine) for semantic similarity between two incidents.
INCIDENT_SIMILARITY_THRESHOLD: float = _get_float("INCIDENT_SIMILARITY_THRESHOLD", 0.55)

# Sender/customer email for automatically created problem tickets.
PROBLEM_TICKET_AUTHOR_EMAIL: str = os.getenv(
    "PROBLEM_TICKET_AUTHOR_EMAIL",
    os.getenv("ZAMMAD_SUPPORT_EMAIL", "support@localhost"),
)

# Publicly reachable Zammad base URL for clickable ticket links in the body.
# Falls back to the internal URL if not set separately.
ZAMMAD_PUBLIC_URL: str = (
    os.getenv("ZAMMAD_PUBLIC_URL")
    or os.getenv("ZAMMAD_INTERNAL_URL", "")
).rstrip("/")

# --- Email ticket transmission (first public support article → external mail) ---
EMAIL_TICKET_TRANSMISSION_ENABLED: bool = _get_bool(
    "EMAIL_TICKET_TRANSMISSION_ENABLED", False
)
EMAIL_TICKET_TRANSMISSION_RECIPIENT: str = (
    os.getenv("EMAIL_TICKET_TRANSMISSION_RECIPIENT", "") or ""
).strip()
EMAIL_TICKET_TRANSMISSION_WEBHOOK_SECRET: str = (
    os.getenv("EMAIL_TICKET_TRANSMISSION_WEBHOOK_SECRET", "") or ""
).strip()

_DEFAULT_TRANSMISSION_DB = str(
    Path(__file__).resolve().parent / "data" / "email_ticket_transmissions.sqlite3"
)
EMAIL_TICKET_TRANSMISSION_DB_PATH: str = os.getenv(
    "EMAIL_TICKET_TRANSMISSION_DB_PATH", _DEFAULT_TRANSMISSION_DB
)

# Outbound SMTP for backend-controlled transmission (reuses Zammad Mailpit/SMTP vars).
EMAIL_SMTP_HOST: str = (
    os.getenv("EMAIL_SMTP_HOST") or os.getenv("ZAMMAD_SMTP_HOST", "mailpit")
).strip()
_email_smtp_port_raw = (os.getenv("EMAIL_SMTP_PORT") or "").strip()
EMAIL_SMTP_PORT: int = (
    _get_int("EMAIL_SMTP_PORT", 1025)
    if _email_smtp_port_raw
    else _get_int("ZAMMAD_SMTP_PORT", 1025)
)
EMAIL_SMTP_USER: str = (
    os.getenv("EMAIL_SMTP_USER") or os.getenv("ZAMMAD_SMTP_USER", "") or ""
).strip()
EMAIL_SMTP_PASSWORD: str = (
    os.getenv("EMAIL_SMTP_PASSWORD") or os.getenv("ZAMMAD_SMTP_PASSWORD", "") or ""
)
EMAIL_SMTP_FROM: str = (
    os.getenv("EMAIL_SMTP_FROM")
    or os.getenv("ZAMMAD_SUPPORT_EMAIL", "support@localhost")
).strip()
EMAIL_SMTP_USE_TLS: bool = _get_bool("EMAIL_SMTP_USE_TLS", False)
