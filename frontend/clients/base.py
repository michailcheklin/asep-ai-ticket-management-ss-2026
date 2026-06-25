"""Chat client interface for live backend and mock frontend testing."""
from typing import Protocol


class ChatClient(Protocol):
    def send_message(self, payload: dict) -> dict:
        """Send a user message and return the assistant response payload."""
        ...

    def send_feedback(self, payload: dict) -> dict:
        """Send solution feedback and return the follow-up response payload."""
        ...
