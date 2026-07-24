"""Central, configurable settings for incident-to-problem escalation.

All values can be overridden via environment variables (or the .env file)
so thresholds can be adjusted without changing code.
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _get_int(name: str, default: int) -> int:
    """
    Convert an environment variable to a Python int.
    :param name: Environment variable name
    :param default: Default value if unset or invalid
    :return: The value as int
    """
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _get_float(name: str, default: float) -> float:
    """
    Convert an environment variable to a Python float.
    :param name: Environment variable name
    :param default: Default value if unset or invalid
    :return: The value as float
    """
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# Minimum number of thematically identical open incidents (including the new one)
# required before a problem ticket is created.
INCIDENT_ESCALATION_MIN_COUNT: int = _get_int("INCIDENT_ESCALATION_MIN_COUNT", 5)

# Time window in hours within which incidents are considered "recent".
INCIDENT_RECENCY_WINDOW_HOURS: float = _get_float("INCIDENT_RECENCY_WINDOW_HOURS", 8.0)

# Similarity threshold (cosine) for semantic similarity between two incidents.
INCIDENT_SIMILARITY_THRESHOLD: float = _get_float("INCIDENT_SIMILARITY_THRESHOLD", 0.55)

# Scaled-similarity threshold above which a newly submitted FAQ entry counts as
# "redundant" (already covered by an existing entry). Compared against the top
# faq_match similarity returned by retrieve_relevant_entries.
FAQ_REDUNDANCY_THRESHOLD: float = _get_float("FAQ_REDUNDANCY_THRESHOLD", 0.5)

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
