from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages


class ChatbotState(TypedDict):
    """
    Defines the structured data schema the Chatbot is working with
    """
    # add_messages sorgt dafür, dass neue Chat-Nachrichten immer an die Liste angehängt werden
    messages: Annotated[list, add_messages]

    # Hier speichern wir die extrahierten Daten für Zammad
    user_email: str
    matrikelnummer: str
    issue_description: str

    #Priority of the ticket:0 =non-ungent/normal, 1 = urgent/important
    priority:int

    # Ein Signal für das Frontend, dass wir alle Daten haben
    is_complete: bool