"""Erkennung und Anlage von Problem-Tickets aus gehäuften, ähnlichen Incidents.

Kernablauf (siehe register_and_check_incident):
    1. Alte Incidents (> Zeitfenster) aus dem RAG entfernen.
    2. Neuen Incident speichern.
    3. Semantisch ähnliche offene Incidents suchen.
    4. Bei genügend Treffern prüfen, ob bereits ein Problem existiert:
       - ja  -> neuen Incident diesem Problem zuordnen
       - nein -> neues Problem-Ticket in Zammad anlegen und alle betroffenen
                 Incidents verknüpfen.
"""
from langchain_core.messages import HumanMessage

from ..config import (
    INCIDENT_ESCALATION_MIN_COUNT,
    PROBLEM_TICKET_AUTHOR_EMAIL,
    ZAMMAD_PUBLIC_URL,
)
from ..llm.llm import llm
from ..rag import recent_incidents
from ..api.zammad import (
    create_system_ticket,
    add_tag_to_ticket,
    add_article_to_ticket,
)


def _problem_tag(problem_id: int) -> str:
    """
    Wandelt eine Problem ID in den String mit dem Format "problem:<problem_id>" um. Dies ist,
    um in Zammad einen Tag nutzen zu können, der die Problem-ID enthält
    :param problem_id: Die Problem-ID
    :return: Ein mit "problem:" präfixierter String der Problem ID
    """
    return f"problem:{problem_id}"


class ProblemService:
    """Kapselt die Incident-zu-Problem-Eskalationslogik."""

    def register_and_check_incident(
        self,
        ticket_id: int,
        issue_description: str,
        additional_info: list[str],
    ) -> dict:
        """Haupteinstieg; wird aufgerufen, wenn ein Ticket als 'Incident' gilt.

        :return: {'escalated': bool, 'problem_id': int|None, 'created': bool}
        """
        text = recent_incidents.build_incident_text(issue_description, additional_info)
        if not text:
            return {"escalated": False, "problem_id": None, "created": False}

        # 1. + 2.: aufräumen, dann neuen Incident speichern
        recent_incidents.purge_stale_incidents()
        recent_incidents.add_incident(ticket_id=ticket_id, text=text)

        # 3.: ähnliche offene Incidents (ohne den gerade eingefügten) suchen
        similar = recent_incidents.find_similar_open_incidents(
            text=text, exclude_ticket_id=ticket_id
        )

        # 4.: Schwelle prüfen (neuer Incident zählt mit)
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
    # Interne Helfer
    # ------------------------------------------------------------------
    def _create_problem(
        self, new_ticket_id: int, similar_incidents: list[dict], new_text: str
    ) -> int | None:
        """Legt ein neues Problem-Ticket an und verknüpft alle betroffenen Incidents."""
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
            print("[ProblemService] Problem-Ticket konnte nicht erstellt werden.")
            return None

        for incident_id in all_incident_ids:
            recent_incidents.assign_incident_to_problem(incident_id, problem_id, topic=topic)
            add_tag_to_ticket(incident_id, _problem_tag(problem_id))

        print(
            f"[ProblemService] Neues Problem {problem_id} aus "
            f"{len(all_incident_ids)} Incidents erstellt."
        )
        return problem_id

    def _attach_to_problem(
        self, problem_id: int, new_ticket_id: int, similar_incidents: list[dict]
    ) -> None:
        """Ordnet den neuen Incident einem bestehenden Problem zu."""
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
            print(f"[ProblemService] Konnte Incident nicht am Problem vermerken: {e}")

        print(
            f"[ProblemService] Incident {new_ticket_id} bestehendem "
            f"Problem {problem_id} zugeordnet."
        )

    def _derive_topic(self, similar_incidents: list[dict], new_text: str) -> str:
        """Bestimmt ein kurzes gemeinsames Thema für den Problem-Titel (per LLM)."""
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
            print(f"[ProblemService] Themen-Ableitung fehlgeschlagen: {e}")
            return "Gehäufte ähnliche Incidents"

    def _ticket_link(self, ticket_id: int) -> str:
        """
        Bildet den internen Ticket-Link in Zammad anhand der Ticket-ID. Dies ist für die
        Eintragung der Links in einem Problem-Ticket.
        :param ticket_id: Die Ticket-ID, aus der der Link erstellt werden soll
        :return: Der Ticket-Link in Zammad, der zum Ticket mit der angegebenen Ticket-ID führt
        """
        if ZAMMAD_PUBLIC_URL:
            return f"{ZAMMAD_PUBLIC_URL}/#ticket/zoom/{ticket_id}"
        return f"Ticket #{ticket_id}"

    def _build_problem_body(self, incident_ids: list[int], topic: str) -> str:
        """
        Bildet den Ticket-Body für das vom System erstellte Problem-Ticket in Zammad
        :param incident_ids: Die Ticket-IDs der Incidents
        :param topic: Das Thema des Problems
        :return:
        """
        links = "\n".join(f"- {self._ticket_link(tid)}" for tid in incident_ids)
        return (
            "Automatisch erstelltes Problem-Ticket.\n\n"
            f"Gemeinsames Thema: {topic}\n"
            f"Anzahl betroffener Incidents: {len(incident_ids)}\n\n"
            "Zugehörige Incidents:\n"
            f"{links}\n"
        )
