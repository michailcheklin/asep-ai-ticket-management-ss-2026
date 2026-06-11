import os
from typing import Optional, cast, List
from pydantic import BaseModel, Field, SecretStr
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from state import ChatbotState
from zammad_endpoints import create_ticket_by_user_email


USE_SAIA = os.getenv("USE_SAIA_API", "false").lower() == "true"
# temperature 0.2 for less hallucination
# Toggles between the SAIA API model (70B) and local Ollama (3B).
# Defaults to 'false' to avoid useing up the monthly SAIA limit (3000 requests)
# during standard code development and pipeline testing
if USE_SAIA:
    raw_key =os.getenv("SAIA_API_KEY", "")
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
        model="llama3.2",
        temperature=0.2,
        base_url=ollama_url
    )


class ExtractedTicketData(BaseModel):
    """
    Schema defining the structured ticket data to be extracted from user messages
    """
    email: Optional[str] = Field(None,
                                 description="Die E-Mail-Adresse des Users. Nur ausfüllen, wenn sie ein @-Zeichen enthält.")
    matrikelnummer: Optional[str] = Field(None,
                                          description="Die 7-stellige Matrikelnummer des Studenten, falls genannt.")
    problem: Optional[str] = Field(None,
                                   description="Das IT-Problem (z.B. 'WLAN geht nicht', 'Passwort vergessen', 'Moodle lädt nicht'). Auch kurze, umgangssprachliche Sätze zählen!")
    additional_info: Optional[List[str]] = Field(default_factory=list,
                                                 description="Eine Liste von spezifischen Zusatzinformationen, die für den IT-Support an einer Universität relevant sind (z.B. Gebäude, Raumnummer, Fehlermeldung, Gerätetyp, OS). Keine Füllwörter."
    )

class AdditionalInfoDecision(BaseModel):
    """Schema decision, if additional info is needed for effective problem treatment"""
    is_complete: bool = Field(
        description="True, wenn die Zusatzinfos ausreichen, um das Problem zu bearbeiten. False, wenn wichtige Details fehlen (z.B. bei 'WLAN kaputt' fehlt das Gebäude)."
    )
    follow_up_question: Optional[str] = Field(
        description="Wenn is_complete False ist: Eine kurze, höfliche Frage an den User, um die fehlenden Details herauszufinden. Wenn is_complete True ist, lasse dieses Feld leer (null)."
    )


# Forces the LLM to return data strictly matching the ExtractedTicketData schema in JSON format
structured_llm = llm.with_structured_output(ExtractedTicketData)


def extract_information(state: ChatbotState):
    """
    Analyzes the latest user message to extract structured ticket details.
    :param state: The current state of the chatbot conversation.
    :return: A dictionary containing the newly extracted fields to update the state.
    """
    last_user_message = [msg for msg in state["messages"] if isinstance(msg, HumanMessage)][-1]

    system_prompt = ("""Du bist ein hochpräziser KI-Daten-Extraktor für ein IT-Support-Unternehmen, das exklusiv mit Universitäten zusammenarbeitet.
    Deine Aufgabe ist es, aus den eingehenden Chat-Nachrichten von Studierenden und Mitarbeitern strukturierte Ticket-Daten zu extrahieren.
    EXTRAKTIONS-REGELN:
    1. Basis-Daten (Textfelder): Suche nach der 'email', der 'matrikelnummer' und dem Haupt-'problem' und speichere diese ausschließlich in ihren jeweiligen Textfeldern.
    2. Zusatzinformationen (Listen-Feld): Extrahiere alle weiteren technischen oder lokalen Details, die für die Lösung des Problems nützlich sein könnten, und weise sie dem Feld 'additional_info' zu.
    - Beispiele für wertvolle Details: Orte (z.B. 'Gebäude LF', 'Bibliothek'), Geräte/Systeme (z.B. 'MacBook', 'Windows 11'), betroffene Services (z.B. 'eduroam', 'VPN') oder spezifische Fehlercodes.
    - FORMAT: Speichere diese Zusatzinfos als einzelne, kompakte Strings innerhalb der Liste (z.B. ["Gebäude LF", "MacBook", "eduroam"]).
    3. Strikte Wahrheit: Wenn eine Information fehlt, setze das entsprechende Feld zwingend auf null (bzw. lasse die Liste leer). Erfinde unter keinen Umständen Daten dazu!"""
    )

    # Telling python to treat output from structured llm as ExtractedTicketData instance
    extracted_data = cast(ExtractedTicketData, structured_llm.invoke([
        SystemMessage(content=system_prompt),
        last_user_message
    ]))

    state_update = {}

    if extracted_data.email:
        state_update["user_email"] = extracted_data.email
    if extracted_data.matrikelnummer:
        state_update["matrikelnummer"] = extracted_data.matrikelnummer
    if extracted_data.problem:
        state_update["issue_description"] = extracted_data.problem
    if extracted_data.additional_info:
        state_update["additional_info"] = extracted_data.additional_info

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
    system_prompt = SystemMessage(content=(
        "Du bist ein IT-Support-Bot. Dir fehlt noch eine genaue Beschreibung des IT-Problems. "
        "Frage den User kurz und höflich, womit du ihm heute helfen kannst."
    ))

    full_messages = [system_prompt] + state["messages"]
    response = llm.invoke(full_messages)

    return {"messages": [response]}

def ask_for_additional_info(state: ChatbotState):
    """
    Queries Llama to politely ask the user for the missing additional info, if needed
    :param state: The current conversation and ticket state
    :return: A dictionary containing the newly extracted fields to update the state.
    """

    problem = state.get("issue_description", "")
    infos = state.get("additional_info", [])

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
        2. Wenn alles Wichtige da ist, setze is_complete auf True.
        3. Wenn wichtige Details fehlen, setze is_complete auf False und formuliere 
           eine kurze, freundliche follow_up_question an den User.
        """
    ))

    decision = cast(AdditionalInfoDecision, aditionalInfo_llm.invoke([system_prompt]))

    # Logic switch if all information needed is collected or not
    if decision.is_complete:
        return {"is_complete": True}
    else:
        return {
            "is_complete": False,
            "messages": [AIMessage(content=decision.follow_up_question)]
        }


def finish_ticket(state: ChatbotState):
    """
    Finalizes the ticket creation process by generating a concise title
    and preparing the payload for the Zammad API.
    """
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
        f"Problembeschreibung des Nutzers:\n"
        f"{state['issue_description']}\n\n"
        f"Zusätzliche Infos (automatisch extrahiert durch den Chatbot):\n"
        f"{state['additional_info']}"
    )

    try:
        create_ticket_by_user_email(
            email=state["user_email"],
            title=zammad_title,
            body=zammad_body
        )
        final_message = (f"Perfekt! Dein Ticket wurde erfolgreich erstellt. Ein Supporter meldet sich bald bei dir.\n"
        f"**Deine Ticket-Übersicht:**\n"
        f"**Betreff:** {zammad_title}\n"
        f"**Inhalt:** {zammad_body}")
    except Exception as e:
        print(f"🚨 [FEHLER] Zammad API-Aufruf fehlgeschlagen: {e}")
        final_message = "Dein Ticket ist fertiggestellt, aber es gab ein Problem bei der Übermittlung an Zammad. Bitte versuche es später noch einmal."

    return {
        "messages": [AIMessage(content=final_message)],
        "is_complete": True
    }