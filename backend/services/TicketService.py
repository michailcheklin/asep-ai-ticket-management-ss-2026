# backend/services/ticket_service.py

from langchain_core.messages import HumanMessage, AIMessage
from ..graph.nodes import llm
from ..api.zammad import create_ticket_by_user_email, add_tag_to_ticket


class TicketService:

    # -------------------------
    # Title Generation
    # -------------------------
    def generate_title(self, issue_description: str, matrikelnummer: str) -> str:
        prompt = (
            "Du bist ein IT-Support-Assistent. "
            "Fasse das folgende Problem in maximal 4-5 Worten als Ticket-Betreff zusammen. "
            "Antworte nur mit dem Betreff ohne Anführungszeichen:\n\n"
            f"{issue_description}"
        )

        response = llm.invoke([HumanMessage(content=prompt)])
        title = response.content.strip()

        return f"[{matrikelnummer}] {title}"

    # -------------------------
    # Public API
    # -------------------------
    def create_support_ticket(self, state):
        title = self.generate_title(
            state["issue_description"],
            state["matrikelnummer"],
        )

        body = self._build_open_body(state)

        try:
            create_ticket_by_user_email(
                email=state["user_email"],
                title=title,
                body=body,
                priority=state["priority"],
            )

            return self._success_message(title, state)

        except Exception as e:
            print(f"[TicketService ERROR] {e}")
            return self._error_message()

    def create_ai_solved_ticket(self, state):
        title = self.generate_title(
            state["issue_description"],
            state["matrikelnummer"],
        )

        body = self._build_ai_body(state)

        try:
            ticket_id = create_ticket_by_user_email(
                email=state["user_email"],
                title=title,
                body=body,
                priority=state["priority"],
                state="closed"
            )

            if ticket_id:
                add_tag_to_ticket(ticket_id, "AISolved")

            return {
                "messages": [
                    AIMessage(content=(
                        "Super, das freut mich! Wenn du wieder Hilfe brauchst, bin ich da 🙂"
                    ))
                ],
                "is_complete": True
            }

        except Exception as e:
            print(f"[TicketService ERROR] {e}")
            return {
                "messages": [
                    AIMessage(content="Fehler beim Erstellen des Tickets.")
                ],
                "is_complete": True
            }

    # -------------------------
    # Body Builders
    # -------------------------
    def _build_open_body(self, state):
        return (
            f"Matrikelnummer: {state['matrikelnummer']}\n"
            f"E-Mail: {state['user_email']}\n\n"
            f"Priorität: {'urgent' if state.get('priority') == 1 else 'normal'}\n"
            f"Problem:\n{state['issue_description']}\n\n"
            f"Zusatzinfos:\n{state.get('additional_info', [])}"
        )

    def _build_ai_body(self, state):
        return (
            f"Matrikelnummer: {state['matrikelnummer']}\n"
            f"E-Mail: {state['user_email']}\n\n"
            f"Problem:\n{state['issue_description']}\n\n"
            f"Zusatzinfos:\n{state.get('additional_info', [])}\n\n"
            f"Status: Durch KI gelöst"
        )

    # -------------------------
    # Response Helpers
    # -------------------------
    def _success_message(self, title, state):
        return {
            "messages": [
                AIMessage(content=(
                    f"Perfekt! Ticket erstellt.\n\n"
                    f"**Betreff:** {title}\n"
                    f"Ich melde mich bald 🙂"
                ))
            ],
            "is_complete": True
        }

    def _error_message(self):
        return {
            "messages": [
                AIMessage(content=(
                    "Ticket konnte nicht erstellt werden. Bitte später erneut versuchen."
                ))
            ],
            "is_complete": True
        }