"""Detection and creation of problem tickets from clustered, similar incidents.

Core flow (see register_and_check_incident):
    1. Remove stale incidents (older than the time window) from the RAG.
    2. Store the new incident.
    3. Search for semantically similar open incidents.
    4. If enough matches are found, check whether a problem already exists:
       - yes -> assign the new incident to that problem
       - no  -> create a new problem ticket in Zammad and link all affected
                incidents.
"""
from langchain_core.messages import HumanMessage

from ..api.zammad import (
    add_article_to_ticket,
    add_tag_to_ticket,
    create_system_ticket,
)
from ..config import (
    INCIDENT_ESCALATION_MIN_COUNT,
    PROBLEM_TICKET_AUTHOR_EMAIL,
    ZAMMAD_PUBLIC_URL,
)
from ..llm.llm import llm
from ..rag import recent_incidents


def _problem_tag(problem_id: int) -> str:
    """
    Converts a problem ID into the string format "problem:<problem_id>"
    for use as a Zammad tag containing the problem ID.
    """
    return f"problem:{problem_id}"


class ProblemService:
    """Encapsulates the incident-to-problem escalation logic."""

    def register_and_check_incident(
        self,
        ticket_id: int,
        issue_description: str,
        additional_info: list[str],
    ) -> dict:
        """Main entry point; called when a ticket is classified as 'Incident'.

        :return: {'escalated': bool, 'problem_id': int|None, 'created': bool}
        """
        text = recent_incidents.build_incident_text(issue_description, additional_info)
        if not text:
            return {"escalated": False, "problem_id": None, "created": False}

        # 1. + 2.: clean up stale entries, then store the new incident
        recent_incidents.purge_stale_incidents()
        recent_incidents.add_incident(ticket_id=ticket_id, text=text)

        # 3.: find similar open incidents (excluding the one just inserted)
        similar = recent_incidents.find_similar_open_incidents(
            text=text, exclude_ticket_id=ticket_id
        )

        # 4.: check threshold (new incident counts toward total)
        if len(similar) + 1 < INCIDENT_ESCALATION_MIN_COUNT:
            return {"escalated": False, "problem_id": None, "created": False}

        existing_problem_id = recent_incidents.find_existing_problem_id(similar)

        if existing_problem_id is not None:
            self._attach_to_problem(existing_problem_id, ticket_id, similar)
            return {"escalated": True, "problem_id": existing_problem_id, "created": False}

        new_problem_id = self._create_problem(ticket_id, similar, text)
        if new_problem_id is None:
            return {"escalated": False, "problem_id": None, "created": False}
        return {"escalated": True, "problem_id": new_problem_id, "created": True}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _create_problem(
        self, new_ticket_id: int, similar_incidents: list[dict], new_text: str
    ) -> int | None:
        """Creates a new problem ticket and links all affected incidents."""
        all_incident_ids = [i["ticket_id"] for i in similar_incidents] + [new_ticket_id]
        topic = self._derive_topic(similar_incidents, new_text)

        title = f"[Problem] {topic}"
        body = self._build_problem_body(all_incident_ids, topic)

        problem_id = create_system_ticket(
            title=title,
            body=body,
            author_email=PROBLEM_TICKET_AUTHOR_EMAIL,
            priority=1,
            tags=["AI-Created", "Problem"],
        )

        if not problem_id or problem_id == -1:
            print("[ProblemService] Could not create problem ticket.")
            return None

        for incident_id in all_incident_ids:
            recent_incidents.assign_incident_to_problem(incident_id, problem_id, topic=topic)
            add_tag_to_ticket(incident_id, _problem_tag(problem_id))

        print(
            f"[ProblemService] Created new problem {problem_id} from "
            f"{len(all_incident_ids)} incidents."
        )
        return problem_id

    def _attach_to_problem(
        self, problem_id: int, new_ticket_id: int, similar_incidents: list[dict]
    ) -> None:
        """Assigns the new incident to an existing problem."""
        topic = next(
            (i.get("topic") for i in similar_incidents if i.get("topic")), None
        )
        recent_incidents.assign_incident_to_problem(new_ticket_id, problem_id, topic=topic)
        add_tag_to_ticket(new_ticket_id, _problem_tag(problem_id))

        link = self._ticket_link(new_ticket_id)
        try:
            add_article_to_ticket(
                ticket_id=problem_id,
                body=f"Weiterer zugehöriger Incident: {link}",
                sender="Agent",
                article_type="note",
                internal=True,
            )
        except Exception as e:
            print(f"[ProblemService] Could not attach incident to problem: {e}")

        print(
            f"[ProblemService] Assigned incident {new_ticket_id} to existing "
            f"problem {problem_id}."
        )

    def _derive_topic(self, similar_incidents: list[dict], new_text: str) -> str:
        """Derives a short common topic for the problem title (via LLM)."""
        samples = [new_text] + [i.get("text", "") for i in similar_incidents]
        samples = [s for s in samples if s][:6]
        joined = "\n---\n".join(samples)
        prompt = (
            "Mehrere IT-Support-Incidents beschreiben dasselbe zugrunde liegende Problem. "
            "Fasse das gemeinsame Thema in maximal 6 Worten als kurzen Titel zusammen. "
            "Antworte nur mit dem Titel, ohne Anführungszeichen:\n\n"
            f"{joined}"
        )
        try:
            response = llm.invoke([HumanMessage(content=prompt)])
            topic = (response.content or "").strip().splitlines()[0].strip()
            return topic or "Gehäufte ähnliche Incidents"
        except Exception as e:
            print(f"[ProblemService] Topic derivation failed: {e}")
            return "Gehäufte ähnliche Incidents"

    def _ticket_link(self, ticket_id: int) -> str:
        """
        Builds the internal Zammad ticket link from a ticket ID,
        for inclusion in problem ticket bodies.
        """
        if ZAMMAD_PUBLIC_URL:
            return f"{ZAMMAD_PUBLIC_URL}/#ticket/zoom/{ticket_id}"
        return f"Ticket #{ticket_id}"

    def _build_problem_body(self, incident_ids: list[int], topic: str) -> str:
        """Builds the ticket body for the system-created problem ticket in Zammad."""
        links = "\n".join(f"- {self._ticket_link(tid)}" for tid in incident_ids)
        return (
            "Automatisch erstelltes Problem-Ticket.\n\n"
            f"Gemeinsames Thema: {topic}\n"
            f"Anzahl betroffener Incidents: {len(incident_ids)}\n\n"
            "Zugehörige Incidents:\n"
            f"{links}\n"
        )
