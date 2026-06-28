from pydantic import BaseModel
from typing import List, Dict

class ChatRequest(BaseModel):
    """
    Data model representing the request payload sent by the frontend.
    """
    user_message: str
    history: List[Dict[str, str]]
    user_email: str = ""
    matrikelnummer: str = ""
    issue_description: str = ""
    additional_info: List[str] = []
    priority: int = 0
    category: str = ""
    helpful: bool = False
    solutions: List[Dict] = []
    bot_message: str = ""
    additional_info_attempts: int = 0
    ask_issue_attempts: int = 0
    ticket_id: int | None = None