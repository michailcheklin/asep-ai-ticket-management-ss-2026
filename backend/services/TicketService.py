# backend/services/ticket_service.py

from langchain_core.messages import HumanMessage, AIMessage
from ..api.zammad import (
    create_ticket_by_user_email,
    add_tag_to_ticket,
    add_article_to_ticket,
    replace_tag_for_ticket,
    mark_ticket_as_closed,
    update_ticket_kategorie,
    update_ticket_title,
    resolve_zammad_kategorie,
    log_ticket_close_event,
)

from ..llm.llm import llm
from .BackendLoggingService import BackendLogger

ticketservice_logger = BackendLogger("Ticket Service")

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

        if matrikelnummer:
            return f"[{matrikelnummer}] {title}"
        return title


    def update_ticket_title_from_state(self, state, ticket_id, use_llm: bool = False):
        """
        Rebuilds the ticket title from the current chatbot state and
        overwrites it on the existing Zammad ticket.

        :param state: Current chatbot state.
        :param ticket_id: ID of the existing Zammad ticket.
        :param use_llm: If True, generate a concise title via LLM (used when
            the conversation is finalized). If False, build a cheap plain
            title (used on every extractor iteration).
        """
        issue = state.get("issue_description", "")
        matrikelnummer = state.get("matrikelnummer", "")
        if not issue:
           return

        if use_llm:
            summary = state.get("full_conversation") or issue
            title = self.generate_title(summary, matrikelnummer)
        else:
            title = f"[{matrikelnummer or 'unknown'}] {issue}"

        update_ticket_title(ticket_id, title)

    
    def _finalize_ticket_metadata(self, state, ticket_id):
        """
        Updates category and title on the existing ticket once the
        conversation with the chatbot is finalized.
        """
        update_ticket_kategorie(ticket_id, state.get("category"))
        self.update_ticket_title_from_state(state, ticket_id, use_llm=True)
        
    # -------------------------
    # Public API
    # -------------------------
    def create_support_ticket(self, state, internal):
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
            ticket_id = create_ticket_by_user_email(
                email=state["user_email"],
                title=title,
                body=body,
                priority=state["priority"],
                internal=internal,
                kategorie=state.get("category"),
            )
            success = self._success_message(title, state)
            success["ticket_id"] = ticket_id
            ticketservice_logger.info(f"Successfully created ticket with ID: {ticket_id}")
            return success

        except Exception as e:
            ticketservice_logger.error(f"Error happened while creating support ticket:\nError: {e}")
            return self._error_message()
        
    def append_support_ticket_context(self, state, ticket_id, internal=True):
        """
        Appends the full ticket context to an already existing ticket.
        
        :param state: Current chatbot state containing all ticket information.
        :param ticket_id: The ID of the existing ticket to append to.
        :param internal: Whether the message should be internal.
        """

        solution_body = self._build_solution_body(state)
        chat_info_body = f"Das Gespräch mit dem Chatbot wurde abgeschlossen. Folgende Informationen wurden erfasst:\n\n{self._build_open_body(state)}"
        
        try:
            # Internal article with the chat history formatted for the ZIM team
            self._finalize_ticket_metadata(state, ticket_id)
            self.append_message_to_ticket(
                ticket_id=ticket_id,
                body=chat_info_body,
                sender="Agent",
                internal=internal
            )

            # Public article with the solutions
            self.append_message_to_ticket(
                ticket_id=ticket_id,
                body=solution_body,
                sender="Agent",
                internal=False
            )

            ticketservice_logger.info(f"Successfully appended context to ticket {ticket_id}")
        except Exception as e:
            ticketservice_logger.error(f"Error while appending context: {e}")

    def append_message_to_ticket(self, ticket_id: int, body: str, sender: str = "Agent", internal: bool = True) -> None:
        """
        Appends a follow-up article to an already-created ticket.
        Use sender="Customer" for user messages, "Agent" for bot replies.
        """
        try:
            add_article_to_ticket(ticket_id=ticket_id, body=body, sender=sender, internal=internal)
        except Exception as e:
            ticketservice_logger.error(f"Failed to append article: {e}")

    def create_ai_solved_ticket(self, state):
        """
        Marks the existing ticket as resolved by the AI chatbot.
        Appends a resolution message, adds the 'AISolved' tag and closes the ticket.

        :param state: Current chatbot state containing all ticket information.
        :return: State update containing chatbot messages and completion flag.
        """
        ticket_id = state.get("ticket_id")

        try:
            if ticket_id:
                self._finalize_ticket_metadata(state, ticket_id)
                self.append_message_to_ticket(
                    ticket_id=ticket_id,
                    body="[ZIM AI-AGENT] Der Nutzer hat das Problem als durch den KI-Chatbot gelöst markiert. Das Ticket wird daher geschlossen.",
                    sender="Agent",
                    internal=True
                )
                replace_tag_for_ticket(ticket_id=ticket_id, old_tag="AI-Created", new_tag="AI-Solved")
                log_ticket_close_event(
                    ticket_id=ticket_id,
                    source="chatbot_api",
                    metadata={"state": "closed", "title": "AI-resolved ticket"}
                )
                mark_ticket_as_closed(ticket_id=ticket_id)
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
            ticketservice_logger.error(f"AI solved ticket could not be created\nError: {e}")
            return {
                "messages": [
                    AIMessage(content="Fehler beim Abschließen des Tickets.")
                ],
                "is_complete": True
            }
        
    def create_closed_tutorial_ticket(self, state):
        """
        Erstellt fuer ein per Anleitung geloestes Anliegen ein Ticket, das sofort
        geschlossen und mit dem AI-Solved-Tag versehen wird (Issue #161).
        Dient dem Performance-Tracking des Chatbots in Zammad.
        """
        user_messages = [m.content for m in state.get("messages", []) if isinstance(m, HumanMessage)]
        issue = state.get("issue_description") or (user_messages[0] if user_messages else "Anliegen per Chatbot geloest")

        title = self.generate_title(issue, state.get("matrikelnummer", ""))
        body = (
            f"E-Mail: {state.get('user_email', '')}\n"
            f"Anliegen:\n{issue}\n\n"
            f"Status: Durch KI-Anleitung geloest (Tutorial-Pfad)\n\n"
            f"{'=' * 40}\nCHATVERLAUF\n{'=' * 40}\n\n"
            f"{self._format_chat_history(state)}"
        )

        try:
            ticket_id = create_ticket_by_user_email(
                email=state["user_email"],
                title=title,
                body=body,
                priority=state.get("priority") or 0,
                internal=True,
                state="closed",
            )
            add_tag_to_ticket(ticket_id, "AI-Solved")
            return {"ticket_id": ticket_id, "is_complete": True}
        except Exception as e:
            ticketservice_logger.error(f"Failed to close tutorial ticket\nError: {e}")
            return {"is_complete": True}

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
            f"Kategorie: {resolve_zammad_kategorie(state.get('category')) or state.get('category', 'Service Request')}\n"
            f"Problem:\n{state['issue_description']}\n\n"
            f"Zusatzinfos:\n{self._format_additional_info(state.get('additional_info', []))}"
            f"{self._chat_history_section(state)}"
        )

    def _build_solution_body(self, state):
        """
        Builds the body for the public article with the solutions that the bot offered.
        :param state: Current chatbot state.
        :return: Formatted solution body as plain text.
        """
        return self._solutions_section(state)


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
            f"Priorität: {'urgent' if state.get('priority') == 1 else 'normal'}\n"
            f"Kategorie: {resolve_zammad_kategorie(state.get('category')) or state.get('category', 'Service Request')}\n"
            f"Problem:\n{state['issue_description']}\n\n"
            f"Zusatzinfos:\n{self._format_additional_info(state.get('additional_info', []))}"
            f"\n\nStatus: Durch KI gelöst"
            f"{self._chat_history_section(state)}"
        )

    def _chat_history_section(self, state) -> str:
        """
        Returns the chat history formatted into Zammad ticket format based on the state
        :param state: The current state of the chatbot
        :return: The formatted chat history
        """
        summary = (state.get("full_conversation") or "").strip() or "(keine Zusammenfassung vorhanden)"
        addendum = (state.get("user_addendum") or "").strip()
        addendum_section = ""
        if addendum:
            addendum_section = (
                f"\n\n{'=' * 40}\n"
                f"ERGÄNZUNG DURCH NUTZER\n"
                f"{'=' * 40}\n\n"
                f"{addendum}\n"
            )
        return (
            f"\n\n{'=' * 40}\n"
            f"GESPRÄCHSZUSAMMENFASSUNG\n"
            f"{'=' * 40}\n\n"
            f"{summary}"
            f"{addendum_section}\n\n"
        )

    def _solutions_section(self, state) -> str:
        """
        Returns the solutions formatted into Zammad ticket format based on the state
        :param state: The current state of the chatbot
        :return: The formatted solutions offered by the chatbot
        """
        return (
            f"{'=' * 40}\n"
            f"VOM BOT ANGEBOTENE LÖSUNGEN\n"
            f"{'=' * 40}\n\n"
            f"{self._format_solutions(state)}"
        )

    def _format_additional_info(self, additional_info) -> str:
        """
        Formats all additional info to Zammad ticket format
        :param additional_info: The additional info from the state
        :return: The formatted additional info
        """
        if not additional_info:
            return "  (keine)"
        if isinstance(additional_info, list):
            return "\n".join(f"  • {info}" for info in additional_info)
        return f"  {additional_info}"

    def _format_solutions(self, state) -> str:
        """
        Formats all solutions that were offered to Zammad ticket format
        :param state: The state of the chatbot
        :return: The formatted additional info
        """
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
        """
        Parses a string into a key-value-dict
        :param text: The text to parse
        :return: The dict that could be parsed
        """
        fields = {}
        for line in text.splitlines():
            if ": " in line:
                key, _, value = line.partition(": ")
                fields[key.strip().lower()] = value.strip()
        return fields

    def _format_chat_history(self, state) -> str:
        """
        Formats the chat history so that the ZIM staff can see how the user chatted with the chatbot before
        :param state: The state of the chatbot
        :return: The formatted chat history
        """
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
        first_name = state.get("display_name", "").split()[0] if state.get("display_name") else ""
        greeting = f"Perfekt, {first_name}!" if first_name else "Perfekt!"
        return {
            "messages": [
                AIMessage(content=(
                    f"{greeting} Dein Ticket wurde erfolgreich erstellt.\n\n"
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