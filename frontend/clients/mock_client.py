"""Mock chat client with keyword-triggered UI scenarios (no backend calls)."""


class MockChatClient:
    """Returns fixed responses for frontend layout and interaction testing."""

    def send_message(self, payload: dict) -> dict:
        user_message = payload.get("user_message", "")
        text = user_message.casefold()

        base = {
            "issue_description": payload.get("issue_description", ""),
            "additional_info": payload.get("additional_info", []),
            "priority": payload.get("priority", 2),
            "additional_info_attempts": payload.get("additional_info_attempts", 0),
            "ask_issue_attempts": payload.get("ask_issue_attempts", 0),
            "solutions": [],
            "ui_flags": [],
        }

        if "faq" in text:
            return {
                **base,
                "bot_response": "Hier sind passende FAQ-Einträge zu deinem Anliegen:",
                "ui_flags": ["show_faq"],
            }

        if "ticket" in text:
            return {
                **base,
                "bot_response": "Ich konnte leider keine passende Lösung finden. Du kannst ein Support-Ticket erstellen.",
                "ui_flags": ["show_ticket_button"],
            }

        if "lösung" in text or "solution" in text:
            return {
                **base,
                "bot_response": "Ich habe folgende Lösungsvorschläge für dich gefunden:",
                "solutions": [
                    {
                        "title": "FAQ: WLAN-Verbindung",
                        "description": "Verbinde dich mit dem Uni-WLAN über eduroam und deine Uni-Kennung.",
                    },
                    {
                        "title": "Ähnliches Ticket (Netzwerk)",
                        "description": "Ein anderer Nutzer hatte ein ähnliches Problem. Router-Neustart half.",
                    },
                ],
            }

        return {
            **base,
            "bot_response": (
                "Das ist eine feste Mock-Antwort. "
                "Tippe „FAQ“, „Ticket“ oder „Lösung“, um verschiedene UI-Elemente zu testen."
            ),
        }

    def send_feedback(self, payload: dict) -> dict:
        if payload.get("helpful"):
            return {
                "bot_response": (
                    "Super, freut mich, dass ich dir helfen konnte! "
                    "Wenn du in Zukunft weitere Fragen hast, stehe ich gerne zur Verfügung."
                )
            }

        return {
            "bot_response": (
                "Dein Support-Ticket wurde erstellt (Mock). "
                "Unser Team wird sich in Kürze bei dir melden."
            )
        }
