from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages
import operator


class ChatbotState(TypedDict):
    """
    Defines the structured data schema the Chatbot is working with
    """
    # add_messages sorgt dafür, dass neue Chat-Nachrichten immer an die Liste angehängt werden
    messages: Annotated[list, add_messages]

    ask_issue_attempts: int
    # ticket data
    user_email: str
    matrikelnummer: str
    issue_description: str
    additional_info: Annotated[list[str], operator.add]
    additional_info_attempts: int
    ticket_id: int
    full_conversation: str

    #Priority of the ticket:0 =non-ungent/normal, 1 = urgent/important
    priority:int

    # Support category assigned by classify_ticket_node (or at ticket creation)
    category: str

    # signal if user needs more information
    needs_additional_info: bool

    is_complete: bool

    #
    solutions: Annotated[list[dict], operator.add]