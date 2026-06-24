"""HTTP client for the live AI backend."""
import os

import requests
from requests import JSONDecodeError

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")

# Timeout for every AI request (20 minutes).
AI_COMMUNICATION_TIMEOUT_IN_SECONDS: int = 1200


class LiveChatClient:
    def send_message(self, payload: dict) -> dict:
        res = requests.post(
            url=f"{BACKEND_URL}/chat",
            json=payload,
            timeout=AI_COMMUNICATION_TIMEOUT_IN_SECONDS,
        )

        try:
            return res.json()
        except JSONDecodeError:
            return {
                "bot_response": res.text,
                "issue_description": payload.get("issue_description", ""),
                "additional_info": payload.get("additional_info", []),
                "priority": payload.get("priority", 0),
                "solutions": [],
                "additional_info_attempts": payload.get("additional_info_attempts", 0),
                "ask_issue_attempts": payload.get("ask_issue_attempts", 0),
            }

    def send_feedback(self, payload: dict) -> dict:
        return requests.post(
            f"{BACKEND_URL}/solution-feedback",
            json=payload,
            timeout=AI_COMMUNICATION_TIMEOUT_IN_SECONDS,
        ).json()
