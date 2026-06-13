from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages
import operator


class ChatbotState(TypedDict):
    """
    Defines the structured data schema the Chatbot is working with
    """
    # add_messages sorgt dafür, dass neue Chat-Nachrichten immer an die Liste angehängt werden
    messages: Annotated[list, add_messages]

    # ticket data
    user_email: str
    matrikelnummer: str
    issue_description: str
    additional_info: Annotated[list[str], operator.add]

    #Priority of the ticket:0 =non-ungent/normal, 1 = urgent/important
    priority:int

    # signal if ticket is complete
    is_complete: bool

    #
    solutions: Annotated[list[dict], operator.add]