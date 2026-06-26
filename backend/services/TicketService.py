# backend/services/ticket_service.py

from langchain_core.messages import HumanMessage, AIMessage
from ..api.zammad import create_ticket_by_user_email, add_tag_to_ticket
from ..llm.llm import llm


class TicketService:
    """
        Service responsible for creating and managing support tickets.

        This service encapsulates all ticket-related business logic, including:
        - generating ticket titles,
        - building ticket bodies,
        - creating tickets in Zammad,
        - tagging AI-resolved tickets,
        - generating user-facing success/error responses.
        """
    # -------------------------
    # Title Generation
    # -------------------------
    def generate_title(self, issue_description: str, matrikelnummer: str) -> str:
        """
        Generates a concise ticket title using the configured LLM.

        The generated title is prefixed with the student's matriculation number
        to simplify ticket identification inside the ticket system.

        :param issue_description: User's problem description.
        :param matrikelnummer: Student's matriculation number.
        :return: Formatted ticket title.
        """
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
        """
        Creates a new open support ticket in Zammad.

        The method generates a ticket title, builds the ticket body,
        submits the ticket to Zammad and returns either a success
        or an error message for the chatbot.

        :param state: Current chatbot state containing all ticket information.
        :return: State update containing chatbot messages and completion flag.
        """
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
        """
        Creates a ticket that has already been solved by the AI.

        The ticket is created in the closed state and receives the
        'AISolved' tag for later analysis.

        :param state: Current chatbot state containing all ticket information.
        :return: State update containing chatbot messages and completion flag.
        """
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
                        "Super, das freut mich! Wenn du in Zukunft weitere Fragen hast, "
                        "stehe ich gerne zur Verfügung. Hab einen schönen Tag!"
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
        """
        Builds the ticket body for a regular support request.

        Includes user information, priority, issue description
        and all collected additional information.

        :param state: Current chatbot state.
        :return: Formatted ticket body as plain text.
        """
        return (
            f"Matrikelnummer: {state['matrikelnummer']}\n"
            f"E-Mail: {state['user_email']}\n\n"
            f"Priorität: {'urgent' if state.get('priority') == 1 else 'normal'}\n"
            f"Problem:\n{state['issue_description']}\n\n"
            f"Zusatzinfos:\n{self._format_additional_info(state.get('additional_info', []))}"
            f"{self._chat_history_and_solutions_section(state)}"
        )

    def _build_ai_body(self, state):
        """
        Builds the ticket body for tickets that were resolved by the AI.

        Similar to the regular ticket body but additionally marks
        the ticket as AI-resolved.

        :param state: Current chatbot state.
        :return: Formatted ticket body as plain text.
        """
        return (
            f"Matrikelnummer: {state['matrikelnummer']}\n"
            f"E-Mail: {state['user_email']}\n\n"
            f"Problem:\n{state['issue_description']}\n\n"
            f"Zusatzinfos:\n{self._format_additional_info(state.get('additional_info', []))}"
            f"{self._chat_history_and_solutions_section(state)}\n\n"
            f"Status: Durch KI gelöst"
        )

    def _chat_history_and_solutions_section(self, state) -> str:
        return (
            f"\n\n{'=' * 40}\n"
            f"CHATVERLAUF\n"
            f"{'=' * 40}\n\n"
            f"{self._format_chat_history(state)}\n\n"
            f"{'=' * 40}\n"
            f"VOM BOT ANGEBOTENE LÖSUNGEN\n"
            f"{'=' * 40}\n\n"
            f"{self._format_solutions(state)}"
        )

    def _format_additional_info(self, additional_info) -> str:
        if not additional_info:
            return "  (keine)"
        if isinstance(additional_info, list):
            return "\n".join(f"  • {info}" for info in additional_info)
        return f"  {additional_info}"

    def _format_solutions(self, state) -> str:
        solutions = state.get("solutions", [])
        if not solutions:
            return "  (keine Lösungen gespeichert)"

        blocks = []
        for i, solution in enumerate(solutions, 1):
            title = solution.get("title", "Unbekannt").removeprefix("FAQ: ").strip()
            fields = self._parse_key_value_text(solution.get("description", ""))

            lines = [f"Lösung {i}: {title}", "-" * 30]
            field_labels = {
                "context": "Kontext",
                "problem": "Problem",
                "solution": "Lösung",
                "last_update": "Stand",
                "url": "Link",
                "ticket": "Ticket",
                "category": "Kategorie",
            }
            for key, label in field_labels.items():
                if key in fields and fields[key]:
                    lines.append(f"  {label:10} {fields[key]}")

            if len(lines) == 2:
                raw = solution.get("description", "").strip()
                if raw:
                    lines.append(f"  {raw}")

            blocks.append("\n".join(lines))

        return "\n\n".join(blocks)

    def _parse_key_value_text(self, text: str) -> dict[str, str]:
        fields = {}
        for line in text.splitlines():
            if ": " in line:
                key, _, value = line.partition(": ")
                fields[key.strip().lower()] = value.strip()
        return fields

    def _format_chat_history(self, state) -> str:
        lines = []
        for msg in state.get("messages", []):
            if isinstance(msg, HumanMessage):
                content = (msg.content or "").strip()
                if content:
                    lines.append(f"[Kunde]\n  {content}")
            elif isinstance(msg, AIMessage):
                content = (msg.content or "").strip()
                if content:
                    lines.append(f"[Bot]\n  {content}")

        return "\n\n".join(lines) if lines else "  (kein Chatverlauf vorhanden)"

    # -------------------------
    # Response Helpers
    # -------------------------
    def _success_message(self, title, state):
        """
        Creates the chatbot response after a ticket has been created successfully.

        The response contains a short confirmation together with a
        summary of the submitted ticket.

        :param title: Generated ticket title.
        :param state: Current chatbot state.
        :return: State update containing the confirmation message.
        """
        return {
            "messages": [
                AIMessage(content=(
                    "Perfekt! Dein Ticket wurde erfolgreich erstellt.\n\n"
                    "Ein Support-Mitarbeiter meldet sich so bald wie möglich bei dir.\n\n"
                    "**Ticketübersicht**\n\n"
                    f"**Betreff:** {title}\n\n"
                    f"**E-Mail:** {state['user_email']}\n\n"
                    f"**Problembeschreibung:**\n"
                    f"{state['issue_description']}"
                ))
            ],
            "is_complete": True
        }

    def _error_message(self):
        """
        Creates a generic chatbot response for ticket creation failures.

        :return: State update containing an error message.
        """
        return {
            "messages": [
                AIMessage(content=(
                    "Ticket konnte nicht erstellt werden. Bitte später erneut versuchen."
                ))
            ],
            "is_complete": True
        }