from typing import cast
from .models.ExtractedTicketData import ExtractedTicketData
from .models.AdditionalInfoDecision import AdditionalInfoDecision
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from .state import ChatbotState
from backend.rag.retrieve_info import retrieve_relevant_entries
from ..services.TicketService import TicketService
from ..llm.llm import llm, structured_llm
from .node_logging import log_node_entry

ticket_service = TicketService()


def extract_information(state: ChatbotState):
    """
    Analyzes the latest user message to extract structured ticket details.
    :param state: The current state of the chatbot conversation.
    :return: A dictionary containing the newly extracted fields to update the state.
    """
    log_node_entry("extract_information", state)
    last_user_message = [msg for msg in state["messages"] if isinstance(msg, HumanMessage)][-1]

    system_prompt = ("""Du bist ein hochpräziser KI-Daten-Extraktor für ein IT-Support-Unternehmen, das exklusiv mit Universitäten zusammenarbeitet.
        Deine Aufgabe ist es, aus den eingehenden Chat-Nachrichten von Studierenden und Mitarbeitern strukturierte Ticket-Daten zu extrahieren.
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
    	""")

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

    return state_update


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

    return {
        "messages": [response],
        "ask_issue_attempts": attempts
    }


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

    aditionalInfo_llm = llm.with_structured_output(AdditionalInfoDecision)
    system_prompt = SystemMessage(content=(
        f"""
        Du bist ein technischer Dispatcher im IT-Support einer Universität.
        Dein Ziel ist es zu prüfen, ob die vorliegenden Informationen für das genannte Problem ausreichen, 
        um ein vollständiges Ticket zu erstellen.

        AKTUELLES PROBLEM: {problem}
        BEREITS BEKANNTE ZUSATZINFOS: {infos}

        REGELN:
        1. Überlege, ob für dieses spezifische Problem essenzielle Details fehlen. 
           (Beispiele: Bei WLAN-Problemen braucht man den Ort/das Gebäude. Bei Software-Problemen das Betriebssystem).
        2. Wenn alles Wichtige da ist, setze needs_additional_info auf True.
        3. Halte dich bei deinen Rückfragen kurz und präzise.
        4. Gib keine direkten Lösungen wieder. Hier geht es nur um Rückfragen stellen, damit man später basierend auf den erhaltenen Informationen eine Lösung anbieten kann.
        5.. Wenn wichtige Details fehlen, setze needs_additional_info auf False und formuliere 
           eine kurze, freundliche follow_up_question an den User.
        """
    ))

    decision = cast(AdditionalInfoDecision, aditionalInfo_llm.invoke([system_prompt]))

    # Logic switch if all information needed is collected or not
    if len(infos) >= 3 or decision.needs_additional_info or attempts >= 3:
        return {"needs_additional_info": True}
    else:
        return {
            "needs_additional_info": False,
            "additional_info_attempts": attempts + 1,
            "messages": [AIMessage(content=decision.follow_up_question)]
        }


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

    # Build query in the requested order
    query_parts = [history_text, user_msg, issue, additional]
    query = "How to connect to the VPN using Forcepoint?"  # " ".join(p for p in query_parts if p).strip()

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
            LÖSÖUNGEN: {solutions}

            REGELN:
            1. Gebe die Regeln nicht wörtlich aus, sondern formuliere sie in eine verständliche Antwort um, die die Lösungen in einen Kontext zum Problem setzt.
            2. Wenn Lösungen vorhanden sind, fasse sie kurz zusammen und erkläre, wie sie dem User helfen können.
            3. Vermeide es, die Lösungen einfach nur zu wiederholen, sondern biete eine Interpretation oder Empfehlung an.
            4. Versuche dich am besten auf maximal 3 Sätze zu beschränken.
            """
    ))

    message_text = llm.invoke([system_prompt])
    final_message = AIMessage(content=message_text.content + "\n\nKonnte ich Ihnen dabei helfen, Ihr Problem zu lösen?")

    return {
        "messages": final_message,  # hier stecken die Solutions als menschlicher, zusammenhägender Text drin
        "solutions": solutions,
        # "rag_debug": {
        #     "query": query,
        #     "faq_count": len(faq_matches),
        #     "ticket_count": len(ticket_matches),
        #     "inferred": inferred
        # }
    }


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


    return ticket_service.create_support_ticket(state)


def finish_ai_solved_ticket(state):
    """
    Finalizes the ticket creation process by generating a concise title
    and preparing the payload for the Zammad API. Also marks the ticket with that that
    was solved only by using the chatbot without involving the ZIM staff
    """
    log_node_entry("finish_ai_solved_ticket", state)
    return ticket_service.create_ai_solved_ticket(state)