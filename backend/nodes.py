import os
from typing import Optional, cast
from pydantic import BaseModel, Field
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from state import ChatbotState
from zammad_endpoints import create_ticket_by_user_email

ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# temperature 0.2 for less hallucination
llm = ChatOllama(
    model="llama3.2",
    temperature=0.2,
    base_url=ollama_url
)


class ExtractedTicketData(BaseModel):
    """
    Schema defining the structured ticket data to be extracted from user messages
    """
    email: Optional[str] = Field(None, description="Die E-Mail-Adresse des Users. Nur ausfüllen, wenn sie ein @-Zeichen enthält.")
    matrikelnummer: Optional[str] = Field(None,
                                          description="Die 7-stellige Matrikelnummer des Studenten, falls genannt.")
    problem: Optional[str] = Field(None, description="Das IT-Problem (z.B. 'WLAN geht nicht', 'Passwort vergessen', 'Moodle lädt nicht'). Auch kurze, umgangssprachliche Sätze zählen!")


# Forces the LLM to return data strictly matching the ExtractedTicketData schema in JSON format
structured_llm = llm.with_structured_output(ExtractedTicketData)


def extract_information(state: ChatbotState):
    """
    Analyzes the latest user message to extract structured ticket details.
    :param state: The current state of the chatbot conversation.
    :return: A dictionary containing the newly extracted fields to update the state.
    """
    last_user_message = [msg for msg in state["messages"] if isinstance(msg, HumanMessage)][-1]

    system_prompt = (
        "Du bist ein präziser Daten-Extraktor. Lies den Text des Users. "
        "Finde die email, die Matrikelnummer und das IT-Problem. "
        "Beispiele für ein Problem: 'Ich habe kein Internet', 'Mein Account ist gesperrt', 'WLAN kaputt'. "
        "WICHTIG: Wenn eine Information fehlt, setze das Feld zwingend auf null. Erfinde absolut nichts dazu!"
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

    return state_update



def ask_for_email(state: ChatbotState):
    """
    Queries Llama 3.2 to politely ask the user for their missing email
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
    Queries Llama 3.2 to politely ask the user for their missing matrikelnummer
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
    Queries Llama 3.2 to politely ask the user for the missing problem description
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
        f"{state['issue_description']}"
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