import os
from typing import Optional, cast, List
from pydantic import BaseModel, Field, SecretStr
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from backend.state import ChatbotState
from backend.zammad_endpoints import create_ticket_by_user_email, add_tag_to_ticket
from backend.rag.retrieve_info import retrieve_relevant_entries

USE_SAIA = os.getenv("USE_SAIA_API", "false").lower() == "true"
# temperature 0.2 for less hallucination
# Toggles between the SAIA API model (70B) and local Ollama (3B).
# Defaults to 'false' to avoid useing up the monthly SAIA limit (3000 requests)
# during standard code development and pipeline testing
if USE_SAIA:
    raw_key = os.getenv("SAIA_API_KEY", "")
    # LangChain requires API keys to be wrapped in a Pydantic 'SecretStr' type
    # This prevents the key from being exposed in plain text within logs
    # if the application crashes or the 'llm' object is accidentally printed to the terminal
    secure_saia_api_key = SecretStr(raw_key) if raw_key else None
    llm = ChatOpenAI(
        model="deepseek-r1-distill-llama-70b",
        api_key=secure_saia_api_key,
        base_url="https://chat-ai.academiccloud.de/v1",
        temperature=0.2
    )
else:
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    llm = ChatOllama(
        model="qwen3:8b",
        temperature=0.2,
        base_url=ollama_url
    )

TICKET_CATEGORIES = [
    "Zugang/Login",
    "Technisches Problem",
    "Allgemeine Anfrage",
    "Beschwerde",
    "Rechnung",
]


class ExtractedTicketData(BaseModel):
    """
    Schema defining the structured ticket data to be extracted from user messages
    """
    email: Optional[str] = Field(None,
                                 description="Die E-Mail-Adresse des Users. Nur ausfüllen, wenn sie ein @-Zeichen enthält.")
    matrikelnummer: Optional[str] = Field(None,
                                          description="Die 7-stellige Matrikelnummer des Studenten, falls genannt.")
    problem: Optional[str] = Field(None,
                                   description="Das vom Nutzer explizit beschriebene IT-Problem oder die Supportanfrage. "
                                                "Nur setzen, wenn tatsächlich ein konkretes Problem genannt wird. "
                                                "Bei Begrüßungen, einzelnen Buchstaben, Testnachrichten, Smalltalk, "
                                                "Dankesnachrichten oder unverständlichem Text muss der Wert null sein. "
                                                "Niemals ein Problem erfinden oder aus Vermutungen ableiten."
                                   )
    additional_info: Optional[List[str]] = Field(default_factory=list,
                                                 description="Eine Liste von spezifischen Zusatzinformationen, die für den IT-Support an einer Universität relevant sind (z.B. Gebäude, Raumnummer, Fehlermeldung, Gerätetyp, OS). Keine Füllwörter."
                                                 )
    priority: Optional[int] = Field(
        None,
        description=(
            "Priority of the ticket. Use 1 for urgent or important issues, "
            "for example locked account, no login possible, exam or deadline affected, "
            "complete outage. Use 0 for normal or non-urgent issues."
        )
    )


class AdditionalInfoDecision(BaseModel):
    """Schema decision, if additional info is needed for effective problem treatment"""
    needs_additional_info: bool = Field(
        description="True, wenn die Zusatzinfos ausreichen, um das Problem zu bearbeiten. False, wenn wichtige Details fehlen (z.B. bei 'WLAN kaputt' fehlt das Gebäude)."
    )
    follow_up_question: Optional[str] = Field(
        description="Wenn needs_additional_info False ist: Eine kurze, höfliche Frage an den User, um die fehlenden Details herauszufinden. Wenn needs_additional_info True ist, lasse dieses Feld leer (null)."
    )


# Forces the LLM to return data strictly matching the ExtractedTicketData schema in JSON format
structured_llm = llm.with_structured_output(ExtractedTicketData)


class TicketCategoryDecision(BaseModel):
    category: str = Field(
        description=f"Exactly one of: {', '.join(TICKET_CATEGORIES)}"
    )


category_llm = llm.with_structured_output(TicketCategoryDecision)

_CATEGORY_RULES = """
Klassifiziere nach Hauptabsicht des Nutzers, nicht nach einzelnen Schlüsselwörtern.

Kategorien:

1. Beschwerde:
Wähle diese Kategorie nur, wenn die Hauptabsicht des Nutzers eine Beschwerde über Support,
Bearbeitung, Wartezeit oder schlechte Kommunikation ist.
Ein technisches Problem allein ist keine Beschwerde.

2. Rechnung:
Wähle diese Kategorie, wenn das Hauptproblem Zahlung, Gebühren, Rechnung, Rückerstattung
oder Zahlungsstatus betrifft.
Auch technische Fehler in einem Zahlungsportal bleiben Rechnung, wenn die Zahlung das
eigentliche Ziel ist.

3. Zugang/Login:
Wähle diese Kategorie, wenn der Nutzer keinen Zugang zu einem Konto oder Uni-System bekommt.
Dazu gehören Login-Probleme, Passwort, 2FA, gesperrte Accounts, falsche Zugangsdaten oder
Authentifizierung — auch ohne explizite Nennung von Systemnamen.

4. Technisches Problem:
Wähle diese Kategorie, wenn ein System, Gerät, Netzwerk oder eine Software technisch nicht
funktioniert, aber der Schwerpunkt nicht auf Login, Zahlung oder Beschwerde liegt.

5. Allgemeine Anfrage:
Wähle diese Kategorie, wenn der Nutzer nur Informationen möchte oder noch kein konkretes
Problem beschreibt.

Bei Überschneidungen gilt:
Beschwerde > Rechnung > Zugang/Login > Technisches Problem > Allgemeine Anfrage.

Bewerte die Kategorie immer anhand des GESAMTEN Chatverlaufs und aller bekannten Infos.
Gib genau eine Kategorie zurück.
"""


def classify_ticket_category(
    issue_description: str,
    additional_info: list[str],
    user_messages: list[str],
) -> str:
    """Classify a ticket using the full conversation context, not just the last message."""
    conversation = "\n".join(f"- {msg}" for msg in user_messages) if user_messages else "(keine)"
    infos = ", ".join(additional_info) if additional_info else "(keine)"
    prompt = f"""Du bist ein Kategorisierer für IT-Support-Tickets an einer Universität.
Ordne das Ticket nach der Hauptabsicht des Nutzers genau einer Kategorie zu:
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
    return "Allgemeine Anfrage"


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


def classify_ticket(state: ChatbotState):
    """Workflow node: assign ticket category once enough context is available."""
    user_messages = [msg.content for msg in state["messages"] if isinstance(msg, HumanMessage)]
    category = classify_ticket_category(
        state.get("issue_description", ""),
        list(state.get("additional_info", [])),
        user_messages,
    )
    return {"category": category}


def extract_information(state: ChatbotState):
    """
    Analyzes the latest user message to extract structured ticket details.
    :param state: The current state of the chatbot conversation.
    :return: A dictionary containing the newly extracted fields to update the state.
    """
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

    if extracted_data.email:
        state_update["user_email"] = extracted_data.email
    if extracted_data.matrikelnummer:
        state_update["matrikelnummer"] = extracted_data.matrikelnummer
    if extracted_data.problem:
        state_update["issue_description"] = extracted_data.problem
    if extracted_data.additional_info:
        state_update["additional_info"] = extracted_data.additional_info
    if extracted_data.priority is not None:
        state_update["priority"] = extracted_data.priority

    return state_update


def ask_for_email(state: ChatbotState):
    """
    Queries Llama to politely ask the user for their missing email
    :param state: The current conversation and ticket state
    :return: A dictionary containing the newly extracted fields to update the state.
    """
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
    attempts = state.get("ask_issue_attempts",0) + 1
    system_prompt = SystemMessage(content=(
        "Du bist ein IT-Support-Bot des ZIM einer Universität. "
        "Du unterstützt ausschließlich bei Problemen mit universitären IT-Diensten "
        "(z. B. WLAN, VPN, E-Mail, Moodle, Benutzerkonto, Drucker oder bereitgestellter Software). "

        "Falls der Nutzer ein anderes Anliegen beschreibt, das nichts mit den "
        "IT-Diensten des ZIM zu tun hat, gehe nicht auf dieses Thema ein und gib "
        "keine fachliche Beratung dazu. Weise stattdessen freundlich darauf hin, "
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
    if len(infos) >= 3 or decision.needs_additional_info or attempts >=3:
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
    query = "How to connect to the VPN using Forcepoint?" #" ".join(p for p in query_parts if p).strip()

    if not query:
        return {"messages": [AIMessage(content="Keine ausreichende Anfrage für die Suche.")], "solutions": []}

    try:
        print(f"[RAG QUERY] {query}")
        results = retrieve_relevant_entries(query, n_results=2)
        print(f"[RAG RESULT] faq={len(results.get('faq_matches',[]))} tickets={len(results.get('ticket_matches',[]))} inferred={results.get('inferred')}")
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
            solutions.append({"title": f"Ähnliches Ticket ({t.get('category','unknown')})", "description": t.get("text", "")})

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
        "messages": final_message, # hier stecken die Solutions als menschlicher, zusammenhägender Text drin
        "solutions": solutions,
        # "rag_debug": {
        #     "query": query,
        #     "faq_count": len(faq_matches),
        #     "ticket_count": len(ticket_matches),
        #     "inferred": inferred
        # }
    }


def finish_ticket(state: ChatbotState):
    """
    Finalizes the ticket creation process by generating a concise title
    and preparing the payload for the Zammad API.
    """
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

    title_prompt = (
        f"Du bist ein IT-Support-Assistent. Fasse das folgende Problem in maximal "
        f"4-5 Worten als Ticket-Betreff zusammen. Antworte NUR mit dem Betreff, ohne Anführungszeichen:\n"
        f"{state['issue_description']}"
    )
    title_response = llm.invoke([HumanMessage(content=title_prompt)])
    generated_title = title_response.content.strip()

    zammad_title = f"[{state['matrikelnummer']}] {generated_title}"
    zammad_body = (
        f"Matrikelnummer: {state['matrikelnummer']}\n"
        f"E-Mail: {state['user_email']}\n\n"
        f"Priorität: {'urgent' if state.get('priority') == 1 else 'normal'}\n"
        f"Kategorie: {category}\n"
        f"Problembeschreibung des Nutzers:\n"
        f"{state['issue_description']}\n\n"
        f"Zusätzliche Infos (automatisch extrahiert durch den Chatbot):\n"
        f"{state['additional_info']}"
    )

    try:
        create_ticket_by_user_email(
            email=state["user_email"],
            title=zammad_title,
            body=zammad_body,
            priority=state["priority"],
        )
        user_visible_body = (
            f"Matrikelnummer: {state['matrikelnummer']}\n"
            f"E-Mail: {state['user_email']}\n\n"
            f"Problembeschreibung des Nutzers:\n"
            f"{state['issue_description']}"
        )

        final_message = (
            f"Perfekt! Dein Ticket wurde erfolgreich erstellt. Ein Supporter meldet sich bald bei dir.\n"
            f"**Deine Ticket-Übersicht:**\n"
            f"**Betreff:** {zammad_title}\n"
            f"**Inhalt:** {user_visible_body}"
        )
    except Exception as e:
        print(f"🚨 [FEHLER] Zammad API-Aufruf fehlgeschlagen: {e}")
        final_message = "Dein Ticket ist fertiggestellt, aber es gab ein Problem bei der Übermittlung an Zammad. Bitte versuche es später noch einmal."

    print("[Finish Ticket Node]: Reached end of node without exception.")
    return {
        "messages": [AIMessage(content=final_message)],
        "is_complete": True,
        "category": category,
    }


def finish_ai_solved_ticket(state: ChatbotState):
    """
    Erstellt ein geschlossenes Ticket mit AISolved-Tag,
    wenn der User die Bot-Lösung akzeptiert hat.
    Kein Mitarbeiter wird involviert.
    """
    title_response = llm.invoke([HumanMessage(content=(
        f"Fasse das folgende Problem in maximal 4-5 Worten als Ticket-Betreff zusammen. "
        f"Antworte NUR mit dem Betreff, ohne Anführungszeichen:\n{state['issue_description']}"
    ))])
    generated_title = title_response.content.strip()
    zammad_title = f"[{state['matrikelnummer']}] {generated_title}"

    # Chatverlauf aufbereiten
    verlauf = ""
    for msg in state.get("messages", []):
        if isinstance(msg, HumanMessage):
            verlauf += f"Kunde: {msg.content}\n"
        elif isinstance(msg, AIMessage):
            verlauf += f"Bot: {msg.content}\n"

    # Angebotene Lösungen aufbereiten
    loesungen = ""
    for i, solution in enumerate(state.get("solutions", []), 1):
        loesungen += f"{i}. {solution.get('title', '')}\n{solution.get('description', '')}\n\n"

    zammad_body = (
        f"Matrikelnummer: {state['matrikelnummer']}\n"
        f"E-Mail: {state['user_email']}\n\n"
        f"Problembeschreibung: {state['issue_description']}\n"
        f"Zusatzinfos: {state['additional_info']}\n\n"
        f"--- Vom Bot angebotene Lösungen ---\n"
        f"{loesungen if loesungen else 'Keine Lösungen gespeichert.'}\n"
        f"--- Chatverlauf ---\n"
        f"{verlauf}\n"
        f"Status: Durch KI-Bot gelöst. Kein Mitarbeiter involviert."
    )

    try:
        ticket_id = create_ticket_by_user_email(
            email=state["user_email"],
            title=zammad_title,
            body=zammad_body,
            priority=state["priority"],
            state="closed"
        )
        if ticket_id:
            add_tag_to_ticket(ticket_id, "AISolved")
    except Exception as e:
        print(f"🚨 [FEHLER] AISolved-Ticket konnte nicht erstellt werden: {e}")

    return {
        "messages": [AIMessage(content=(
            "Super, das freut mich! Wenn du in Zukunft weitere Fragen hast, "
            "stehe ich gerne zur Verfügung. Hab einen schönen Tag!"
        ))],
        "is_complete": True
    }