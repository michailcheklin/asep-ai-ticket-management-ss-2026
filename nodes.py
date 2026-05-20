from typing import Optional, cast
from pydantic import BaseModel, Field
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from state import ChatbotState

# temperature 0.2 for less hallucination
llm = ChatOllama(model="llama3.2", temperature=0.2)


class ExtractedTicketData(BaseModel):
    """
    Schema defining the structured ticket data to be extracted from user messages
    """
    name: Optional[str] = Field(None, description="Der vollständige Vor- und Nachname des Users, falls genannt.")
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
        "Finde den Namen, die Matrikelnummer und das IT-Problem. "
        "Beispiele für ein Problem: 'Ich habe kein Internet', 'Mein Account ist gesperrt', 'WLAN kaputt'. "
        "WICHTIG: Wenn eine Information fehlt, setze das Feld zwingend auf null. Erfinde absolut nichts dazu!"
    )

    # Telling python to treat output from structured llm as ExtractedTicketData instance
    extracted_data = cast(ExtractedTicketData, structured_llm.invoke([
        SystemMessage(content=system_prompt),
        last_user_message
    ]))

    state_update = {}

    if extracted_data.name:
        state_update["customer_name"] = extracted_data.name
    if extracted_data.matrikelnummer:
        state_update["matrikelnummer"] = extracted_data.matrikelnummer
    if extracted_data.problem:
        state_update["issue_description"] = extracted_data.problem

    return state_update



def ask_for_name(state: ChatbotState):
    """
    Queries Llama 3.2 to politely ask the user for their missing name
    :param state: The current conversation and ticket state
    :return: A dictionary containing the newly extracted fields to update the state.
    """
    system_prompt = SystemMessage(content=(
        "Du bist ein IT-Support-Bot. Dir fehlt noch der Vor- und Nachname des Users. "
        "Frage kurz und höflich nach dem vollständigen Namen. Beantworte keine anderen Fragen "
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
    Called when all information is collected. Prints a final message for the user
    """

    final_message = SystemMessage(
        content="Vielen Dank! Ich habe alle Daten erfasst. Ihr Ticket wird nun in Zammad erstellt."
    )

    # Wir setzen is_complete auf True, was für das Frontend wichtig ist
    return {"messages": [final_message], "is_complete": True}