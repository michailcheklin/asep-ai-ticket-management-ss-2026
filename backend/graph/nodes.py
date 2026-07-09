import re
from typing import cast
from pydantic import BaseModel, Field

from langsmith import traceable

from .models.ExtractedTicketData import ExtractedTicketData
from .models.AdditionalInfoDecision import AdditionalInfoDecision
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from .state import ChatbotState
from backend.rag.retrieve_info import retrieve_relevant_entries
from ..services.TicketService import TicketService
from ..llm.llm import llm, structured_llm, AGENT_PROMPT
from .node_logging import log_node_entry
from ..api.zammad import create_ticket_by_user_email, add_tag_to_ticket
from .models.IntentDecision import IntentDecision


ticket_service = TicketService()


def _format_faq_match_for_prompt(match: tuple) -> str:
    """Rendert ein faq_matches-Tuple (id, problem, solution, extracted_urls, similarity) als Prompt-Text."""
    _, problem, solution, extracted_urls, _ = match
    lines = [f"problem: {problem}", f"solution: {solution}"]
    for url, status, url_type, content, notes in extracted_urls:
        if status == "success" and content:
            lines.append(f"[{url}]: {content}")
        elif notes:
            lines.append(f"[{url}]: {notes}")
    return "\n".join(lines)

TICKET_CATEGORIES = [
    "Incident",
    "Service Request",
    "Change",
    "Problem",
    "Complaint",
]


class TicketCategoryDecision(BaseModel):
    """Schema for the LLM output of the dedicated ticket category classification step."""
    category: str = Field(
        description=f"Exactly one of: {', '.join(TICKET_CATEGORIES)}"
    )

category_llm = llm.with_structured_output(TicketCategoryDecision)

_CATEGORY_RULES = """
Klassifiziere nach ITSM-Ticket-Typ und Hauptabsicht des Nutzers.
Ignoriere einzelne Schlüsselwörter, wenn sie nicht zur Hauptabsicht passen.

Ticket-Typen:

1. Complaint:
Wähle diesen Typ, wenn die Hauptabsicht eine Beschwerde, Unzufriedenheit,
Frust, Ärger oder Kritik an Support, Bearbeitung, Wartezeit, Kommunikation
oder fehlender Hilfe ist.
Das gilt auch dann, wenn zusätzlich ein technisches Problem erwähnt wird.
Typische Hinweise: "unhappy", "frustrated", "angry", "upset", "unacceptable",
"complained", "nobody fixed it", "no help in time", "not answered".

2. Problem:
Wähle diesen Typ nur, wenn die Hauptabsicht die Analyse einer wiederkehrenden
oder grundlegenden Ursache ist.
Ein aktueller Ausfall bleibt Incident, auch wenn mehrere Nutzer betroffen sind.
Problem ist passend bei Root-Cause-Analyse, wiederkehrenden Incidents,
bekannter Fehlerursache oder systematischer Untersuchung.

3. Change:
Wähle diesen Typ, wenn eine Änderung an System, Konfiguration, Berechtigung,
Rolle, Gruppe, Weiterleitung oder Prozess gewünscht wird.
Beispiele: neue Rolle vergeben, Gruppe anpassen, Zugriff ändern,
Mailbox-Weiterleitung ändern, Berechtigung erweitern.

4. Service Request:
Wähle diesen Typ bei Anfragen, Anträgen, Informationswünschen oder
administrativen Anliegen ohne Fokus auf eine technische Störung.
Wichtig: Zahlungs-, Gebühren-, Rechnungs-, Rückerstattungs- und
Accounting-Anliegen sind in diesem Projekt Service Request, auch wenn ein
Portal einen falschen Zahlungsstatus, eine Fehlermeldung oder ein Exportproblem zeigt.
Beispiele: Semesterbeitrag klären, Rechnung anfordern, Zahlungsstatus prüfen,
Rückerstattung, Software anfordern, Anleitung erhalten, Zugriff beantragen.

5. Incident:
Wähle diesen Typ, wenn ein IT-Service, System, Gerät, Netzwerk oder eine
Software aktuell nicht funktioniert und keine speziellere Kategorie oben passt.
Beispiele: Login unmöglich, WLAN aus, Drucker defekt, Moodle Upload geht nicht,
VPN verbindet nicht, Anwendung stürzt ab.

Priorität bei Überschneidungen:
Complaint > Problem > Change > Service Request > Incident.

Wenn ein Ticket sowohl eine technische Störung als auch ein Zahlungs-/Rechnungsanliegen enthält,
wähle Service Request, sofern Zahlung, Rechnung, Gebühr oder Accounting das eigentliche Ziel ist.

Wenn ein Ticket sowohl eine technische Störung als auch Ärger/Beschwerde enthält,
wähle Complaint, sofern die Beschwerde die Hauptabsicht ist.

Bewerte den Ticket-Typ immer anhand des GESAMTEN Chatverlaufs und aller bekannten Infos.
Gib genau einen Ticket-Typ zurück.
"""


def classify_ticket_category(
    issue_description: str,
    additional_info: list[str],
    user_messages: list[str],
) -> str:
    """Classify a ticket using the full conversation context, not just the last message."""
    conversation = "\n".join(f"- {msg}" for msg in user_messages) if user_messages else "(keine)"
    infos = ", ".join(additional_info) if additional_info else "(keine)"
    prompt = AGENT_PROMPT + "\n\n" + f"""Ordne das Ticket nach ITSM-Ticket-Typ genau einem der folgenden Typen zu:
[{", ".join(TICKET_CATEGORIES)}].

KONTEXT:
Chatverlauf (User-Nachrichten):
{conversation}

Problembeschreibung: {issue_description or "(noch nicht bekannt)"}
Zusatzinfos: {infos}

{_CATEGORY_RULES}"""
    decision = cast(TicketCategoryDecision, category_llm.invoke([SystemMessage(content=prompt)]))
    if decision.category in TICKET_CATEGORIES:
        return decision.category
    return "Service Request"


def _resolve_ticket_category(state: ChatbotState) -> str:
    """Use an existing category from state or classify exactly once."""
    existing = (state.get("category") or "").strip()
    if existing in TICKET_CATEGORIES:
        return existing

    user_messages = [msg.content for msg in state["messages"] if isinstance(msg, HumanMessage)]
    return classify_ticket_category(
        state.get("issue_description", ""),
        list(state.get("additional_info", [])),
        user_messages,
    )


@traceable
def classify_ticket(state: ChatbotState):
    """Workflow node: assign ticket category once enough context is available."""
    user_messages = [msg.content for msg in state["messages"] if isinstance(msg, HumanMessage)]
    category = classify_ticket_category(
        state.get("issue_description", ""),
        list(state.get("additional_info", [])),
        user_messages,
    )
    return {"category": category}



INTENTS = ["tutorial", "problem", "unclear", "solved"]
intent_llm = llm.with_structured_output(IntentDecision)


@traceable
def classify_intent(state: ChatbotState):
    """Workflow-Node: bewertet bei jeder Nachricht neu, was der Nutzer moechte (Issue #161)."""
    log_node_entry("classify_intent", state)

    # 1)
    user_messages = [msg.content for msg in state["messages"] if isinstance(msg, HumanMessage)]
    conversation = "\n".join(f"- {m}" for m in user_messages) if user_messages else "(keine)"
    previous_intent = state.get("intent") or "(noch keiner)"

    # 2) Entscheidungskriterien
    system_prompt = SystemMessage(content=f"""Du bist ein Verteiler im IT-Support des ZIM einer Universitaet.
Entscheide anhand des GESAMTEN Chatverlaufs, was der Nutzer AKTUELL moechte:

- "tutorial": Der Nutzer moechte wissen, WIE etwas geht, und es selbst tun.
  Typisch: "Wie richte ich ... ein?", "Wo finde ich ...?", "Anleitung fuer ...".
- "problem": Etwas funktioniert nicht oder der Nutzer moechte, dass der Support
  sich kuemmert. Typisch: "... ist kaputt", "... geht nicht", "erstellt mir ein Ticket".
- "unclear": Die Absicht ist aus den Nachrichten nicht erkennbar (z. B. nur "Hallo").
- "solved": NUR waehlen, wenn der Bot zuvor eine Anleitung gegeben hat UND der
  Nutzer jetzt bestaetigt, dass sein Anliegen damit geloest ist.
  Typisch: "hat geklappt", "funktioniert jetzt", "danke, erledigt".

BISHERIGER INTENT: {previous_intent}
REGELN FUER DEN WECHSEL:
- Wechsle nur dann vom bisherigen Intent, wenn der Nutzer das erkennbar signalisiert.
- Sagt der Nutzer nach einer Anleitung NUR, dass es nicht funktioniert hat
  (z. B. "hat nicht geklappt", "geht immer noch nicht", "hat leider nicht funktioniert"),
  bleibt der Intent "tutorial" — der Bot vertieft dann die Anleitung.
- Waehle "problem" nach einer Anleitung erst, wenn der Nutzer AUSDRUECKLICH moechte,
  dass der Support uebernimmt (z. B. "erstell mir ein Ticket", "leite es bitte an
  einen Mitarbeiter weiter", "ich will mit einem Menschen sprechen").
- Eine reine Zwischenantwort (E-Mail-Adresse, Ja/Nein, Detailangabe) ist KEIN Wechsel.
- Entscheide nach der Hauptabsicht, nicht nach einzelnen Schluesselwoertern.

CHATVERLAUF (User-Nachrichten):
{conversation}""")

    # 3)
    decision = cast(IntentDecision, intent_llm.invoke([
        system_prompt,
        HumanMessage(content="Bitte klassifiziere die Absicht des Nutzers.")
    ]))
    intent = decision.intent if decision.intent in INTENTS else "unclear"

    state_update = {"intent": intent}

    # 4)
    if not state.get("user_email") and user_messages:
        match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", user_messages[-1])
        if match:
            state_update["user_email"] = match.group(0)

    return state_update



@traceable
def ask_intent(state: ChatbotState):
    """Fragt nach, ob der Nutzer eine Anleitung moechte oder Support braucht."""
    log_node_entry("ask_intent", state)
    system_prompt = SystemMessage(content=(
          AGENT_PROMPT + "\n\n"
        "Die Absicht des Nutzers ist noch unklar. Frage kurz und freundlich, ob er eine Schritt-fuer-Schritt-"
        "Anleitung zum Selbermachen moechte oder ob der Support sich um sein Anliegen "
        "kuemmern soll. Beantworte keine anderen Fragen und wechsle nicht das Thema."
    ))
    response = llm.invoke([system_prompt] + state["messages"])
    return {"messages": [response]}

@traceable
def give_tutorial(state: ChatbotState):
    """Erstellt eine Schritt-fuer-Schritt-Anleitung aus der Wissensdatenbank (Issue #161)."""
    log_node_entry("give_tutorial", state)
    attempts = state.get("tutorial_attempts", 0)

    user_messages = [msg.content for msg in state["messages"] if isinstance(msg, HumanMessage)]
    query = " ".join(user_messages[-2:]) if user_messages else ""

    rag_results = retrieve_relevant_entries(query, n_results=2)
    faq_context = "\n".join(f"- {_format_faq_match_for_prompt(m)}" for m in rag_results.get("faq_matches", []))
    ticket_context = "\n".join(f"- {m['text']}" for m in rag_results.get("ticket_matches", []))


    system_prompt = SystemMessage(content=AGENT_PROMPT + "\n\n" + f"""

    Der Nutzer moechte eine Anleitung, um sein Anliegen SELBST zu loesen.

WISSENSDATENBANK (FAQs):
{faq_context or "(keine Treffer)"}

WISSENSDATENBANK (aehnliche Tickets):
{ticket_context or "(keine Treffer)"}

BISHERIGE ANLEITUNGSVERSUCHE: {attempts}

REGELN:
1. Erstelle eine NUMMERIERTE Schritt-fuer-Schritt-Anleitung (1., 2., 3., ...),
   basierend auf der Wissensdatenbank. Erfinde keine Schritte, die dort keine
   Grundlage haben. Gib Links an, wenn sie in den Quellen stehen.
2. Maximal 6 Schritte pro Antwort. Ist die Anleitung laenger, stoppe an einer
   sinnvollen Stelle und frage, ob es bis hierhin geklappt hat.
3. Wenn BISHERIGE ANLEITUNGSVERSUCHE groesser als 0 ist: Wiederhole NICHT die
   komplette Anleitung. Frage stattdessen gezielt, an welchem Schritt es hakt,
   und vertiefe nur diesen Teil anhand des Chatverlaufs.
4. Liefert die Wissensdatenbank nichts Passendes, sage das ehrlich und biete an,
   das Anliegen an einen Mitarbeiter zu uebergeben.
5. Beende deine Antwort IMMER mit der Frage, ob das Problem damit geloest ist.""")

    response = llm.invoke([system_prompt] + state["messages"])

    return {
        "messages": [response],
        "tutorial_attempts": attempts + 1
    }

@traceable
def finish_tutorial(state: ChatbotState):
    """Schliesst den Tutorial-Pfad ab: geschlossenes AI-Solved-Ticket y Verabschiedung."""
    log_node_entry("finish_tutorial", state)
    result = ticket_service.create_closed_tutorial_ticket(state)

    system_prompt = SystemMessage(content=(
        AGENT_PROMPT + "\n\n"
        "Der Nutzer hat gerade bestaetigt, dass deine Anleitung sein Anliegen "
        "geloest hat. Verabschiede dich kurz, freundlich und natuerlich, mit Bezug "
        "auf sein konkretes Anliegen. Maximal 2 Saetze. Erwaehne, dass er sich "
        "jederzeit wieder melden kann."
    ))
    response = llm.invoke([system_prompt] + state["messages"])

    return {**result, "messages": [response]}

@traceable
def extract_information(state: ChatbotState):
    """
    Analyzes the latest user message to extract structured ticket details.
    :param state: The current state of the chatbot conversation.
    :return: A dictionary containing the newly extracted fields to update the state.
    """
    log_node_entry("extract_information", state)
    last_user_message = [msg for msg in state["messages"] if isinstance(msg, HumanMessage)][-1]
    user_messages = [msg.content for msg in state["messages"] if isinstance(msg, HumanMessage)]
    prior_issue = state.get("issue_description", "")
    prior_infos = state.get("additional_info", [])
    conversation_context = "\n".join(f"- {msg}" for msg in user_messages)

    system_prompt = AGENT_PROMPT + "\n\n" + ("""Deine Aufgabe ist es, als hochpräziser KI-Daten-Extraktor aus den eingehenden Chat-Nachrichten von Studierenden und Mitarbeitern strukturierte Ticket-Daten zu extrahieren.

        BEREITS BEKANNTER KONTEXT:
        Problembeschreibung: {prior_issue}
        Zusatzinfos: {prior_infos}
        Chatverlauf (User-Nachrichten):
        {conversation_context}

        EXTRAKTIONS-REGELN:
        1. Basis-Daten (Textfelder): Suche nach der 'email', der 'matrikelnummer' und dem Haupt-'problem' und speichere diese ausschließlich in ihren jeweiligen Textfeldern.
        2. Das 'problem' darf ausschließlich gesetzt werden, wenn der Nutzer tatsächlich ein konkretes IT-Problem oder eine Supportanfrage beschreibt.
        3. Zusatzinformationen (Listen-Feld): Extrahiere alle weiteren technischen oder lokalen Details, die für die Lösung des Problems nützlich sein könnten, und weise sie dem Feld 'additional_info' zu.
        - Beispiele für wertvolle Details: Orte (z.B. 'Gebäude LF', 'Bibliothek'), Geräte/Systeme (z.B. 'MacBook', 'Windows 11'), betroffene Services (z.B. 'eduroam', 'VPN') oder spezifische Fehlercodes.
        - FORMAT: Speichere diese Zusatzinfos als einzelne, kompakte Strings innerhalb der Liste (z.B. ["Gebäude LF", "MacBook", "eduroam"]).
        4. Fehlende Daten: Wenn eine Information fehlt, setze das entsprechende Feld zwingend auf null (bzw. lasse die Liste leer).
    	Bewerte zusätzlich die Priorität des Problems.
        Setze priority auf 1 bei dringenden Problemen wie gesperrtem Account,
        Login nicht möglich, Prüfungs-/Abgabeproblemen oder komplettem Ausfall.
        Setze priority auf 0 bei normalen oder weniger dringenden Problemen.
        5. Zusammenfassung (full_conversation): Dieses Feld MUSS bei jeder Antwort neu gesetzt werden - auch wenn sich nur wenig geändert hat. Schreibe eine aktualisierte Zusammenfassung des gesamten bisherigen Gesprächs aus der Perspektive eines Support-Agenten, der einem Kollegen den Fall erklärt. Integriere alle bisher bekannten Informationen, einschließlich Antworten auf Rückfragen. Beispiel: "Der Student fragt nach einer kostenlosen Windows 10 Lizenz für sein universitätseigenes Gerät. Er hat bereits ein qualifizierendes Betriebssystem und benötigt eine Vollversion." Maximal 3 Sätze, keine Aufzählung.
        """.format(
        prior_issue=prior_issue or "noch nicht bekannt",
        prior_infos=", ".join(prior_infos) if prior_infos else "keine",
        conversation_context=conversation_context or "keine",
    ))

    # Telling python to treat output from structured llm as ExtractedTicketData instance
    extracted_data = cast(ExtractedTicketData, structured_llm.invoke([
        SystemMessage(content=system_prompt),
        last_user_message
    ]))

    print("\n===== EXTRACTED DATA =====")
    print(extracted_data)
    print("==========================\n")

    state_update = {}

    if extracted_data.email and not state.get("user_email"):
        state_update["user_email"] = extracted_data.email
    if extracted_data.matrikelnummer and not state.get("matrikelnummer"):
        state_update["matrikelnummer"] = extracted_data.matrikelnummer
    if extracted_data.problem and not state.get("issue_description"):
        state_update["issue_description"] = extracted_data.problem
    if extracted_data.priority is not None and not state.get("priority"):
        state_update["priority"] = extracted_data.priority
    if extracted_data.additional_info:
        current_infos = state.get("additional_info", [])

        new_infos = [info for info in extracted_data.additional_info if info not in current_infos]
        if new_infos:
            state_update["additional_info"] = new_infos
    state_update["full_conversation"] = extracted_data.full_conversation or state.get("full_conversation", "")

    ticket_id = state.get("ticket_id")
    # If ticket already exists: append
    if ticket_id is not None:
        print(f"Appending to ticket {ticket_id} the user message: {last_user_message.content}")
        ticket_service.append_message_to_ticket(ticket_id, last_user_message.content, sender="Customer")
    # If this is the first message with a valid issue: create ticket
    elif extracted_data.problem is not None and extracted_data.problem != "":
        matrikelnummer = extracted_data.matrikelnummer or state.get("matrikelnummer", "unknown")
        title = f"[{matrikelnummer}] {extracted_data.problem}"
        result = create_ticket_by_user_email(
            email=state["user_email"],
            title=title,
            body=last_user_message.content,
            priority=extracted_data.priority if extracted_data.priority is not None else state["priority"],
            internal=True,
            state="new",
            kategorie=state.get("category"),
        )
        state_update["ticket_id"] = result
        add_tag_to_ticket(result, "AI-Created")

        print(f"Created ticket with ID {result} for the state update: {state_update}")


    return state_update

@traceable
def ask_for_email(state: ChatbotState):
    """
    Queries Llama to politely ask the user for their missing email
    :param state: The current conversation and ticket state
    :return: A dictionary containing the newly extracted fields to update the state.
    """
    log_node_entry("ask_for_email", state)
    system_prompt = SystemMessage(content=(
        AGENT_PROMPT + "\n\n" +
        "Dir fehlt noch die Uni-E-Mail-Adresse des Users (eine private Adresse ist auch in Ordnung). Frage danach."
    ))

    full_messages = [system_prompt] + state["messages"]
    response = llm.invoke(full_messages)

    return {"messages": [response]}

@traceable
def ask_for_matrikelnummer(state: ChatbotState):
    """
    Queries Llama to politely ask the user for their missing matrikelnummer
    :param state: The current conversation and ticket state
    :return: A dictionary containing the newly extracted fields to update the state.
    """
    log_node_entry("ask_for_matrikelnummer", state)
    system_prompt = SystemMessage(content=(
        AGENT_PROMPT + "\n\n" +
        "Dir fehlt noch die 7-stellige Matrikelnummer des Users. Frage danach."
    ))

    full_messages = [system_prompt] + state["messages"]
    response = llm.invoke(full_messages)

    return {"messages": [response]}

@traceable
def ask_for_issue(state: ChatbotState):
    """
    Queries Llama to politely ask the user for the missing problem description
    :param state: The current conversation and ticket state
    :return: A dictionary containing the newly extracted fields to update the state.
    """
    log_node_entry("ask_for_issue", state)
    attempts = state.get("ask_issue_attempts", 0) + 1
    system_prompt = SystemMessage(content=(
        AGENT_PROMPT + "\n\n" +
        "Der Nutzer hat noch kein konkretes IT-Anliegen beschrieben. "
        "Bitte ihn, sein IT-Problem zu schildern."
    ))

    full_messages = [system_prompt] + state["messages"]
    response = llm.invoke(full_messages)

    if attempts >= 3:
        return {
            "messages": [response],
            "ask_issue_attempts": attempts,
            "is_complete": True
        }

    return {
        "messages": [response],
        "ask_issue_attempts": attempts
    }

@traceable
def ask_for_additional_info(state: ChatbotState):
    """
    Queries Llama to politely ask the user for the missing additional info, if needed
    :param state: The current conversation and ticket state
    :return: A dictionary containing the newly extracted fields to update the state.
    """
    log_node_entry("ask_for_additional_info", state)
    issue = state.get("issue_description", "")
    infos = state.get("additional_info", [])
    attempts = state.get("additional_info_attempts", 0)

    print(f"[DEBUG: ask_for_additional_info]: attempts: {attempts} ")

    aditionalInfo_llm = llm.with_structured_output(AdditionalInfoDecision)


    query = f"{issue} + {infos}"
    rag_results = retrieve_relevant_entries(query, n_results=2)

    faq_matches = rag_results.get("faq_matches", [])
    ticket_matches = rag_results.get("ticket_matches", [])

    if not faq_matches and not ticket_matches:
        print("[DEBUG] RAG lieferte keine Ergebnisse. Überspringe Rückfrage.")
        return {"needs_additional_info": True}

    faq_context = "\n".join([f"- {_format_faq_match_for_prompt(match)}" for match in faq_matches])
    ticket_context = "\n".join([f"- {match['text']} (Kategorie: {match['category']})" for match in ticket_matches])


    system_prompt = SystemMessage(content=(
        AGENT_PROMPT + "\n\n" +
        f"""
        Dein Ziel ist es zu prüfen, ob die vorliegenden Informationen für das genannte Problem ausreichen,
        um ein vollständiges Ticket zu erstellen.
        
        AKTUELLES PROBLEM: {issue}
        BEREITS BEKANNTE ZUSATZINFOS: {infos}
        
        WISSENSDATENBANK (Historische Tickets & FAQs für dieses Problem):
        FAQs:
        {faq_context}
        
        Alte Tickets:
        {ticket_context}
        
        REGELN:
        1. Lies die Einträge in der WISSENSDATENBANK und prüfe zwei Dinge:
           a) Fehlen im "AKTUELLEN PROBLEM" Details, die in den alten Tickets oder FAQs zur Lösung 
              zwingend notwendig waren?
           b) Gibt es in der WISSENSDATENBANK mehrere unterschiedliche Einträge (FAQs oder Tickets), die 
              auf das AKTUELLE PROBLEM ähnlich gut passen könnten, aber zu unterschiedlichen Lösungen oder 
              Ursachen führen? Falls ja, identifiziere das unterscheidende Merkmal zwischen diesen Einträgen 
              (z.B. Betriebssystem, Standort, Nutzergruppe, Fehlerzeitpunkt) – dieses Merkmal zählt ebenfalls 
              als "fehlende Information", auch wenn das AKTUELLE PROBLEM auf den ersten Blick vollständig wirkt.
        2. Wenn weder (a) noch (b) zutrifft, ODER wenn die WISSENSDATENBANK keine relevanten Inhalte für 
           eine Nachfrage liefert, setze needs_additional_info auf True und follow_up_question auf den 
           leeren String.
        3. Wenn (a) und/oder (b) zutrifft, setze needs_additional_info auf False und formuliere wenige, 
           direkt-relevante, kurze follow-up-question(s) an den User. Bei (b) soll die Frage explizit darauf 
           abzielen, zwischen den überschneidenden Kontexten zu unterscheiden (z.B. "Welches Betriebssystem 
           nutzt du?" wenn sich zwei Tickets nur darin unterscheiden).
        4. Gib die Fragen als Bullet-Liste zurück. Es muss diese genaue Syntax befolgen:
           Multiple-Choice-Fragen müssen das Format verwenden:
           "* [Frage]? (options: [A], [B], [C])"
           Offene Fragen dürfen ohne Optionen geschrieben werden:
           "* [Frage]?"
        5. Stelle die Fragen soweit wie möglich immer als Multiple-Choice mit dem gezeigten Format.
        6. Begrenze dich auf maximal 5 Optionen, wobei "Andere" IMMER eine Option sein muss.
        """
    ))

    # Benchmark compatibility:
    # DeepSeek and Apertus accept prompts consisting only of a SystemMessage,
    # but Qwen returns "No user query found in messages" in that case.
    # Adding a minimal HumanMessage preserves the existing prompting logic
    # while making the structured-output request compatible with all evaluated models.

    decision = cast(AdditionalInfoDecision, aditionalInfo_llm.invoke([
        system_prompt,
        HumanMessage(
            content="Bitte prüfe anhand des Problems und der Zusatzinfos, ob weitere Informationen benötigt werden.")
    ]))


    # Logic switch if all information needed is collected or not
    if len(infos) >= 2 or decision.needs_additional_info or attempts >= 3:
        return {"needs_additional_info": True}
    else:
        llm_msg = f"Ich habe für dich gerade ein Support-Ticket erstellt. Um dich optimal zu unterstützen, beantworte  bitte folgende Fragen:\n{decision.follow_up_question}"
        ticket_id = state.get("ticket_id")
        if llm_msg:
            try:
                ticket_service.append_message_to_ticket(
                    ticket_id=ticket_id,
                    body=f"[ZIM AI-AGENT]\n\n{llm_msg}",
                    sender="Agent",
                    internal=True
                )
            except Exception as e:
                print(f"Failed to add internal article: {e}")
            return {
                "needs_additional_info": False,
                "additional_info_attempts": attempts + 1,
                "messages": [AIMessage(content=llm_msg)]
            }

@traceable
def give_solutions(state: ChatbotState):
    """
    Build a RAG query from: history + user_message + issue_description + additional_info
    (in that exact order), then retrieve and return up to two solutions.
    """
    log_node_entry("give_solutions", state)
    msgs = state.get("messages", []) or []
    # history = all messages except the last one
    history_parts = [m.content for m in msgs[:-1]] if len(msgs) > 1 else []
    history_text = " ".join(history_parts).strip()

    # user_message = last message if present
    user_msg = msgs[-1].content.strip() if msgs else ""

    issue = (state.get("issue_description") or "").strip()
    additional = " ".join(state.get("additional_info", [])) if state.get("additional_info") else ""

    query = f"{issue} + {additional}"

    if not query:
        return {"messages": [AIMessage(content="Keine ausreichende Anfrage für die Suche.")], "solutions": []}

    try:
        print(f"[RAG QUERY] {query}")
        results = retrieve_relevant_entries(query, n_results=2)
        print(
            f"[RAG RESULT] faq={len(results.get('faq_matches', []))} tickets={len(results.get('ticket_matches', []))} inferred={results.get('inferred')}")
    except Exception as e:
        print(f"[RAG ERROR] {e}")
        return {"messages": [AIMessage(content="Fehler bei der Suche in der Wissensdatenbank.")], "solutions": []}

    faq_matches = results.get("faq_matches", [])
    ticket_matches = results.get("ticket_matches", [])
    inferred = results.get("inferred", {})

    # Build up to 2 solutions (FAQ first)
    solutions = []
    for m in faq_matches[:2]:
        solutions.append({"title": f"FAQ: {m[0]}", "description": _format_faq_match_for_prompt(m)})
    if len(solutions) < 2:
        for t in ticket_matches[: 2 - len(solutions)]:
            solutions.append(
                {"title": f"Ähnliches Ticket ({t.get('category', 'unknown')})", "description": t.get("text", "")})

    print(f"[Node: give_solutions] Solutions: {solutions}")

    problem = state.get("issue_description", "")
    infos = state.get("additional_info", [])

    system_prompt = SystemMessage(content=(
        AGENT_PROMPT + "\n\n" +
        f"""
            Deine Aufgabe ist es, basierend auf dem 
            aktuellen Problem und den bereits bekannten Zusatzinfos eine konkrete, direkt umsetzbare Lösung zu geben.
            
            AKTUELLES PROBLEM: {problem}
            BEREITS BEKANNTE ZUSATZINFOS: {infos}
            LÖSUNGEN (RAG-Kontext): {solutions}
            
            REGELN:
            1. Antworte in einem einzigen zusammenhängenden Fließtext, "...NICHT als Liste, Aufzählung oder mit Zwischenüberschriften. 
               Bei mehreren aufeinanderfolgenden Handlungsschritten nutze stattdessen Ordinalwörter im Fließtext
               ('Öffne zunächst...', 'Klicke anschließend...', 'Bestätige abschließend...'), 
               um die Reihenfolge erkennbar zu machen, ohne Listenformat zu verwenden.
            2. Formuliere die Lösung so, als würdest du dem Nutzer direkt sagen, was er jetzt tun soll – nicht 
               "es gibt folgende Lösungsansätze", sondern konkret "Deaktiviere X, dann..." bzw. "Das Problem liegt 
               an Y, daher solltest du Z tun".
            3. Wenn mehrere Lösungen im Kontext vorhanden sind, wähle die passensten Lösungen. 
               Die Lösungen darfst du nicht vermischen. Behandle sie seperat.
            4. Gib die Lösungen nie wörtlich aus dem Kontext wieder. Interpretiere sie und setze sie in Bezug zum 
               konkreten Problem des Nutzers.
            5. Maximal 6 Sätze pro Lösung, auf die du eingehst.
               Bei mehrschrittigen technischen Anleitungen darf die Satzzahl überschritten werden, 
               wenn sonst notwendige Schritte fehlen würden – Vollständigkeit (Regel 6) hat Vorrang vor Kürze. 
               Keine Begrüßungsfloskeln, keine Zusammenfassung am Ende, keine Abschlussfrage wie 'Konnte ich helfen?".
            6. Die Lösung muss aus sich selbst heraus vollständig verständlich sein. Der Nutzer soll keinen Link 
               öffnen müssen, um zu verstehen, was ihn dort erwartet. Nenne alle relevanten Schritte/Infos direkt im Text,
               fasse dabei den Linkinhalt kurz zusammen statt ihn vollständig wiederzugeben.
               Füge Links an der Stelle im Text ein, zu der sie inhaltlich gehören.
               - Liegt zu einem Link Content vor: bau den Inhalt des Kontexts in der Lösung ein, sofern dieser relevant für das "AKTUELLE PROBLEM" ist.
               - Liegt kein Content vor (nur eine Notiz zum Fehlschlag): beschreibe nur, was sich sicher aus 
                 problem/solution ableiten lässt, erfinde keine Details, und mache transparent, dass der Inhalt 
                 nicht automatisch abrufbar war.
               - Ist der Link selbst der auszuführende Schritt (Formular, Login, Download, Zahlung), bleibt er 
                 Pflichtklick – erkläre vorher, was dort zu tun ist.
            7. Wenn im Kontext keine passende Lösung vorhanden ist, sage das ehrlich und kurz, anstatt vage zu 
               bleiben oder den Nutzer zur eigenen Recherche zu schicken.
            8. Enthält eine Lösung irreversible oder folgenreiche Schritte (z. B. Konto löschen, Daten zurücksetzen, Zahlung auslösen),
            weise im Text kurz und klar darauf hin, bevor du den Schritt nennst.
            """
    ))
    message_text = llm.invoke([system_prompt, HumanMessage(content="Bitte fasse die Lösungen für den User zusammen.")])


    final_message = AIMessage(content=message_text.content + "\n\n Konnte ich dir dabei helfen, dein Problem zu lösen?")

    ticket_id = state.get("ticket_id")
    try:
        print(f"appending bot message to ticket {ticket_id}")
        ticket_service.append_message_to_ticket(
            ticket_id = ticket_id,
            body=f"[ZIM AI-AGENT]\n\n{final_message.content}",
            sender="Agent",
            internal = True
        )
    except:
        print("Could not append message to ticket (give solutions).")


    return {
        "messages": [final_message],
        "solutions": solutions,
        # "rag_debug": {
        #     "query": query,
        #     "faq_count": len(faq_matches),
        #     "ticket_count": len(ticket_matches),
        #     "inferred": inferred
        # }
    }

@traceable
def finish_ticket(state):
    """
    Finalizes the ticket creation process by generating a concise title
    and preparing the payload for the Zammad API.
    """
    log_node_entry("finish_ticket", state)
    # If the issue was asked three times, and no problem could be extracted,
    # say instead that the off-topic issue cannot be processed by support
    attempts = state.get("ask_issue_attempts", 0)
    if attempts >= 3:
        final_message = (
            "Ich kann dein Anliegen leider nicht weiter als ZIM-IT-Support bearbeiten, "
            "da keine eindeutige IT-/ZIM-bezogene Problemstellung erkannt wurde.\n\n"
            "Falls du später ein IT-Problem rund um Dienste der Universität hast "
            "(z. B. WLAN, VPN, E-Mail, Moodle oder Account-Probleme), helfe ich dir gerne weiter."
        )
        return {
            "messages": [AIMessage(content=final_message)],
            "is_complete": True
        }

    category = _resolve_ticket_category(state)
    state_with_category = {**state, "category": category}
    result = ticket_service.create_support_ticket(state_with_category)
    # Append the bot's confirmation reply as an Agent article to the new ticket.
    ticket_id = result.get("ticket_id")
    try:
        bot_message_content = result["messages"][0].content
        print(f"appending bot message {bot_message_content}")
        ticket_service.append_message_to_ticket(
            ticket_id = ticket_id,
            body=f"[ZIM AI-AGENT]\n\n{bot_message_content}",
            sender="Agent",
            internal = True
        )
    except:
        print("Could not append message to ticket (give solutions).")

    return {**result, "category": category}

@traceable
def finish_ai_solved_ticket(state):
    """
    Finalizes the ticket creation process by generating a concise title
    and preparing the payload for the Zammad API. Also marks the ticket with that that
    was solved only by using the chatbot without involving the ZIM staff
    """
    log_node_entry("finish_ai_solved_ticket", state)
    category = _resolve_ticket_category(state)
    state_with_category = {**state, "category": category}
    result = ticket_service.create_ai_solved_ticket(state_with_category)
    return {**result, "category": category}