from typing import cast

from langsmith import traceable

from .models.ExtractedTicketData import ExtractedTicketData
from .models.AdditionalInfoDecision import AdditionalInfoDecision
from .models.TicketCategoryDecision import TICKET_CATEGORIES, TicketCategoryDecision
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from .state import ChatbotState
from backend.rag.retrieve_info import retrieve_relevant_entries
from ..services.TicketService import TicketService
from ..llm.prompts import TICKET_CATEGORY_RULES
from ..services.ProblemService import ProblemService
from ..llm.llm import llm, structured_llm, AGENT_PROMPT, category_llm, with_structured_fallback
from ..llm.strings import t
from .node_logging import log_node_entry, langgraph_logger, truncate_long_strings_in_dicts_for_logging, visit
from ..api.zammad import create_ticket_by_user_email, add_tag_to_ticket
from .models.IntentDecision import IntentDecision
from backend.rag.rag_logging import rag_logger

ticket_service = TicketService()
problem_service = ProblemService()


def _append_agent_article_to_ticket(ticket_id, body: str, context: str) -> None:
    """Append an internal agent article; log and continue on failure."""
    try:
        ticket_service.append_message_to_ticket(
            ticket_id=ticket_id,
            body=body,
            sender="Agent",
            internal=True,
        )
    except Exception:
        langgraph_logger.exception(f"[{context}] Could not append message to ticket {ticket_id}")


def _build_metadata_context(state: dict) -> str:
    parts = []
    if state.get("display_name"):
        parts.append(f"Name des Nutzers: {state['display_name']}")
    if state.get("role"):
        parts.append(f"Rolle: {state['role']}")
    if state.get("faculty"):
        parts.append(f"Fakultaet: {state['faculty']}")
    if state.get("device"):
        parts.append(f"Geraet: {state['device']}")
    if state.get("os_name"):
        parts.append(f"Betriebssystem: {state['os_name']}")
    if state.get("language"):
        response_language = "Deutsch" if state["language"] == "de" else "Englisch"
        parts.append(f"Antwortsprache: {response_language}")
    if not parts:
        return ""
    context = "\n\nBENUTZER-KONTEXT:\n" + "\n".join(parts)
    if state.get("display_name"):
        first_name = state["display_name"].split()[0]
        context += f"\n\nSprich den Nutzer in deiner Antwort mit seinem Vornamen ({first_name}) an."
    return context


def _format_faq_match_for_prompt(match: dict) -> str:
    """Render a faq_matches entry (dict with id, text, similarity,
    optional extracted_urls) as prompt text."""
    lines = [match.get("text", "")]
    for url_entry in match.get("extracted_urls", []):
        url = url_entry.get("url")
        status = url_entry.get("status")
        content = url_entry.get("content")
        error = url_entry.get("error")
        if status == "success" and content:
            lines.append(f"[{url}]: {content}")
        elif error:
            lines.append(f"[{url}]: {error}")
    return "\n".join(lines)


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

{TICKET_CATEGORY_RULES}"""
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
    return {
        **visit("classify_ticket_node"),
        "category": category
        }


@traceable
def escalate_incidents(state: ChatbotState):
    """Workflow node: maintain the 'Recent Incidents' RAG and escalate if needed.

    Only runs when the category is 'Incident' and a ticket already exists.
    This node does not affect the user chat (fire-and-forget) and therefore
    returns no state changes.
    """
    if state.get("category") != "Incident":
        return visit("escalate_incidents_node")

    ticket_id = state.get("ticket_id")
    if not ticket_id or ticket_id == -1:
        return visit("escalate_incidents_node")

    try:
        result = problem_service.register_and_check_incident(
            ticket_id=ticket_id,
            issue_description=state.get("issue_description", ""),
            additional_info=list(state.get("additional_info", [])),
        )
        langgraph_logger.info(f"Escalating incident for ticket {ticket_id} -> {result}")
    except Exception:
        langgraph_logger.exception(f"Escalating incident failed for ticket {ticket_id}")

    return visit("escalate_incidents_node")



INTENTS = ["tutorial", "problem", "unclear", "solved"]
intent_llm = with_structured_fallback(IntentDecision)
aditionalInfo_llm = with_structured_fallback(AdditionalInfoDecision)


@traceable
def classify_intent(state: ChatbotState):
    """Workflow node: re-evaluates on every message what the user wants """
    log_node_entry("classify_intent", state)

    # 1)
    user_messages = [msg.content for msg in state["messages"] if isinstance(msg, HumanMessage)]
    ai_messages = [msg.content for msg in state["messages"] if isinstance(msg, AIMessage)]
    last_bot_message = ai_messages[-1][-400:] if ai_messages else "(keine)"
    conversation = "\n".join(f"- {m}" for m in user_messages) if user_messages else "(keine)"
    previous_intent = state.get("intent") or "(noch keiner)"

    # 2) Decision criteria
    system_prompt = SystemMessage(content=f"""Du bist ein Verteiler im IT-Support des ZIM einer Universitaet.
Entscheide anhand des GESAMTEN Chatverlaufs, was der Nutzer AKTUELL moechte:

- "tutorial": Der Nutzer sucht nach einer Anleitung, Hilfe zur Selbsthilfe oder einer Loesung, um ein Problem/eine Stoerung SELBST zu beheben.
  WICHTIG: Auch wenn der Nutzer Formulierungen nutzt wie "Ich habe ein Problem", "X geht nicht", "X funktioniert nicht" oder "Ich komme nicht rein", gilt dies als "tutorial", solange er wissen moechte, wie er es selbst loesen kann (z. B. "Was kann ich tun?", "Wie loese ich das?", "Wie richte ich ... ein?").
- "problem": Der Nutzer moechte EXPLIZIT, dass der menschliche Support übernimmt / ein Ticket erstellt wird, ODER meldet einen reinen Infrastruktur-Ausfall, den er selbst nicht beheben kann.
  Typisch: "Erstellt mir ein Ticket", "Ich will mit einem Mitarbeiter sprechen", "WLAN in Raum R14 ist komplett ausgefallen", "Das System ist down".
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
- AUSNAHME: Endet die LETZTE BOT-NACHRICHT mit der Frage, ob das Problem
  geloest ist, und antwortet der Nutzer darauf zustimmend (z. B. "Ja", "jo",
  "passt", "danke"), dann waehle "solved".
- Ein zustimmendes "Ja" auf eine ANDERE Rueckfrage (z. B. nach Geraet,
  Standort oder Betriebssystem) bleibt eine Zwischenantwort und ist KEIN Wechsel.
- Entscheide nach der Hauptabsicht, nicht nach einzelnen Schluesselwoertern.

LETZTE BOT-NACHRICHT (Ende):
{last_bot_message}

CHATVERLAUF (User-Nachrichten):
{conversation}""")

    # 3)
    decision = cast(IntentDecision, intent_llm.invoke([
        system_prompt,
        HumanMessage(content="Bitte klassifiziere die Absicht des Nutzers.")
    ]))
    intent = decision.intent if decision.intent in INTENTS else "unclear"

    state_update = {"intent": intent}

    return {
        **visit("classify_intent_node"),
        **state_update
        }



@traceable
def ask_intent(state: ChatbotState):
    """Asks whether the user wants a tutorial or needs support."""
    log_node_entry("ask_intent", state)
    metadata_context = _build_metadata_context(state)
    system_prompt = SystemMessage(content=(
          AGENT_PROMPT + metadata_context + "\n\n"
        "Die Absicht des Nutzers ist noch unklar. Frage kurz und freundlich, ob er eine Schritt-fuer-Schritt-"
        "Anleitung zum Selbermachen moechte oder ob der Support sich um sein Anliegen "
        "kuemmern soll. Beantworte keine anderen Fragen und wechsle nicht das Thema."
    ))
    response = llm.invoke([system_prompt] + state["messages"])
    return {
        **visit("ask_intent_node"),
        "messages": [response]
        }

@traceable
def give_tutorial(state: ChatbotState):
    """Creates a step-by-step tutorial from the knowledge base"""
    log_node_entry("give_tutorial", state)
    attempts = state.get("tutorial_attempts", 0)

    issue = state.get("issue_description", "")
    additional_info = " ".join(state.get("additional_info", []))
    query = f"{issue} {additional_info}".strip()

    rag_results = retrieve_relevant_entries(query, n_results=2)
    faq_context = "\n".join(f"- {_format_faq_match_for_prompt(m)}" for m in rag_results.get("faq_matches", []))
    ticket_context = "\n".join(f"- {m['text']}" for m in rag_results.get("ticket_matches", []))


    metadata_context = _build_metadata_context(state)

    system_prompt = SystemMessage(content=AGENT_PROMPT + metadata_context + "\n\n" + f"""

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
        **visit("give_tutorial_node"),
        "messages": [response],
        "tutorial_attempts": attempts + 1
    }

@traceable
def finish_tutorial(state: ChatbotState):
    """Closes the tutorial path: creates a closed AI-solved ticket and says goodbye."""
    log_node_entry("finish_tutorial", state)
    result = ticket_service.create_closed_tutorial_ticket(state)

    # set ticket tag to AI-solved
    finish_ai_solved_ticket(state)

    metadata_context = _build_metadata_context(state)
    system_prompt = SystemMessage(content=(
        AGENT_PROMPT + metadata_context + "\n\n"
        "Der Nutzer hat gerade bestaetigt, dass deine Anleitung sein Anliegen "
        "geloest hat. Verabschiede dich kurz, freundlich und natuerlich, mit Bezug "
        "auf sein konkretes Anliegen. Maximal 2 Saetze. Erwaehne, dass er sich "
        "jederzeit wieder melden kann."
    ))
    response = llm.invoke([system_prompt] + state["messages"])

    return {
        **visit("finish_tutorial_node"),
        **result,
        "messages": [response]
        }

def _build_extraction_system_prompt(
    prior_issue: str,
    prior_infos: list,
    conversation_context: str,
    metadata_context: str = "",
) -> str:
    """Build the structured-extraction system prompt for extract_information."""
    return AGENT_PROMPT + metadata_context + "\n\n" + ("""Deine Aufgabe ist es, als hochpräziser KI-Daten-Extraktor aus den eingehenden Chat-Nachrichten von Studierenden und Mitarbeitern strukturierte Ticket-Daten zu extrahieren.

        BEREITS BEKANNTER KONTEXT:
        Problembeschreibung: {prior_issue}
        Zusatzinfos: {prior_infos}
        Chatverlauf (User-Nachrichten):
        {conversation_context}

        EXTRAKTIONS-REGELN:
        1. Basis-Daten (Textfelder): Suche nach der 'student_id' und dem Haupt-'problem' und speichere diese ausschließlich in ihren jeweiligen Textfeldern.
        2. Das 'problem' darf ausschließlich gesetzt werden, wenn der Nutzer tatsächlich ein konkretes IT-Problem oder eine Supportanfrage beschreibt.
        2a. Ist in BEREITS BEKANNTER KONTEXT unter "Problembeschreibung" bereits ein Wert vorhanden, setze 'problem' NICHT erneut. Beschreibt die aktuelle Nachricht eine Verfeinerung, Präzisierung oder Detailantwort zum bereits bekannten Problem (z.B. eine Antwort auf eine Rückfrage), ordne diesen Inhalt stattdessen dem Feld 'additional_info' zu.
        3. Zusatzinformationen (Listen-Feld): Extrahiere alle weiteren technischen oder lokalen Details, die für die Lösung des Problems nützlich sein könnten, und weise sie dem Feld 'additional_info' zu.
        - Beispiele für wertvolle Details: Orte (z.B. 'Gebäude LF', 'Bibliothek'), Geräte/Systeme (z.B. 'MacBook', 'Windows 11'), betroffene Services (z.B. 'eduroam', 'VPN') oder spezifische Fehlercodes.
        - FORMAT: Speichere diese Zusatzinfos als einzelne, kompakte Strings innerhalb der Liste (z.B. ["Gebäude LF", "MacBook", "eduroam"]).
        4. Fehlende Daten: Wenn eine Information fehlt, setze das entsprechende Feld zwingend auf null (bzw. lasse die Liste leer).
    	Bewerte zusätzlich die Priorität des Problems.
        Setze priority auf 1 bei dringenden Problemen wie gesperrtem Account,
        Login nicht möglich, Prüfungs-/Abgabeproblemen oder komplettem Ausfall.
        Setze priority auf 0 bei normalen oder weniger dringenden Problemen.
        5. Zusammenfassung (summary): Dieses Feld MUSS bei jeder Antwort neu gesetzt werden - auch wenn sich nur wenig geändert hat. Schreibe eine aktualisierte Zusammenfassung des gesamten bisherigen Gesprächs aus der Perspektive eines Support-Agenten, der einem Kollegen den Fall erklärt. Integriere alle bisher bekannten Informationen, einschließlich Antworten auf Rückfragen. Beispiel: "Der Student fragt nach einer kostenlosen Windows 10 Lizenz für sein universitätseigenes Gerät. Er hat bereits ein qualifizierendes Betriebssystem und benötigt eine Vollversion." Maximal 3 Sätze, keine Aufzählung. Schreib die Zusamenfassung IMMER auf Deutsch, unabhaengig von der Antwortsprache - dieses Feld ist nur fuer das Support-Team in Zammad bestimmt, nicht fuer den Nutzer sichtbar.
        5a. Nutzer-Zusammenfassung (user_summary): Schreibe zusaetzlich dieselbe Zusammenfassung inhaltlich identisch noch einmal in das Feld 'user_summary' - aber in der im BENUTZER-KONTEXT angegebenen Antwortsprache statt zwingend auf Deutsch. Dieses Feld MUSS wie 'summary' bei jeder Antwort neu gesetzt werden und wird dem Nutzer selbst angezeigt.
        6. Integriere in der Zusammenfassung (summary und user_summary) die Metadata des Users.
        7. Sprache (language): Erkenne die Sprache der aktuellsten Nutzernachricht (der beigefuegten HumanMessage, NICHT dieser Instruktionen) und setze 'language' auf 'de' oder 'en'. Ist die Sprache nicht eindeutig erkennbar (z.B. nur Zahlen, Matrikelnummer, Emojis, einzelnes Wort), setze 'language' auf null.

        """.format(
        prior_issue=prior_issue or "noch nicht bekannt",
        prior_infos=", ".join(prior_infos) if prior_infos else "keine",
        conversation_context=conversation_context or "keine",
    ))


def _state_update_from_extracted_data(state: ChatbotState, extracted_data: ExtractedTicketData) -> dict:
    """Map ExtractedTicketData into a state update without overwriting existing fields."""
    state_update = {}
    state_update["graph_runs"] = state.get("graph_runs", 0) + 1

    if extracted_data.language:
        state_update["language"] = extracted_data.language
    if extracted_data.student_id and not state.get("student_id"):
        state_update["student_id"] = extracted_data.student_id
    if extracted_data.problem and not state.get("issue_description"):
        state_update["issue_description"] = extracted_data.problem
    if extracted_data.priority is not None and not state.get("priority"):
        state_update["priority"] = extracted_data.priority
    if extracted_data.additional_info:
        current_infos = state.get("additional_info", [])

        new_infos = [info for info in extracted_data.additional_info if info not in current_infos]
        if new_infos:
            state_update["additional_info"] = new_infos
    state_update["summary"] = extracted_data.summary or state.get("summary", "")
    state_update["user_summary"] = extracted_data.user_summary or state.get("user_summary", "")

    return state_update


def _sync_ticket_after_extraction(
    state: ChatbotState,
    state_update: dict,
    extracted_data: ExtractedTicketData,
    last_user_message,
) -> None:
    """Append to an existing ticket or create one when a problem was first extracted.

    Mutates state_update in place when a new ticket is created.
    """
    ticket_id = state.get("ticket_id")
    # If ticket already exists: append
    if ticket_id is not None:
        langgraph_logger.info(f"Appending customer message to ticket {ticket_id}")
        ticket_service.append_message_to_ticket(ticket_id, last_user_message.content, sender="Customer")
        # Update the ticket title with the latest extracted information
        merged_state = {**state, **state_update}
        if extracted_data.problem:
            merged_state["issue_description"] = extracted_data.problem
        ticket_service.update_ticket_title_from_state(merged_state, ticket_id)

    # If this is the first message with a valid issue: create ticket
    elif extracted_data.problem is not None and extracted_data.problem != "":
        student_id = extracted_data.student_id or state.get("student_id", "unknown")
        title = f"[{student_id}] {extracted_data.problem}"
        result = create_ticket_by_user_email(
            email=state["user_email"],
            title=title,
            body=last_user_message.content,
            priority=extracted_data.priority if extracted_data.priority is not None else state["priority"],
            internal=True,
            state="new",
            category=state.get("category"),
        )
        state_update["ticket_id"] = result
        add_tag_to_ticket(result, "AI-Created")
        langgraph_logger.info(f"Created ticket with ID {result}")


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

    metadata_context = _build_metadata_context(state)
    system_prompt = _build_extraction_system_prompt(
        prior_issue, prior_infos, conversation_context, metadata_context
    )

    # Cast structured LLM output to ExtractedTicketData
    extracted_data = cast(ExtractedTicketData, structured_llm.invoke([
        SystemMessage(content=system_prompt),
        last_user_message
    ]))

    langgraph_logger.debug(f"EXTRACTED DATA: {extracted_data}")

    state_update = _state_update_from_extracted_data(state, extracted_data)
    _sync_ticket_after_extraction(state, state_update, extracted_data, last_user_message)

    return {
        **visit("extractor_node"),
        **state_update,
        }


@traceable
def ask_for_issue(state: ChatbotState):
    """
    Queries Llama to politely ask the user for the missing problem description
    :param state: The current conversation and ticket state
    :return: A dictionary containing the newly extracted fields to update the state.
    """
    log_node_entry("ask_for_issue", state)
    attempts = state.get("ask_issue_attempts", 0) + 1

    if attempts >= 3:
        final_message = t(
            "Das Anliegen kann leider nicht weiter als ZIM-IT-Support bearbeitet werden, "
            "da keine eindeutige IT-/ZIM-bezogene Problemstellung erkannt wurde.\n\n"
            "Bei einem späteren IT-Problem rund um Dienste der Universität "
            "(z. B. WLAN, VPN, E-Mail, Moodle oder Account-Probleme) hilft der ZIM-IT-Support gerne weiter.",
            state.get("language", "de"),
        )
        return {
            **visit("ask_issue_node"),
            "messages": [AIMessage(content=final_message)],
            "ask_issue_attempts": attempts,
            "is_complete": True
        }

    metadata_context = _build_metadata_context(state)
    system_prompt = SystemMessage(content=(
        AGENT_PROMPT + metadata_context + "\n\n" +
        "Der Nutzer hat noch kein konkretes IT-Anliegen beschrieben. "
        "Bitte ihn, sein IT-Problem zu schildern."
    ))

    full_messages = [system_prompt] + state["messages"]
    response = llm.invoke(full_messages)

    return {
        **visit("ask_issue_node"),
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

    langgraph_logger.debug(f"ask_for_additional_info node: attempts: {attempts} ")

    query = f"{issue} + {infos}"
    rag_results = retrieve_relevant_entries(query, n_results=2)

    faq_matches = rag_results.get("faq_matches", [])
    ticket_matches = rag_results.get("ticket_matches", [])

    if not faq_matches and not ticket_matches:
        rag_logger.debug(f"Query {query} returned no result. Skipping follow up question")
        return {
            **visit("ask_for_additional_info"),
            "needs_additional_info": False
            }

    faq_context = "\n".join([f"- {_format_faq_match_for_prompt(match)}" for match in faq_matches])
    ticket_context = "\n".join([f"- {match['text']} (Kategorie: {match['category']})" for match in ticket_matches])


    rag_logger.debug(f"faq_matches:\n{truncate_long_strings_in_dicts_for_logging(faq_matches)}")
    rag_logger.debug(f"faq_context:\n{truncate_long_strings_in_dicts_for_logging(faq_context)}")


    metadata_context = _build_metadata_context(state)

    system_prompt = SystemMessage(content=(
        AGENT_PROMPT + metadata_context + "\n\n" +
        f"""
        Dein Ziel ist es zu prüfen, ob die vorliegenden Informationen ausreichen, um das aktuelle Problem eindeutig zu bearbeiten.

        AKTUELLES PROBLEM:
        {issue}
        
        BEREITS BEKANNTE ZUSATZINFOS:
        {infos}
        
        WISSENSDATENBANK (Historische Tickets & FAQs):
        FAQs:
        {faq_context}
        
        Alte Tickets:
        {ticket_context}
        
        REGELN:
        
        1. Analysiere das AKTUELLE PROBLEM zusammen mit der WISSENSDATENBANK.
        
        2. Prüfe dabei zwei Dinge:
           a) Fehlen Informationen, die laut den ähnlichen Tickets oder FAQs erforderlich sind, um eine passende Lösung vorzuschlagen?
           b) Gibt es mehrere unterschiedliche Einträge, die ähnlich gut zum Problem passen, sich aber in ihren Voraussetzungen oder Lösungen unterscheiden (z. B. Betriebssystem, Gerät, Standort, Softwareversion oder Netzwerk)? 
           In diesem Fall stelle gezielte Rückfragen, um zwischen diesen Einträgen unterscheiden zu können.
        
        3. Stelle nur Rückfragen, wenn deren Antwort die Auswahl der passenden Lösung tatsächlich beeinflusst.
         Wenn eine Antwort die spätere Lösung nicht verändern würde, stelle keine Rückfrage.
         Frage nicht nach einzelnen Schritten, Aktionen oder Details, die erst Teil der späteren Lösung sind.
        
        4. Wenn weder (a) noch (b) zutrifft oder die Wissensdatenbank keine sinnvollen Rückfragen ermöglicht, setze needs_additional_info auf False und follow_up_question auf einen leeren String.
        
        5. Wenn (a) und/oder (b) zutrifft, setze needs_additional_info auf True und 
           formuliere möglichst wenige, kurze und präzise Rückfragen.
        
        6. Gib alle Fragen als Bullet-Liste zurück.
        
           Multiple-Choice-Fragen müssen exakt folgendes Format verwenden, mit
           EXAKT "|" (Pipe-Zeichen) als Trenner zwischen den Optionen:
           * [Frage]? (options: [Option A] | [Option B] | [Option C])
        
        7. Verwende IMMER Multiple-Choice-Fragen, auch wenn es eine offene Frage ist.
            Bei offenen Fragen: gib die bestmöglichen Antwortoptionen an.
        
        8. Verwende höchstens fünf Antwortoptionen. Dabei muss "Andere" immer eine Antwortoption sein.
        
        9. Stelle niemals Rückfragen über Informationen, die nicht aus dem aktuellen Problem oder der Wissensdatenbank ableitbar sind.
        
        10. Jede Rückfrage darf nur ein einziges, unabhängiges Thema abfragen.
            Mische niemals völlig verschiedene Themen in einer Frage 
            (Frage z.B. NICHT: "Welches Gerät wird genutzt und welche Fehlermeldung erscheint?").
        
        11. Wenn du mehrere unabhängige Themen klären musst, erstelle dafür separate Bullet-Fragen.
            Jede Frage muss genau ein Unterscheidungsmerkmal zwischen den möglichen Lösungen klären.
            
        12. Die Rückfragen dienen NUR dazu, die passenden Lösungen zu klassifizieren. Daher nicht die einzelnen todos der Lösung als Frage formulieren.
        
        13. Vermeide Wenn-Dann-Abhängigkeiten zwischen separaten Fragen.
            Da alle Fragen dem Nutzer GLEICHZEITIG angezeigt werden, dürfen sie logisch nicht aufeinander aufbauen. 
            Fasse solche Abhängigkeiten stattdessen über inklusive Antwortoptionen in einer einzigen Frage zusammen 
            (z.B. statt zwei Fragen zu stellen, frage lieber: "Welche Maßnahmen hast du bereits ergriffen?" mit den Optionen: [Maßnahme A] | [Maßnahme B] | [Bisher noch keine Maßnahmen ergriffen] | [Andere]).

        14. Stelle KEINE Rückfragen zu Informationen, die bereits im BENUTZER-KONTEXT bekannt sind (z.B. Betriebssystem, Gerät, Rolle). Diese Daten sind bereits verifiziert und muessen nicht erneut erfragt werden. Nutze sie direkt fuer die Auswahl der passenden Lösung.
        
        15. Trenne Optionen AUSSCHLIESSLICH mit "|", niemals mit Komma - auch wenn eine Option selbst ein Komma enthaelt (z.B. "options: Keine Verbindung | Verbindung hergestellt, aber kein Internet | Verbindungsabbrüche | Keine IP‑Adresse | Andere").
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

    langgraph_logger.debug(f"decision.needs_additional_info: {decision.needs_additional_info}")
    langgraph_logger.debug(f"decision.follow_up_question: {decision.follow_up_question!r}")

    # Logic switch if all information needed is collected or not
    follow_up_question = (decision.follow_up_question or "").strip()
    if len(infos) >= 2 or not decision.needs_additional_info or attempts >= 3 or not follow_up_question:

        return {
            **visit("ask_for_additional_info"),
            "needs_additional_info": False
            }

    known_parts = []
    if state.get("display_name"):
        known_parts.append(f"Name: {state['display_name']}")
    if state.get("device"):
        known_parts.append(f"Gerät: {state['device']}")
    if state.get("os_name"):
        known_parts.append(f"Betriebssystem: {state['os_name']}")
    known_str = ""
    if known_parts:
        known_str = " Folgende Informationen liegen uns bereits vor: " + ", ".join(known_parts) + "."

    ticket_intro = t(
        "Ich habe gerade ein Support-Ticket erstellt. Für eine optimale Bearbeitung bitte die folgenden Fragen beantworten:",
        state.get("language", "de"),
    )
    llm_msg = f"{ticket_intro}\n{follow_up_question}"
    ticket_id = state.get("ticket_id")
    _append_agent_article_to_ticket(
        ticket_id,
        f"[ZIM AI-AGENT]\n\n{llm_msg}",
        "ask_for_additional_info",
    )
    return {
        **visit("ask_for_additional_info"),
        "needs_additional_info": True,
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

    issue = (state.get("issue_description") or "").strip()
    additional = " ".join(state.get("additional_info", [])) if state.get("additional_info") else ""

    query = f"{issue} + {additional}"

    if not issue:
        return {
             **visit("give_solutions_node"),
             "messages": [AIMessage(content=t("Keine ausreichende Anfrage für die Suche.", state.get("language", "de")))], "solutions": []
             }

    try:
        rag_logger.info(f"Sending RAG query '{query}'")
        results = retrieve_relevant_entries(query, n_results=2)

        rag_logger.info("The RAG query returned following results:")
        rag_logger.info(f"faq={len(results.get('faq_matches', []))}")
        rag_logger.info(f"tickets={len(results.get('ticket_matches', []))} ")
        rag_logger.info(f"inferred={results.get('inferred')}")

    except Exception:
        rag_logger.exception(f"RAG retrieval failed for ticket {state.get('ticket_id')}")
        return {
             **visit("give_solutions_node"),
             "messages": [AIMessage(content=t("Fehler bei der Suche in der Wissensdatenbank.", state.get("language", "de")))],
             "solutions": []}

    faq_matches = results.get("faq_matches", [])
    ticket_matches = results.get("ticket_matches", [])

    # Build up to 2 solutions (FAQ first)
    solutions = []
    for m in faq_matches[:2]:
        solutions.append({"title": f"FAQ: {m['id']}", "description": _format_faq_match_for_prompt(m)})
    for ticket_match in ticket_matches:
        solutions.append(
            {"title": f"Ähnliches Ticket ({ticket_match.get('category', 'unknown')})", "description": ticket_match.get("text", "")})
    # Writing a truncated version of the solutions into the logs in the console
    # while the actual solutions are kept intact
    truncated_solutions_for_logs = [truncate_long_strings_in_dicts_for_logging(solution) for solution in solutions]
    langgraph_logger.info(f"give_solutions node returned: {truncated_solutions_for_logs}")

    problem = state.get("issue_description", "")
    infos = state.get("additional_info", [])

    tutorial_handover = ""
    if state.get("tutorial_attempts", 0) > 3:
        tutorial_handover = (
            "\nWICHTIG: Die Anleitung wurde bereits mehrfach ausgegeben, das Problem "
            "besteht weiterhin. Weise zu Beginn der Antwort kurz darauf hin, dass die "
            "Anleitung offenbar nicht geholfen hat und nun konkrete Loesungen "
            "vorgeschlagen bzw. das Anliegen an den Support uebergeben wird. "
            "Formuliere durchgehend neutral, ohne direkte Anrede (weder 'du' noch 'Sie')."
        )

    metadata_context = _build_metadata_context(state)

    system_prompt = SystemMessage(content=(
        AGENT_PROMPT + "\n\n" + tutorial_handover + "\n\n" + metadata_context + "\n\n" +
        f"""
            Deine Aufgabe ist es, basierend auf dem aktuellen Problem und den bereits bekannten Zusatzinfos eine konkrete, direkt umsetzbare Lösung zu geben.

        AKTUELLES PROBLEM: {problem}
        BEREITS BEKANNTE ZUSATZINFOS: {infos}
        LÖSUNGEN (RAG-Kontext): {solutions}

        REGELN:
        1. Nutze zur Strukturierung AUSSCHLIESSLICH die HTML-Tags `<details>` und `<summary>` für aufklappbare Bereiche. 
            - Jeder Lösungsansatz MUSS in einem `<details>`-Tag stehen. 
            - Die Überschrift kommt in ein `<summary>`-Tag (fettgedruckt mit <b>). 
            - GANZ WICHTIG: Nach dem schließenden `</summary>`-Tag MUSS zwingend eine leere Zeile (Zeilenumbruch) folgen!
            - Darunter erstellst du eine NUMMERIERTE Schritt-fuer-Schritt-Anleitung (1., 2., 3., ...) basierend auf dem RAG-Kontext.
            Beispiel-Format:
            <details>
            <summary><b>Ansatz 1: eduroam-Profil löschen</b></summary>
   
            1. Öffne das Self-Care-Portal und melde dich an.
            2. Wähle danach "Authentifizierungsserver testen".
            3. Falls ein Fehler erscheint, sende einen Screenshot an den support.
            </details>
        2. Formuliere die Lösung als konkrete Handlungsanweisung – nicht 
           "es gibt folgende Lösungsansätze", sondern konkret, was zu tun ist, z. B. "X deaktivieren, dann..." 
           bzw. "Das Problem liegt an Y, daher sollte Z erfolgen".
        3. Wenn mehrere Lösungen im Kontext vorhanden sind, wähle die passendsten Lösungen. Die Lösungen darfst du nicht vermischen. Behandle sie separat in eigenen aufklappbaren Blöcken.
        4. Gib die Lösungen nie wörtlich aus dem Kontext wieder. Interpretiere sie und setze sie in Bezug zum konkreten Problem des Nutzers.
        5. Maximal 6 Sätze pro Lösung, auf die du eingehst. Bei mehrschrittigen technischen Anleitungen darf die Satzzahl überschritten werden, wenn sonst notwendige Schritte fehlen würden – Vollständigkeit (Regel 6) hat Vorrang vor Kürze. Keine Begrüßungsfloskeln, keine Zusammenfassung am Ende, keine Abschlussfrage wie 'Konnte ich helfen?'.
        6. Die Lösung muss aus sich selbst heraus vollständig verständlich sein. Der Nutzer soll keinen Link öffnen müssen, um zu verstehen, was ihn dort erwartet. Nenne alle relevanten Schritte/Infos direkt im Text, fasse dabei den Linkinhalt kurz zusammen statt ihn vollständig wiederzugeben.
        Füge Links an der Stelle im Text ein, zu der sie inhaltlich gehören.
        - Liegt zu einem Link Content vor: bau den Inhalt des Kontexts in der Lösung ein, sofern dieser relevant für das "AKTUELLE PROBLEM" ist.
        - Liegt kein Content vor (nur eine Notiz zum Fehlschlag): beschreibe nur, was sich sicher aus problem/solution ableiten lässt, erfinde keine Details, und mache transparent, dass der Inhalt nicht automatisch abrufbar war.
        - Ist der Link selbst der auszuführende Schritt (Formular, Login, Download, Zahlung), bleibt er Pflichtklick – erkläre vorher, was dort zu tun ist.
        7. Halluziniere dir keine Lösungen herbei, sondern gebe nah am Kontext die Lösung wieder!
        8. Enthält eine Lösung irreversible oder folgenreiche Schritte (z. B. Konto löschen, Daten zurücksetzen, Zahlung auslösen), weise im Text kurz und klar darauf hin, bevor du den Schritt nennst.
        """
    ))
    message_text = llm.invoke([system_prompt])


    final_message = AIMessage(content=message_text.content + t("\n\n Konnte das Problem damit gelöst werden?", state.get("language", "de")))

    ticket_id = state.get("ticket_id")
    langgraph_logger.info(f"appending bot message to ticket {ticket_id}")
    _append_agent_article_to_ticket(
        ticket_id,
        f"[ZIM AI-AGENT]\n\n{final_message.content}",
        "give_solutions",
    )

    return {
        **visit("give_solutions_node"),
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
def finish_ai_created_ticket(state):
    """
    Finalizes the ticket creation process by generating a concise title
    and preparing the payload for the Zammad API.
    """
    log_node_entry("finish_ai_created_ticket", state)
    # If the issue was asked three times, and no problem could be extracted,
    # say instead that the off-topic issue cannot be processed by support
    attempts = state.get("ask_issue_attempts", 0)
    if attempts >= 3:
        final_message = t(
            "Das Anliegen kann leider nicht weiter als ZIM-IT-Support bearbeitet werden, "
            "da keine eindeutige IT-/ZIM-bezogene Problemstellung erkannt wurde.\n\n"
            "Bei einem späteren IT-Problem rund um Dienste der Universität "
            "(z. B. WLAN, VPN, E-Mail, Moodle oder Account-Probleme) hilft der ZIM-IT-Support gerne weiter.",
            state.get("language", "de"),
        )
        return {
            **visit("finish_ai_created_ticket_node"),
            "messages": [AIMessage(content=final_message)],
            "is_complete": True
        }

    category = _resolve_ticket_category(state)
    # Append the bot's confirmation reply as an Agent article to the new ticket.
    ticket_id = state.get("ticket_id")
    if ticket_id:
        state_for_update = {**state, "category": category}
        try:
            ticket_service.finalize_ticket_metadata(state_for_update, ticket_id)
        except Exception as e:
            langgraph_logger.error(f"Konnte Metadaten für Ticket {ticket_id} nicht setzen: {e}")
    try:
        bot_message_content = state["messages"][-1].content
    except Exception:
        langgraph_logger.exception(
            f"Could not read bot message to append to ticket {ticket_id}"
        )
    else:
        langgraph_logger.info(f"appending bot message to ticket {ticket_id}")
        _append_agent_article_to_ticket(
            ticket_id,
            f"[ZIM AI-AGENT]\n\n{bot_message_content}",
            "finish_ai_created_ticket",
        )

    return {
        **visit("finish_ai_created_ticket_node"),
        "category": category
        }

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
    return {
        **result,
        "category": category
        }


@traceable
def email_retrieve_solutions(state: ChatbotState):
    """
    Sucht RAG-Lösungen basierend auf der E-Mail (die als combined_message im State liegt)
    und generiert eine E-Mail-freundliche Antwort für den Nutzer.
    """
    log_node_entry("email_retrieve_solutions", state)

    # Im E-Mail-Channel speichern wir den E-Mail-Text initial in den messages.
    # Alternativ greifst du hier auf state.get("issue_description") zu,
    # falls du vorher einen Extraktions-Node laufen lässt.
    issue = state.get("issue_description", "").strip()
    if not issue and state.get("messages"):
        issue = state["messages"][0].content.strip()

    query = issue

    if not issue:
        return {
            **visit("email_retrieve_solutions_node"),
            "messages": [AIMessage(content="Leider konnte aus der E-Mail kein konkretes Problem extrahiert werden.")],
            "solutions": []
        }

    try:
        rag_logger.info(f"[EMAIL] Sending RAG query '{query}'")
        results = retrieve_relevant_entries(query, n_results=2)
    except Exception:
        rag_logger.exception(f"[EMAIL] RAG retrieval failed for incoming email.")
        return {
            **visit("email_retrieve_solutions_node"),
            "messages": [AIMessage(
                content="Es gab ein internes Problem bei der Suche nach Lösungen in unserer Wissensdatenbank. Ein Support-Mitarbeiter wird sich in Kürze melden.")],
            "solutions": []
        }

    faq_matches = results.get("faq_matches", [])
    ticket_matches = results.get("ticket_matches", [])

    solutions = []
    for m in faq_matches[:2]:
        solutions.append({"title": f"FAQ: {m['id']}", "description": _format_faq_match_for_prompt(m)})
    for ticket_match in ticket_matches:
        solutions.append(
            {"title": f"Ähnliches Ticket ({ticket_match.get('category', 'unknown')})",
             "description": ticket_match.get("text", "")})

    truncated_solutions_for_logs = [truncate_long_strings_in_dicts_for_logging(solution) for solution in solutions]
    langgraph_logger.info(f"[EMAIL] email_retrieve_solutions node returned: {truncated_solutions_for_logs}")

    # LLM Prompt für die Formulierung der Antwort (angepasst für E-Mail)
    system_prompt = SystemMessage(content=(
            AGENT_PROMPT + "\n\n" +
            f"""
        Deine Aufgabe ist es, basierend auf dem aktuellen E-Mail-Text eine konkrete, direkt umsetzbare Lösung zu formulieren, die dem Nutzer per E-Mail zugesendet wird.

        AKTUELLES PROBLEM: {issue}
        LÖSUNGEN (RAG-Kontext): {solutions}

        REGELN:
        1. Formuliere eine professionelle, hilfsbereite E-Mail-Antwort.
        2. VERWENDE KEIN HTML. Nutze stattdessen saubere Absätze, Bindestriche für Listen und Großbuchstaben zur Hervorhebung, falls nötig. Die E-Mail muss in reinem Text gut lesbar sein.
        3. Formuliere die Lösung als konkrete Handlungsanweisung.
        4. Wenn mehrere Lösungen vorhanden sind, behandle sie in separaten Absätzen mit einer klaren Überschrift (z.B. "--- Lösungsansatz 1 ---").
        5. Keine Begrüßungsfloskeln am Anfang generieren, diese fügt das Ticket-System automatisch hinzu.
        6. Beende die Nachricht mit einem Hinweis, dass das Ticket erstellt wurde und der Nutzer einfach auf diese E-Mail antworten kann, falls die Schritte nicht helfen.
        7. Erfinde keine Schritte, bleibe beim RAG-Kontext.
        """
    ))

    # LLM Aufruf (passe dies an deinen spezifischen LLM-Aufruf an)
    message_text = llm.invoke([system_prompt])
    final_message = AIMessage(content=message_text.content)

    return {
        **visit("email_retrieve_solutions_node"),
        "messages": [final_message],
        "solutions": solutions
    }