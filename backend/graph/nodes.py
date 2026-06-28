from typing import cast
from pydantic import BaseModel, Field

from langsmith import traceable

from .models.ExtractedTicketData import ExtractedTicketData
from .models.AdditionalInfoDecision import AdditionalInfoDecision
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from .state import ChatbotState
from backend.rag.retrieve_info import retrieve_relevant_entries
from ..services.TicketService import TicketService
from ..llm.llm import llm, structured_llm
from .node_logging import log_node_entry
from ..api.zammad import create_ticket_by_user_email, add_tag_to_ticket

ticket_service = TicketService()

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
    prompt = f"""Du bist ein Klassifizierer für IT-Support-Tickets an einer Universität.
Ordne das Ticket nach ITSM-Ticket-Typ genau einem der folgenden Typen zu:
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

    system_prompt = ("""Du bist ein hochpräziser KI-Daten-Extraktor für ein IT-Support-Unternehmen, das exklusiv mit Universitäten zusammenarbeitet.
        Deine Aufgabe ist es, aus den eingehenden Chat-Nachrichten von Studierenden und Mitarbeitern strukturierte Ticket-Daten zu extrahieren.

        BEREITS BEKANNTER KONTEXT:
        Problembeschreibung: {prior_issue}
        Zusatzinfos: {prior_infos}
        Chatverlauf (User-Nachrichten):
        {conversation_context}

        EXTRAKTIONS-REGELN:
        1. Basis-Daten (Textfelder): Suche nach der 'email', der 'matrikelnummer' und dem Haupt-'problem' und speichere diese ausschließlich in ihren jeweiligen Textfeldern.
        2. Das 'problem' darf ausschließlich gesetzt werden, wenn der Nutzer tatsächlich ein konkretes IT-Problem oder eine Supportanfrage beschreibt. Erfinde niemals ein Problem.
        2. Zusatzinformationen (Listen-Feld): Extrahiere alle weiteren technischen oder lokalen Details, die für die Lösung des Problems nützlich sein könnten, und weise sie dem Feld 'additional_info' zu.
        - Beispiele für wertvolle Details: Orte (z.B. 'Gebäude LF', 'Bibliothek'), Geräte/Systeme (z.B. 'MacBook', 'Windows 11'), betroffene Services (z.B. 'eduroam', 'VPN') oder spezifische Fehlercodes.
        - FORMAT: Speichere diese Zusatzinfos als einzelne, kompakte Strings innerhalb der Liste (z.B. ["Gebäude LF", "MacBook", "eduroam"]).
        3. Strikte Wahrheit: Wenn eine Information fehlt, setze das entsprechende Feld zwingend auf null (bzw. lasse die Liste leer). Erfinde unter keinen Umständen Daten dazu!
    	Bewerte zusätzlich die Priorität des Problems.
        Setze priority auf 1 bei dringenden Problemen wie gesperrtem Account,
        Login nicht möglich, Prüfungs-/Abgabeproblemen oder komplettem Ausfall.
        Setze priority auf 0 bei normalen oder weniger dringenden Problemen.
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
        "Du bist ein IT-Support-Bot. Dir fehlt noch die email des Users. "
        "Frage kurz und höflich nach der Uni email Adresse. Beantworte keine anderen Fragen "
        "und wechsle nicht das Thema."
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
        "Du bist ein IT-Support-Bot. Dir fehlt noch die 7-stellige Matrikelnummer des Users. "
        "Frage kurz und höflich nach der Matrikelnummer. Beantworte keine anderen Fragen."
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
        "Du bist ein IT-Support-Bot des Zentrums für Information und Medientechnik (ZIM) an einer Universität. "
        "Du unterstützt ausschließlich bei Problemen mit universitären IT-Diensten "
        "(z. B. WLAN, VPN, E-Mail, Moodle, Benutzerkonto, Drucker oder bereitgestellter Software). "

        "Falls der Nutzer ein anderes Anliegen beschreibt, das nichts mit den "
        "IT-Diensten des ZIM zu tun hat, gebe keine fachliche Beratung dazu."
        
        "Weise stattdessen freundlich darauf hin, "
        "dass du nur bei ZIM-bezogenen IT-Anliegen helfen kannst, und bitte den "
        "Nutzer, sein entsprechendes IT-Problem zu schildern."
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
    problem = state.get("issue_description", "")
    infos = state.get("additional_info", [])
    attempts = state.get("additional_info_attempts", 0)

    print(f"[DEBUG: ask_for_additional_info]: attempts: {attempts} ")

    aditionalInfo_llm = llm.with_structured_output(AdditionalInfoDecision, method="json_mode")


    search_query = problem
    rag_results = retrieve_relevant_entries(search_query, n_results=2)

    faq_matches = rag_results.get("faq_matches", [])
    ticket_matches = rag_results.get("ticket_matches", [])

    if not faq_matches and not ticket_matches:
        print("[DEBUG] RAG lieferte keine Ergebnisse. Überspringe Rückfrage.")
        return {"needs_additional_info": True}

    faq_context = "\n".join([f"- {match['text']}" for match in faq_matches])
    ticket_context = "\n".join([f"- {match['text']} (Kategorie: {match['category']})" for match in ticket_matches])


    system_prompt = SystemMessage(content=(
        f"""
        Du bist ein technischer Dispatcher im IT-Support einer Universität.
        Dein Ziel ist es zu prüfen, ob die vorliegenden Informationen für das genannte Problem ausreichen, 
        um ein vollständiges Ticket zu erstellen.

        AKTUELLES PROBLEM: {problem}
        BEREITS BEKANNTE ZUSATZINFOS: {infos}

        WISSENSDATENBANK (Historische Tickets & FAQs für dieses Problem):
        FAQs:
        {faq_context}

        Alte Tickets:
        {ticket_context}

        REGELN:
        1. Lies die Einträge in der WISSENSDATENBANK. Fehlen in unserem "AKTUELLEN PROBLEM" Details, 
           die in den alten Tickets oder FAQs zur Lösung zwingend notwendig waren?
        2. Wenn alles Wichtige da ist, ODER wenn die WISSENSDATENBANK keine relevanten Inhalte für eine Nachfrage liefert, 
           setze needs_additional_info auf True und setze follow_up_question auf den leeren String. 
        3. Wenn wichtige Details fehlen, setze needs_additional_info auf False und formuliere 
           wenige, direkt-relevante, kurze, follow-up-question(s) an den User basierend auf dem RAG-Kontext.
        4. Gib die Fragen als Bullet-Liste zurück. Es muss dieses genaues Syntax befolgen:
           Multiple-Choice-Fragen müssen das Format verwenden:
           "* [Frage]? (options: [A], [B], [C])"
           Offene Fragen dürfen ohne Optionen geschrieben werden:
           "* [Frage]?"
        5. Stelle die Fragen soweit wie möglich immer als Multiple-Choice mit dem gezeigten Format, wo du nur die Felder in [] ändern darsf.
        6. Deine Nachricht MUSS IMMER mit "Um Ihnen weiter helfen zu können, beantworten Sie bitte folgende Fragen" beginnen. (dieser Satz ist kein Teil der Liste)
        7. Begrenze dich auf maximal 5 Optionen, wobei "Andere" immer eine Option sein muss.
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
    if len(infos) >= 1 or decision.needs_additional_info or attempts >= 3:
        return {"needs_additional_info": True}
    else:
        llm_msg = decision.follow_up_question
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

    query = issue

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
        solutions.append({"title": f"FAQ: {m.get('id')}", "description": m.get("text", "")})
    if len(solutions) < 2:
        for t in ticket_matches[: 2 - len(solutions)]:
            solutions.append(
                {"title": f"Ähnliches Ticket ({t.get('category', 'unknown')})", "description": t.get("text", "")})

    problem = state.get("issue_description", "")
    infos = state.get("additional_info", [])

    system_prompt = SystemMessage(content=(
        f"""
            Du bist ein technischer Dispatcher im IT-Support einer Universität.
            Deine Aufgabe ist es, basierend auf dem aktuellen Problem und den bereits bekannten Zusatzinfos
            Lösungen wiederzugeben.

            AKTUELLES PROBLEM: {problem}
            BEREITS BEKANNTE ZUSATZINFOS: {infos}
            LÖSUNGEN: {solutions}

            REGELN:
            1. Gebe die Regeln nicht wörtlich aus, sondern formuliere sie in eine verständliche Antwort um, die die Lösungen in einen Kontext zum Problem setzt.
            2. Wenn Lösungen vorhanden sind, fasse sie kurz zusammen und erkläre, wie sie dem User helfen können.
            3. Vermeide es, die Lösungen einfach nur zu wiederholen, sondern biete eine Interpretation oder Empfehlung an.
            4. Versuche dich am besten auf maximal 3 Sätze zu beschränken.
            """
    ))
    message_text = llm.invoke([system_prompt, HumanMessage(content="Bitte fasse die Lösungen für den User zusammen.")])


    final_message = AIMessage(content=message_text.content + "\n\nKonnte ich Ihnen dabei helfen, Ihr Problem zu lösen?")

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