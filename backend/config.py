"""Zentrale, konfigurierbare Einstellungen für die Incident-zu-Problem-Eskalation.

Alle Werte lassen sich über Umgebungsvariablen (bzw. die .env-Datei) überschreiben,
damit Schwellenwerte ohne Code-Änderung angepasst werden können.
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# Anzahl thematisch gleicher offener Incidents (inkl. dem neuen), ab der ein
# Problem-Ticket erzeugt wird.
INCIDENT_ESCALATION_MIN_COUNT: int = _get_int("INCIDENT_ESCALATION_MIN_COUNT", 5)

# Zeitfenster in Stunden, innerhalb dessen Incidents als "recent" gelten.
INCIDENT_RECENCY_WINDOW_HOURS: float = _get_float("INCIDENT_RECENCY_WINDOW_HOURS", 8.0)

# Similarity-Schwelle (Cosine) für die semantische Ähnlichkeit zweier Incidents.
INCIDENT_SIMILARITY_THRESHOLD: float = _get_float("INCIDENT_SIMILARITY_THRESHOLD", 0.55)

# Absender-/Kunden-E-Mail für automatisch erzeugte Problem-Tickets.
PROBLEM_TICKET_AUTHOR_EMAIL: str = os.getenv(
    "PROBLEM_TICKET_AUTHOR_EMAIL",
    os.getenv("ZAMMAD_SUPPORT_EMAIL", "support@localhost"),
)

# Öffentlich erreichbare Zammad-Basis-URL für klickbare Ticket-Links im Body.
# Fällt auf die interne URL zurück, falls nicht separat gesetzt.
ZAMMAD_PUBLIC_URL: str = (
    os.getenv("ZAMMAD_PUBLIC_URL")
    or os.getenv("ZAMMAD_INTERNAL_URL", "")
).rstrip("/")
